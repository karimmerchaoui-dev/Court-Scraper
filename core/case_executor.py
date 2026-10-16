"""
core/case_executor.py
=====================
Orchestrates batch case execution, eligibility pre-checks, parallel scraping,
and automated retries.

Architecture:
  - DriverPool lifecycle is decoupled into `create_driver_pool()`, allowing
    pools to be reused across runs or passed directly into `CaseExecutor`.
  - Case submission is simplified into two clear steps:
      1. `_process_cases`: orchestrates the worker pool, queue dispatch, result collection, and retries.
      2. `_submit_case`: prepares directories, acquires a driver, checks VPN, and dispatches to county processor.
  - Backward-compatible aliases are preserved so external callers and legacy scripts never break.
"""

from __future__ import annotations

import os
import time
import traceback
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, Callable, Dict, List, Optional, Tuple

import pysnooper
from supabase import create_client

from app import _settings, log_message, set_status_text, update_case_status
from browser.browser_helpers import safe_int, set_download_dir
from browser.driver_pool import DriverPool
from config import settings
from core.excel_helpers import save_batch_folder_to_excel
from database.supabase_service import rip_flag
from models import Case
from network.network_helpers import is_us_ip
from pipeline_tracker import PipelineTracker, set_current_tracker
from state import state
from utils.formatting import save_to_excel

MAX_DEFENDANTS = 10


def init_case(report_cases: Dict[str, Any], case_id: str, case_info: Dict[str, Any]) -> None:
    """Initialize an empty case report record."""
    case = OrderedDict()

    # Base fields
    case['Case number'] = case_id.replace('\n', '')
    case['County'] = case_info.get('county', '')
    case['court_address'] = ''
    case['case_type'] = ''
    case['court_case_status'] = ''
    case['processing_duration'] = ''
    case['status'] = ''
    case['total_final_judgment_amount'] = ''
    case['files'] = []

    # Property fields
    case['address'] = ''
    case['sales_web_address'] = ''
    case['found'] = ''
    case['Upset Price'] = ''
    case['Upset Amount'] = ''
    case['Approx. Judgment'] = ''
    case['Approx. Upset'] = ''
    case['Equity'] = ''
    case['zestimate'] = ''
    case['zillow_status'] = ''
    case['home_type'] = ''
    case['main_defendant'] = ''

    # Defendant columns
    for i in range(1, MAX_DEFENDANTS + 1):
        case[f"name_{i}"] = ''
        case[f"description_{i}"] = ''

    report_cases[case_id] = case


def create_driver_pool(
    max_workers: int = 4,
    *,
    case_queue=None,
    headless_mode: Optional[bool] = None,
    get_force_stop: Optional[Callable[[], bool]] = None,
    get_max_workers: Optional[Callable[[], int]] = None,
    setup_driver_func: Optional[Callable[..., Any]] = None,
    attach_web_monitor_func: Optional[Callable[[Any], None]] = None,
    append_driver_log_func: Optional[Callable[..., None]] = None,
    reset_vpn_func: Optional[Callable[..., None]] = None,
    element_exists_id_func: Optional[Callable[..., bool]] = None,
    element_exists_xpath_func: Optional[Callable[..., bool]] = None,
    refresh_url_func: Optional[Callable[..., None]] = None,
    check_js_popup_func: Optional[Callable[..., bool]] = None,
    request_url_func: Optional[Callable[..., None]] = None,
    delete_driver_func: Optional[Callable[[Any], None]] = None,
    nj_login_page: Optional[str] = None,
) -> DriverPool:
    """
    Factory function to initialize a DriverPool with sensible defaults.
    Decouples DriverPool instantiation from CaseExecutor so the pool can be
    managed independently.
    """
    import main

    resolved_headless = headless_mode if headless_mode is not None else getattr(state, 'headless_mode', False)

    return DriverPool(
        max_workers,
        setup_driver_func=setup_driver_func or main.setup_driver,
        attach_web_monitor_func=attach_web_monitor_func or main.attach_web_monitor,
        append_driver_log_func=append_driver_log_func or main.append_driver_log,
        reset_vpn_func=reset_vpn_func or main.reset_vpn,
        element_exists_id_func=element_exists_id_func or main.element_exists_id,
        element_exists_xpath_func=element_exists_xpath_func or main.element_exists_xpath,
        refresh_url_func=refresh_url_func or main.refresh_url,
        check_js_popup_func=check_js_popup_func or main.check_js_popup,
        request_url_func=request_url_func or main.request_url,
        delete_driver_func=delete_driver_func or main.delete_driver,
        case_queue=case_queue if case_queue is not None else (getattr(state, 'case_queue', None) or main.case_queue),
        headless_mode=resolved_headless,
        get_force_stop=get_force_stop or (lambda: state.force_stop),
        get_max_workers=get_max_workers or (lambda: max_workers),
        nj_login_page=nj_login_page or main.NJ_LOGIN_PAGE,
    )


