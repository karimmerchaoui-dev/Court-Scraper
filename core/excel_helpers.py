"""
Excel I/O helpers — load_cases_from_excel, save_batch_folder_to_excel,
mark_case_as_processed, remove_selected_cases.
"""

import os
import re
import traceback

import pandas as pd

from ai.llm_helper import normalize_case_numbers_haiku
from app import log_message, update_case_status
from models import Case
from utils.formatting import (
    format_case_number_bw,
    format_case_number_lee,
    format_case_number_md,
    format_case_number_nj,
    format_case_number_oc,
    format_case_number_pasco,
)


def remove_selected_cases(case_ids: list):
    """
    Web equivalent of the Tkinter remove_selected_cases().
    Called from app.py's /api/cases/remove endpoint, which passes case_ids.
    """
    from app import case_queue, case_status

    ids_to_remove = set(str(i).strip() for i in case_ids)
    for cid in ids_to_remove:
        case_status.pop(cid, None)

    with case_queue.mutex:
        all_items = list(case_queue.queue)
        case_queue.queue.clear()
        case_queue.all_tasks_done.notify_all()
        case_queue.unfinished_tasks = 0

    kept = []
    for item in all_items:
        year, docket, court_type, county,processor_name = item[:5]
        case_obj = Case(year=year, case_number=docket, county=processor_name, case_type=court_type)
        if case_obj.id.strip() not in ids_to_remove:
            kept.append(item)

    for item in kept:
        case_queue.put(item)

    removed_count = len(all_items) - len(kept)
    log_message(f"🗑️ Removed {removed_count} case(s) from queue: {', '.join(ids_to_remove)}")
    return removed_count


