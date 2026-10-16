from __future__ import annotations

f"""
county_config.py
----------------
Defines the per-county configuration schema and the county registry.
Each county describes ONLY what differs between counties; all shared
download logic lives in downloader.py.
"""


from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from seleniumbase import Driver


class ScrapeMode(Enum):
    ROW_BY_ROW = "row_by_row"       # loop through each row and trigger download individually
    BULK = "bulk"                    # a single function downloads all files at once

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
DriverAction = Callable[[Driver], None]


class SearchMode(Enum):
    BOOK_PAGE  = "book_page"    # current default
    INSTRUMENT = "instrument"
    NAME       = "name"

# ---------------------------------------------------------------------------
# Configuration schema
# ---------------------------------------------------------------------------
@dataclass
class CountyConfig:
    """
    All county-specific metadata needed to search and download deed files.

    Fields
    ------
    name : str
        Human-readable county name used for logging and folder naming.
    url : str
        Landing / search page URL.
    book_xpath : str
        XPath of the "Book number" input field.
    page_xpath : str
        XPath of the "Page number" input field.
    deed_type_xpath : str
        XPath of the deed-type selector (dropdown, checkbox group, etc.).
    submit_button_xpath : str
        XPath of the search / submit button.
    deeds_table_xpath : str
        XPath of the results table container.
    row_tag_name : str
        Tag name used to identify individual result rows ('tr', 'div', …).
    get_to_download_page_func : DriverAction
        Callable ``(driver) -> None`` that navigates from a result row to
        the deed's dedicated download page (e.g. clicks a "View" button).
        Receives the *already-located row element* as context via a closure
        or the driver itself — see examples below.
    file_trigger_download_func : DriverAction
        Callable ``(driver) -> None`` that triggers the actual file download
        once on the deed's download page.
    deed_type_value : str, optional
        The value / label to select in the deed-type field (if applicable).
    download_timeout : int
        Seconds to wait for a download to complete (default 60).
    extra_wait : float
        Extra sleep (seconds) injected between actions for slow sites.
    """

    # --- Identity ---
    name: str

    # --- Navigation ---
    url: str

    # --- Search form XPaths ---
    book_xpath: str
    page_xpath: str
    deed_type_xpath: str
    submit_button_xpath: str




    # --- Results ---
    deeds_table_xpath: str
    row_tag_name: str

    # --- Per-row / per-deed actions ---
    get_to_download_page_func: DriverAction
    file_trigger_download_func: DriverAction
    get_to_download_page_name_func: Optional[DriverAction] = None
    return_to_table_func: Optional[DriverAction] = None

    supported_search_modes: list[SearchMode] = field(
        default_factory=lambda: [SearchMode.BOOK_PAGE,SearchMode.INSTRUMENT,SearchMode.NAME]
    )
    # --- Optional / tuneable ---
    deed_type_values: list[str] = field(default_factory=list)  # e.g. ["Warranty Deed", "Deed of Trust"]
    download_timeout: int = 60
    extra_wait: float = 1.0
    extra_setup: Optional[DriverAction] = None   # e.g. accept cookies, login
    navigate_to_search_func: Optional[DriverAction] = None  # click tab/nav to reach the search form
    navigate_to_table_func: Optional[DriverAction] = None   # action to perform before reading the table
    scrape_mode: ScrapeMode = ScrapeMode.ROW_BY_ROW
    bulk_download_func: Optional[DriverAction] = None  # only used when scrape_mode
    validate_file_func: Optional[Callable[[Driver], bool]] = None  # returns True if valid, False to skip
    scroll_to_load_rows_func: Optional[Callable[[Driver], None]] = None
    max_rows: Optional[int] = None  # None means no limit — process all rows


    navigate_to_instrument_search_func: Optional[DriverAction] = None
    navigate_to_name_search_func: Optional[DriverAction] = None



    filter_rows_func: Optional[Callable[[Driver, list, str, str], list]] = None

    ###
    instrument_xpath: Optional[str] = None
    instrument_url: Optional[str] = None   # if instrument search has a different URL

    # name search
    first_name_xpath: Optional[str] = None
    last_name_xpath: Optional[str] = None
    name_url: Optional[str] = None         # if name search has a different URL

    instrument_submit_button_xpath: Optional[str] = None
    name_submit_button_xpath: Optional[str] = None

    # --- Related documents (optional) ---
    related_docs_make_table_visible_func: Optional[DriverAction] = None  # makes the related docs table visible
    related_docs_table_xpath: Optional[str] = None                        # xpath of the related docs table
    related_docs_row_tag_name: Optional[str] = None                       # e.g. "/tr[contains(@class,'item')]"
    related_docs_trigger_download_func: Optional[DriverAction] = None     # triggers download for row i
    related_docs_return_to_table_func: Optional[DriverAction] = None      # returns to related docs table

# ---------------------------------------------------------------------------
# County registry
# ---------------------------------------------------------------------------
class CountyRegistry:
    """Central store for all county configurations."""

    def __init__(self) -> None:
        self._registry: dict[str, CountyConfig] = {}

    def register(self, config: CountyConfig) -> None:
        key = config.name.lower().replace(" ", "_")
        self._registry[key] = config

    def get(self, name: str) -> CountyConfig:
        key = name.lower().replace(" ", "_")
        if key not in self._registry:
            raise KeyError(f"No county registered under '{name}'. "
                           f"Available: {list(self._registry)}")
        return self._registry[key]

    def all(self) -> list[CountyConfig]:
        return list(self._registry.values())

    def names(self) -> list[str]:
        return [c.name for c in self._registry.values()]


# Singleton registry — import this everywhere
registry = CountyRegistry()
