import os
import sys
from pathlib import Path

# Add project root to sys.path to allow running this script directly
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import json
import time
import traceback
from datetime import datetime, timezone

import pysnooper
from httpx import ReadError, RemoteProtocolError
from supabase import create_client

from ai.llm_helper import extract_first_last_name_anthropic
from config import settings
from core.CaseStatus import CaseStatus
from pipeline_tracker import update_pipeline_status
from utils.map_helpers import get_city_population_wikipedia
from utils.obituary_helpers import process_obituary_link, search_obituaries

url = settings.supabase_url
key = settings.supabase_key
if not url or not key:
    raise ValueError(
        "CRITICAL: SUPABASE_URL or SUPABASE_KEY is missing! "
        "Check your .env file or configuration."
    )

supabase = create_client(url, key)


def _update_status(case_id: str, status: str, error: str = None):
    payload = {
        "processing_status": status,
        "updated_at": "now()"
    }
    # reuse the existing error_message column from case_documents
    # or add it to cases if you want — for now log it
    if error:
        print(f"[{case_id}] ERROR: {error}")
    while True:
        try:
            supabase.table("cases") \
                .update(payload) \
                .eq("case_number", case_id) \
                .execute()
            break
        except RemoteProtocolError:
            time.sleep(5)
        except Exception as e:
            print(f"❌ Error updating status for '{case_id}': {e}")
            break

    print(f"[{case_id}] Status → {status}")


@pysnooper.snoop()
def rip_flag(case_id: str, reason="RIP", batch_name="", address=None, county=None):
    """
    Set the RIP flag for a case and optionally update address and county.

    Args:
        case_id: The case number or case ID
        reason: The RIP reason
        batch_name: The batch name
        address: Optional address to update in case_property_details
        county: Optional county to update in cases table
    """
    # 1. Update the cases table with RIP flag and county
    payload = {
        "case_number": case_id,  # Required for upsert to identify or insert the row
        "rip": True,
        "rip_reason": reason,
        "batch_name": batch_name,
        "updated_at": "now()"
    }

    # Add county to payload if provided
    if county:
        payload["county"] = county

    while True:
        try:
            supabase.table("cases") \
                .upsert(payload, on_conflict="case_number") \
                .execute()
            break
        except RemoteProtocolError:
            time.sleep(5)
        except Exception as e:
            print(f"❌ Error setting RIP flag for '{case_id}': {e}")
            break

    print(f"[{case_id}] RIP flag set (created or updated)")

    # 2. Update address in case_property_details if provided
    if address:
        try:
            # Get the case UUID first
            case_uuid = get_case_id_by_number(case_id)

            if case_uuid:
                # Check if property details already exist
                existing = supabase.table("case_property_details") \
                    .select("id") \
                    .eq("case_id", case_uuid) \
                    .execute()

                property_payload = {
                    "case_id": case_uuid,
                    "address": address
                }

                if existing.data and len(existing.data) > 0:
                    # Update existing record
                    supabase.table("case_property_details") \
                        .update(property_payload) \
                        .eq("case_id", case_uuid) \
                        .execute()
                    print(f"[{case_id}] Address updated in case_property_details")
                else:
                    # Insert new record
                    supabase.table("case_property_details") \
                        .insert(property_payload) \
                        .execute()
                    print(f"[{case_id}] Address inserted in case_property_details")
            else:
                print(f"⚠️ Could not find case UUID for '{case_id}', address not updated")

        except Exception as e:
            print(f"❌ Error updating address for '{case_id}': {e}")



def upload_deeds_to_case(case_id, jurisdiction, case_directory, supabase_case_id=None):
    """
    Recursively finds all files inside the 'deeds' folder and syncs them
    to the 'deed_documents' table.
    """
    _snoop_log = os.path.join(case_directory, "upload_deeds_to_case.log")
    with pysnooper.snoop(_snoop_log):
        deed_base_path = os.path.join(case_directory)

        if not os.path.exists(deed_base_path):
            print(f"No deeds folder found at {deed_base_path}")
            return

        # os.walk allows us to go through all subfolders recursively
        for root, dirs, files in os.walk(deed_base_path):
            for file_name in files:
                # Full path to the local file
                local_file_path = os.path.join(root, file_name)
                # Metadata for DB
                extension = file_name.split('.')[-1].lower()
                folder = jurisdiction if jurisdiction else "unspecified"

                # Storage path: deeds/county/case_number/file.pdf
                # We keep it flat in storage for easier retrieval, or you can
                # mimic the subfolder structure if preferred.
                storage_path = f"{folder}/{case_id}/{file_name}"

                try:
                    # 1. Upload to Storage
                    with open(local_file_path, 'rb') as f:
                        supabase.storage.from_("case-deed-documents").upload(
                            path=storage_path,
                            file=f,
                            file_options={"upsert": "true"}
                        )

                    # 2. Insert into deed_documents table
                    deed_data = {
                        "case_id": supabase_case_id,
                        "case_number": case_id,
                        "file_name": file_name,
                    }

                    supabase.table("deed_documents").insert(deed_data).execute()
                    print(f"Successfully uploaded deed: {file_name}")

                except Exception as e:
                    print(f"Failed to upload deed {file_name}: {e}")


