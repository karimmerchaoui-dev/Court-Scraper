"""
Pipeline Blocks Package
=======================
Contains discrete, modular execution blocks for the Court Scraper pipeline.
Each block encapsulates a single phase of court scraping with robust error
containment, verification, and retry signaling.

New Jersey Blocks (Statewide Portal):
------------------------------------
- Block 1: `PrecheckBlock` (`nj_precheck.py`)
    Pre-filters cases via SalesWeb and Zillow, evaluating RIP/ineligibility rules.
- Block 2: `CourtNavigationBlock` (`nj_court_navigation.py`)
    Navigates to NJ portal, authenticates, solves CAPTCHA, and searches docket.
- Block 3: `CaseCheckingBlock` (`nj_case_checking.py`)
    Verifies docket table results, scrapes case metadata, launches parcel lookup.
- Block 4: `FilePickingBlock` (`nj_file_picking.py`)
    Scans docket documents via multi-threading, identifying complaint & judgment PDFs.
- Block 5: `CourtDownloadingBlock` (`nj_downloading.py`)
    Downloads identified filings, joins property address futures.
- Block 6: `ObituarySearchBlock` (`nj_obituary.py`)
    Asynchronously queries obituary data for defendants/parties.
- Block 7: `DeedSearchBlock` (`nj_deed.py`)
    Parses deed references (book/page/block/lot) and queues deed queries.
- Block 8: `DatabaseAddingBlock` (`nj_database.py`)
    Validates required filings, persists record to Supabase, and releases driver.

Florida Blocks (County-Specific Portals):
----------------------------------------
- Block 1: `NavigateToUrlBlock` (`fl_navigate_to_url.py`)
    Opens county court landing page with automated DOM verifiers.
- Block 2: `NavigateToSearchBlock` (`fl_navigate_to_search.py`)
    Navigates to docket search form (supporting login credentials where required).
- Block 3: `SearchCaseNumberBlock` (`fl_search_case_number.py`)
    Formats case ID, inputs into search form, and verifies result display.
- Block 4: `NavigateToFilesBlock` (`fl_navigate_to_files.py`)
    Switches to the documents or docket entries tab.
- Block 5: `DownloadFilesBlock` (`fl_download.py`)
    Scans document table, handles downloads, and executes two-tier retries.
- Block 8: `FloridaDatabaseBlock` (`fl_database.py`)
    Verifies complaint presence, enriches Zillow data, pushes to DB, releases driver.
"""

# ── NJ blocks ────────────────────────────────────────────────────────────────
from .fl_database import FloridaDatabaseBlock
from .fl_download import DownloadFilesBlock
from .fl_navigate_to_files import NavigateToFilesBlock
from .fl_navigate_to_search import NavigateToSearchBlock

# ── Florida / Generic county blocks ──────────────────────────────────────────
from .fl_navigate_to_url import NavigateToUrlBlock
from .fl_search_case_number import SearchCaseNumberBlock
from .nj_case_checking import CaseCheckingBlock
from .nj_court_navigation import CourtNavigationBlock
from .nj_database import DatabaseAddingBlock
from .nj_deed import DeedSearchBlock
from .nj_downloading import CourtDownloadingBlock
from .nj_file_picking import FilePickingBlock
from .nj_obituary import ObituarySearchBlock
from .nj_precheck import PrecheckBlock

__all__ = [
    # NJ
    "PrecheckBlock",
    "CourtNavigationBlock",
    "CaseCheckingBlock",
    "FilePickingBlock",
    "CourtDownloadingBlock",
    "ObituarySearchBlock",
    "DeedSearchBlock",
    "DatabaseAddingBlock",
    # Florida
    "NavigateToUrlBlock",
    "NavigateToSearchBlock",
    "SearchCaseNumberBlock",
    "NavigateToFilesBlock",
    "DownloadFilesBlock",
    "FloridaDatabaseBlock",
]