def load_cases_from_excel(file_path):
    import main
    from app import case_queue

    try:
        df = pd.read_excel(file_path)

        first_row_case = df.iloc[0, 0] if len(df) > 0 else None

        if first_row_case and str(first_row_case).startswith("BATCH_FOLDER:"):

            batch_folder_path = (
                str(first_row_case)
                .replace("BATCH_FOLDER:", "")
                .strip()
            )

            if os.path.exists(batch_folder_path):
                main.current_batch_folder = batch_folder_path
                main._settings["output_folder"] = os.path.dirname(
                    batch_folder_path
                )

                log_message(
                    f"📁 Loaded existing batch folder: {batch_folder_path}"
                )

            else:
                log_message(
                    f"⚠️ Batch folder not found: {batch_folder_path}, "
                    f"will create new one"
                )

            start_idx = 1

        else:
            start_idx = 0

        seen_cases = set()

        # ---------------------------------------------------------
        # Determine columns
        # ---------------------------------------------------------

        has_salesweb_column = len(df.columns) >= 4

        # ---------------------------------------------------------
        # First pass:
        # Collect NJ cases that need normalization
        # ---------------------------------------------------------

        nj_cases_to_normalize = []
        nj_case_indexes = []

        # We keep the information for every row so that after
        # normalization we can process the rows normally.
        row_data = []

        for idx in range(start_idx, len(df)):

            case_data = df.iloc[idx, 0]

            if pd.isna(case_data):
                continue

            county = df.iloc[idx, 1]

            if pd.isna(county):
                continue

            county = str(county).strip()
            county_l = county.lower()

            address = ""
            salesweb_county = ""
            status = ""

            # -----------------------------------------------------
            # Column 2: Address OR Status
            # -----------------------------------------------------

            if len(df.columns) > 2:

                cell = df.iloc[idx, 2]

                if not pd.isna(cell):

                    val = str(cell).strip()

                    # Determine based on the column name if possible
                    column_name = str(df.columns[2]).lower()

                    if "status" in column_name:
                        status = val
                    else:
                        address = val

            # -----------------------------------------------------
            # Column 3: SalesWeb County
            # -----------------------------------------------------

            if len(df.columns) > 3:

                cell = df.iloc[idx, 3]

                if not pd.isna(cell):
                    salesweb_county = str(cell).strip()

            # -----------------------------------------------------
            # Skip already processed
            # -----------------------------------------------------

            if status.lower() == "processed":
                continue

            # -----------------------------------------------------
            # NJ
            # -----------------------------------------------------

            if "jersey" in county_l or county_l == "nj":

                year, docket = format_case_number_nj(case_data)

                # If deterministic parsing failed, send it to
                # the batch LLM normalization.
                if year is None or docket is None:

                    nj_case_indexes.append(len(row_data))
                    nj_cases_to_normalize.append(str(case_data).strip())

                row_data.append({
                    "idx": idx,
                    "case_data": case_data,
                    "county": county,
                    "county_l": county_l,
                    "address": address,
                    "salesweb_county": salesweb_county,
                    "status": status,
                    "year": year,
                    "docket": docket,
                    "court_type": "civil",
                    "is_nj": True,
                })

            else:

                row_data.append({
                    "idx": idx,
                    "case_data": case_data,
                    "county": county,
                    "county_l": county_l,
                    "address": address,
                    "salesweb_county": salesweb_county,
                    "status": status,
                    "year": None,
                    "docket": None,
                    "court_type": None,
                    "is_nj": False,
                })

        # ---------------------------------------------------------
        # ONE MISTRAL REQUEST FOR ALL INVALID NJ CASES
        # ---------------------------------------------------------

        if nj_cases_to_normalize:

            log_message(
                f"🤖 Sending {len(nj_cases_to_normalize)} NJ case numbers "
                f"to Mistral for batch normalization..."
            )

            normalized_cases = normalize_case_numbers_haiku(
                nj_cases_to_normalize
            )

            # -----------------------------------------------------
            # Put the normalized values back into row_data
            # -----------------------------------------------------

            for row_position, normalized in zip(
                nj_case_indexes,
                normalized_cases
            ):
                print(normalized)
                if normalized == "INVALID":
                    continue

                parts = normalized['normalized'].split("-")

                if len(parts) != 3:
                    continue

                prefix = parts[0]
                docket = parts[1]
                year = parts[2]

                if prefix not in ("f", "ch"):
                    continue

                if not re.fullmatch(r"\d+", docket):
                    continue

                if not re.fullmatch(r"\d{2}", year):
                    continue

                row_data[row_position]["year"] = year
                row_data[row_position]["docket"] = docket
                row_data[row_position]["court_type"] = "civil"

        # ---------------------------------------------------------
        # Second pass:
        # Process ALL rows
        # ---------------------------------------------------------

        for row in row_data:

            case_data = row["case_data"]
            county = row["county"]
            county_l = row["county_l"]
            address = row["address"]
            salesweb_county = row["salesweb_county"].lower()
            if "county" in salesweb_county:
                salesweb_county = salesweb_county.split("county")[0]
            year = row["year"]
            docket = row["docket"]
            court_type = row["court_type"]

            # -----------------------------------------------------
            # NJ
            # -----------------------------------------------------

            if "jersey" in county_l or county_l == "nj":

                if year is None or docket is None:
                    log_message(
                        f"⚠️ Could not normalize NJ case: {case_data}"
                    )
                    continue

                court_type = "civil"

                case = Case(
                    year,
                    docket,
                    county,
                    court_type
                )

            # -----------------------------------------------------
            # Miami
            # -----------------------------------------------------

            elif "miami" in county_l:

                year, docket, court_type = format_case_number_md(
                    case_data
                )

                case = Case(
                    year,
                    docket,
                    county,
                    court_type
                )

            # -----------------------------------------------------
            # Orange
            # -----------------------------------------------------

            elif "orange" in county_l:

                year, docket, court_type = format_case_number_oc(
                    case_data
                )

                case = Case(
                    year,
                    docket,
                    county,
                    court_type
                )

            # -----------------------------------------------------
            # Broward
            # -----------------------------------------------------

            elif "broward" in county_l:

                year, docket, court_type = format_case_number_bw(
                    case_data
                )

                case = Case(
                    year,
                    docket,
                    county,
                    court_type
                )

            # -----------------------------------------------------
            # Lee
            # -----------------------------------------------------

            elif "lee" in county_l:

                year, docket, court_type = format_case_number_lee(
                    case_data
                )

                case = Case(
                    year,
                    docket,
                    county,
                    court_type
                )

            # -----------------------------------------------------
            # Florida counties where the entire value is the docket
            # -----------------------------------------------------

            elif (
                "palm" in county_l
                or "beach" in county_l
            ):

                year = ""
                docket = case_data
                court_type = ""

                case = Case(
                    year,
                    docket,
                    county,
                    court_type
                )

            elif "pinn" in county_l:

                year = ""
                docket = case_data
                court_type = ""

                case = Case(
                    year,
                    docket,
                    county,
                    court_type
                )

            elif "duval" in county_l:

                year = ""
                docket = case_data
                court_type = ""

                case = Case(
                    year,
                    docket,
                    county,
                    court_type
                )

            elif "volusia" in county_l:

                year = ""
                docket = case_data
                court_type = ""

                case = Case(
                    year,
                    docket,
                    county,
                    court_type
                )

            elif "brevard" in county_l:

                year = ""
                docket = case_data
                court_type = ""

                case = Case(
                    year,
                    docket,
                    county,
                    court_type
                )

            elif "polk" in county_l:

                year = ""
                docket = case_data
                court_type = ""

                case = Case(
                    year,
                    docket,
                    county,
                    court_type
                )

            elif "seminole" in county_l:

                year = ""
                docket = case_data
                court_type = ""

                case = Case(
                    year,
                    docket,
                    county,
                    court_type
                )

            elif "sarasota" in county_l:

                year = ""
                docket = case_data
                court_type = ""

                case = Case(
                    year,
                    docket,
                    county,
                    court_type
                )

            elif "manatee" in county_l:

                year = ""
                docket = case_data
                court_type = ""

                case = Case(
                    year,
                    docket,
                    county,
                    court_type
                )

            elif "osceola" in county_l:

                year = ""
                docket = case_data
                court_type = ""

                case = Case(
                    year,
                    docket,
                    county,
                    court_type
                )
            elif "clay" in county_l:

                year = ""
                docket = case_data
                court_type = ""

                case = Case(
                    year,
                    docket,
                    county,
                    court_type
                )
            elif "stjohns" in county_l:

                year = ""
                docket = case_data
                court_type = ""

                case = Case(
                    year,
                    docket,
                    county,
                    court_type
                )
            elif "pasco" in county_l:
                year, court_type, docket = format_case_number_pasco(case_data)
                case = Case(year, docket, county, court_type)
            else:

                log_message(
                    f"{county} was not found"
                )

                continue

            # ---------------------------------------------------------
            # Deduplicate
            # ---------------------------------------------------------

            if case.id not in seen_cases:

                seen_cases.add(case.id)

                case_queue.put(
                    (
                        year,
                        docket,
                        court_type,
                        county.strip(),
                        address,
                        salesweb_county
                    )
                )

                log_message(
                    f"📥 Added {case.id} ({county}) - "
                    f"Address: "
                    f"{address[:30] if address else 'N/A'} | "
                    f"SalesWeb County: "
                    f"{salesweb_county or 'N/A'}"
                )

            update_case_status(
                None,
                case.id,
                county,
                "Pending",
                details="Waiting to process",
                address=address
            )

    except Exception as e:

        traceback.print_exc()

        log_message(
            f"Error loading cases: {str(e)}"
        )