def upload_files_to_case(case_id, case_number, jurisdiction, local_source, file_source):
    # Define the extensions you want to allow (lower case)
    os.makedirs(os.path.join(file_source, "add_case_with_files_logs"), exist_ok=True)

    with pysnooper.snoop(os.path.join(file_source, "add_case_with_files_logs", "add_case_with_files.log")):
        ALLOWED_EXTENSIONS = {'.pdf', '.tiff'}

        if isinstance(local_source, str) and os.path.isdir(local_source):
            files_to_process = [
                os.path.join(local_source, f)
                for f in os.listdir(local_source)
                if os.path.isfile(os.path.join(local_source, f))
            ]
        elif isinstance(local_source, list):
            files_to_process = local_source
        else:
            print("No valid files or directory provided.")
            return

        uploaded_count = 0
        print(f"case_id : {case_id}")
        print(f"case_number : {case_number}")
        for path in files_to_process:
            while True:
                if not os.path.exists(path):
                    break

                file_name = os.path.basename(path)
                # Correctly extract extension (e.g., '.pdf')
                _, ext = os.path.splitext(file_name)
                ext = ext.lower()

                # --- EXTENSION FILTER START ---
                if ext not in ALLOWED_EXTENSIONS:
                    print(f"Skipping {file_name}: Extension {ext} not allowed.")
                    break
                # --- EXTENSION FILTER END ---

                folder = jurisdiction if jurisdiction else "unspecified"
                storage_path = f"{folder}/{case_number}/{file_name}"

                try:
                    print(f"path : {path}")
                    print(f"file_name : {file_name}")
                    print(f"storage_path : {storage_path}")
                    # 1. Upload/Overwrite in Storage
                    with open(path, 'rb') as f:
                        supabase.storage.from_("case-files").upload(
                            path=storage_path,
                            file=f,
                            file_options={"upsert": "true"}
                        )

                    # 2. UPSERT the Document Record
                    doc_data = {
                        "case_id": case_id,
                        "file_name": file_name,
                        "file_path": storage_path,
                        "file_extension": ext.replace('.', ''),  # store as 'pdf' instead of '.pdf'
                        "transaction_id": file_name.split('_')[0] if 'pdf' in ext else None
                    }

                    print(f"doc_data : {doc_data}")
                    supabase.table("case_documents").upsert(
                        doc_data,
                        on_conflict="case_id, file_name"
                    ).execute()

                    uploaded_count += 1
                    break
                except Exception as e:
                    print(f"Error uploading {file_name}: {e}")
                    break
                except ReadError as re:
                    print(f"Read error: {re}")

        print(f"Successfully synced {uploaded_count} valid files for case {case_number}")



def get_case_id_by_number(case_number: str):
    """
    Queries Supabase to retrieve the database UUID (id) for a given case_number.
    Returns the string UUID if found, otherwise returns None.
    """
    try:
        # Strip any accidental whitespace from the case number input
        clean_number = str(case_number).strip()

        response = supabase.table("cases") \
            .select("id") \
            .eq("case_number", clean_number) \
            .execute()

        # Check if the query returned any matching rows
        if response.data and len(response.data) > 0:
            return response.data[0]['id']

        print(f"⚠️ Case number '{clean_number}' not found in the database.")
        return None

    except Exception as e:
        traceback.print_exc()
        print(f"❌ Error fetching case_id for '{case_number}': {e}")
        return None


def _normalize_case_data(data_dict):
    normalized = {}
    for k, v in data_dict.items():
        clean_key = str(k).lower().strip()
        val = v if not (isinstance(v, str) and v.strip() == "") else None
        if clean_key not in normalized or (normalized[clean_key] is None and val is not None):
            normalized[clean_key] = val
        elif val is not None:
            # If we already have a real county, don't overwrite it with processor state name
            if clean_key == 'county' and normalized.get('county') and str(val).lower().strip() in ['new jersey', 'nj']:
                continue
            normalized[clean_key] = val
    return normalized


def _sync_city_data(clean_data, file_source):
    with pysnooper.snoop(os.path.join(file_source, "add_case_with_files_logs", "_sync_city_data.log")):
        raw_city = clean_data.get("city")
        raw_state = clean_data.get("state") or "NJ"
        city_id_fk = None

        if raw_city:
            clean_city_name = str(raw_city).strip().title()
            clean_state_code = str(raw_state).strip().upper()[:2]
            print(f"clean_city_name : {clean_city_name}")
            city_query = (
                supabase.table("city")
                .select("id")
                .eq("city_name", clean_city_name)
                .eq("state", clean_state_code)
                .execute()
            )
            print(f"city_query.data : {city_query.data}")
            if city_query.data:
                city_id_fk = city_query.data[0]["id"]
                if not city_query.data[0].get("population"):
                    wiki_pop = get_city_population_wikipedia(clean_city_name, clean_state_code)
                    if wiki_pop:
                        supabase.table("city").update({"population": wiki_pop}).eq("id", city_id_fk).execute()
            else:
                print(f"🌐 Fetching Wikipedia population for: {clean_city_name}, {clean_state_code}...")
                fetched_pop = get_city_population_wikipedia(clean_city_name, clean_state_code)
                new_city_res = supabase.table("city").insert({
                    "city_name": clean_city_name,
                    "state": clean_state_code,
                    "population": fetched_pop,
                }).execute()
                if new_city_res.data:
                    city_id_fk = new_city_res.data[0]["id"]
        return city_id_fk


def _perform_defendant_research(case_id, clean_data, file_source):
    with pysnooper.snoop(os.path.join(file_source, "add_case_with_files_logs", "_perform_defendant_research.log")):
        if clean_data.get("main_defendant"):
            defendant_name = (
                clean_data["main_defendant"]
                .split(",")[0]
                .replace("AKA", "")
                .strip()
            )
            if defendant_name and "john doe" not in defendant_name.lower() and "jane doe" not in defendant_name.lower():
                try:
                    """api_response = defendant_skip_trace(
                        defendant_name,
                        f"{clean_data.get('address') or clean_data.get('court_address')}, NJ",
                    )
                    sync_defendant_research(case_id, api_response)
                    update_pipeline_status("tracer", "SUCCESS")"""
                except Exception as res_err:
                    update_pipeline_status("tracer", "FAILED", tb_message=traceback.format_exc())
                    print(f"Defendant research pipeline failed: {res_err}")


def build_cases_payload(case_number, clean_data, is_new, batch_name, city_id_fk):
    return {
        "case_number": case_number,
        "batch_name": batch_name,
        "city_id": city_id_fk,
        "county": clean_data.get("county"),
        "case_type": clean_data.get("case_type") or clean_data.get("case number"),
        "court_case_status": clean_data.get("court_case_status"),
        "processing_status": CaseStatus.NEW if is_new else CaseStatus.UPDATED,
        "processing_duration": clean_data.get("processing_duration"),
        "bankruptcy_case_status": clean_data.get("bankruptcy_case_status")
    }