class CaseExecutor:
    """
    Manages the lifecycle of a batch processing run:
    1. Prepares environment, keyword filters, and output batch directories.
    2. Runs concurrent eligibility checks (Zillow + Salesweb) for NJ cases.
    3. Streams eligible cases to worker threads for county scraping.
    4. Automatically collects results and executes retries for failed cases.
    5. Produces final Excel reports and notifies UI via WebSockets.
    """

    def __init__(
        self,
        *,
        driver_pool: Optional[DriverPool] = None,
        # ── State Accessors (default to state.py / main.py) ──────────────────
        get_running: Optional[Callable[[], bool]] = None,
        set_running: Optional[Callable[[bool], None]] = None,
        get_force_stop: Optional[Callable[[], bool]] = None,
        get_driver_pool: Optional[Callable[[], Any]] = None,
        set_driver_pool: Optional[Callable[[Any], None]] = None,
        get_current_batch_folder: Optional[Callable[[], Optional[str]]] = None,
        set_current_batch_folder: Optional[Callable[[str], None]] = None,
        get_report_cases: Optional[Callable[[], Dict[str, Any]]] = None,
        set_keyword_list: Optional[Callable[[List[str]], None]] = None,
        set_unwanted_list: Optional[Callable[[List[str]], None]] = None,
        set_total_cases: Optional[Callable[[int], None]] = None,
        set_active_threads: Optional[Callable[[List[Any]], None]] = None,
        get_case_queue: Optional[Callable[[], Any]] = None,
        get_max_workers_var: Optional[Callable[[], int]] = None,
        get_headless_mode: Optional[Callable[[], bool]] = None,
        get_keywords: Optional[Callable[[], str]] = None,
        get_unwanted_keywords: Optional[Callable[[], str]] = None,
        get_output_folder: Optional[Callable[[], str]] = None,
        get_input_file: Optional[Callable[[], str]] = None,
        get_driver_monitor: Optional[Callable[[], Any]] = None,
        set_driver_monitor_pool: Optional[Callable[[Any], None]] = None,
        # ── Functional Dependencies ──────────────────────────────────────────
        is_us_ip_func: Optional[Callable[[], bool]] = None,
        log_message_func: Optional[Callable[[str], None]] = None,
        set_status_text_func: Optional[Callable[[str], None]] = None,
        set_download_dir_func: Optional[Callable[..., None]] = None,
        save_to_excel_func: Optional[Callable[..., None]] = None,
        save_batch_folder_to_excel_func: Optional[Callable[..., None]] = None,
        get_shuffled_main_accounts_func: Optional[Callable[[], List[Any]]] = None,
        get_county_processor_func: Optional[Callable[[str], Any]] = None,
        emit_report_func: Optional[Callable[[Any], None]] = None,
        socketio_emit_func: Optional[Callable[..., None]] = None,
        # ── DriverPool Setup Dependencies (optional passthrough) ─────────────
        setup_driver_func: Optional[Callable[..., Any]] = None,
        attach_web_monitor_func: Optional[Callable[[Any], None]] = None,
        append_driver_log_func: Optional[Callable[..., None]] = None,
        reset_vpn_func: Optional[Callable[..., None]] = None,
        element_exists_id_func: Optional[Callable[..., bool]] = None,
        element_exists_xpath_func: Optional[Callable[..., bool]] = None,
        refresh_url_func: Optional[Callable[..., None]] = None,
        check_js_popup_func: Optional[Callable[..., bool]] = None,
        request_url_func: Optional[Callable[..., None]] = None,
        delete_driver_func: Optional[Callable[[Any], None]] = None,
        nj_login_page: Optional[str] = None,
        # ── Constants & Helpers ──────────────────────────────────────────────
        default_keywords: Optional[List[str]] = None,
        default_unwanted: Optional[List[str]] = None,
        StopRequested: Optional[type] = None,
        record_rip_case_func: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        import main

        # State accessors
        self._get_running = get_running or (lambda: state.running)
        self._set_running = set_running or (lambda v: setattr(state, 'running', v))
        self._get_force_stop = get_force_stop or (lambda: state.force_stop)
        self._get_driver_pool = get_driver_pool or (lambda: state.driver_pool)
        self._set_driver_pool = set_driver_pool or (lambda v: setattr(state, 'driver_pool', v))
        self._get_current_batch_folder = get_current_batch_folder or (lambda: state.current_batch_folder)
        self._set_current_batch_folder = set_current_batch_folder or (lambda v: setattr(state, 'current_batch_folder', v))
        self._get_report_cases = get_report_cases or (lambda: state.report_cases)
        self._set_keyword_list = set_keyword_list or (lambda v: setattr(state, 'keyword_list', v))
        self._set_unwanted_list = set_unwanted_list or (lambda v: setattr(state, 'unwanted_list', v))
        self._set_total_cases = set_total_cases or (lambda v: setattr(state, 'total_cases', v))
        self._set_active_threads = set_active_threads or (lambda v: setattr(state, 'active_threads', v))
        self._get_case_queue = get_case_queue or (lambda: getattr(state, 'case_queue', None) or main.case_queue)
        self._get_max_workers_var = get_max_workers_var or (lambda: getattr(main, 'max_workers_var', None) and main.max_workers_var.get() or 4)
        self._get_headless_mode = get_headless_mode or (
            lambda: (
                main.headless_mode.get() if getattr(main, 'headless_mode', None) and hasattr(main.headless_mode, 'get')
                else getattr(state, 'headless_mode', False)
            )
        )
        self._get_keywords = get_keywords or (lambda: getattr(main, 'keywords', None) and main.keywords.get() or "")
        self._get_unwanted_keywords = get_unwanted_keywords or (lambda: getattr(main, 'unwanted_keywords', None) and main.unwanted_keywords.get() or "")
        self._get_output_folder = get_output_folder or (lambda: getattr(main, 'output_folder', None) and main.output_folder.get() or ".")
        self._get_input_file = get_input_file or (lambda: getattr(main, 'input_file', None) and main.input_file.get() or "")
        self._get_driver_monitor = get_driver_monitor or (lambda: getattr(state, 'driver_monitor', None))
        self._set_driver_monitor_pool = set_driver_monitor_pool or (lambda v: setattr(state.driver_monitor, 'driver_pool', v) if getattr(state, 'driver_monitor', None) else None)

        # Helpers
        self._is_us_ip = is_us_ip_func or is_us_ip
        self._log_message = log_message_func or log_message
        self._set_status_text = set_status_text_func or set_status_text
        self._set_download_dir = set_download_dir_func or set_download_dir
        self._save_to_excel = save_to_excel_func or save_to_excel
        self._save_batch_folder_to_excel = save_batch_folder_to_excel_func or save_batch_folder_to_excel
        self._get_shuffled_main_accounts = get_shuffled_main_accounts_func or main._get_shuffled_main_accounts
        self._get_county_processor = get_county_processor_func or main._get_county_processor
        self._emit_report = emit_report_func or main._safe_emit_report
        self._socketio_emit = socketio_emit_func or (getattr(main, '_socketio', None) and main._socketio.emit or (lambda *a, **k: None))

        # DriverPool factory dependencies (stored for lazy pool initialization)
        self._setup_driver = setup_driver_func
        self._attach_web_monitor = attach_web_monitor_func
        self._append_driver_log = append_driver_log_func
        self._reset_vpn = reset_vpn_func
        self._element_exists_id = element_exists_id_func
        self._element_exists_xpath = element_exists_xpath_func
        self._refresh_url = refresh_url_func
        self._check_js_popup = check_js_popup_func
        self._request_url = request_url_func
        self._delete_driver = delete_driver_func
        self._nj_login_page = nj_login_page

        # Constants
        self._default_keywords = default_keywords or getattr(main, 'DEFAULT_KEYWORDS', [])
        self._default_unwanted = default_unwanted or getattr(main, 'DEFAULT_UNWANTED', [])
        self._StopRequested = StopRequested or getattr(main, 'StopRequested', Exception)
        self.record_rip_case_func = record_rip_case_func or getattr(main, '_record_rip_case', lambda: None)

        # Injected or existing driver pool
        self.driver_pool: Optional[DriverPool] = driver_pool or self._get_driver_pool()

    # ══════════════════════════════════════════════════════════════════════
    # DRIVER POOL ACCESS
    # ══════════════════════════════════════════════════════════════════════

    def _get_or_create_driver_pool(self, max_workers: int) -> DriverPool:
        """
        Reuses the active DriverPool if healthy; otherwise creates a new one
        via the standalone factory.
        """
        desired_headless = bool(self._get_headless_mode())
        existing = self.driver_pool or self._get_driver_pool()

        if (
            existing is not None
            and getattr(existing, "max_workers", 0) == max_workers
            and getattr(existing, "_headless_mode", None) == desired_headless
            and not existing.stop_requested.is_set()
        ):
            self.driver_pool = existing
            return existing

        # If existing pool has mismatched headless mode, gracefully stop and close its old drivers
        if existing is not None and getattr(existing, "_headless_mode", None) != desired_headless:
            self._log_message(f"[POOL] Recreating driver pool (headless_mode changed to {desired_headless})")
            try:
                existing.request_stop()
                for d in getattr(existing, "available", []) + getattr(existing, "in_use", []):
                    try:
                        d.quit()
                    except Exception:
                        pass
            except Exception:
                pass

        driver_pool = create_driver_pool(
            max_workers,
            case_queue=self._get_case_queue(),
            headless_mode=desired_headless,
            get_force_stop=self._get_force_stop,
            get_max_workers=self._get_max_workers_var,
            setup_driver_func=self._setup_driver,
            attach_web_monitor_func=self._attach_web_monitor,
            append_driver_log_func=self._append_driver_log,
            reset_vpn_func=self._reset_vpn,
            element_exists_id_func=self._element_exists_id,
            element_exists_xpath_func=self._element_exists_xpath,
            refresh_url_func=self._refresh_url,
            check_js_popup_func=self._check_js_popup,
            request_url_func=self._request_url,
            delete_driver_func=self._delete_driver,
            nj_login_page=self._nj_login_page,
        )
        self.driver_pool = driver_pool
        self._set_driver_pool(driver_pool)
        dm = self._get_driver_monitor()
        if dm is not None:
            self._set_driver_monitor_pool(driver_pool)
        return driver_pool

    # ══════════════════════════════════════════════════════════════════════
    # TOP-LEVEL RUN ENTRY POINT
    # ══════════════════════════════════════════════════════════════════════

    def run(self) -> None:
        """Top-level batch execution entry point."""
        if self._get_case_queue().empty():
            self._log_message("⚠️ No cases in queue — nothing to process.")
            try:
                import app as _app
                _app.running = False
            except Exception:
                pass
            return

        if not hasattr(self, "_run_counter"):
            self._run_counter = 0
        self._run_counter += 1
        log_dir = "."
        os.makedirs(log_dir, exist_ok=True)
        _snoop_log = os.path.join(log_dir, f"snoop_case_executor_run_{self._run_counter}.log")

        with pysnooper.snoop(_snoop_log):
            final_output_folder = None
            try:
                self._setup_processing_environment()
                final_output_folder = self._get_or_create_batch_folder()
                max_workers = max(1, min(8, self._get_max_workers_var()))
                self._get_or_create_driver_pool(max_workers)

                case_processing_times = self._process_cases(max_workers, final_output_folder)
                self._print_processing_summary(case_processing_times)
                self._finalize_processing(final_output_folder)
            except Exception as e:
                if not self._get_force_stop():
                    self._log_message(f"Error during processing: {str(e)}")
                    traceback.print_exc()
            finally:
                self._cleanup_and_save_report(final_output_folder)

    # ══════════════════════════════════════════════════════════════════════
    # ENVIRONMENT & FOLDER HELPERS
    # ══════════════════════════════════════════════════════════════════════

    def _setup_processing_environment(self) -> None:
        self._set_running(True)
        self._set_active_threads([])
        kw_text = self._get_keywords().strip()
        unwanted_text = self._get_unwanted_keywords().strip()
        keyword_list = (
            [k.strip().lower() for k in kw_text.split(",")]
            if kw_text
            else self._default_keywords
        )
        unwanted_list = (
            [k.strip().lower() for k in unwanted_text.split(",")]
            if unwanted_text
            else self._default_unwanted
        )
        self._set_keyword_list(keyword_list)
        self._set_unwanted_list(unwanted_list)
        self._log_message(f"Using keywords: {', '.join(keyword_list)}")
        self._log_message(f"Excluding files with: {', '.join(unwanted_list)}")
        total_cases = self._get_case_queue().qsize()
        self._set_total_cases(total_cases)
        self._log_message(f"Found {total_cases} cases to process")

    def _has_rip_data(self, address: str, processor_name: str) -> bool:
        return bool(address and processor_name)

    def _get_or_create_batch_folder(self) -> str:
        current = self._get_current_batch_folder()
        if current and os.path.exists(current):
            self._log_message(f"📁 Using existing batch folder: {current}")
            return current
        batch_timestamp = int(time.time())
        base_dir = (self._get_output_folder() or "").strip() or "output"
        final_output_folder = os.path.abspath(
            os.path.join(base_dir, f"Batch_{batch_timestamp}")
        )
        os.makedirs(final_output_folder, exist_ok=True)
        self._log_message(f"📁 Batch folder created: {final_output_folder}")
        self._set_current_batch_folder(final_output_folder)
        input_f = self._get_input_file()
        if input_f:
            self._save_batch_folder_to_excel(input_f, final_output_folder)
        return final_output_folder

    # ══════════════════════════════════════════════════════════════════════
    # CORE BATCH EXECUTION PIPELINE
    # ══════════════════════════════════════════════════════════════════════

    def _process_cases(self, max_workers: int, final_output_folder: str) -> Dict[str, float]:
        """
        Main batch execution pipeline:
        1. Launches worker ThreadPoolExecutor.
        2. Drains case_queue, running eligibility prechecks concurrently for NJ cases.
        3. Streams eligible cases to scraping workers via `_submit_case`.
        4. Collects results and times.
        5. Automatically retries any failed cases.
        """
        main_accounts = self._get_shuffled_main_accounts()
        driver_pool = self._get_or_create_driver_pool(max_workers)

        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="Scraper") as executor:
            futures: Dict[Any, Tuple[Any, ...]] = {}
            self._dispatch_case_queue(
                executor=executor,
                driver_pool=driver_pool,
                main_accounts=main_accounts,
                futures=futures,
                final_output_folder=final_output_folder,
                max_workers=max_workers,
            )
            case_processing_times, failed_cases = self._collect_case_results(futures)

            if self._get_running() and failed_cases:
                self._retry_failed_cases(executor, main_accounts, final_output_folder, failed_cases)

        return case_processing_times

    def _dispatch_case_queue(
        self,
        executor: ThreadPoolExecutor,
        driver_pool: DriverPool,
        main_accounts: List[Any],
        futures: Dict[Any, Tuple[Any, ...]],
        final_output_folder: str,
        max_workers: int = 1,
    ) -> Dict[Any, Tuple[Any, ...]]:
        """
        Drains `case_queue`. Submits prechecks concurrently for NJ cases,
        streaming passed cases to `_submit_case`. Direct cases submit immediately.
        """
        case_queue = self._get_case_queue()
        report_cases = self._get_report_cases()
        precheck_futures: Dict[Any, Tuple[str, ...]] = {}
        eligibility_executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="Eligibility")

        # 1. Drain the queue, kicking off eligibility checks or direct submissions
        while not case_queue.empty() and self._get_running():
            if self._get_force_stop():
                break

            item = case_queue.get()
            if len(item) >= 6:
                year, docket, court_type, processor_name, address, county = item[:6]
            else:
                year, docket, court_type, processor_name = item[:4]
                address = item[4] if len(item) > 4 else ""
                county = ""

            processor_name_lower = processor_name.lower().strip()
            is_nj = "jersey" in processor_name_lower or processor_name_lower == "nj"

            case_obj = Case(
                year=year, case_number=docket, county=processor_name,
                case_type=court_type, county_name=county
            )
            case_id = case_obj.id

            init_case(report_cases, case_id, {'county': processor_name_lower})
            report_cases[case_id]['address'] = address
            report_cases[case_id]['county'] = county

            if address and processor_name:
                self._log_message(f"🔍 Queuing eligibility check for {case_id} ({address})...")
                report_cases[case_id]['status'] = 'Checking Eligibility'
                update_case_status(
                    None, case_id, processor_name, "Checking Eligibility",
                    details=f"Running RIP check for {address}"
                )

                pf = eligibility_executor.submit(
                    self._check_eligibility,
                    case_id, address, processor_name, county, final_output_folder, report_cases
                )
                precheck_futures[pf] = (year, docket, court_type, processor_name, county, address, case_id)
            else:
                report_cases[case_id]['status'] = 'Pending'
                update_case_status(None, case_id, processor_name, "Pending", details="Waiting to process")
                self._submit_case(
                    executor=executor,
                    driver_pool=driver_pool,
                    main_accounts=main_accounts,
                    futures=futures,
                    year=year,
                    docket=docket,
                    court_type=court_type,
                    processor_name=processor_name,
                    county=county,
                    final_output_folder=final_output_folder,
                )
            case_queue.task_done()

        # 2. As each precheck completes, stream eligible cases immediately to scraping
        for pf in as_completed(precheck_futures):
            if self._get_force_stop():
                break
            year, docket, court_type, processor_name, county, address, case_id = precheck_futures[pf]
            try:
                eligible, precheck_data = pf.result()
            except Exception:
                traceback.print_exc()
                eligible, precheck_data = True, {}

            if not eligible:
                self._handle_ineligible_case(case_id, address, processor_name, precheck_data)
                continue

            precheck_data['county'] = processor_name.lower().strip()
            if county:
                precheck_data['salesweb_county'] = county

            self._handle_eligible_case(case_id, address, precheck_data)
            self._submit_case(
                executor=executor,
                driver_pool=driver_pool,
                main_accounts=main_accounts,
                futures=futures,
                year=year,
                docket=docket,
                court_type=court_type,
                processor_name=processor_name,
                county=county,
                final_output_folder=final_output_folder,
            )

        eligibility_executor.shutdown(wait=False)
        return futures

    def _submit_case(
        self,
        executor: ThreadPoolExecutor,
        driver_pool: DriverPool,
        main_accounts: List[Any],
        futures: Dict[Any, Tuple[Any, ...]],
        year: str,
        docket: str,
        court_type: str,
        processor_name: str,
        county: str,
        final_output_folder: str,
    ) -> Optional[Any]:
        """
        Unified single-case submission:
        Grabs an account & driver, checks VPN, prepares directories,
        submits to county processor, and registers the future.
        """
        if self._get_force_stop():
            self._log_message(f"⏹️ [{docket}] Skipped — force stop active")
            return None

        account = main_accounts[len(futures) % len(main_accounts)] if main_accounts else {}
        self._log_message(f"⏳ [{docket}] Requesting browser driver from pool...")
        driver = driver_pool.get_driver()
        if not driver:
            self._log_message(f"⏹️ [{docket}] Unable to acquire driver (force stop or pool closed) — skipping")
            return None

        try:
            self._log_message(f"▶️ [{docket}] Driver acquired ({id(driver)}). Preparing case files...")
            if not self._is_us_ip():
                driver_pool.reset_vpn_pool(driver)

            case_obj = Case(
                year=year, case_number=docket, county=processor_name,
                case_type=court_type, county_name=county
            )
            case_id = case_obj.id
            file_dir = case_obj.get_file_dir(final_output_folder)

            report_cases = self._get_report_cases()
            if case_id not in report_cases:
                init_case(report_cases, case_id, {'county': processor_name.lower().strip()})

            processor = self._get_county_processor(case_obj.county.lower())
            if not processor:
                driver_pool.release_driver(driver)
                self._log_message(f"❌ [{case_id}] Unknown processor '{processor_name}' — skipping")
                return None

            try:
                from config.sentry_config import set_sentry_case_context
                set_sentry_case_context(case_id=case_id, county=case_obj.county, stage="court_scraping")
            except Exception:
                pass

            processor_name_lower = case_obj.county.lower()
            if "jersey" in processor_name_lower or processor_name_lower == "nj":
                self._set_download_dir(driver, file_dir.strip())
                driver.files_dir = file_dir.strip()
                future = processor(
                    executor, case_obj.year, case_obj.case_number,
                    case_obj.case_type, driver, driver_pool, account, file_dir.strip()
                )
            else:
                future = processor(
                    executor, case_obj.year, case_obj.case_number,
                    case_obj.case_type, driver, driver_pool, file_dir.strip()
                )

            if future:
                futures[future] = (year, docket, processor_name, time.time())
                self._log_message(f"🚀 [{docket}] Case successfully submitted to worker pool")
            return future

        except self._StopRequested:
            try:
                driver_pool.release_driver(driver)
            except Exception:
                pass
            self._log_message(f"⏹️ Stop requested, aborting {docket}")
            return None
        except Exception as e:
            try:
                driver_pool.release_driver(driver)
            except Exception:
                pass
            traceback.print_exc()
            self._log_message(f"❌ [{docket}] Exception submitting case: {e}")
            return None


    # ══════════════════════════════════════════════════════════════════════
    # ELIGIBILITY / PRE-CHECK
    # ══════════════════════════════════════════════════════════════════════
    def _check_eligibility(
        self,
        case_id: str,
        address: str,
        processor_name: str,
        county: str,
        final_output_folder: str,
        report_case: Dict[str, Any],
    ) -> Tuple[bool, Dict[str, Any]]:
        """Run Zillow and Salesweb checks to decide if the case is worth processing."""
        precheck_data: Dict[str, Any] = {}
        url = settings.supabase_url
        key = settings.supabase_key
        batch_name = settings.batch_name or _settings.get("batch_name")
        supabase = create_client(url, key)
        tracker = PipelineTracker(supabase_client=supabase, case_number=case_id, batch_name=batch_name)
        tracker.start_run()
        set_current_tracker(tracker)

        if not address or not processor_name:
            self._log_message(f"ℹ️ Skipping eligibility check for {case_id} - missing address or processor")
            return True, precheck_data

        try:
            from browser.OP import extract_info_from_salesweb
            from utils.calls_helpers import _fetch_zillow

            files_dir = final_output_folder or "."
            os.makedirs(files_dir, exist_ok=True)

            processor_name_lower = processor_name.lower().strip()
            is_nj = "jersey" in processor_name_lower or processor_name_lower == "nj"

            if is_nj:
                if "nj" not in address.lower() and "jersey" not in address.lower():
                    address = f"{address}, NJ"
            else:
                if "fl" not in address.lower() and "florida" not in address.lower():
                    address = f"{address}, FL"

            # ── Zillow ──────────────────────────────────────────────────────
            zest, status, home_type, city, prop_type, is_agent, is_auction = _fetch_zillow(address, files_dir)
            print(f"zillow info : {zest, status, home_type, city, prop_type, is_agent, is_auction }")
            precheck_data['zestimate'] = zest
            precheck_data['zillow_status'] = "AUCTION" if is_auction else status
            precheck_data['home_type'] = home_type

            # ── Salesweb (NJ only) ──────────────────────────────────────────
            if is_nj:
                print(f"📍 SalesWeb County: {county} | Address: {address}")
                try:
                    clean_county = county.split("County")[0].strip() if county else ""
                    sw = extract_info_from_salesweb(address, clean_county, 'NJ')
                    if sw:
                        price = safe_int(sw.get('Upset Price'))
                        amount = safe_int(sw.get('Upset Amount'))
                        judgment = safe_int(sw.get('Approx. Judgment'))
                        upset = safe_int(sw.get('Approx. Upset'))
                        financial_obligations = sw.get("financial_obligations") or []

                        unpaid_amount_values = [
                            safe_int(obligation.get('amount'))
                            for obligation in financial_obligations
                            if isinstance(obligation, dict) and obligation.get('category') == 'unpaid_amount'
                        ]
                        valid_unpaid_amounts = [x for x in unpaid_amount_values if x is not None]
                        max_unpaid = max(valid_unpaid_amounts) if valid_unpaid_amounts else None

                        candidates = [x for x in [price, amount, judgment, upset, max_unpaid] if x is not None]
                        unpaid_balance = max(candidates) if candidates else None

                        precheck_data['salesweb'] = sw
                        precheck_data['unpaid_balance'] = unpaid_balance
                except Exception as e:
                    print(f"⚠️ Salesweb extraction error: {e}")

            # ── Decision Logic ─────────────────────────────────────────────
            if precheck_data.get('zillow_status') == "FOR_SALE":
                reason = f"Zillow Status: {status}"
                rip_flag(case_id, reason=reason, batch_name=batch_name, address=address, county=county or processor_name)
                if callable(self.record_rip_case_func):
                    self.record_rip_case_func()
                update_case_status(None, case_id, processor_name, "RIP", details=reason)
                return False, precheck_data

            return True, precheck_data

        except Exception as e:
            print(f"⚠️ Eligibility check error: {e}")
            traceback.print_exc()
            return True, precheck_data

    def _handle_ineligible_case(
        self, case_id: str, address: str, processor_name: str, precheck_data: Dict[str, Any]
    ) -> None:
        self._log_message(f"⏭️ Skipping {case_id} — ineligible")
        report_cases = self._get_report_cases()
        report_cases[case_id]['status'] = 'Ineligible'
        report_cases[case_id]['address'] = address
        update_case_status(None, case_id, processor_name, "Ineligible", details="Ineligible")
        sw = precheck_data.get('salesweb', {})
        for key in ['found', 'Upset Price', 'Upset Amount', 'Approx. Judgment', 'Approx. Upset']:
            report_cases[case_id][key] = sw.get(key, '')
        if precheck_data.get('zillow_status'):
            report_cases[case_id]['zillow_status'] = precheck_data['zillow_status']
        if precheck_data.get('home_type'):
            report_cases[case_id]['home_type'] = precheck_data['home_type']

    def _handle_eligible_case(
        self, case_id: str, address: str, precheck_data: Dict[str, Any]
    ) -> None:
        from counties.nj_helpers import set_precheck_data

        self._log_message(f"✅ {case_id} passed eligibility check")
        report_cases = self._get_report_cases()
        report_cases[case_id]['address'] = address
        set_precheck_data(case_id, precheck_data)
        if precheck_data.get('zestimate'):
            report_cases[case_id]['zestimate'] = precheck_data['zestimate']
        if precheck_data.get('zillow_status'):
            report_cases[case_id]['zillow_status'] = precheck_data['zillow_status']
        if precheck_data.get('home_type'):
            report_cases[case_id]['home_type'] = precheck_data['home_type']
        sw = precheck_data.get('salesweb', {})
        for key in ['found', 'Upset Price', 'Upset Amount', 'Approx. Judgment', 'Approx. Upset', 'unpaid_balance']:
            report_cases[case_id][key] = sw.get(key, '')

    # ══════════════════════════════════════════════════════════════════════
    # RESULT COLLECTION & RETRIES
    # ══════════════════════════════════════════════════════════════════════

    def _collect_case_results(
        self, futures: Dict[Any, Tuple[Any, ...]]
    ) -> Tuple[Dict[str, float], List[Tuple[str, str, str]]]:
        case_processing_times: Dict[str, float] = {}
        failed_cases: List[Tuple[str, str, str]] = []

        for future in as_completed(futures):
            if self._get_force_stop():
                break
            year, docket, processor_name, start_time = futures[future]
            case_id = f"f-{docket}-{year}" if year else docket
            try:
                future.result()
                processing_time = time.time() - start_time
                case_processing_times[case_id] = processing_time
                self._log_message(f"✅ {case_id} ({processor_name}) processed in {processing_time:.2f}s")
            except (TimeoutError, FuturesTimeoutError) as e:
                traceback.print_exc()
                processing_time = time.time() - start_time
                case_processing_times[case_id] = processing_time
                self._log_message(f"⏰ Timeout processing {case_id} ({processor_name}) after {processing_time:.2f}s: {e}")
                failed_cases.append((year, docket, processor_name))
            except Exception as e:
                traceback.print_exc()
                processing_time = time.time() - start_time
                case_processing_times[case_id] = processing_time
                self._log_message(f"❌ Error processing {case_id} ({processor_name}) after {processing_time:.2f}s: {e}")
                failed_cases.append((year, docket, processor_name))

        return case_processing_times, failed_cases

    def _retry_failed_cases(
        self,
        executor: ThreadPoolExecutor,
        main_accounts: List[Any],
        final_output_folder: str,
        failed_cases: List[Tuple[str, str, str]],
    ) -> None:
        self._log_message(f"🔄 Retrying {len(failed_cases)} failed cases...")
        driver_pool = self.driver_pool or self._get_driver_pool()
        retry_futures: Dict[Any, Tuple[Any, ...]] = {}

        for year, docket, processor_name in failed_cases:
            if not self._get_running():
                break
            account = main_accounts[len(retry_futures) % len(main_accounts)] if main_accounts else {}
            driver = driver_pool.get_driver()
            processor_name_lower = processor_name.lower()
            if "jersey" in processor_name_lower:
                file_dir = f"{final_output_folder}--retry/f-{docket}-{year}"
            else:
                file_dir = f"{final_output_folder}--retry/{docket}"
            os.makedirs(file_dir, exist_ok=True)
            self._set_download_dir(driver, file_dir)
            processor = self._get_county_processor(processor_name_lower)
            if processor:
                future = processor(executor, year, docket, None, driver, driver_pool, account, file_dir)
                if future:
                    retry_futures[future] = (year, docket, processor_name, time.time())

        for future in as_completed(retry_futures):
            if not self._get_running():
                break
            year, docket, processor_name = retry_futures[future][:3]
            case_id = f"f-{docket}-{year}" if year else docket
            try:
                future.result()
                self._log_message(f"✅ Retry successful: {case_id}")
            except Exception as e:
                self._log_message(f"❌ Retry failed: {case_id} - {e}")

    # ══════════════════════════════════════════════════════════════════════
    # FINALIZATION & CLEANUP
    # ══════════════════════════════════════════════════════════════════════

    def _print_processing_summary(self, case_processing_times: Dict[str, float]) -> None:
        if not case_processing_times:
            return
        self._log_message("\n=== Processing Time Summary ===")
        total_time = sum(case_processing_times.values())
        avg_time = total_time / len(case_processing_times)
        self._log_message(f"Total cases processed: {len(case_processing_times)}")
        self._log_message(f"Total processing time: {total_time:.2f}s ({total_time / 60:.1f}m)")
        self._log_message(f"Average time per case: {avg_time:.2f}s")
        self._log_message(f"Fastest case: {min(case_processing_times.values()):.2f}s")
        self._log_message(f"Slowest case: {max(case_processing_times.values()):.2f}s")

    def _finalize_processing(self, final_output_folder: str) -> None:
        if self._get_running():
            self._log_message("✅ Processing completed!")
            self._set_status_text("Completed")
        else:
            self._log_message("⚠️ Processing stopped by user")
            self._set_status_text("Stopped")

    def _cleanup_and_save_report(self, final_output_folder: str) -> None:
        self._set_active_threads([])
        self._set_running(False)
        report_cases = self._get_report_cases()
        if final_output_folder:
            self._save_to_excel(report_cases, final_output_folder)
            self._log_message(f"📊 Excel report saved to: {final_output_folder}")
        try:
            self._emit_report(report_cases)
        except Exception:
            try:
                self._socketio_emit("processing_state", {"running": False, "report": report_cases})
            except Exception:
                pass