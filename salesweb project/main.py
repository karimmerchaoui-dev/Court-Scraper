"""
Foreclosure Scraper — CLI entry point

Usage examples
--------------
Scrape all NJ counties (open listings):
    python main.py --state NJ --status open --output NJ_listings.xlsx

Scrape a single county:
    python main.py --state NJ --county "Bergen County, NJ" --status both
"""

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from supabase import create_client
from tqdm import tqdm

# Ensure project root is in sys.path so ai.llm_helper can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from ai.llm_helper import normalize_case_numbers_haiku
except ImportError:
    from court_scraper_basic.ai.llm_helper import normalize_case_numbers_haiku

from src.exporters.excel import save_to_excel
from src.scrapers.civilview import CivilViewForeclosureScraper

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")


supabase = create_client(url, key)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape foreclosure listings from salesweb.civilview.com"
    )
    parser.add_argument(
        "--state",
        required=True,
        help="Two-letter state abbreviation to filter counties (e.g. NJ, PA)",
    )
    parser.add_argument(
        "--county",
        default=None,
        help="Exact county name to scrape (optional; scrapes all matching counties if omitted)",
    )
    parser.add_argument(
        "--status",
        choices=["open", "sold", "both"],
        default="open",
        help="Listing status filter (default: open)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output Excel file path (default: <state>_listings.xlsx)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Maximum parallel worker threads (default: 5)",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=2,
        help="Base delay between requests in seconds (default: 2)",
    )
    return parser.parse_args()


def normalize_listings_case_numbers(listings: list[dict], batch_size: int = 50) -> None:
    """
    Finds all listings with a non-empty 'case_number', batches them,
    and normalizes them in-place using normalize_case_numbers_haiku.
    """
    listings_with_cases = [
        listing for listing in listings
        if listing.get("case_number") and str(listing.get("case_number")).strip()
    ]

    total_cases = len(listings_with_cases)
    if not total_cases:
        print("[*] No case numbers found to normalize.")
        return

    print(f"\n[*] Found {total_cases} listings with case numbers. Normalizing with Haiku in batches of {batch_size}...")

    with tqdm(total=total_cases, desc="Normalizing Case Numbers", unit="case") as pbar:
        for start_idx in range(0, total_cases, batch_size):
            batch = listings_with_cases[start_idx : start_idx + batch_size]
            raw_nums = [str(l["case_number"]).strip() for l in batch]

            try:
                norm_results = normalize_case_numbers_haiku(raw_nums)
                for i, item in enumerate(norm_results):
                    val = item.get("normalized") if isinstance(item, dict) else item
                    if val and val != "INVALID":
                        batch[i]["case_number"] = val
            except Exception as e:
                print(f"\n   [!] Error normalizing batch starting at {start_idx}: {e}")

            pbar.update(len(batch))

    print("[*] Case number normalization complete.")


def _check_exists(listing: dict) -> tuple[dict, bool]:
    """
    Check if listing['case_number'] already exists in the Supabase 'cases' table.
    Returns (listing, exists: bool).
    """
    case_number = str(listing.get("case_number", "")).strip()
    try:
        result = supabase.table("cases").select("id").eq("case_number", case_number).execute()
        exists = bool(result.data)
    except Exception as e:
        print(f"   [!] Supabase check error for {case_number!r}: {e}")
        exists = False  # on error, keep the listing (safe default)
    return listing, exists


def deduplicate_against_db(listings: list[dict], workers: int = 20) -> list[dict]:
    """
    Remove listings whose case_number already exists in the database.
    Runs checks in parallel across `workers` threads.
    Returns the filtered list (new listings only).
    """
    # Only check listings that actually have a case number
    has_case = [l for l in listings if l.get("case_number") and str(l.get("case_number")).strip()]
    no_case  = [l for l in listings if not (l.get("case_number") and str(l.get("case_number")).strip())]

    if not has_case:
        print("[*] No case numbers to deduplicate against DB.")
        return listings

    print(f"\n[*] Checking {len(has_case)} listings against Supabase with {workers} threads...")

    kept: list[dict] = []
    removed = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_check_exists, listing): listing for listing in has_case}

        with tqdm(total=len(has_case), desc="DB Dedup", unit="listing") as pbar:
            for future in as_completed(futures):
                try:
                    listing, exists = future.result()
                    if exists:
                        removed += 1
                        pbar.set_postfix_str(f"removed: {removed}")
                    else:
                        kept.append(listing)
                except Exception as e:
                    # Keep on unexpected error
                    kept.append(futures[future])
                pbar.update(1)

    print(f"[*] Deduplication complete: {removed} already in DB removed, {len(kept)} new listings kept.")
    return kept + no_case  # listings without a case number always pass through


def main() -> None:
    args = parse_args()
    output_path = Path(args.output or f"{args.state}_listings.xlsx")

    scraper = CivilViewForeclosureScraper(delay=args.delay, max_workers=args.workers)
    all_counties = scraper.get_all_counties()

    # Filter counties by state abbreviation
    target_counties = {
        name: info
        for name, info in all_counties.items()
        if args.state.upper() in name
    }

    if args.county:
        target_counties = {
            name: info
            for name, info in target_counties.items()
            if name == args.county
        }

    if not target_counties:
        print(f"No counties found for state '{args.state}'. Check the spelling or abbreviation.")
        return

    print(f"Found {len(target_counties)} county/ies to scrape.")
    total_listings: list[dict] = []

    for county_name, county_info in target_counties.items():
        print(f"\n--- Scraping: {county_name} ---")
        listings = scraper.scrape_county_listings(
            county_name=county_name,
            county_info=county_info,
            number_input="",
            include_details=True,
            status=args.status,
        )
        total_listings.extend(listings)
        print(f"    {len(listings)} listings collected from {county_name}")
    print(f"\nTotal listings: {len(total_listings)}")

    # ── Normalize case numbers with Haiku in batches ──────────────────────────
    normalize_listings_case_numbers(total_listings, batch_size=50)

    # ── Remove listings that already exist in the database ────────────────────
    total_listings = deduplicate_against_db(total_listings, workers=20)
    print(f"[*] Final listings after dedup: {len(total_listings)}")

    save_to_excel(total_listings, output_path)


if __name__ == "__main__":
    main()