def build_defendant_payload(case_id: str, clean_data: dict) -> dict:
    payload = {
        "case_id": case_id,
        "main_defendant": clean_data.get("main_defendant"),
        "homeowner_deceased": clean_data.get("homeowner_deceased"),
        "date_of_death": clean_data.get("date_of_death"),
    }
    return payload if any(v is not None for k, v in payload.items() if k != "case_id") else None


def build_location_payload(case_id: str, clean_data: dict) -> dict:
    payload = {
        "case_id": case_id,
        "court_address": clean_data.get("court_address"),
        "block": clean_data.get("block"),
        "lot": clean_data.get("lot"),
    }
    return payload if any(v is not None for k, v in payload.items() if k != "case_id") else None


def build_judgment_payload(case_id: str, clean_data: dict) -> dict:
    payload = {
        "case_id": case_id,
        "additional_sums_count": clean_data.get("additional_sums_count"),
        "judgment_date": clean_data.get("judgment_date"),
        "total_final_judgment_amount": clean_data.get("total_final_judgment_amount"),
    }
    return payload if any(v is not None for k, v in payload.items() if k != "case_id") else None


def build_mortgage_payload(case_id: str, clean_data: dict) -> dict:
    payload = {
        "case_id": case_id,
        "mortgage_execution_date": clean_data.get("mortgage_execution_date"),
        "original_mortgage_amount": clean_data.get("original_mortgage_amount"),
        "modified_mortgage_date": clean_data.get("modified_mortgage_date"),
        "interest_rate": clean_data.get("interest_rate"),
        "liens": clean_data.get("liens"),
    }
    return payload if any(v is not None for k, v in payload.items() if k != "case_id") else None


@pysnooper.snoop()
def build_sales_web_payload(case_id: str, clean_data: dict) -> dict:
    payload = {
        "case_id": case_id,
        "sales_web_address": clean_data.get("sales_web_address"),
        "found": clean_data.get("found"),
        "upset_price": clean_data.get("upset price") or clean_data.get("upset_price"),
        "upset_amount": clean_data.get("upset amount") or clean_data.get("upset_amount"),
        "approx_judgment": clean_data.get("approx. judgment") or clean_data.get("approx_judgment"),
        "approx_upset": clean_data.get("approx. upset") or clean_data.get("approx_upset"),
        "unpaid_amount": clean_data.get("unpaid_balance"),
        "sales_date": clean_data.get("sales_date"),
        "status_history": str(clean_data.get("status_history")),
        "financial_obligation": str(clean_data.get("financial_obligations")),
    }
    return payload if any(v is not None for k, v in payload.items() if k != "case_id") else None


def build_property_details_payload(case_id: str, clean_data: dict) -> dict:
    payload = {
        "case_id": case_id,
        "address": clean_data.get("address") or clean_data.get("court_address"),
        "zestimate": clean_data.get("zestimate"),
        "zillow_status": clean_data.get("zillow_status"),
        "home_type": clean_data.get("home_type"),
        "equity": clean_data.get("equity"),
        "is_current_signed_in_agent_responsible": clean_data.get("is_current_signed_in_agent_responsible"),
    }
    return payload if any(v is not None for k, v in payload.items() if k != "case_id") else None

import pysnooper


def build_parties_batch_payload(case_id: str, clean_data: dict) -> list:
    parties = []
    for i in range(1, 11):
        name = clean_data.get(f"name_{i}")
        if name:
            parties.append({
                "case_id": case_id,
                "name": name,
                "description": clean_data.get(f"description_{i}"),
                "party_index": i,
            })
    return parties


def build_events_batch_payload(case_id: str, clean_data: dict) -> list:
    event_maps = [
        ("bankruptcy", "bankruptcy", "bankruptcy_date"),
        ("vacate", "vacate", "vacate_date"),
        ("cancel", "cancel", "cancel_date"),
        ("order to stay/motion to stay", "motion_to_stay", "order_to_stay_date"),
        ("certification of mailing", "certification_of_mailing", "certification_of_mailing"),
    ]
    events = []
    for source_key, event_type, date_field in event_maps:
        if clean_data.get(source_key) == "✅":
            occurred_at = None
            if date_field and date_field in clean_data:
                date_str = clean_data[date_field]
                if date_str and "_" in date_str:
                    try:
                        parts = date_str.split("_")
                        if len(parts) == 3:
                            occurred_at = f"{parts[2]}-{parts[0]}-{parts[1]}"
                    except:
                        pass
                elif date_str:
                    occurred_at = date_str
            events.append({
                "case_id": case_id,
                "event_type": event_type,
                "occurred_at": occurred_at
            })
    return events


def build_deceased_batch_payload(clean_data: dict) -> list:
    """
    Safely extracts the dictionary array from the parsed cases payload mapping.
    """
    # Check both potential key string styles depending on your layout parsers
    if clean_data.get("deceased_persons"):
        deceased_raw = list(clean_data.get("deceased_persons"))
        print(f"deceased_raw : {deceased_raw}")
        if not deceased_raw or not isinstance(deceased_raw, list):
            return []

        return deceased_raw


# --- Your Updated Engine ---



