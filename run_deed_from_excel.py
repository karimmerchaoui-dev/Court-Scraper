"""
run_deed_from_excel.py
----------------------
Reads an Excel file with columns:
    main_defendant | county_name | case_id

Runs build_payload + run_deed_job for every row concurrently using
ThreadPoolExecutor, then writes a results Excel file alongside the input.

Usage:
    python run_deed_from_excel.py path/to/input.xlsx [--workers 4]
"""

import argparse
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

# ── Allow imports from project root ─────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from deed_search.deed_api import run_deed_job
from main import build_payload

# ── Per-row worker ───────────────────────────────────────────────────────────

def _process_row(row: dict) -> dict:
    """
    Builds the deed payload and runs the deed job for a single row.
    Returns a result dict that is merged back into the output DataFrame.
    """
    main_defendant = str(row.get("main_defendant", "")).strip()
    county_name    = str(row.get("county_name", "")).strip()
    case_id        = str(row.get("case_id", "")).strip()

    result_row = {
        "case_id":        case_id,
        "main_defendant": main_defendant,
        "county_name":    county_name,
        "status":         "pending",
        "deed_status":    "",
        "extracted_data": "",
        "error":          "",
    }

    try:
        print(f"▶  [{case_id}] Building payload for '{main_defendant}' | county='{county_name}'")

        # Strip trailing " county" if already included so build_payload doesn't double it
        if isinstance(county_name, str) and county_name.lower().endswith(" county"):
            county_bare = county_name[: -len(" county")].strip()
        else:
            county_bare = county_name

        payload = build_payload(main_defendant, county_bare)

        print(f"🔄 [{case_id}] Submitting deed job …")
        result  = run_deed_job(payload)

        if result.get("status") == "error":
            result_row["status"]      = "error"
            result_row["deed_status"] = result.get("status", "")
            result_row["error"]       = result.get("error", str(result))
            print(f"❌ [{case_id}] Deed job returned error: {result_row['error']}")
        else:
            extracted = result.get("extracted_data", {})
            result_row["status"]         = "done"
            result_row["deed_status"]    = result.get("status", "done")
            result_row["extracted_data"] = str(extracted) if extracted else ""
            print(f"✅ [{case_id}] Done — extracted keys: {list(extracted.keys()) if isinstance(extracted, dict) else 'n/a'}")

    except Exception as exc:
        result_row["status"] = "exception"
        result_row["error"]  = traceback.format_exc()
        print(f"💥 [{case_id}] Exception: {exc}")

    return result_row


# ── Main ─────────────────────────────────────────────────────────────────────

def run_from_excel(input_path: str, max_workers: int = 4):
    input_path = Path(input_path).resolve()
    if not input_path.exists():
        print(f"❌ File not found: {input_path}")
        sys.exit(1)

    print(f"📂 Reading: {input_path}")
    df = pd.read_excel(input_path)

    # Normalise column names
    df.columns = [c.strip() for c in df.columns]

    required = {"main_defendant", "county_name", "case_id"}
    missing  = required - set(df.columns)
    if missing:
        print(f"❌ Missing columns in Excel: {missing}")
        print(f"   Found columns: {list(df.columns)}")
        sys.exit(1)

    rows = df.to_dict(orient="records")
    print(f"📋 {len(rows)} rows to process  |  max_workers={max_workers}\n")

    results = []
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="DeedBatch") as executor:
        future_map = {executor.submit(_process_row, row): row for row in rows}
        for future in as_completed(future_map):
            try:
                results.append(future.result())
            except Exception as exc:
                original = future_map[future]
                results.append({
                    "case_id":        original.get("case_id", "?"),
                    "main_defendant": original.get("main_defendant", ""),
                    "county_name":    original.get("county_name", ""),
                    "status":         "exception",
                    "deed_status":    "",
                    "extracted_data": "",
                    "error":          str(exc),
                })

    # ── Write results ────────────────────────────────────────────────────────
    out_df      = pd.DataFrame(results)
    output_path = input_path.with_name(input_path.stem + "_deed_results.xlsx")
    out_df.to_excel(output_path, index=False)

    done  = (out_df["status"] == "done").sum()
    error = (out_df["status"] != "done").sum()
    print(f"\n📊 Summary: {done} succeeded  |  {error} failed")
    print(f"💾 Results saved to: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run deed jobs from an Excel file in parallel."
    )
    parser.add_argument(
        "input",
        help="Path to the Excel file (columns: main_defendant, county_name, case_id)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel threads (default: 4)",
    )
    args = parser.parse_args()
    run_from_excel(args.input, max_workers=args.workers)