def save_batch_folder_to_excel(file_path, batch_folder):
    try:
        df = pd.read_excel(file_path)
        if len(df) > 0 and str(df.iloc[0, 0]).startswith("BATCH_FOLDER:"):
            df.iloc[0, 0] = f"BATCH_FOLDER:{batch_folder}"
        else:
            new_row = pd.DataFrame([[f"BATCH_FOLDER:{batch_folder}", "", ""]], columns=df.columns[:3])
            df = pd.concat([new_row, df], ignore_index=True)
        df.to_excel(file_path, index=False)
        log_message(f"💾 Saved batch folder path to Excel: {batch_folder}")
    except Exception as e:
        log_message(f"Error saving batch folder to Excel: {str(e)}")


def mark_case_as_processed(file_path, case_id):
    try:
        df = pd.read_excel(file_path)
        start_idx = 1 if (len(df) > 0 and str(df.iloc[0, 0]).startswith("BATCH_FOLDER:")) else 0
        if len(df.columns) < 3:
            df['Status'] = ''
        case_column = df.iloc[start_idx:, 0]
        county_column = df.iloc[start_idx:, 1]
        for idx, (case_data, county) in enumerate(zip(case_column, county_column), start=start_idx):
            if pd.isna(case_data) or pd.isna(county):
                continue
            county_l = county.lower()
            if "jersey" in county_l or "nj" in county_l:
                year, docket = format_case_number_nj(case_data)
                current_case_id = f"f-{docket}-{year}"
            elif "miami" in county_l:
                year, docket, _ = format_case_number_md(case_data)
                current_case_id = f"{year}-{docket}"
            elif "orange" in county_l:
                year, docket, _ = format_case_number_oc(case_data)
                current_case_id = f"{year}-{docket}"
            elif "broward" in county_l:
                year, docket, ct = format_case_number_bw(case_data)
                current_case_id = f"{ct}-{year}-{docket}"
            elif "lee" in county_l:
                year, docket, _ = format_case_number_lee(case_data)
                current_case_id = f"{year}-{docket}"
            elif "palm" in county_l or "beach" in county_l:
                current_case_id = str(case_data)
            elif "duval" in county_l:
                current_case_id = str(case_data)
            elif "pasco" in county_l:
                year, court_type, docket = format_case_number_pasco(case_data)
                current_case_id = f"{year}-{court_type}-{docket}"
            else:
                continue
            if current_case_id == case_id:
                df.iloc[idx, 2] = "processed"
                df.to_excel(file_path, index=False)
                log_message(f"Marked {case_id} as processed in Excel")
                break
    except Exception as e:
        log_message(f"Error marking case as processed: {str(e)}")