def add_case_with_files(data_dict, file_source=None, batch_name="", force_replace: bool = True, tracker=None):

        """
        Transactional execution engine. Compiles metadata and streams
        everything to a dedicated PostgreSQL schema processor in a single HTTP request.

        If force_replace is True, it will delete any existing case with the same case_number
        and all its associated data before inserting the new data.
        """
        print(f"file_source: {file_source}")
        os.makedirs(os.path.join(file_source, "add_case_with_files_logs"), exist_ok=True)
        first_name = None
        last_name = None
        
        with pysnooper.snoop(os.path.join(file_source, "add_case_with_files_logs", "add_case_with_files.log")):
            supabase = create_client(url, key)
            case_number = None
            try:
                # Normalize and identify initial state
                clean_data = _normalize_case_data(data_dict)
                case_number = clean_data.get("case number") or clean_data.get("case_number")
                if not case_number:
                    print("Error: 'case_number' missing context dictionary data.")
                    return None

                # Check if case already exists
                
                existing = supabase.table("cases").select("id").eq("case_number", case_number).execute()
                case_exists = len(existing.data) > 0
                if case_exists and force_replace:
                    case_id = existing.data[0]["id"]
                # 🔥 NEW: Delete existing case and all associated data if force_replace is True
                """if case_exists and force_replace:
                    case_id = existing.data[0]["id"]
                    print(f"🔄 Case '{case_number}' already exists. Deleting all associated data...")

                    delete_case_completely(case_number, case_id, file_source)
                    print(f"✅ Case '{case_number}' and all associated data deleted successfully.")

                    # Case is now new after deletion
                    is_new = True
                else:
                    is_new = len(existing.data) == 0"""
                is_new = True
                # Resolve city foreign key dependencies locally (retains dynamic scrape checking)
                city_id_fk = _sync_city_data(clean_data, file_source)

                # Build all payloads without saving them yet
                temp_uuid = "00000000-0000-0000-0000-000000000000"
                with open(os.path.join(file_source, "clean_data.json"), "w", encoding="utf-8") as f:
                    json.dump(clean_data, f, indent=2, default=str)

                rpc_payload = {
                    "p_case_number": case_number,
                    "p_batch_name": batch_name,
                    "p_city_id_fk": city_id_fk,
                    "p_case_payload": build_cases_payload(case_number, clean_data, is_new, batch_name, city_id_fk),
                    "p_def_payload": build_defendant_payload(temp_uuid, clean_data),
                    "p_loc_payload": build_location_payload(temp_uuid, clean_data),
                    "p_judg_payload": build_judgment_payload(temp_uuid, clean_data),
                    "p_mort_payload": build_mortgage_payload(temp_uuid, clean_data),
                    "p_sales_payload": build_sales_web_payload(temp_uuid, clean_data),
                    "p_prop_payload": build_property_details_payload(temp_uuid, clean_data),
                    "p_parties_batch": build_parties_batch_payload(temp_uuid, clean_data),
                    "p_events_batch": build_events_batch_payload(temp_uuid, clean_data),
                    "p_deceased_batch": build_deceased_batch_payload(clean_data)
                }

                try:
                    payload_dir = os.path.join(file_source, "add_case_with_files_logs", "payloads")
                    os.makedirs(payload_dir, exist_ok=True)
                    payload_path = os.path.join(payload_dir, f"{case_number}_payload.json")
                    with open(payload_path, "w", encoding="utf-8") as f:
                        json.dump(rpc_payload, f, indent=2, default=str)
                    print(f"💾 Payload saved to: {payload_path}")
                except Exception as save_err:
                    print(f"⚠️ Could not save payload to disk: {save_err}")

                # EXECUTE THE ENTIRE SYNC IN ONE SINGLE NETWORK CALL
                print(f"🚀 Streaming unified relational block transaction for Case {case_number}...")
                if tracker:
                    with tracker.track_step("supabase_upload", "upsert_unified_case_data") as _rpc_step:
                        response = supabase.rpc("upsert_unified_case_data", rpc_payload).execute()
                        case_id = response.data
                        _rpc_step.set_metadata("case_id", case_id)
                        _rpc_step.set_metadata("case_number", case_number)
                else:
                    response = supabase.rpc("upsert_unified_case_data", rpc_payload).execute()
                    case_id = response.data
                #print(f"✅ Transaction processed successfully. Database Internal Identity -> {case_id}")

                # =========================================================================
                # 🔥 INLINE OBITUARY LOOKUP & SYNC BLOCK
                # =========================================================================
                deceased_list = clean_data.get("deceased_persons") or clean_data.get("deceased persons") or []
                for person_entry in deceased_list:
                    full_name = person_entry.get("name") or person_entry.get("full_name")
                    if not full_name:
                        continue
                    if "aka" in full_name.lower():
                        full_name = full_name.split("aka")[0].strip()
                    elif "a/k/a" in full_name.lower():
                        full_name = full_name.split("a/k/a")[0].strip()
                    try:
                        # 1. Fetch your search results list of dicts
                        state = clean_data.get("state")
                        print("state : {state}")
                        if "nj" in state.lower() or "jersey" in state.lower():
                            formatted_name = extract_first_last_name_anthropic(full_name)
                            if formatted_name.startswith("```"):
                                formatted_name = formatted_name.removeprefix("```json").removeprefix("```")
                                formatted_name = formatted_name.removesuffix("```").strip()
                                first_name = formatted_name.get("first_name")
                                last_name = formatted_name.get("last_name")
                                    
                            if formatted_name:
                                try:
                                    formatted_name = json.loads(formatted_name)
                                    first_name = formatted_name.get("first_name")
                                    last_name = formatted_name.get("last_name")
                                    
                                except json.JSONDecodeError as e:
                                    print(f"Warning: Invalid JSON from extract_final_judgment: {e}")
                                    print(f"Content was: {repr(formatted_name)}")
                                    formatted_name = None
                            else:
                                formatted_name = None
                            

                            search_results = search_obituaries(first_name,last_name, "New Jersey")
                        elif "fl" in state.lower() or "florida" in state.lower():
                            search_results = search_obituaries(first_name,last_name, "Florida")

                        if search_results:
                            # 2. Grab the auto-generated database ID for this specific person
                            person_db_record = supabase.table("case_deceased_persons") \
                                .select("id") \
                                .eq("case_id", case_id) \
                                .eq("full_name", full_name) \
                                .execute()

                            if person_db_record.data:
                                deceased_person_uuid = person_db_record.data[0]["id"]
                                # 3. Stream the search results into the database matches table
                                process_and_save_search_matches(
                                    deceased_person_id=deceased_person_uuid,
                                    search_results=search_results
                                )
                    except Exception as loop_err:
                        print(f"⚠️ Non-fatal search failure for {full_name}: {loop_err}")
                # =========================================================================

                # Execute auxiliary downstream features outside structural row transaction
                _perform_defendant_research(case_id, clean_data, file_source)

                # Handle storage attachments
                jurisdiction = clean_data.get("county") or "unspecified"
                if file_source:
                    if tracker:
                        with tracker.track_step("supabase_upload", "upload_court_documents") as _up_step:
                            upload_files_to_case(case_id, case_number, jurisdiction, file_source, file_source)
                            _up_step.set_metadata("file_source", file_source)
                            _up_step.set_metadata("jurisdiction", jurisdiction)
                    else:
                        upload_files_to_case(case_id, case_number, jurisdiction, file_source, file_source)

                return case_id
            except (RemoteProtocolError,UnboundLocalError):
                supabase = create_client(url, key)
            except Exception as e:
                traceback.print_exc()
                if case_number:
                    _update_status(case_number, CaseStatus.FAILED, error=str(e))
                update_pipeline_status("supabase_upload", "FAILED", tb_message=traceback.format_exc())
                return None


