"""
downloader.py
-------------
County-agnostic download engine.
Given a CountyConfig and a list of (book, page) pairs it:
  1. Opens the search page
  2. Fills the form
  3. Iterates over result rows
  4. Navigates to each deed's download page
  5. Triggers and waits for the file download
  6. Moves the file into an organised output directory
"""
from __future__ import annotations

import logging
import random
import shutil
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pysnooper
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumbase import Driver

from deed_search.browser_helpers import (
    _build_combined_name,
    _fill_field,
    element_exists_xpath,
    find_element_in_iframes,
    is_restricted_document,
    set_download_dir,
)
from deed_search.county_config import CountyConfig, SearchMode
from deed_search.download_manager import DownloadManager

logger = logging.getLogger(__name__)





# ---------------------------------------------------------------------------
# Request / Result models
# ---------------------------------------------------------------------------
@dataclass
class DeedRequest:
    # book/page search
    book: Optional[str] = None
    page: Optional[str] = None



    block: Optional[str] = None  # ✅ add
    lot: Optional[str] = None    # ✅ add

    # instrument search
    instrument: Optional[str] = None

    # name search
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    deed_type: Optional[str] = None

    download_file: bool = False  # ✅ Add option to download or just extract
    case_number: Optional[str] = None  # ✅ Add case_number for database sync
    
    @property
    def search_mode(self) -> str:
        """Infer the search mode from what fields are populated."""
        if self.instrument:
            return SearchMode.INSTRUMENT
        if self.first_name or self.last_name:
            return SearchMode.NAME
        return SearchMode.BOOK_PAGE

@dataclass
class DeedResult:
    request: DeedRequest
    county: str
    success: bool
    file_path: Optional[Path] = None
    error: Optional[str] = None
    extracted_data: list[dict] = None  # ✅ Add field for extracted data



from datetime import datetime


