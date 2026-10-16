from __future__ import annotations

"""
main.py
-------
CLI entry point.

Usage examples
--------------
# Download a single deed
python main.py --county "Example County A" --book 1234 --page 56

# Batch download from a CSV file (columns: county, book, page[, deed_type])
python main.py --csv requests.csv

# List registered counties
python main.py --list-counties
"""


import argparse
import logging
import sys
from pathlib import Path

# Add project root to sys.path to allow running this script directly or via test.py
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Importing the counties package populates the global registry (side-effects)
import deed_search.counties  # noqa: F401
from deed_search.county_config import registry
from deed_search.downloader import DeedDownloader, DeedRequest

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_downloader(county_name: str, output_dir: Path, headless: bool, search_mode: str) -> DeedDownloader:
    config = registry.get(county_name)
    return DeedDownloader(config, output_dir=output_dir, headless=headless, search_mode=search_mode)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automated deed downloader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--county", help="County name (must match registry)")
    parser.add_argument("--book", help="Book number")
    parser.add_argument("--page", help="Page number")
    parser.add_argument("--deed-type", help="Deed type (optional override)")
    parser.add_argument("--csv", type=Path, help="Path to batch CSV file")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("downloads"),
        help="Root download directory (default: ./downloads)",
    )
    parser.add_argument(
        "--no-headless", action="store_true",
        help="Run browser in visible mode (useful for debugging)",
    )
    parser.add_argument(
        "--list-counties", action="store_true",
        help="Print all registered county names and exit",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    headless = not args.no_headless

    if args.list_counties:
        print("Registered counties:")
        for name in registry.names():
            print(f"  • {name}")
        sys.exit(0)



    elif args.county and args.book and args.page:
        downloader = build_downloader(args.county, args.output_dir, headless,args.search_mode)
        req = DeedRequest(
            book=args.book,
            page=args.page,
            deed_type=args.deed_type,
            search_mode=args.search_mode
        )
        result = downloader.download_one(req)
        if result.success:
            logger.info("Downloaded to: %s", result.file_path)
        else:
            logger.error("Download failed: %s", result.error)
            sys.exit(1)

    else:
        logger.error(
            "Provide either --csv <file> or --county + --book + --page. "
            "Use --help for details."
        )
        sys.exit(1)


import pysnooper


@pysnooper.snoop()
def download_deed(
    county_name: str,
    output_dir: str | Path,
    book: str = None,
    page: str = None,
    headless: bool = True,
    deed_type: str = None,
    instrument: str = None,
    first_name: str = None,
    last_name: str = None,
    search_mode: str = None,
    block: str = None,
    lot: str = None,
    case_number: str = None,  # ✅ added
    download_file: bool = False,
    **kwargs,  # Accept extra arguments like llm_service/api_key silently
) -> dict:
    """
    Simple API function to download a deed programmatically.

    Parameters
    ----------
    county_name : str
        Must match a registered county name exactly (e.g. "Ocean County").
    book : str
        Book number.
    page : str
        Page number.
    output_dir : str | Path
        Folder where the file will be saved.
    headless : bool
        Run browser invisibly (default True). Pass False to watch it run.
    deed_type : str, optional
        Override the county's default deed type(s).

    Returns
    -------
    dict with keys:
        success  : bool
        file_path: str | None   — path to downloaded file if successful
        error    : str | None   — error message if failed
        county   : str
        book     : str
        page     : str

    Examples
    --------
    result =download_deed("Ocean County", "14", "5", "C:/deeds")
    if result["success"]:
        print(f"Downloaded to: {result['file_path']}")
    else:
        print(f"Failed: {result['error']}")
    """
    
    try:
        downloader = build_downloader(
            county_name=county_name,
            output_dir=Path(output_dir),
            headless=headless,
            search_mode=search_mode
        )
        req = DeedRequest(
            book=book,
            page=page,
            instrument=instrument,
            first_name=first_name,
            last_name=last_name,
            block=block,
            lot=lot,
            case_number=case_number,  # ✅ added
            deed_type=deed_type,
            download_file=download_file,
        )
        result = downloader.download_one(req)

        # Find the actual downloaded file path from the run folder
        file_path = None

        files = list(downloader.output_dir.iterdir())
        if files:
            file_path = str(sorted(files, key=lambda f: f.stat().st_mtime)[-1])
            
        return {
            "success": result.success,
            "file_path": file_path,
            "error": result.error,
            "county": county_name,
            "book": str(book),
            "page": str(page),
            "extracted_data": result.extracted_data,
        }

    except KeyError:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "file_path": None,
            "error": f"County '{county_name}' not found. Available: {registry.names()}",
            "county": county_name,
            "book": str(book),
            "page": str(page),
        }
    except Exception as e:
        return {
            "success": False,
            "file_path": None,
            "error": str(e),
            "county": county_name,
            "book": str(book),
            "page": str(page),
        }