def _split_names(value):
    """Turn a grantee value into a list for the text[] column."""
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()] or None

    text = str(value).strip()
    if not text:
        return None

    for sep in (";", "\n"):
        if sep in text:
            return [p.strip() for p in text.split(sep) if p.strip()]

    return [text]


# Scraped keys that don't share the same name as their deed_documents column.
_FIELD_MAP = {
    "date": "recording_date",
    "mortgagee": "grantee",
    "mortgagor": "grantor",
    "type": "document_type",

    # Existing mappings if you need them
    "pages": "total_pages",
    "legal": "property_address",
}

# Only "grantee" is a text[] column — everything else is plain text.
_ARRAY_COLUMNS = {"grantee"}

DEED_DOCUMENT_COLUMNS = {
    "id",
    "case_id",
    "file_name",
    "file_extension",
    "ocr_text",
    "created_at",
    "case_number",
    "status",
    "processed_at",
    "document_type",
    "instrument_no",
    "recording_date",
    "book_type",
    "book",
    "page",
    "book_page",
    "total_pages",
    "consideration",
    "property_address",
    "municipality",
    "reference_town",
    "grantor",
    "grantee",
    "township",
    "block_lot",
}


def _build_row(
        case_id: str,
        case_number: str,
        record: dict
) -> dict:
    """Map one scraped record onto a deed_documents row."""

    row = {
        "case_id": case_id,
        "case_number": str(case_number).strip(),
        "status": "processed",
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }

    for key, value in record.items():

        # Convert source field name to database column name
        column = _FIELD_MAP.get(key, key)

        # Ignore anything that isn't an actual deed_documents column
        if column not in DEED_DOCUMENT_COLUMNS:
            continue

        if value is None:
            continue

        # Don't allow scraped data to override these
        if column in {"id", "case_id", "case_number", "status", "processed_at"}:
            continue

        # Array column
        if column in _ARRAY_COLUMNS:
            row[column] = _split_names(value)

        else:
            text = str(value).strip()
            row[column] = text or None

    return row


def sync_deed_dictionary_to_documents(case_number: str, records: list):
    """
    Insert a list of deed records into `deed_documents` for the case
    matching `case_number`, in a single batch insert.

    Records can use either grantor/grantee or mortgagor/mortgagee, and
    fields can be a plain string or a list of strings (e.g. multiple
    grantors) — both are normalized automatically. Any source field that
    isn't an actual deed_documents column is dropped.

    Parameters
    ----------
    case_number : str
        Used to look up case_id via get_case_id_by_number().
    records : list[dict]
        The raw list of scraped deed records to insert.

    Returns
    -------
    list[dict] | None
        The inserted rows as returned by Supabase, or None if nothing
        was synced.
    """
    case_id = get_case_id_by_number(case_number)
    if not case_id:
        return None

    rows = [
        _build_row(case_id, case_number, record)
        for record in records
        if isinstance(record, dict) and record
    ]
    if not rows:
        print(f"⚠️ No deed records to sync for case '{case_number}'.")
        return None

    try:
        response = supabase.table("deed_documents").insert(rows).execute()
        print(f"✅ Synced {len(rows)} deed_documents row(s) for case '{case_number}'.")
        return response.data
    except Exception as e:
        traceback.print_exc()
        print(f"❌ Error syncing deed data for case '{case_number}': {e}")
        return None


def sync_defendant_research(case_id, api_response):
    """
    Parses the FastPeopleSearch-style API response and saves it to Supabase.
    """
    # 1. Collect all non-empty emails into a list
    emails = [api_response.get(f"Email-{i}") for i in range(1, 6) if api_response.get(f"Email-{i}")]

    # 2. Collect phones into a structured list of dictionaries
    phones = []
    for i in range(1, 6):
        num = api_response.get(f"Phone-{i}")
        if num:
            phones.append({
                "number": num,
                "type": api_response.get(f"Phone-{i} Type"),
                "provider": api_response.get(f"Phone-{i} Provider"),
                "first_reported": api_response.get(f"Phone-{i} First Reported")
            })

    # 3. Prepare Payload
    research_payload = {
        "case_id": case_id,
        "full_name": api_response.get("Input Given"),
        "age": int(api_response.get("Age")) if api_response.get("Age") else None,
        "born": api_response.get("Born"),
        "current_address": api_response.get("Lives in"),
        "city": api_response.get("Address Locality"),
        "state": api_response.get("Address Region"),
        "zip_code": api_response.get("Postal Code"),
        "emails": emails,
        "phones": phones,
        "previous_addresses": api_response.get("Previous Addresses"),
        "relatives": api_response.get("Relatives"),
        "associates": api_response.get("Associates"),
        "source_link": api_response.get("Person Link")
    }

    # 4. Upsert into database
    return supabase.table("main_defendants_research").upsert(research_payload, on_conflict="case_id").execute()