# ---------------------------------------------------------------------------
# Downloader
# ---------------------------------------------------------------------------
class DeedDownloader:
    """
    Orchestrates the full download workflow for one county + many requests.

    Parameters
    ----------
    config : CountyConfig
        County-specific configuration (XPaths, actions, …).
    output_dir : Path
        Root folder for downloads.  Files land in
        ``output_dir/<county_name>/<book>_<page>.<ext>``.
    headless : bool
        Run the browser headlessly (default True in production).
    """

    def __init__(
        self,
        config: CountyConfig,
        output_dir: Path = Path("downloads"),
        headless: bool = True,
        search_mode: str = None,
    ) -> None:
        self.config = config
        run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.output_dir = output_dir / "deeds" / run_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.search_mode = search_mode

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def download_many(self, requests: list[DeedRequest]) -> list[DeedResult]:
        """Download all deeds in *requests*, reusing a single browser session."""
        results: list[DeedResult] = []
        driver = self._open_driver()
        try:
            if self.config.extra_setup:
                logger.info("[%s] Running extra_setup …", self.config.name)
                self.config.extra_setup(driver)

            for req in requests:
                result = self._download_one(driver, req)
                results.append(result)
                status = "✓" if result.success else f"✗  {result.error}"
                logger.info(
                    "[%s] book=%s page=%s → %s",
                    self.config.name, req.book, req.page, status,
                )
        finally:
            driver.quit()
        return results

    def download_one(self, request: DeedRequest) -> DeedResult:
        """Convenience wrapper for a single request."""
        return self.download_many([request])[0]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    
    def request_url(self, driver: Driver, req: DeedRequest, cfg: Optional[CountyConfig] = None) -> Optional[DeedResult]:
        if cfg is None:
            cfg = self.config
        for attempt in range(1, 4):
            try:
                if req.search_mode == SearchMode.INSTRUMENT:
                    driver.get(cfg.instrument_url)
                elif req.search_mode == SearchMode.BOOK_PAGE:
                    driver.get(cfg.url)
                elif req.search_mode == SearchMode.NAME:
                    driver.get(cfg.name_url)

                # Check for browser error page — skip deed entirely
                if driver.execute_script(
                    "return !!document.getElementById('main-frame-error');"
                ):
                    logger.warning("[%s] Browser error page on attempt %d — skipping deed.", cfg.name, attempt)
                    return DeedResult(req, cfg.name, False, error="Browser error page (main-frame-error) — site unreachable")

                WebDriverWait(driver, 20).until(lambda d: (
                    d.execute_script("return document.readyState") == "complete"
                    and "please wait..." not in (
                        d.execute_script("return document.body ? document.body.innerText : ''") or ""
                    ).lower()
                ))
                break

            except Exception as e:
                traceback.print_exc()
                if attempt == 3:
                    logger.error("[%s] All 3 attempts failed for deed — skipping.", cfg.name)
                    return DeedResult(req, cfg.name, False, error=f"Failed after 3 attempts: {e}")
                continue
        return None

    def enter_case_number(self, driver, req, cfg, deed_type):
        for attempt in range(1, 4):
            try:
                if req.search_mode == SearchMode.BOOK_PAGE:
                    if cfg.navigate_to_search_func:
                        cfg.navigate_to_search_func(driver)
                    _fill_field(driver, cfg.book_xpath, req.book)
                    _fill_field(driver, cfg.page_xpath, req.page)
                    if deed_type and cfg.deed_type_xpath:
                        self._select_deed_type(driver, cfg.deed_type_xpath, deed_type)
                    submit = find_element_in_iframes(driver, cfg.submit_button_xpath)
                    submit.click()

                elif req.search_mode == SearchMode.INSTRUMENT:
                    if cfg.navigate_to_instrument_search_func:
                        cfg.navigate_to_instrument_search_func(driver)

                    _fill_field(driver, cfg.instrument_xpath, req.instrument)
                    submit = find_element_in_iframes(driver, cfg.instrument_submit_button_xpath)
                    submit.click()
                    
                elif req.search_mode == SearchMode.NAME:
                    if cfg.navigate_to_name_search_func:
                        cfg.navigate_to_name_search_func(driver)
                    if cfg.first_name_xpath and cfg.last_name_xpath and cfg.first_name_xpath == cfg.last_name_xpath:
                        combined = _build_combined_name(req.first_name, req.last_name)
                        _fill_field(driver, cfg.first_name_xpath, combined)
                    else:
                        if req.first_name and cfg.first_name_xpath:
                            print(f"req.first_name : {req.first_name}")
                            _fill_field(driver, cfg.first_name_xpath, req.first_name)
                        if req.last_name and cfg.last_name_xpath:
                            print(f" req.last_name: { req.last_name}")
                            _fill_field(driver, cfg.last_name_xpath, req.last_name)
                    submit = find_element_in_iframes(driver, cfg.name_submit_button_xpath)

                    driver.execute_script("arguments[0].click();", submit)

                time.sleep(random.uniform(0.5, 3))
                break

            except Exception as e:
                traceback.print_exc()
                if attempt == 3:
                    logger.error("[%s] All 3 attempts failed to enter case number: %s", cfg.name, e)
                    raise
                time.sleep(1)
                continue
    def _open_driver(self) -> Driver:
        driver = Driver(
            browser="chrome",
            headless=False,
            uc=True,external_pdf=True
        )
        # Point the browser's download directory at our organised output folder
        driver.execute_cdp_cmd(
            "Page.setDownloadBehavior",
            {
                "behavior": "allow",
                "downloadPath": str(self.output_dir.resolve()),
            },
        )
        return driver

    def _download_one(self, driver: Driver, req: DeedRequest) -> DeedResult:
        with pysnooper.snoop(r"C:\Users\pc\PycharmProjects\Court-Scraper\_download_one.log"):
            cfg = self.config
            all_failed = []
            deed_types = [req.deed_type] if req.deed_type else cfg.deed_type_values or [None]
            extracted_data_list = []  # ✅ List to hold data for each row


            
            # If a specific deed_type is passed in the request, use only that.
            # Otherwise loop through all configured deed_type_values.
            if req.search_mode not in cfg.supported_search_modes:
                return DeedResult(
                    req, cfg.name, False,
                    error=f"{cfg.name} does not support {req.search_mode.value} search. "
                        f"Supported: {[m.value for m in cfg.supported_search_modes]}"
                )

            
            
            
            
            try:
                for deed_type in deed_types:
                    print(f"--- Processing deed type: {deed_type} ---")
                    req_result = self.request_url(driver, req, cfg)
                    if req_result:
                        return req_result

                    self.enter_case_number(driver, req, cfg, deed_type)

                    if cfg.navigate_to_table_func:
                        cfg.navigate_to_table_func(driver)



                    time.sleep(1)
                    if cfg.scroll_to_load_rows_func:
                            cfg.scroll_to_load_rows_func(driver)

                    rows = self._get_rows(driver)
                    
                    if rows is None:
                        for retry in range(2):
                            self.request_url(driver, req, cfg)
                            self.enter_case_number(driver, req, cfg, deed_type)
                            if cfg.navigate_to_table_func:
                                cfg.navigate_to_table_func(driver)
                            rows = self._get_rows(driver)
                            if rows:
                                break

                    if not rows:
                        print(f"No results for deed type: {deed_type}, skipping.")
                        continue
                    if (req.block or req.lot) and cfg.filter_rows_func:
                        cfg.filter_rows_func(driver, rows, req.block, req.lot)
                        rows = self._get_rows(driver)
                        logger.info("[%s] After block/lot filter: %d row(s) remaining", cfg.name, len(rows))
                        if not rows:
                            print(f"No rows passed block/lot filter, skipping.")
                            continue          
                    # Apply row limit if configured
                    if cfg.max_rows is not None:
                        rows = rows[:cfg.max_rows]
                        logger.info("[%s] Row limit applied: processing %d/%d row(s)", cfg.name, len(rows), len(rows))

                    logger.info("[%s] deed_type=%s — Found %d row(s)", cfg.name, deed_type, len(rows))

                    dm = DownloadManager(driver, self.output_dir)
                    print(f"len(rows) : {len(rows)}")
                    MAX_RETRIES = 3
                    for i, row in enumerate(rows):

                        try:
                            logger.info("[%s] Processing row %d/%d", cfg.name, i + 1, len(rows))

                            before = dm.get_existing_files()
                            
                            # ── End related documents ──────────────────────────────────────
                            if not element_exists_xpath(driver, cfg.deeds_table_xpath):
                                if cfg.return_to_table_func:
                                    cfg.return_to_table_func(driver,i)

                            if cfg.get_to_download_page_func:
                                trigger_result = cfg.get_to_download_page_func(driver, i)
                                trigger_result["file_name"] = f"{trigger_result.get("type")}_{datetime.now()}"

                                if isinstance(trigger_result, dict):
                                        extracted_data_list.append(trigger_result)
                            else:
                                if req.search_mode == SearchMode.NAME:
                                    last = (req.last_name or "").lower().replace(" ", "_")
                                    first = (req.first_name or "").lower().replace(" ", "_")
                                    new_name = f"name_{last}_{first}_row_{i + 1}"
                                extracted_data_list.append({"file_name" : new_name})
                            if cfg.validate_file_func: 
                                is_valid = cfg.validate_file_func(driver)
                                if not is_valid:
                                    logger.info("[%s] Row %d skipped — failed validation.", cfg.name, i + 1)
                                    if cfg.return_to_table_func:
                                        cfg.return_to_table_func(driver, i)
                                    continue

                            # ── Retry loop ───────────────────────────────────────────────
                            downloaded = False
                            last_error = None

                            for attempt in range(1, MAX_RETRIES + 1):
                                try:
                                    if attempt > 1:
                                        logger.info("[%s] Row %d — retry %d/%d", cfg.name, i + 1, attempt, MAX_RETRIES)

                                    # ✅ correct — check flag BEFORE calling the county function
                                    if req.download_file:
                                        set_download_dir(driver, self.output_dir)
                                        
                                        before = dm.get_existing_files()  # refresh snapshot before each retry
                                        if is_restricted_document(driver):
                                            downloaded = True
                                            break
                                        cfg.file_trigger_download_func(driver, i)
                                        started = dm.wait_for_download_start(before, timeout=10)
                                        if not started:
                                            last_error = "Download did not start."
                                            continue

                                        if started.endswith(".crdownload"):
                                            dm.wait_for_download_completion(started.replace(".crdownload", ""))

                                        final_file = dm.wait_for_file_detection(before, timeout=7)
                                        if not final_file:
                                            last_error = "File not detected after download."
                                            continue

                                        if req.search_mode == SearchMode.BOOK_PAGE:
                                            type_slug = deed_type.lower().replace(" ", "_") if deed_type else "any"
                                            new_name = f"book_{req.book}_page_{req.page}_{type_slug}_row_{i + 1}"
                                        elif req.search_mode == SearchMode.INSTRUMENT:
                                            new_name = f"instrument_{req.instrument}_row_{i + 1}"
                                        elif req.search_mode == SearchMode.NAME:
                                            last = (req.last_name or "").lower().replace(" ", "_")
                                            first = (req.first_name or "").lower().replace(" ", "_")
                                            new_name = f"name_{last}_{first}_row_{i + 1}"

                                        if dm.rename_file(new_name, new_file=final_file):
                                            last_error = "Rename failed."
                                            continue

                                    else:
                                        logger.info("[%s] Row %d — download skipped (download_file=False).", cfg.name, i + 1)

                                    downloaded = True
                                    break

                                except Exception as e:
                                    last_error = str(e)
                                    logger.warning("[%s] Row %d attempt %d failed: %s", cfg.name, i + 1, attempt, e)
                                    traceback.print_exc()
                            # ── End retry loop ───────────────────────────────────────────
                            if (downloaded and cfg.related_docs_table_xpath
                                    and cfg.related_docs_trigger_download_func):

                                try:
                                    # 1. Make the related docs table visible
                                    if cfg.related_docs_make_table_visible_func:
                                        cfg.related_docs_make_table_visible_func(driver)

                                    # 2. Get related doc rows
                                    related_table = find_element_in_iframes(driver, cfg.related_docs_table_xpath)
                                    related_rows = related_table.find_elements(
                                        By.XPATH, f"./{cfg.related_docs_row_tag_name}"
                                    ) if cfg.related_docs_row_tag_name else []

                                    if related_rows:
                                        # Create related_documents subfolder next to the main file
                                        related_dir = self.output_dir / f"book_{req.book}_page_{req.page}_row_{i+1}_related"
                                        related_dir.mkdir(parents=True, exist_ok=True)
                                        related_dm = DownloadManager(driver, related_dir)

                                        for j, row in enumerate(related_rows):
                                            try:
                                                before_related = related_dm.get_existing_files()
                                                cfg.related_docs_trigger_download_func(driver, row)

                                                started = related_dm.wait_for_download_start(before_related, timeout=10)
                                                if started and started.endswith(".crdownload"):
                                                    related_dm.wait_for_download_completion(started.replace(".crdownload", ""))

                                                final_related = related_dm.wait_for_file_detection(before_related, timeout=7)
                                                if final_related:
                                                    rel_name = f"book_{req.book}_page_{req.page}_row_{i+1}_related_{j+1}"
                                                    related_dm.rename_file(rel_name, new_file=final_related)
                                                    logger.info("[%s] Related doc %d/%d downloaded", cfg.name, j+1, len(related_rows))
                                                else:
                                                    logger.warning("[%s] Related doc %d/%d — file not detected", cfg.name, j+1, len(related_rows))

                                                if cfg.related_docs_return_to_table_func:
                                                    cfg.related_docs_return_to_table_func(driver, j)

                                            except Exception as e:
                                                logger.warning("[%s] Related doc %d failed: %s", cfg.name, j+1, e)
                                                if cfg.related_docs_return_to_table_func:
                                                    try:
                                                        cfg.related_docs_return_to_table_func(driver, j)
                                                    except Exception:
                                                        pass

                                except Exception as e:
                                    logger.warning("[%s] Row %d — related docs failed: %s", cfg.name, i+1, e)
                            if not downloaded:
                                logger.error("[%s] Row %d failed after %d attempts: %s", cfg.name, i + 1, MAX_RETRIES,
                                            last_error)
                                all_failed.append((deed_type, i, f"Failed after {MAX_RETRIES} attempts: {last_error}"))

                            if cfg.return_to_table_func:
                                cfg.return_to_table_func(driver, i)

                        except Exception as e:
                            logger.warning("[%s] deed_type=%s row %d failed: %s", cfg.name, deed_type, i + 1, e)
                            traceback.print_exc()
                            all_failed.append((deed_type, i, str(e)))
                            if cfg.return_to_table_func:
                                try:
                                    cfg.return_to_table_func(driver, i)
                                except Exception:
                                    pass

                if all_failed:
                    return DeedResult(req, cfg.name, False, error=f"{len(all_failed)} failures: {all_failed}", extracted_data=extracted_data_list)
                return DeedResult(req, cfg.name, True, extracted_data=extracted_data_list)

            except Exception as exc:
                logger.exception("[%s] Unexpected error for book=%s page=%s", cfg.name, req.book, req.page)
                return DeedResult(req, cfg.name, False, error=str(exc), extracted_data=extracted_data_list if 'extracted_data_list' in locals() else None)

    # ------------------------------------------------------------------
    # Form helpers
    # ------------------------------------------------------------------
    

    def _select_deed_type(self, driver: Driver, xpath: str, value: str) -> None:
        element = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        if element.tag_name.lower() == "select":
            from selenium.webdriver.support.ui import Select
            Select(element).select_by_visible_text(value)
        else:
            option = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, f"{xpath}//input[@value='{value}']"))
            )
            option.click()
    def _get_rows(self, driver: Driver) -> Optional[list]:
        """Returns list of rows, [] if genuinely empty, or None if timed out."""
        timeout = 10
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                #//*[@id="working"]/h3
                try:
                    working = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.XPATH, f'//*[@id="working"]/h3'))
                    ).text
                    if "please wait" in working.lower():
                        time.sleep(1)
                        continue
                except TimeoutException:
                    pass

                table = find_element_in_iframes(
                    driver,
                    self.config.deeds_table_xpath
                )

                rows = table.find_elements(
                    By.XPATH,
                    f"./{self.config.row_tag_name}"
                )
                print(f"self.config.deeds_table_xpath : {self.config.deeds_table_xpath}")
                print(f"self.config.row_tag_name : {self.config.row_tag_name}")
                print(f"rows : {rows}")
                print(f"lenarows : {rows}")
                if rows:
                    return rows

                # Table exists but has no rows — genuinely empty, not a timeout.
                return []

            except Exception:
                traceback.print_exc()
                time.sleep(1)

        print("⚠️ Timeout: rows were not found within 15 seconds.")
        return None

    # ------------------------------------------------------------------
    # Download management
    # ------------------------------------------------------------------
    def _wait_for_download(self, before: set[Path]) -> Optional[Path]:
        deadline = time.time() + self.config.download_timeout
        while time.time() < deadline:
            after = set(self.output_dir.iterdir())
            new_files = after - before
            completed = [
                f for f in new_files
                if not f.suffix.endswith(".crdownload")
                and not f.name.startswith(".")
            ]
            if completed:
                return completed[0]
            time.sleep(0.5)
        return None

    def _rename_download(self, src: Path, req: DeedRequest, index: int = 0) -> Path:
        dest = self.output_dir / f"book_{req.book}_page_{req.page}_row_{index + 1}{src.suffix}"
        counter = 1
        while dest.exists():
            dest = self.output_dir / f"book_{req.book}_page_{req.page}_row_{index + 1}_{counter}{src.suffix}"
            counter += 1
        shutil.move(str(src), str(dest))
        return dest
    