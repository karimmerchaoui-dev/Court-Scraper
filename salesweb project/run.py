"""
run.py — entry point for foreclosure-radar.

Examples:
    # Scrape NJ open listings, save to DB, auto-export Excel
    python run.py --state NJ --status open

    # Scrape NJ + PA, export CSV instead
    python run.py --state NJ --state PA --format csv

    # Export what's already in the DB without scraping
    python run.py --export-only --county "Essex County, NJ"

    # Export with a Zestimate filter
    python run.py --export-only --min-zestimate 100000 --max-zestimate 300000
"""

import argparse
import os

from src.config import DEFAULT_DELAY, DEFAULT_MAX_WORKERS, OUTPUT_DIR
from src.scrapers.civilview import CivilViewForeclosureScraper
from src.utils.database import Database


def parse_args():
    p = argparse.ArgumentParser(description="foreclosure-radar — lead sourcing pipeline")

    # --- scraping ---
    p.add_argument("--state",  action="append", default=[],
                   help="State abbreviation(s), e.g. --state NJ --state PA")
    p.add_argument("--status", choices=["open", "sold", "both"], default="open")

    # --- export ---
    p.add_argument("--format", choices=["excel", "csv", "both"], default="excel",
                   help="Output format (default: excel)")
    p.add_argument("--output", default=None,
                   help="Custom output file path")

    # --- filters (apply to export, not to scrape) ---
    p.add_argument("--county",        default=None, help="Filter export by county name")
    p.add_argument("--min-zestimate", type=float,   help="Minimum Zestimate value")
    p.add_argument("--max-zestimate", type=float,   help="Maximum Zestimate value")

    # --- modes ---
    p.add_argument("--export-only", action="store_true",
                   help="Skip scraping, just export what's already in the DB")
    p.add_argument("--db", default="foreclosures.db",
                   help="SQLite database path (default: foreclosures.db)")

    # --- tuning ---
    p.add_argument("--delay",   type=int, default=DEFAULT_DELAY)
    p.add_argument("--workers", type=int, default=DEFAULT_MAX_WORKERS)

    return p.parse_args()


def main():
    args = parse_args()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    db = Database(db_path=args.db)

    # ------------------------------------------------------------------
    # 1. Scrape (unless --export-only)
    # ------------------------------------------------------------------
    if not args.export_only:
        if not args.state:
            print("❌ Provide at least one --state, or use --export-only")
            return

        states = [s.upper() for s in args.state]
        scraper = CivilViewForeclosureScraper(delay=args.delay, max_workers=args.workers)
        counties = scraper.get_all_counties()
        print(f"Found {len(counties)} counties total")

        for county_name, county_info in counties.items():
            if any(f" {state}" in county_name or county_name.endswith(state)
                   for state in states):
                print(f"\n📍 Scraping: {county_name}")
                listings = scraper.scrape_county_listings(
                    county_name, county_info,
                    number_input="",
                    include_details=True,
                    status=args.status,
                )
                inserted, updated = db.insert_listings(listings)
                print(f"   ✅ {inserted} new  |  {updated} updated  |  {db.count()} total in DB")

    # ------------------------------------------------------------------
    # 2. Export
    # ------------------------------------------------------------------
    filter_kwargs = dict(
        county=args.county,
        min_zestimate=args.min_zestimate,
        max_zestimate=args.max_zestimate,
    )

    print(f"\n📦 Exporting from DB ({db.count()} total rows)…")

    if args.format in ("excel", "both"):
        db.export_excel(path=args.output, **filter_kwargs)

    if args.format in ("csv", "both"):
        csv_path = args.output.replace(".xlsx", ".csv") if args.output else None
        db.export_csv(path=csv_path, **filter_kwargs)


if __name__ == "__main__":
    main()