def sync_complaint_extracted_case_data(case_number: str, extraction_data: dict):
    """
    Distributes extracted legal and financial data across case_results
    and case_parties tables in a structured, relational format.
    """
    try:
        # 1. Look up the internal Case UUID using your helper function
        if isinstance(extraction_data, str):
            extraction_data = json.loads(extraction_data)
        case_id_uuid = get_case_id_by_number(case_number)
        if not case_id_uuid:
            print(f"❌ Aborting: Case {case_number} must exist in 'cases' table first.")
            return False

        # ---------------------------------------------------------
        # STEP 1: Update or Insert into 'case_results'
        # ---------------------------------------------------------
        # Pull or calculate figures based on your schema layout

        homeowner_deceased = extraction_data.get("homeowner_deceased")

        results_payload = {
            "id": case_id_uuid,
            "case_number": case_number,
            "homeowner_deceased": homeowner_deceased,
            "updated_at": "now()"
        }
        # Use upsert here so it overwrites safely if re-scraped
        supabase.table("cases").upsert(results_payload, on_conflict="id").execute()
        print(f"📊 Updated financial stats in case_results for {case_number}")

        """        # ---------------------------------------------------------
        # STEP 2: Process and insert into 'case_parties'
        # ---------------------------------------------------------
        # We consolidate plaintiffs and defendants into a unified loop tracker
        parties_to_sync = []

        # Track plaintiffs
        for idx, p in enumerate(extraction_data.get("plaintiffs", []), start=1):
            if p.get("name"):
                parties_to_sync.append({
                    "case_id": case_id_uuid,
                    "name": p["name"].strip(),
                    "description": f"Plaintiff | Address: {p.get('address')}",
                    "party_index": idx,
                    "party_status": "PLAINTIFF"
                })

        # Track defendants (Offsetting index so they don't collide with plaintiffs)
        for idx, d in enumerate(extraction_data.get("defendants", []), start=11):
            if d.get("name"):
                desc_parts = [f"Defendant | Address: {d.get('address')}"]
                if d.get("relationship"):
                    desc_parts.append(f"Relationship: {d['relationship']}")

                parties_to_sync.append({
                    "case_id": case_id_uuid,
                    "name": d["name"].strip(),
                    "description": " / ".join(desc_parts),
                    "party_index": idx,
                    "party_status": "DEFENDANT"
                })

        # Multi-row Upsert to case_parties for maximum network efficiency
        if parties_to_sync:
            supabase.table("case_parties").upsert(
                parties_to_sync, 
                on_conflict="case_id, party_index"
            ).execute()
            print(f"👥 Synced {len(parties_to_sync)} parties to case_parties for {case_number}")
        """
        return True

    except Exception as e:
        print(f"❌ Error syncing extracted case data for {case_number}: {e}")
        return False


def sync_final_judgment_extracted_case_data(case_number: str, extraction_data: dict):
    """
    Distributes extracted legal data and dynamically calculates equity fallback
    using the lowest Zestimate if equity wasn't resolved during scraping.
    """

    try:
        if isinstance(extraction_data, str):
            extraction_data = json.loads(extraction_data)

        case_id_uuid = get_case_id_by_number(case_number)
        if not case_id_uuid:
            print(f"❌ Aborting: Case {case_number} must exist in 'cases' table first.")
            return False

        judgment_date = extraction_data.get("judgment_date")

        # Ensure we handle conversion safely if the value comes in as a string with commas
        raw_judgment = extraction_data.get("total_final_judgment_amount")
        total_final_judgment_amount = None
        if raw_judgment is not None:
            try:
                total_final_judgment_amount = float(str(raw_judgment).replace(",", "").replace("$", "").strip())
            except ValueError:
                total_final_judgment_amount = str(raw_judgment).replace(",", "").replace("$", "").strip()
                pass

        # ---------------------------------------------------------
        # STEP 1: Update or Insert into 'cases'
        # ---------------------------------------------------------
        print(f"total_final_judgment_amount : {total_final_judgment_amount}")
        results_payload = {
            "case_id": case_id_uuid,
            "case_number": case_number,
            "judgment_date": judgment_date,
            "total_final_judgment_amount": total_final_judgment_amount,
        }
        supabase.table("case_judgment_details").upsert(results_payload, on_conflict="case_id").execute()
        print(f"📊 Updated financial stats in case_judgment_details table for {case_number}")

        # ---------------------------------------------------------
        # STEP 2: Equity Existence Check & Fallback Calculation
        # ---------------------------------------------------------
        if total_final_judgment_amount:
            # Query the existing property details for this case
            prop_query = supabase.table("case_property_details") \
                .select("equity, zestimate") \
                .eq("case_id", case_id_uuid) \
                .execute()

            if prop_query.data:
                existing_record = prop_query.data[0]
                existing_equity = existing_record.get("equity")
                lowest_zest = existing_record.get("zestimate")

                # If equity doesn't exist (or is 0/None), calculate it using the fallback
                if not existing_equity and lowest_zest:
                    calculated_equity = float(lowest_zest) - total_final_judgment_amount

                    print(f"💡 Equity missing for {case_number}. Calculating fallback: "
                          f"{lowest_zest} (Zestimate) - {total_final_judgment_amount} (Judgment) = {calculated_equity}")

                    # Update equity in the database
                    supabase.table("case_property_details") \
                        .update({"equity": calculated_equity}) \
                        .eq("case_id", case_id_uuid) \
                        .execute()

        """        # ---------------------------------------------------------
        # STEP 2: Process and insert into 'case_parties'
        # ---------------------------------------------------------
        # We consolidate plaintiffs and defendants into a unified loop tracker
        parties_to_sync = []

        # Track plaintiffs
        for idx, p in enumerate(extraction_data.get("plaintiffs", []), start=1):
            if p.get("name"):
                parties_to_sync.append({
                    "case_id": case_id_uuid,
                    "name": p["name"].strip(),
                    "description": f"Plaintiff | Address: {p.get('address')}",
                    "party_index": idx,
                    "party_status": "PLAINTIFF"
                })

        # Track defendants (Offsetting index so they don't collide with plaintiffs)
        for idx, d in enumerate(extraction_data.get("defendants", []), start=11):
            if d.get("name"):
                desc_parts = [f"Defendant | Address: {d.get('address')}"]
                if d.get("relationship"):
                    desc_parts.append(f"Relationship: {d['relationship']}")

                parties_to_sync.append({
                    "case_id": case_id_uuid,
                    "name": d["name"].strip(),
                    "description": " / ".join(desc_parts),
                    "party_index": idx,
                    "party_status": "DEFENDANT"
                })

        # Multi-row Upsert to case_parties for maximum network efficiency
        if parties_to_sync:
            supabase.table("case_parties").upsert(
                parties_to_sync, 
                on_conflict="case_id, party_index"
            ).execute()
            print(f"👥 Synced {len(parties_to_sync)} parties to case_parties for {case_number}")
        """
        return True

    except Exception as e:
        print(f"❌ Error syncing extracted case data for {case_number}: {e}")
        return False


