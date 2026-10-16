import re
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BANNED_PARTY_KEYWORDS = [
    "llc", "unknown", "inc", "united", "county", "housing", "state", "florida", "city",
    "clerk", "court", "bank", "association", "national", "business", "admin", "corporation",
    "department", "serivce", "the ", "finance", "secretary"
]

MAX_DEFENDANTS = 10

def parse_date_safe(date_str):
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%m_%d_%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return datetime.min

import time


def extract_defendants_into_report(driver, parties_table_xpath, case_id, report_cases, banned=None, max_defendants=MAX_DEFENDANTS, show_parties_table=None, show_dockets_table=None):
    """
    Extracts defendants from the parties table and puts them into report_cases[case_id]
    just like in get_defendants:
    - name_1, description_1, name_2, description_2, ... up to max_defendants
    - main_defendant (newest defendant not containing banned keywords)
    - defendant
    """
    if not parties_table_xpath:
        return report_cases

    if banned is None:
        banned = BANNED_PARTY_KEYWORDS

    try:
        # ── If county requires an action to reveal/show the parties table ─────────
        if show_parties_table:
            try:
                if callable(show_parties_table):
                    show_parties_table(driver)
                elif isinstance(show_parties_table, str):
                    btn = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, show_parties_table))
                    )
                    driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.5)
            except Exception as e:
                print(f"⚠️ Error executing show_parties_table: {e}")

        try:
            table = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, parties_table_xpath))
            )
        except Exception:
            return report_cases

        try:
            rows = table.find_elements(By.XPATH, ".//tr")
            if not rows:
                rows = table.find_elements(By.XPATH, "./tr | .//div[contains(@class, 'row')]")
            if not rows:
                return report_cases

            name_col_idx = None
            type_col_idx = None
            date_col_idx = None
            header_row_idx = None

            # Inspect up to first 2 rows for header labels
            for r_idx in range(min(2, len(rows))):
                cells = rows[r_idx].find_elements(By.XPATH, "./th | ./td")
                texts = [c.text.strip().lower() for c in cells]
                for c_idx, txt in enumerate(texts):
                    if "name" in txt and name_col_idx is None:
                        name_col_idx = c_idx
                        header_row_idx = r_idx
                    if "type" in txt and type_col_idx is None:
                        type_col_idx = c_idx
                        header_row_idx = r_idx
                    if any(d_kw in txt for d_kw in ("date", "filing", "added")) and date_col_idx is None:
                        date_col_idx = c_idx

            if name_col_idx is None:
                name_col_idx = 0
            if type_col_idx is None:
                type_col_idx = 1

            start_row = (header_row_idx + 1) if header_row_idx is not None else 0
            data_rows = rows[start_row:]

            date_pattern = re.compile(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b')
            defendant_count = 0
            valid_candidates = []

            for idx, row in enumerate(data_rows):
                cells = row.find_elements(By.XPATH, "./td | ./th")
                if len(cells) <= max(name_col_idx, type_col_idx):
                    continue

                name = cells[name_col_idx].text.strip()
                party_type = cells[type_col_idx].text.strip()

                name_low = name.lower()
                party_low = party_type.lower()

                # Skip header-like text if present in data rows
                if (
                    name_low in ("name", "party name", "name / dob / dl / id #")
                    or ("name" in name_low and ("dob" in name_low or "dl" in name_low or "id #" in name_low))
                    or party_low in ("type", "party type")
                ):
                    continue

                # Must have type 'Defendant'
                if "defendant" not in party_low:
                    continue

                clean_name = name.split('(')[0].replace("AKA", "").strip()

                # Populate name_i and description_i up to max_defendants
                defendant_count += 1
                if defendant_count <= max_defendants:
                    report_cases[case_id][f"name_{defendant_count}"] = clean_name
                    report_cases[case_id][f"description_{defendant_count}"] = party_type

                # Check if this defendant does not contain banned keywords
                if not any(b in name_low for b in banned):
                    row_date = None
                    if date_col_idx is not None and len(cells) > date_col_idx:
                        match = date_pattern.search(cells[date_col_idx].text.strip())
                        if match:
                            row_date = parse_date_safe(match.group(0))

                    if row_date is None:
                        for c in cells:
                            match = date_pattern.search(c.text.strip())
                            if match:
                                parsed = parse_date_safe(match.group(0))
                                if parsed != datetime.min:
                                    row_date = parsed
                                    break

                    valid_candidates.append({
                        "index": idx,
                        "name": clean_name,
                        "date": row_date
                    })

            # Set main_defendant to newest valid candidate
            if valid_candidates:
                print(f"valid_candidates : {valid_candidates}")
                candidates_with_dates = [c for c in valid_candidates if c["date"] is not None and c["date"] != datetime.min]
                if candidates_with_dates:
                    candidates_with_dates.sort(key=lambda c: c["date"], reverse=True)
                    main_def = candidates_with_dates[0]["name"]
                else:
                    main_def = valid_candidates[0]["name"]

                report_cases[case_id]["main_defendant"] = main_def
                report_cases[case_id]["defendant"] = main_def

            return report_cases
        except Exception as e:
            print(f"Error extracting defendants into report: {e}")
            return report_cases
    finally:
        # ── If county requires an action to navigate back to dockets table ─────────
        if show_dockets_table:
            try:
                if callable(show_dockets_table):
                    show_dockets_table(driver)
                elif isinstance(show_dockets_table, str):
                    btn = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, show_dockets_table))
                    )
                    driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.5)
            except Exception as e:
                print(f"⚠️ Error executing show_dockets_table: {e}")


def extract_newest_defendant(driver, parties_table_xpath, banned=None):
    """Convenience wrapper returning only the newest defendant name."""
    dummy_report = {"temp_case": {}}
    extract_defendants_into_report(driver, parties_table_xpath, "temp_case", dummy_report, banned=banned)
    return dummy_report["temp_case"].get("main_defendant")