def final_judgment_flag(case_number, flag):
    case_id_uuid = get_case_id_by_number(case_number)
    if not case_id_uuid:
        print(f"❌ Aborting: Case {case_number} must exist in 'cases' table first.")
        return False

    results_payload = {
        "id": case_id_uuid,
        "case_number": case_number,
        "is_final_judgment": flag,
    }
    supabase.table("cases").upsert(results_payload, on_conflict="id").execute()


def delete_case_completely_from_supabase(case_number, files_dir):
    """f
    Purges all related records for a case using the case_number string.
    Verifies if rows were actually removed on the server side.
    """
    _snoop_log = os.path.join(files_dir, "download_files_nj_case.log")
    with pysnooper.snoop(_snoop_log):
        if not case_number:
            return False

        try:
            clean_num = str(case_number).strip()
            case_id_uuid = get_case_id_by_number(clean_num)
            print(f"🧹 Commencing complete database purge for case number: {clean_num}...")

            # 1. Clean up child tables using the raw case_number string
            child_tables = [
                "case_documents",
                "case_parties",
                "case_property_details",
                "case_results",
                "case_sales_web",
                "deed_documents",
                "main_defendants_research"
            ]

            for table in child_tables:
                try:
                    # Target the text case_number column in child tables if they have it
                    supabase.table(table).delete().eq("case_id", case_id_uuid).execute()
                except Exception:
                    # Fallback if a specific child table only implements case_id UUID linking
                    pass

            # 2. Delete from the master table and verify row count mutation
            res = supabase.table("cases").delete().eq("case_number", clean_num).execute()

            # Verify if an actual row index was targeted and dropped
            if res.data and len(res.data) > 0:
                print(f"🗑️ Successfully deleted case {clean_num} from Supabase.")
                return True
            else:
                print(
                    f"⚠️ Warning: Delete request for {clean_num} completed, but 0 rows were found matching that case number in the database. (Check RLS Policies or case creation sequence)")
                return False

        except Exception as e:
            print(f"❌ Critical failure while purging case {clean_num} from Supabase: {e}")
            return False


def bulk_purge_processing_cases():
    """
    Purges all 'processing' cases and their related table data
    using standard PostgREST queries. Safe from schema cache issues.
    """
    try:
        print("🔍 Fetching list of all cases currently marked as 'processing'...")

        # 1. Get the list of target case numbers
        target_search = supabase.table("cases") \
            .select("case_number") \
            .eq("processing_status", "processing") \
            .execute()

        if not target_search.data:
            print("💡 No cases with status 'processing' found. Database is already clean.")
            return 0

        # Extract case numbers into a clean Python list: ['25-001', '25-002', ...]
        case_numbers = [row['case_number'] for row in target_search.data if row.get('case_number')]

        if not case_numbers:
            print("💡 Found rows, but they all had blank or null case numbers.")
            return 0

        total_to_delete = len(case_numbers)
        print(f"🗑️ Found {total_to_delete} cases to purge. Cleaning child tables...")

        # 2. Bulk delete from child tables using the .in_() operator
        child_tables = [
            "case_documents",
            "case_parties",
            "case_property_details",
            "case_results",
            "case_sales_web",
            "deed_documents",
            "main_defendants_research"
        ]

        for table in child_tables:
            try:
                supabase.table(table).delete().in_("case_number", case_numbers).execute()
            except Exception as e:
                # Bypass errors if a specific custom table doesn't use standard string linking
                print(f"⚠️ Minor skip on table '{table}': {e}")

        # 3. Finally, delete the master records from the 'cases' table
        supabase.table("cases").delete().in_("case_number", case_numbers).execute()

        print(f"✨ Bulk purge complete! Cleared {total_to_delete} 'processing' cases and their history.")
        return total_to_delete

    except Exception as e:
        print(f"❌ Failed to execute Python-side bulk processing purge: {e}")
        return False




def process_and_save_search_matches(deceased_person_id: str, search_results: list, cookies: dict = None):
    """
    Saves metadata search hits to 'obituary_search_matches', handles deep-link
    scraping via process_obituary_link, and syncs results into the 'obituaries' table.
    """
    if not search_results or not isinstance(search_results, list):
        return False

    for item in search_results:
        try:
            full_name = item.get("full_name")
            if not full_name:
                continue

            # 1. Parse out the unique links from the raw nested payload structure
            raw_obits_list = item.get("obituaries") or []
            urls_to_process = []
            for obit_node in raw_obits_list:
                for affiliate in obit_node.get("affiliates", []):
                    if affiliate.get("url"):
                        urls_to_process.append(affiliate["url"])

            unique_urls = list(set(urls_to_process))

            # 2. Build the parent metadata match record
            record = {
                "deceased_person_id": deceased_person_id,
                "external_provider_id": str(item.get("person_id") or item.get("id") or ""),
                "matched_full_name": full_name,
                "birth_date": item.get("birth_date") if item.get("birth_date") else None,
                "death_date": item.get("death_date") if item.get("death_date") else None,
                "bio": item.get("bio") or "",
                "obituary_count": int(item.get("obituary_count") or 0),
                "obituaries": unique_urls,  # Flat clean list of strings matches text array schema
                "locations": item.get("locations") or []
            }

            # 3. Upsert parent match metadata, returning the row's primary identity key (UUID)
            # Make sure your database table has a unique index or constraint on (deceased_person_id, external_provider_id)
            db_response = supabase.table("obituary_search_matches") \
                .upsert(record, on_conflict="deceased_person_id,external_provider_id") \
                .execute()

            if not db_response.data:
                continue

            match_uuid = db_response.data[0]["id"]

            # 4. Loop over unique URLs to process and insert individual obituaries
            for unique_url in unique_urls:
                try:
                    # Execute your deep scraper link handler
                    data, obituary_text = process_obituary_link(unique_url)

                    infos = json.loads(data)

                    # 5. Map the extracted 'infos' dictionary to your 'obituaries' schema columns
                    obituary_payload = {
                        "match_id": match_uuid,
                        "source_url": unique_url,
                        "obituary_text": obituary_text,
                        "name": infos.get("name") or full_name,
                        "date_of_birth": infos.get("date_of_birth") or item.get("birth_date"),
                        "place_of_birth": infos.get("place_of_birth"),
                        "date_of_death": infos.get("date_of_death") or item.get("death_date"),
                        "place_of_death": infos.get("place_of_death"),
                        "heirs": infos.get("heirs") or [],  # Maps directly to JSONB
                        "associates": infos.get("associates") or [],  # Maps directly to JSONB
                        "friends": infos.get("friends") or []  # Maps directly to JSONB
                    }
                    print(f"obituary_payload : {obituary_payload}")
                    # 6. Upsert the child obituary records using source_url as conflict resolution target
                    supabase.table("obituaries") \
                        .upsert(obituary_payload, on_conflict="match_id,source_url") \
                        .execute()

                    print(f"✅ Successfully synced deep obituary page: {unique_url}")

                except Exception as link_err:
                    traceback.print_exc()
                    print(f"❌ Error extracting/saving details for individual link [{unique_url}]: {link_err}")
                    continue

        except Exception as e:
            traceback.print_exc()
            print(f"⚠️ Error compiling match payload block: {e}")
            continue

    return True




# Add this to your nj_helpers.py or database/supabase_service.py

@pysnooper.snoop()
def mark_case_as_rip(case_id, files_dir, report_cases, reason, batch_name=""):
    """
    Mark a case as RIP (Removed Ineligible Property) and stop processing.

    Args:
        case_id: The case identifier
        files_dir: Path to the case files directory
        reason: Why the case was marked as RIP

    Returns:
        tuple: (None, []) - matching the return signature of download_files_nj
    """
    from app import log_message, update_case_status

    log_message(f"⏭️ [{case_id}] RIP — {reason}")
    update_case_status(None, case_id, "New Jersey", "RIP", details=reason)

    # Update report_cases
    report_cases[case_id]['status'] = "RIP"
    report_cases[case_id]['rip_reason'] = reason

    # Mark in database
    try:
        rip_flag(case_id, reason, batch_name=batch_name)
    except Exception:
        pass

    # Return the expected format for download_files_nj
    return None, []


def delete_case_completely(case_number: str, case_id: str = None, file_source: str = None) -> bool:
    """
    Delete a case and all its associated data from all tables.
    Also deletes files from storage if file_source is provided.

    Args:
        case_number: The case number to delete
        case_id: Optional case UUID (if not provided, it will be looked up)
        file_source: Optional path to the local files directory to delete

    Returns:
        True if successful, False otherwise
    """
    try:
        clean_num = str(case_number).strip()

        # Get case_id if not provided
        if not case_id:
            case_id = get_case_id_by_number(clean_num)
            if not case_id:
                print(f"⚠️ Case '{clean_num}' not found in database.")
                return False

        print(f"🗑️ Deleting case '{clean_num}' (ID: {case_id}) and all associated data...")

        # 1. Delete from all child tables
        child_tables = [
            "case_documents",
            "case_parties",
            "case_property_details",
            "case_sales_web",
            "deed_documents",
            "main_defendants_research",
            "case_events",
            "case_location",
            "case_judgment_details",
            "case_mortgage_details",
            "case_defendant_details",
            "case_deceased_persons",
            "obituary_search_matches",
            "obituaries"
        ]

        for table in child_tables:
            try:
                response = supabase.table(table).delete().eq("case_id", case_id).execute()
                print(f"  ✅ Deleted from {table}")
            except Exception as e:
                print(f"  ⚠️ Could not delete from {table}: {e}")

        # 2. Delete from the master cases table
        response = supabase.table("cases").delete().eq("id", case_id).execute()
        print(f"  ✅ Deleted from cases")

        # 3. Delete local files if file_source is provided
        if file_source:
            try:
                import shutil
                case_folder = os.path.join(file_source, clean_num)
                if os.path.exists(case_folder):
                    shutil.rmtree(case_folder)
                    print(f"  ✅ Deleted local folder: {case_folder}")
                else:
                    print(f"  ℹ️ Local folder not found: {case_folder}")
            except Exception as e:
                print(f"  ⚠️ Could not delete local files: {e}")

        print(f"✅ Case '{clean_num}' deleted successfully!")
        return True

    except Exception as e:
        print(f"❌ Failed to delete case '{case_number}': {e}")
        traceback.print_exc()
        return False

@pysnooper.snoop()
def valid_flag(case_id: str, batch_name=""):
    payload = {
        "case_number": case_id,  # Required for upsert to identify or insert the row
        "valid": True,
        "batch_name": batch_name,
        "updated_at": "now()"
    }

    while True:
        try:
            supabase.table("cases") \
                .upsert(payload, on_conflict="case_number") \
                .execute()
            break
        except RemoteProtocolError:
            supabase = create_client(url, key)
        except Exception as e:
            print(f"❌ Error setting valid flag for '{case_id}': {e}")
            break

    print(f"[{case_id}] valid flag set (created or updated)")

