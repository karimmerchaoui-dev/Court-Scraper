"""
==============================================================================
Court Scraper — Enterprise Scraping & Case Processing Engine
==============================================================================

Overview:
---------
This module serves as the primary orchestration engine and application entry
point for the Court Scraper system. It coordinates multi-county court record
retrieval, document download workflows, AI/LLM document parsing, and database
synchronization across several distinct jurisdiction pipelines.

Architecture & Pipelines:
-------------------------
1. Web GUI & API Server Layer:
   - Built on Flask and Flask-SocketIO (see app.py).
   - Provides real-time bidirectional communication for case monitoring, live
     screenshots, thread-level logging, and queue control.
   - Entry point: `python main.py` starts the SocketIO WSGI server.

2. Concurrency & Resource Pooling:
   - Browser Automation: Managed via `DriverPool`, pooling headless/headed
     Selenium Chrome instances with realistic cursor simulation (WebCursor/HumanCursor).
   - Execution Model: Multi-threaded task execution using `ThreadPoolExecutor`
     managed by `core.case_executor.CaseExecutor`.
   - Thread Synchronization: Custom decorators, thread-local storage, and
     sentinel signals coordinate work without race conditions.

3. Core Pipelines:
   - New Jersey Pipeline: 8-stage modular pipeline orchestrator (`PipelineOrchestrator`)
     covering Precheck (Zillow/SalesWeb), Portal Auth, Case Metadata Extraction,
     Document Identification, Download, Deed/Obituary search, and Supabase sync.
   - Florida / County Scrapers: Dynamic per-county configurations handling
     Orange, Miami-Dade, Broward, Palm Beach, Duval, Pinellas, Pasco, etc.
   - Deed Search Worker: Autonomous asynchronous daemon worker (`_deed_worker_loop`)
     fetching property deed records in the background.

Lifecycle & State Management:
-----------------------------
- Global State: Unified in `state.py` (`AppState`), with module-level backward
  compatibility hooks in `main.py`.
- Progress Tracking: Monitored via `case_status` dictionary and broadcast to
  clients via WebSocket events (`case_update`, `processing_state`).
==============================================================================
"""

# ── Standard Library ──────────────────────────────────────────────────────────
import ctypes
import functools
import glob
import json
import os
import random
import re
import shutil
import socket
import sys
import threading
import time
import traceback
from pipeline.base import FloridaPipelineContext
from pipeline.blocks import (
    DeedSearchBlock,
    DownloadFilesBlock,
    FloridaDatabaseBlock,
    NavigateToFilesBlock,
    NavigateToSearchBlock,
    NavigateToUrlBlock,
    ObituarySearchBlock,
    SearchCaseNumberBlock,
)
from pipeline.orchestrator import PipelineOrchestrator
import pandas as pd

# ── Third-Party ───────────────────────────────────────────────────────────────
import psutil
import pysnooper

from pipeline_tracker import update_pipeline_status

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))


from typing import Optional

from humancursor import WebCursor

# ── Selenium Exceptions ───────────────────────────────────────────────────────
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    InvalidSessionIdException,
    NoSuchElementException,
    NoSuchWindowException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# ── urllib3 Exceptions ────────────────────────────────────────────────────────
from urllib3.exceptions import (
    MaxRetryError,
    NewConnectionError,
    ReadTimeoutError,
)

from config.county_config import get_county_processors

# ── Project Path Setup ────────────────────────────────────────────────────────
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)



# ── Web GUI (Flask/SocketIO equivalents for all Tkinter calls) ────────────────
# ── AI / LLM Helpers ─────────────────────────────────────────────────────────
from ai.llm_helper import (
    extract_complaint,
    extract_final_judgment,
    get_bankruptcy_case_status,
)
from app import (
    _settings,
    add_case_status_callback,
    append_driver_log,
    case_queue,
    case_status,
    clear_case_status,
    log_message,
    set_status_text,
    update_case_status,
    update_progress,
)
from app import (
    socketio as _socketio,
)

# ── Browser & Driver Helpers ──────────────────────────────────────────────────
from browser.browser_helpers import (
    cancel_all_downloads,
    check_error_message,
    check_for_files_page,
    check_js_popup,
    click_on_save,
    close_extra_tabs,
    close_new_windows,
    delete_driver,
    element_exists_id,
    element_exists_xpath,
    get_thread_number,
    human_type,
    is_logged_in,
    make_sure_tab1_is_selected,
    maximize_driver,
    navigate_to_url_nj,
    random_scroll,
    refresh_url,
    request_url,
    scroll_randomly,
    set_download_dir,
    simulate_human_browsing2,
    switch_to_window_by_url_prefix,
    take_screenshot,
    wait_and_click,
    wait_for_page_to_load,
)
from browser.driver_helpers import setup_driver
from browser.driver_snoop_web import attach_web_monitor

# ── Project Config & Models ───────────────────────────────────────────────────
from config_ import (
    DEFAULT_KEYWORDS,
    DEFAULT_UNWANTED,
    NJ_LOGIN_PAGE,
    SKIP_DEFENDANT_KEYWORDS,
    accounts,
)
from core.case_executor import CaseExecutor
from core.CaseStatus import CaseStatus
from core.SearchResult import SearchResult
from counties.brevard_helpers import trigger_download_brevard
from counties.broward_helpers import trigger_download_bw
from counties.clay_helpers import trigger_download_clay
from counties.duval_helpers import trigger_download_dv
from counties.lee_helpers import trigger_download_lee
from counties.manatee import trigger_download_manatee
from counties.miami_helpers import trigger_download_miami

# ── County-Specific Helpers ───────────────────────────────────────────────────
from counties.nj_helpers import (
    _get_case_information,
    check_main_frame,
    extract_property_details,_get_shuffled_main_accounts
)
from counties.orange_helpers import trigger_download_oc
from counties.osceola_helpers import trigger_download_osceola
from counties.palmbeach import trigger_download_pb
from counties.pasco_helpers import trigger_download_pasco
from counties.polk_helpers import trigger_download_polk
from counties.sarasota import trigger_download_sarasota
from counties.seminole_helpers import trigger_download_seminole
from counties.vs_helpers import trigger_download_vs

# ── Database / Supabase ───────────────────────────────────────────────────────
from database.supabase_service import (
    _update_status,
    add_case_with_files,
    bulk_purge_processing_cases,
    delete_case_completely_from_supabase,
    final_judgment_flag,
    get_case_id_by_number,
    mark_case_as_rip,
    sync_complaint_extracted_case_data,
    sync_deed_dictionary_to_documents,
    sync_final_judgment_extracted_case_data,
    valid_flag,
)

# ── Deed Search ───────────────────────────────────────────────────────────────
from deed_search.deed_api import run_deed_job

# ── Download Helpers ──────────────────────────────────────────────────────────
from download.data_handler import (
    _cleanup_prefixed_files,
    _save_matching_files_log,
    _verify_downloaded_files,
    display_matching_rows,
)
from download.download_helpers import cleanup_failed_download, get_timeout
from download.download_monitor import get_current_downloads_state
from download.DownloadManager import DownloadManager
from download.files_management import cleanup_unwanted_files
from download.scanners import scan_table_multithreaded
from models import Case

# ── Network Helpers ───────────────────────────────────────────────────────────
from network.network_helpers import reset_vpn

# ==============================================================================
# APP STATE  (single source of truth for all mutable globals)
# ==============================================================================
from state import state  # noqa: E402

# ── General Utilities ─────────────────────────────────────────────────────────
from utils.formatting import (
    sanitize_filename,
    save_to_excel,
)
from utils.parties_helpers import extract_defendants_into_report

# ── Backward-compatible aliases ────────────────────────────────────────────────
# All existing code that reads/writes these bare names still works.
# To add a new variable, just add it to state.py and alias it here.

def __getattr__(name):
    """Module-level __getattr__ so  `import main; main.running`  still works."""
    if hasattr(state, name):
        return getattr(state, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# Direct references used by this file's own code (avoids repeated getattr overhead)

# ── Legacy names kept for old code that still references them ─────────────────
case_tree             = None   # not used by web GUI
skip_current          = False  # legacy NJ path
_skip_target_thread_id = None  # legacy NJ path

SUFFIXES = {
    'jr', 'jr.',
    'sr', 'sr.',
    'ii', 'iii', 'iv', 'v',
    'vi', 'vii', 'viii', 'ix', 'x'
}


DOWNLOAD_FUNCTIONS = {
    'polk': trigger_download_polk,
    'oc': trigger_download_oc,
    'seminole': trigger_download_seminole,
    'lee': trigger_download_lee,
    'volusia': trigger_download_vs,
    'manatee': trigger_download_manatee,
    'brevard': trigger_download_brevard,
    'sarasota': trigger_download_sarasota,
    'dv': trigger_download_dv,
    'pb': trigger_download_pb,
    'osceola': trigger_download_osceola,
    'miami dade': trigger_download_miami,
    'bw': trigger_download_bw,
    'pasco': trigger_download_pasco,
    'clay' : trigger_download_clay
}


def _compute_batch_stats():
    """Derive aggregate batch statistics directly from `case_status`.

    `case_status` serves as the authoritative, single source of truth across
    both the local background worker threads and the connected web clients.
    This function tallies terminal outcomes across all queued and processed cases.

    Returns:
        tuple[int, int, int, int, int]: A 5-tuple consisting of:
            - total (int): Total number of cases tracked in the current batch.
            - rip (int): Count of ineligible, skipped, or RIP (auction/for-sale) cases.
            - not_found (int): Count of cases where the docket was missing from court records.
            - error (int): Count of cases encountering fatal scraping/pipeline failures.
            - completed (int): Count of successfully extracted and processed cases.
    """
    statuses = [str(v.get("status", "")).lower() for v in case_status.values()]
    total    = len(statuses)
    rip      = sum(1 for s in statuses if "rip" in s or "ineligible" in s or "skipped" in s)
    not_found = sum(1 for s in statuses if "not found" in s)
    error    = sum(1 for s in statuses if "error" in s)
    completed = sum(1 for s in statuses if "completed" in s)
    return total, rip, not_found, error, completed


# Lock preventing race conditions when evaluating the halfway progress threshold across concurrent workers
_halfway_lock = threading.Lock()

def check_and_update_batch_progress(case=None, status=None):
    """Callback evaluating real-time batch progress on every case state change.

    This function is subscribed to the `case_status` listener bus. Whenever any
    worker thread transitions a case to a terminal state (Completed, Error,
    Skipped, Not Found, RIP, Ineligible), this handler recalculates overall
    completion percentage, updates the GUI progress bar via SocketIO, and
    triggers milestone events (such as the halfway notification report).

    Args:
        case (str, optional): The case identifier that just updated.
        status (str, optional): The new status string assigned to the case.
            If provided and not a terminal status, recalculation is bypassed for efficiency.
    """
    terminal_keywords = ("completed", "error", "skipped", "not found", "rip", "ineligible")
    if status is not None and not any(t in str(status).lower() for t in terminal_keywords):
        return

    _total, _rip, _not_found, _error, _completed = _compute_batch_stats()
    _processed = _rip + _not_found + _error + _completed
    _total_ref = state.total_cases or _total

    if _total_ref > 0:
        progress = min(1.0, _processed / _total_ref)
        update_progress(progress)
        set_status_text(f"Processing... {_processed}/{_total_ref}")

    with _halfway_lock:
        if not state.halfway_report_sent and _total_ref > 0 and _processed >= max(1, _total_ref // 2):
            state.halfway_report_sent = True
            raw_input = input_file.get() if hasattr(input_file, 'get') else ""
            batch_name = _settings.get("batch_name", input_file.get().split("\\")[-1].split(".")[0])
            """log_message(f"⏳ Halfway point reached: {_processed}/{_total_ref} cases state.processed. Sending halfway report...")
            try:
                send_halfway_report(
                    total_cases=_total_ref,
                    rip_cases=_rip,
                    not_found_cases=_not_found,
                    valid_cases=_completed,
                    recipient_emails=[os.getenv("EMAIL_RECIPIENT", "karim@msvproperties.net")],
                    batch_name=batch_name,
                    sender_email=os.getenv("EMAIL_SENDER", "karim.merchaoui@gmail.com"),
                    sender_password=os.getenv("EMAIL_PASSWORD", PASSWORD)
                )
            except Exception as e:
                log_message(f"❌ Failed to send halfway report: {e}")"""

# Register callback so ANY case completion (NJ, Florida, RIP, Error, Not Found) triggers progress & halfway check
add_case_status_callback(check_and_update_batch_progress)


def _record_rip_case():
    """No-op kept for backward compat. RIP tracking is via case_status."""
    pass


def navigate_to_search_nj(driver, account, cookie_file, driver_pool):
    while not (is_logged_in(driver, 3)):
        login_flag = login_nj(driver, account, state.driver_pool, cookie_file)
        if login_flag:
            return 1

def build_payload(main_defendant, county_name, search_mode="NAME", block=None):
    name_parts = main_defendant.strip().split()
    if len(name_parts) >= 2:
        # Check whether the final element is a suffix
        if name_parts[-1].lower() in SUFFIXES:
            # Last name = surname + suffix
            last_name = " ".join(name_parts[-2:])

            # Everything before surname
            first_name = " ".join(name_parts[:-2])
        else:
            # Last element = surname
            last_name = name_parts[-1]

            # Everything before surname = first + middle names
            first_name = " ".join(name_parts[:-1])
    else:
        first_name = name_parts[0]
        last_name = ""

    from app import _settings
    deed_cfg = _settings.get("llm_configs", {}).get("deed", {}) if isinstance(_settings.get("llm_configs"), dict) else {}
    payload = {
        "county_name": f"{county_name.lower()} county",
        "first_name": first_name,
        "last_name": last_name,
        "download_file": False,
        "search_mode": search_mode,
        "block": block,
        "llm_service": deed_cfg.get("service") or _settings.get("llm_service", "groq"),
        "llm_api_key": deed_cfg.get("api_key") or _settings.get("llm_api_key", ""),
        "llm_model": deed_cfg.get("model") or _settings.get("llm_model", ""),
    }
    return payload


def _deed_worker_loop():
    """
    Background thread (Thread 2) — consumes deed jobs from the durable SQLite queue.
    Processes them strictly one-at-a-time; never drops work.
    Jobs that fail are marked 'failed' in the DB (not silently discarded).
    """
    log_message("Deed download worker started.")
    while True:
        item = state.deed_queue.get()  # blocks until something arrives
        book, page, files_dir, block, main_defendant, county_name, supabase_case_id, case_id = item
        print(f"item : {item}")
        print(f"county_name : {county_name}")
        try:
            from pipeline.base import BlockStatus
            _emit_block_status(case_id, "Deed Search", BlockStatus.RUNNING)
            payload = build_payload(main_defendant, county_name, block=block)

            log_message(f"[DeedWorker] Downloading deed for {case_id}  book={book}  page={page}  county={county_name}")
            if isinstance(county_name, dict):
                county_name = county_name['County:'].lower()

            result = run_deed_job(payload)
            if "extracted_data" in result:
                sync_deed_dictionary_to_documents(case_id, result['extracted_data'])

            _emit_block_status(case_id, "Deed Search", BlockStatus.SUCCESS)
            log_message(f"[DeedWorker] Deed done for {case_id}  book={book}  page={page}")
            state.deed_queue.task_done()
        except Exception as e:
            from pipeline.base import BlockStatus
            _emit_block_status(case_id, "Deed Search", BlockStatus.FAILED)
            update_pipeline_status("deed", "FAILED", tb_message=traceback.format_exc())
            log_message(f"[DeedWorker] Error on {case_id} book={book} page={page}: {e}")
            traceback.print_exc()
            # Mark job failed so deed_worker.py or retry_failed() can recover it
            state.deed_queue.mark_failed(error=str(e))


def _ensure_deed_worker():
    """Start the deed worker thread once, lazily, on first use."""
    with state.deed_worker_lock:
        if not state.deed_worker_started:
            t = threading.Thread(target=_deed_worker_loop, name="DeedDownloadWorker", daemon=True)
            t.start()
            state.deed_worker_started = True

# Thin shims so existing code that calls  status_text.set(...)  or
# reads  status_text.get()  keeps working without changes.
class _StringVarShim:
    def __init__(self, value=""):
        self._v = value

    def get(self):  return self._v

    def set(self, v):
        self._v = v
        set_status_text(v)


class _BoolVarShim:
    def __init__(self, value=False): self._v = value

    def get(self):   return self._v

    def set(self, v): self._v = v


class _IntVarShim:
    def __init__(self, value=1): self._v = value

    def get(self):   return self._v

    def set(self, v): self._v = v


status_text = _StringVarShim("Ready")
input_file = _StringVarShim()
output_folder = _StringVarShim()
keywords = _StringVarShim(
    "SETTLEMENT, DISMISSAL,MOTION CORRECTING DEFENDANT NAME,final judgment,judgment,pluries writ,partial stipulation ,order to stay,Motion to stay,bankruptcy, Certification of Mailing,vacate, Complaint, Additional Sums,Summons Issued,notice of sale,notice of dropping party,emergency motion,MOTION TO SUBSTITUTE PARTY DEFENDANT")
unwanted_keywords = _StringVarShim(
    "Proof of mailing,Return of Sums, Request Of Additional Sums,military,answer to complaint,Do not come to the")
headless_mode = _BoolVarShim(value=False)
max_workers_var = _IntVarShim(value=5)
state.driver_monitor = None

# Sync shims with web settings on every get so the web UI can change them
_orig_keywords_get = keywords.get
_orig_unwanted_get = unwanted_keywords.get
_orig_output_get = output_folder.get
_orig_input_get = input_file.get
_orig_headless_get = headless_mode.get
_orig_workers_get = max_workers_var.get


def _kw_get():       return _settings.get("keywords") or _orig_keywords_get()


def _uw_get():       return _settings.get("unwanted_keywords") or _orig_unwanted_get()


def _of_get():       return _settings.get("output_folder") or _orig_output_get()


def _if_get():       return _settings.get("input_file") or _orig_input_get()


def _hm_get():       return _settings.get("headless_mode", False)


def _mw_get():       return int(_settings.get("max_workers", 5))


keywords.get = _kw_get
unwanted_keywords.get = _uw_get
output_folder.get = _of_get
input_file.get = _if_get
headless_mode.get = _hm_get
max_workers_var.get = _mw_get


def get_driver_pool():
    return state.driver_pool


# ══════════════════════════════════════════════════════════════════════════════
# SKIP INFRASTRUCTURE — per-thread, targets a single case by case_id
# ══════════════════════════════════════════════════════════════════════════════

class SkipCase(Exception):
    """Raised in a worker thread to abort only the current case."""
    pass


class StopRequested(Exception):
    """Raised to instantly abort process when 'Stop' is clicked."""
    pass


# Thread-local storage: each worker thread owns its own skip flag + case_id
_thread_local = threading.local()

# Global registry: case_id  →  (thread_id, driver)   — written by skippable wrapper
_case_thread_registry: dict = {}  # {case_id: (thread_ident, driver)}
_registry_lock = threading.Lock()


def _register_case(case_id, driver):
    """Called by the skippable wrapper when a worker starts a case."""
    with _registry_lock:
        _case_thread_registry[case_id] = (threading.current_thread().ident, driver)


def _unregister_case(case_id):
    """Called by the skippable wrapper when a worker finishes (or skips) a case."""
    with _registry_lock:
        _case_thread_registry.pop(case_id, None)


def _inject_skip_into_thread(thread_id, driver, case_id):
    """
    Background watcher: waits up to 30 s for the worker to notice its flag,
    then force-injects SkipCase via the CPython async-exception API.
    """
    deadline = time.time() + 3
    while time.time() < deadline:
        with _registry_lock:
            still_running = case_id in _case_thread_registry
        if not still_running:  # worker already handled it cooperatively
            return
        time.sleep(0.25)

    # Still state.running — inject hard into the specific thread
    if thread_id is not None:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_long(thread_id),
            ctypes.py_object(SkipCase)
        )
        log_message(f"⏭️  Async skip injected into worker for {case_id}.")

    if driver is not None:
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass


def skip_case_by_id(case_id):
    with _registry_lock:
        entry = _case_thread_registry.get(case_id)

    if not entry:
        log_message(f"⚠️ Case {case_id} is not currently state.running — nothing to skip.")
        return

    thread_id, driver = entry
    log_message(f"⏭️ Skipping {case_id}...")

    with _registry_lock:
        state.skip_requested_cases.add(case_id)

    # Stop the browser immediately so Selenium unblocks
    if driver is not None:
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass

    # Start watcher to hard-inject if cooperative check doesn't fire
    watcher = threading.Thread(
        target=_inject_skip_into_thread,
        args=(thread_id, driver, case_id),
        daemon=True,
    )
    watcher.start()





def check_skip():
    """
    Cooperative check — raises SkipCase only if the CURRENT thread's case
    has been targeted. Also checks global `state.force_stop` and raises
    `StopRequested` to terminate the thread immediately.
    """
    case_id = getattr(_thread_local, 'current_case_id', None)
    if state.force_stop:
        raise StopRequested()

    if case_id and case_id in state.skip_requested_cases:
        raise SkipCase()


def skip_current_case():
    """
    Legacy alias — skips whatever case is currently selected in the tree.
    Prefer skip_case_by_id(case_id) from the GUI for multi-worker safety.
    """
    # Try to identify the state.running case from the tree selection (GUI sets this)
    case_id = getattr(skip_current_case, '_selected_case_id', None)
    if case_id:
        skip_case_by_id(case_id)
    else:
        # Fallback: skip all state.running cases (old behaviour)
        with _registry_lock:
            for cid in list(_case_thread_registry):
                state.skip_requested_cases.add(cid)
        log_message("⏭️  Skip requested (no case selected — skipping all state.running cases).")


def skippable(func):
    """
    Decorator for process_* functions.
    - Registers the worker thread in the global registry so skip_case_by_id can
      target it by case_id.
    - Stores the case_id in thread-local so check_skip() knows which case this
      thread is processing.
    - Catches SkipCase and marks the case as Skipped.
    Assumes signature: func(case_id, driver, state.driver_pool, ...)
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        case_id = args[0] if args else "unknown"
        driver = args[1] if len(args) > 1 else None

        _thread_local.current_case_id = case_id
        _register_case(case_id, driver)

        try:
            return func(*args, **kwargs)
        except SkipCase:
            log_message(f"⏭️  Skipped: {case_id}")
            if case_id in state.report_cases:
                state.report_cases[case_id]['status'] = "Skipped"
            update_case_status(driver, case_id, "", "Skipped", details="Skipped by user")
        finally:
            _unregister_case(case_id)
            state.skip_requested_cases.discard(case_id)
            _thread_local.current_case_id = None

    return wrapper


# ══════════════════════════════════════════════════════════════════════════════
# EXECUTOR / CASE SUBMISSION  (delegated to CaseExecutor)
# ══════════════════════════════════════════════════════════════════════════════

def process_cases():
    """Execute the end-to-end batch scraping pipeline across all queued cases.

    This function represents the primary business execution lifecycle of the
    scraper. It coordinates the overall batch workflow by performing the
    following operations:

    1. Pre-Execution Validation:
       - Resets milestone indicators (e.g. `state.halfway_report_sent`).
       - Verifies that `case_queue` contains pending cases; aborts gracefully if empty.
       - Ensures the background deed processing worker thread is active.

    2. Dependency Injection & Executor Setup:
       - Configures a `core.case_executor.CaseExecutor` instance, injecting all
         browser pool factories, network handlers, UI reporters, and state accessors.
       - Isolates execution logic from direct UI coupling.

    3. Concurrent Processing & Barrier Synchronization:
       - Triggers `executor.run()`, which spawns worker threads across available drivers.
       - Enters a polling barrier loop, actively monitoring `case_status` until
         every case transitions into a terminal status (`completed`, `error`,
         `skipped`, `case not found`, `not found`, `rip`, `ineligible`), or until
         an emergency `force_stop` interruption is signaled.

    4. Finalization & Teardown:
       - Guarantees in `finally` that `state.running` is toggled off and the UI
         is notified via the WebSocket `processing_state` event.
       - Aggregates final batch statistics from `case_status` and logs a summary.
    """
    state.halfway_report_sent = False

    # ── Guard: Abort if queue is depleted ─────────────────────────────────────
    if case_queue.empty():
        log_message("⚠️ No cases in queue — nothing to process. Please load cases first.")
        state.running = False
        try:
            from app import socketio
            socketio.emit("processing_state", {"running": False})
        except Exception:
            pass
        return


    # Ensure the background asynchronous deed downloader daemon is running
    _ensure_deed_worker()

    # ── Initialize CaseExecutor with Inversion-of-Control Callbacks ───────────
    executor = CaseExecutor(
        get_headless_mode=lambda: headless_mode.get() if hasattr(headless_mode, 'get') else getattr(state, 'headless_mode', False),
        get_county_processor_func=_get_county_processor,
        get_shuffled_main_accounts_func=_get_shuffled_main_accounts,
        emit_report_func=_safe_emit_report,
        socketio_emit_func=_socketio.emit,
        setup_driver_func=setup_driver,
        attach_web_monitor_func=attach_web_monitor,
        append_driver_log_func=append_driver_log,
        reset_vpn_func=reset_vpn,
        element_exists_id_func=element_exists_id,
        element_exists_xpath_func=element_exists_xpath,
        refresh_url_func=refresh_url,
        check_js_popup_func=check_js_popup,
        request_url_func=request_url,
        delete_driver_func=delete_driver,
        nj_login_page=NJ_LOGIN_PAGE,
        default_keywords=DEFAULT_KEYWORDS,
        default_unwanted=DEFAULT_UNWANTED,
        StopRequested=StopRequested,
        record_rip_case_func=_record_rip_case,
    )
    
    try:
        # Run the concurrent multi-worker case executor loop
        executor.run()

        # Wait until all cases reach a terminal status
        terminal_statuses = {"completed", "error", "skipped", "case not found", "not found", "rip", "ineligible"}
        log_message("⏳ Waiting for all cases to reach final status...")
        while not state.force_stop:
            with_status = list(case_status.values())
            if not with_status:
                break
            all_done = all(
                any(term in str(item.get("status", "")).lower() for term in terminal_statuses)
                for item in with_status
            )
            if all_done:
                break
            time.sleep(1)
    finally:
        # IMPORTANT: Reset state.running flag when done
        state.running = False
        try:
            from app import socketio
            socketio.emit("processing_state", {"running": False})
        except Exception:
            pass
        batch_name = _settings.get("batch_name", input_file.get().split("\\")[-1].split(".")[0])
        log_message("✅ Batch processing completed")
        # ── Derive counts from case_status (single source of truth) ──────────
        _total, _rip, _not_found, _error, _completed = _compute_batch_stats()
        # fall back to state.total_cases if case_status is empty (e.g. force-stop early)
        _total = _total or state.total_cases
        log_message(
            f"📊 Batch stats — total: {_total} | rip: {_rip} | not_found: {_not_found} "
            f"| error: {_error} | completed: {_completed}"
        )
        """send_final_report(
            total_cases=_total,
            rip_cases=_rip,
            not_found_cases=_not_found,
            valid_cases=_completed,
            recipient_emails=[os.getenv("EMAIL_RECIPIENT", "karim@msvproperties.net")],
            batch_name=batch_name,
            sender_email=os.getenv("EMAIL_SENDER", "karim.merchaoui@gmail.com"),
            sender_password=os.getenv("EMAIL_PASSWORD", PASSWORD)
        )"""

def _safe_emit_report(report):
    """Wrapper so CaseExecutor doesn't need to import app."""
    try:
        from app import emit_report
        emit_report(report)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# COUNTY CONFIGS
# ══════════════════════════════════════════════════════════════════════════════






def _get_county_processor(county_lower):
    processors = get_county_processors(process_case, process_nj_case)
    for key, processor in processors.items():
        if key in county_lower:
            return processor
    return None



def reset_and_retry(case_id, driver, driver_pool, config, files_dir, cached_matching_rows):
    new_driver = state.driver_pool.close_and_refill(driver)
    process_case(case_id, new_driver, state.driver_pool, config, files_dir=files_dir,
                 cached_matching_rows=cached_matching_rows)


# ══════════════════════════════════════════════════════════════════════════════
# STEP  VERIFICATION
# Each entry is a lightweight lambda(driver)->bool that confirms the page is
# in the expected state *immediately* after the step runs.  None = skip check.
# ══════════════════════════════════════════════════════════════════════════════

STEP_VERIFIERS = {
    'oc': {
        'navigate_to_url': lambda d: 'myorangeclerk' in d.current_url,
        'navigate_to_search': lambda d: element_exists_id(d, 'caseNumber'),
        'search_case_number': lambda d: element_exists_xpath(d, '//*[@id="caseList"]/tbody/tr/td'),
        'navigate_to_files': lambda d: element_exists_xpath(d, '//*[@id="docketTable"]/tbody'),
    },
    'pb': {
        'navigate_to_url': None,
        'navigate_to_search': lambda d: element_exists_id(d, 'SearchRequest_CaseNumber'),
        'search_case_number': lambda d: element_exists_xpath(d, '//*[@id="searchResults"]/tbody/tr/td[1]/button'),
        'navigate_to_files': lambda d: element_exists_id(d, 'docketTable'),
    },
    'Lee': {
        'navigate_to_url': lambda d: 'leeclerk' in d.current_url,
        'navigate_to_search': lambda d: element_exists_id(d, 'byCaseNumber_CaseNumber'),
        'search_case_number': lambda d: 'leeclerk' in d.current_url,
        'navigate_to_files': lambda d: element_exists_xpath(d,
                                                            '//*[@id="docketCollapse"]/div/div[2]/div[1]/table/tbody'),
    },
    'Seminole': {
        'navigate_to_url': lambda d: 'seminoleclerk' in d.current_url,
        'navigate_to_search': None,
        'search_case_number': lambda d: element_exists_id(d, 'CaseNum') or element_exists_id(d, 'CaseGrid'),
        'navigate_to_files': lambda d: element_exists_id(d, 'collapseDockets'),
    },
    'Sarasota': {
        'navigate_to_url': lambda d: 'sarasotaclerk' in d.current_url,
        'navigate_to_search': lambda d: element_exists_id(d, 'ctl00_cphBody_tbCaseNumber'),
        'search_case_number': lambda d: 'sarasotaclerk' in d.current_url,
        'navigate_to_files': lambda d: element_exists_xpath(d, '//*[@id="ctl00_cphBody_rgDocket_ctl00"]/tbody'),
    },
    'Manatee': {
        'navigate_to_url': lambda d: element_exists_id(d, 'CaseNumber'),
        'navigate_to_search': None,
        'search_case_number': None,
        'navigate_to_files': lambda d: element_exists_xpath(d, '//*[@id="dockets"]/tbody'),
    },
    'bw': {
        'navigate_to_url': lambda d: 'browardclerk' in d.current_url,
        'navigate_to_search': lambda d: element_exists_id(d, 'CaseNumber'),
        'search_case_number': lambda d: element_exists_xpath(d, '//*[@id="SearchResultsGrid"]'),
        'navigate_to_files': lambda d: element_exists_xpath(d, '//*[@id="tblEvents"]/tbody'),
    },
    'Miami Dade': {
        'navigate_to_url': lambda d: 'miamidadeclerk' in d.current_url,
        'navigate_to_search': lambda d: 'miamidadeclerk' in d.current_url,
        'search_case_number': lambda d: 'miamidadeclerk' in d.current_url,
        'navigate_to_files': lambda d: element_exists_xpath(d,
                                                            '//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]'),
    },
    'dv': {
        'navigate_to_url': lambda d: 'duvalclerk' in d.current_url,
        'navigate_to_search': None,
        'search_case_number': lambda d: element_exists_xpath(d, '//*[@id="ContentPlaceHolder1_WebTab1"]'),
        'navigate_to_files': lambda d: element_exists_xpath(d, '//*[@id="c_DocketsPanel"]/div/table'),
    },
    'Osceola': {
        'navigate_to_url': lambda d: 'osceolaclerk' in d.current_url,
        'navigate_to_search': lambda d: element_exists_id(d, 'caseNumber'),
        'search_case_number': lambda d: 'osceolaclerk' in d.current_url,
        'navigate_to_files': lambda d: element_exists_xpath(d, '//*[@id="gridDockets"]/tbody'),
    },
    'Volusia': {
        'navigate_to_url': lambda d: 'clerk.org' in d.current_url,
        'navigate_to_search': lambda d: element_exists_id(d, 'Content1_CaseNum'),
        'search_case_number': lambda d: 'clerk.org' in d.current_url,
        'navigate_to_files': lambda d: element_exists_xpath(d, '//*[@id="GridDocket"]/tbody'),
    },
    'Polk': {
        'navigate_to_url': None,
        'navigate_to_search': lambda d: element_exists_id(d, 'UCN'),
        'search_case_number': lambda d: element_exists_xpath(d, '//*[@id="gridtable"]/tbody'),
        'navigate_to_files': lambda d: element_exists_xpath(d, '//*[@id="doctable"]/tbody'),
    },
    'Brevard': {
        'navigate_to_url': lambda d: element_exists_xpath(d,
                                                          '/html/body/form/table/tbody/tr[2]/td/center/input') or element_exists_xpath(
            d, '/html/body/form/div[1]/input[2]'),
        'navigate_to_search': lambda d: element_exists_xpath(d, '/html/body/form/div[1]'),
        'search_case_number': lambda d: 'brevardclerk' in d.current_url,
        'navigate_to_files': lambda d: element_exists_xpath(d, '//*[@id="tbl-content"]/tbody'),
    },
    'Pasco': {
        'navigate_to_url': lambda d: element_exists_xpath(d,
                                                          '/html/body/div/div[1]/div[3]/form/div[3]/div[1]/div/label') or element_exists_xpath(
            d, '//*[@id="form:j_idt175"]/span'),
        'navigate_to_search': lambda d: element_exists_xpath(d, '/html/body/div[1]/div[1]/form[2]/div[4]/button[1]'),
        'search_case_number': lambda d: element_exists_xpath(d, '/html/body/div[1]/div[1]/form[2]/div[6]/div[2]/div/div[2]/table'),
        'navigate_to_files': lambda d: element_exists_xpath(d, '/html/body/div[1]/div[1]/form[2]/div[6]/div[2]/div/div[2]/table'),
    },
}




def get_verifier_description(verify_fn):
    """Extract a concise readable description of the verifier callable."""
    if not verify_fn:
        return "None"
    doc = getattr(verify_fn, '__doc__', None)
    if doc and not doc.startswith("lambda"):
        return doc.strip()
    try:
        import inspect
        src = inspect.getsource(verify_fn).strip()
        if "lambda" in src:
            src = "lambda" + src.split("lambda", 1)[1]
        if src.endswith(","):
            src = src[:-1].strip()
        return " ".join(src.split())
    except Exception:
        pass
    name = getattr(verify_fn, '__name__', None)
    if name and name != '<lambda>':
        return name
    return str(verify_fn)


def _get_verifier(county_name, step_name):
    """Return the verification lambda for a county+step, or None."""
    if not county_name:
        return None
    v = (
        STEP_VERIFIERS.get(county_name)
        or STEP_VERIFIERS.get(county_name.lower())
        or STEP_VERIFIERS.get(county_name.capitalize())
        or STEP_VERIFIERS.get(county_name.title())
    )
    return v.get(step_name) if v else None


def _wait_and_verify(driver, verify_fn, county_name, case_id, step_name,
                     attempts=3, delay=2):
    for attempt in range(attempts):
        _recover_error_page(driver)
        try:
            WebDriverWait(driver, delay).until(lambda d: (
                    d.execute_script("return document.readyState") == "complete"
                    and "loading" not in (
                            d.execute_script("return document.body ? document.body.innerText : ''") or "").lower()
            ))
        except Exception:
            pass

        try:
            if verify_fn(driver):
                return True
        except Exception:
            pass

        if attempt < attempts - 1:
            log_message(f"⏳ [{county_name}] {step_name} verify {attempt + 1}/{attempts}, retrying...")
    return False


def _recover_error_page(driver, max_reloads=2):
    """Silently reload if the browser is showing an error page."""
    for _ in range(max_reloads):
        try:
            is_error = driver.execute_script("""
                return !!(
                    document.getElementById('main-frame-error') ||
                    document.getElementById('sub-frame-error') ||
                    window.location.href.startsWith('chrome-error://') ||
                    (document.body && (
                        document.body.innerText.includes('ERR_') ||
                        document.body.innerText.includes('Aw, Snap') ||
                        document.body.innerText.includes("This page isn't working")
                    ))
                );
            """)
        except Exception:
            return  # driver itself is broken, let the verifier fail naturally

        if not is_error:
            return

        log_message(f"🔄 Browser error page detected — reloading")
        take_screenshot(driver, label="browser_error")
        try:
            driver.execute_script("location.reload();")
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            time.sleep(3)


def _run_step(step_fn, step_args, driver, driver_pool, county_name, case_id,
              verify=None, max_retries=2, step_timeout=60):
    """
    Execute one navigation step and immediately verify the resulting page state.

    • Runs `step_fn(*step_args)` directly (no extra thread — Selenium WebDriver
      is not thread-safe, so spawning wrapper threads only caused orphan
      threads and race conditions that led to skipped/incomplete cases).
    • Maps the return flag:
        None/0  → OK
        1       → transient failure (retry)
        2       → case not found (abort cleanly)
    • After an OK flag, `verify(driver)` is called.

    Returns True if the step succeeded, False if the case was not found.
    Raises StepAbort on unrecoverable failure.
    """
    step_name = getattr(step_fn, '__name__', str(step_fn))
    for attempt in range(max_retries + 1):
        step_start_time = time.time()
        log_message(f"⏳ [{county_name}] [{case_id}] Executing step '{step_name}' (attempt {attempt + 1}/{max_retries + 1})...")

        try:
            raw_flag = step_fn(*step_args)
        except StepTimeout:
            raise
        except Exception as err:
            traceback.print_exc()
            curr_url = getattr(driver, "current_url", "unknown")
            log_message(
                f"❌ [{county_name}] [{case_id}] Step '{step_name}' failed on attempt {attempt + 1}: "
                f"{type(err).__name__}: {err} (URL: {curr_url})"
            )
            if attempt < max_retries:
                log_message(f"🔄 [{county_name}] [{case_id}] Retrying step '{step_name}' ({attempt + 2}/{max_retries + 1})...")
                continue
            raise StepAbort(step_name, cause=err)

        # ── return-flag handling ───────────────────────────────────────────
        if raw_flag == 2:
            # Case does not exist — clean exit (not an error)
            log_message(f"ℹ️ [{county_name}] [{case_id}] Step '{step_name}' returned flag 2 (Case Not Found)")
            return False
        if raw_flag == 1:
            log_message(f"⚠️ [{county_name}] [{case_id}] Step '{step_name}' returned transient failure flag 1")
            if attempt < max_retries:
                continue  # immediate retry
            state.driver_pool.reset_vpn_pool(driver)
            state.driver_pool.close_and_refill(driver)
            raise StepAbort(step_name, cause=RuntimeError("Step returned retry flag 1 after max attempts"))
        if raw_flag == 3:
            log_message(f"⚠️ [{county_name}] [{case_id}] Step '{step_name}' requested VPN reset (flag 3)")
            state.driver_pool.reset_vpn_pool(driver)
            state.driver_pool.close_and_refill(driver)
            raise StepAbort(step_name, cause=RuntimeError("Step requested VPN reset (flag 3)"))

        # ── page-state verification ────────────────────────────────────────
        if verify:
            log_message(f"🔍 [{county_name}] [{case_id}] Verifying step '{step_name}'...")
            if not _wait_and_verify(driver, verify, county_name, case_id, step_name):
                v_desc = get_verifier_description(verify)
                curr_url = getattr(driver, "current_url", "unknown")
                log_message(f"⚠️ [{county_name}] [{case_id}] {step_name} verify failed: {v_desc} (URL: {curr_url})")
                take_screenshot(driver, label=f"verify_fail_{step_name}", case_id=case_id)
                raise VerifyFailed(step_name, verifier=verify, verifier_desc=v_desc)

        elapsed = time.time() - step_start_time
        log_message(f"✅ [{county_name}] [{case_id}] Step '{step_name}' finished successfully in {elapsed:.2f}s")
        return True  # step passed

    raise StepAbort(step_name)  # exhausted retries


class StepAbort(Exception):
    """Raised by _run_step when a step cannot be recovered."""

    def __init__(self, step_name="unknown", cause=None):
        self.step_name = step_name
        self.cause = cause
        msg = f"Step '{step_name}' failed after retries"
        if cause:
            msg += f" (Cause: {type(cause).__name__}: {cause})"
        super().__init__(msg)


class VerifyFailed(Exception):
    """Raised by _run_step when page verification fails, to trigger a full case retry."""

    def __init__(self, step_name="unknown", verifier=None, verifier_desc=None):
        self.step_name = step_name
        self.verifier = verifier
        self.verifier_desc = verifier_desc or get_verifier_description(verifier)
        super().__init__(f"{step_name} verifier failed: {self.verifier_desc}")


class StepTimeout(Exception):
    """Raised by _run_step when a step exceeds its configured timeout."""

    def __init__(self, step_name="unknown", timeout=60):
        self.step_name = step_name
        self.timeout = timeout
        super().__init__(f"{step_name} timed out after {timeout}s")


# ══════════════════════════════════════════════════════════════════════════════
# UNIFIED PROCESS FUNCTION  — Florida / generic counties pipeline
# ══════════════════════════════════════════════════════════════════════════════
def process_case(case_id, driver, driver_pool, config,
                 files_dir=r"C:\Users\Administrator\Documents\Court Scraper Database", cached_matching_rows=None):
    """
    Process a Florida / generic county case through the 8-block pipeline.

    Blocks (in order):
      1. NavigateToUrlBlock    — open county court website
      2. NavigateToSearchBlock — go to search page (handles login if needed)
      3. SearchCaseNumberBlock — enter case number
      4. NavigateToFilesBlock  — navigate to docket / files tab
      5. DownloadFilesBlock    — scan table & download files (with retry)
      6. ObituarySearchBlock   — background obituary search (fire-and-observe)
      7. DeedSearchBlock       — background deed search (fire-and-observe)
      8. FloridaDatabaseBlock  — Zillow lookup, Supabase push, final_update
    """
    
    # ── Pre-flight setup ──────────────────────────────────────────────────────
    os.makedirs(files_dir, exist_ok=True)
    if "affidavit" in state.keyword_list:
        state.keyword_list.remove("affidavit")
    driver.files_dir = files_dir
    set_download_dir(driver, files_dir)
    county_name = config['county_name']
    update_case_status(driver, case_id, county_name, "Starting", details=config.get('files_page_url', ''))
    state.report_cases[case_id]['county'] = county_name
    # ── Build context ─────────────────────────────────────────────────────────
    ctx = FloridaPipelineContext(
        case_id              = case_id,
        config               = config,
        driver               = driver,
        driver_pool          = driver_pool,
        files_dir            = files_dir,
        cached_matching_rows = cached_matching_rows,
    )

    # ── Run pipeline ──────────────────────────────────────────────────────────
    orchestrator = PipelineOrchestrator(
        blocks=[
            NavigateToUrlBlock(),
            NavigateToSearchBlock(),
            SearchCaseNumberBlock(),
            NavigateToFilesBlock(),
            DownloadFilesBlock(),
            ObituarySearchBlock(),
            DeedSearchBlock(),
            FloridaDatabaseBlock(),
        ],
        on_status_change=_emit_block_status,
    )
    orchestrator.run(ctx)


def download_files(driver, files_dir, case_id, county_name, table_path, row_tag,
                   case_type_xpath, case_url_prefix, max_retry_attempts=4, table_xpath2=None,
                   case_status_xpath=None, cached_matching_rows=None, file_prefix=None,
                   parties_table_xpath=None, show_parties_table=None, show_dockets_table=None):
    driver.state = "downloading"
    retry_attempt = 0
    download_mgr = DownloadManager(driver, state.driver_pool, files_dir, case_id, county_name,
                                   status_callback=update_case_status)
    download_mgr.update_status("Downloading", details="Checking for files")
    matching_rows = None
    _snoop_log = os.path.join(files_dir, "download_files.log")
    with pysnooper.snoop(_snoop_log):
        try:
            table = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, table_path)))
        except TimeoutException:
            return 3, matching_rows
        rows = table.find_elements(By.XPATH, f"./{row_tag}")
        total_rows = len(rows)

        if case_type_xpath:
            case_type = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, case_type_xpath))).text
            state.report_cases[case_id]['case_type'] = case_type

        if case_status_xpath:
            try:
                case_status = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, case_status_xpath))).text
                state.report_cases[case_id]['court_case_status'] = case_status
            except TimeoutException:
                state.report_cases[case_id]['court_case_status'] = ''
        if parties_table_xpath:
            try:
                state.report_cases = extract_defendants_into_report(
                    driver, parties_table_xpath, case_id, state.report_cases,
                    show_parties_table=show_parties_table,
                    show_dockets_table=show_dockets_table
                )
                log_message(f"👤 [{county_name}] Extracted defendants into report. main_defendant: {state.report_cases[case_id].get('main_defendant')}")
                if state.report_cases[case_id].get('main_defendant'):
                    print(f"state.report_cases[case_id]['county'] : {state.report_cases[case_id]['county']}")
                    supabase_case_id = get_case_id_by_number(case_id)
                    state.deed_queue.put((
                    "", "", files_dir, state.report_cases[case_id].get("Block"),
                    state.report_cases[case_id].get('main_defendant'), state.report_cases[case_id]['county'],
                    supabase_case_id, case_id
                    ))
            except Exception as pe:
                log_message(f"⚠️ [{county_name}] Error extracting defendants from parties table: {pe}")

        check_skip()

        # ── Use cached rows if provided (resume mode), otherwise scan ──
        if cached_matching_rows:
            matching_rows = cached_matching_rows
            log_message(f"🔄 [{county_name}] Resuming download for {case_id} with {len(matching_rows)} cached rows")
        else:
            matching_rows_lock = threading.Lock()
            matching_rows = scan_table_multithreaded(driver, case_id, files_dir, state.report_cases, total_rows,
                                                        table_path, matching_rows_lock, state.keyword_list,
                                                        state.unwanted_list, county_name.lower(), start_index=1)
            check_skip()

            if table_xpath2:
                try:
                    table2 = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, table_xpath2)))
                    rows2 = table2.find_elements(By.XPATH, f"./{row_tag}")

                    total_rows2 = len(rows2)
                    matching_rows2 = scan_table_multithreaded(driver, case_id, files_dir, state.report_cases, total_rows2,
                                                                table_xpath2, matching_rows_lock, state.keyword_list,
                                                                state.unwanted_list, county_name.lower(), start_index=1,
                                                                tab2=True)
                    matching_rows = matching_rows + matching_rows2
                    # bell(1)
                except TimeoutException:
                    if county_name.lower() == 'bw':
                        pass
                    else:
                        raise
        _save_matching_files_log(case_id, files_dir, matching_rows)
        display_matching_rows(case_id, driver, matching_rows)

        # ── Filter out files already downloaded on disk ──
        existing_files_on_disk = set(os.listdir(files_dir)) if os.path.isdir(files_dir) else set()
        remaining_rows = []
        for f in matching_rows:
            expected_name = f"{f['filename']} ({f['row_index']})_{f['date']}.pdf"
            # Also check without .pdf in case sanitize_filename changed it
            if expected_name in existing_files_on_disk:
                log_message(f"⏭️ [{county_name}] Skipping already-downloaded: {expected_name}")
            else:
                remaining_rows.append(f)

        if cached_matching_rows is not None and len(remaining_rows) < len(matching_rows):
            log_message(
                f"🔄 [{county_name}] {len(matching_rows) - len(remaining_rows)} files already on disk, {len(remaining_rows)} remaining")

        downloaded_files = []
        download_mgr.update_status("Downloading", details="Checking for files")
        table = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, table_path)))
        for file in remaining_rows:
            check_skip()  # ← skip between files
            try:
                main_window = driver.current_window_handle
            except MaxRetryError:
                main_window = driver.switch_to.window(driver.window_handles[0])
            before_files = download_mgr.get_existing_files()

            while retry_attempt < max_retry_attempts:
                retry_attempt = 0  # ← reset per file
                _cleanup_prefixed_files(files_dir, file_prefix)
                check_skip()  # ← skip between retries
                try:
                    switch_to_window = switch_to_window_by_url_prefix(driver, case_url_prefix)
                    if element_exists_xpath(driver, '//*[@id="caseinfo"]/div[3]/div[1]'):
                        return 1, matching_rows
                    try:
                        table = driver.find_element(By.XPATH, table_path)
                    except NoSuchElementException:
                        take_screenshot(driver,
                                        label=f'TimeoutException , retrying (windows num {len(driver.window_handles)} for county {county_name})')
                        append_driver_log(id(driver), f"TimeoutException , retrying", case_id)
                        return 1, matching_rows
                    except InvalidSessionIdException:
                        take_screenshot(driver,
                                        label=f'InvalidSessionIdException , retrying')
                        append_driver_log(id(driver), f"InvalidSessionIdException , retrying", case_id)
                        return 1, matching_rows
                    random_scroll(driver)

                    index = file['row_index']
                    filename = file['filename']
                    date = file['date']

                    append_driver_log(id(driver), f"Attempting : {filename}", case_id)
                    close_extra_tabs(driver)
                    cleanup_unwanted_files(files_dir)
                    
                    download_mgr.update_status("Downloading", details=f"File {index + 1}/{total_rows}: {filename}")
                    switch_to_window_by_url_prefix(driver, case_url_prefix)

                    windows_before = driver.window_handles
                    row = file.get('row')
                    if element_exists_xpath(driver, f"{table_path}/{row_tag}[{index}]") and not row:
                        row = table.find_element(By.XPATH, f'./{row_tag}[{index}]')
                    set_download_dir(driver, files_dir)
                    trigger_download_func = DOWNLOAD_FUNCTIONS.get(county_name.lower())
                    down_flag = trigger_download_func(driver, row, index, download_mgr, before_files, matching_row=file)
                    close_new_windows(driver, windows_before, main_window)
                    if down_flag == 1:
                        cancel_all_downloads(driver)
                        cleanup_failed_download(download_mgr, before_files)
                        close_extra_tabs(driver)
                        retry_attempt += 1
                        append_driver_log(id(driver), f"❌ Failed Download Attempt {filename}", case_id)
                        continue
                    if down_flag == 2:
                        _cleanup_prefixed_files(files_dir, file_prefix)
                        append_driver_log(id(driver), f"❌ File cannot be downloaded {filename}", case_id)
                        break
                    if down_flag == 3:
                        _cleanup_prefixed_files(files_dir, file_prefix)
                        driver.state = "captcha"
                        state.driver_pool.reset_vpn_pool(driver)
                        return 3, matching_rows

                    new_file = download_mgr.wait_for_file_detection(before_files)

                    if not new_file:
                        append_driver_log(id(driver), f"❌ No file detected for {filename}", case_id)
                        # bell(n=1)
                        retry_attempt += 1
                        cancel_all_downloads(driver)
                        cleanup_failed_download(download_mgr, before_files)
                        close_extra_tabs(driver)
                        continue
                    print(f"✅ New File (Before detecting) {new_file}")
                    append_driver_log(id(driver), f"✅ New File (Before detecting) {new_file}", case_id)
                    path = download_mgr.rename_file(f"{filename} ({index})_{date}.pdf", case_id,
                                                    state.report_cases, new_file=new_file)
                    print(f"path : {path}")
                    driver.switch_to_window(main_window)
                    if path is True:
                        retry_attempt += 1
                        cleanup_failed_download(download_mgr, before_files)
                        # bell(n=1)
                        append_driver_log(id(driver), f"❌ Failed to rename {filename}", case_id)
                        continue
                    """if "complaint" in filename.lower():
                        complaint_info = extract_complaint(path[1])
                        print(f"complaint_info : {complaint_info}")
                        if isinstance(complaint_info, str):
                            complaint_info = json.loads(complaint_info)

                        if complaint_info:
                            state.report_cases[case_id]['mortgage_execution_date'] = complaint_info.get(
                                'mortgage_execution_date')
                            state.report_cases[case_id]['original_mortgage_amount'] = complaint_info.get(
                                'original_mortgage_amount')
                            state.report_cases[case_id]['interest_rate'] = complaint_info.get('interest_rate')
                            state.report_cases[case_id]['deceased_persons'] = complaint_info.get('deceased_persons')
                            state.report_cases[case_id]['city'] = complaint_info.get('property_city')
                            state.report_cases[case_id]['state'] = complaint_info.get('property_state')
                            state.report_cases[case_id]['Block'] = complaint_info.get('block')
                            state.report_cases[case_id]['Lot'] = complaint_info.get('lot')
                            state.report_cases[case_id]['property_address'] = complaint_info.get('property_address')

                            with open(files_dir + f"/complaint_{case_id}.json", 'w') as f:
                                json.dump(complaint_info, f, indent=2, default=str)
                            sync_complaint_extracted_case_data(case_id, complaint_info)
                    if "final judgment" in filename.lower() or "final_judgment" in filename.lower():
                        
                        final_judgment_info = extract_final_judgment(path[1])
                        print(f"final_judgment_info : {final_judgment_info}")
                        if isinstance(final_judgment_info, str):
                            if final_judgment_info.startswith("```"):
                                final_judgment_info = final_judgment_info.removeprefix("```json").removeprefix("```")
                                final_judgment_info = final_judgment_info.removesuffix("```").strip()
                            final_judgment_info = json.loads(final_judgment_info)

                        if final_judgment_info:
                            state.report_cases[case_id]['total_final_judgment_amount'] = final_judgment_info.get(
                                'total_final_judgment_amount')
                            state.report_cases[case_id]['judgment_date'] = final_judgment_info.get('judgment_date')

                            with open(files_dir + f"/final_judgment_{case_id}.json", 'w') as f:
                                json.dump(final_judgment_info, f, indent=2, default=str)
                            sync_final_judgment_extracted_case_data(case_id, final_judgment_info)
                    downloaded_files.append(file)
                    _cleanup_prefixed_files(files_dir, file_prefix)
                    break"""
                    break
                except (MaxRetryError, NewConnectionError):
                    close_extra_tabs(driver)
                    retry_attempt += 1
                    main_window = driver.current_window_handle
                    append_driver_log(id(driver), f"MaxRetryError/NewConnectionError in download_files for {filename}",
                                        case_id)
                except Exception as e:
                    close_extra_tabs(driver)
                    append_driver_log(id(driver),
                                        f"❌ Exception: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}",
                                        case_id)
                    traceback.print_exc()
            if retry_attempt >= max_retry_attempts:
                return 1, matching_rows

        _save_matching_files_log(case_id, files_dir, downloaded_files, file_name='_downloaded_files.txt')
        # ── Compare with previous run if case was state.processed before ────────────
        #from tracker import is_case_processed, get_case, mark_case_processed
        _save_matching_files_log(case_id, files_dir, downloaded_files, file_name='_downloaded_files.txt')
        return None, matching_rows  # Return matching_rows for potential resume


# ══════════════════════════════════════════════════════════════════════════════
# NJ PIPELINE — helpers defined below, process_nj_case is at end of this block
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1: NAVIGATE & LOGIN
# ══════════════════════════════════════════════════════════════════════════════

def _navigate_and_login_nj(driver, account, driver_pool, case_id, thread_num) -> SearchResult:
    """Navigate to NJ portal and login. Returns RETRY_NEEDED if login fails."""
    update_case_status(driver, case_id, "New Jersey", f"Starting (Thread {thread_num})",
                       details="Navigating to NJ Courts portal...")

    navigate_to_url_nj(driver)
    try:
        wait_for_page_to_load(driver)
    except TimeoutException:
        pass

    check_skip()

    update_case_status(driver, case_id, "New Jersey", f"Logging in (Thread {thread_num})",
                       details="Attempting login")

    cookie_file = f"cookies{account['index']}.pkl"
    if navigate_to_search_nj(driver, account, cookie_file,state.driver_pool):
        return SearchResult.RETRY_NEEDED

    check_skip()
    scroll_randomly(driver)

    return SearchResult.SUCCESS


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2: SEARCH CASE
# ══════════════════════════════════════════════════════════════════════════════

def _search_case_nj(driver, year, docket, driver_pool, account, case_id, thread_num) -> SearchResult:
    """Search for the case in NJ system. Returns NOT_FOUND if missing."""
    update_case_status(driver, case_id, "New Jersey",
                       f"Entering docket (Thread {thread_num})",
                       details=f"Entering {case_id}")

    return search_case_number_nj(driver, year, docket, state.driver_pool, account)




# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4: FINALIZE
# ══════════════════════════════════════════════════════════════════════════════

def _finalize_nj_case(case_id, files_dir, start_time, tracker=None):
    """Finalize case processing and update database."""
    duration = time.time() - start_time
    state.report_cases[case_id]['processing_duration'] = f"{duration:.2f}"
    log_message(f"✔️ Took {duration:.2f}s to process {case_id}")

    if state.report_cases[case_id]['status'] == "Completed":
        batch_name = _settings.get("batch_name", input_file.get().split("\\")[-1].split(".")[0])
        downloaded_files = [
            f.lower()
            for f in os.listdir(files_dir)
            if os.path.isfile(os.path.join(files_dir, f))
        ]

        has_complaint = any("complaint" in f for f in downloaded_files)

        has_judgment = any(
            "judgment" in f or "judgement" in f
            for f in downloaded_files
        )

        is_valid = has_complaint and has_judgment

        # Set valid flag BEFORE inserting/updating the case
        valid_flag(
            case_id,
            batch_name=batch_name
        )
        add_case_with_files(state.report_cases[case_id], file_source=files_dir, batch_name=batch_name, force_replace=True, tracker=tracker)

    try:
        snap_path = state.dump_to_file()
        log_message(f"🧾 State snapshot saved: {snap_path}")
    except Exception as e:
        log_message(f"⚠️ Could not save state snapshot: {e}")
    _update_status(case_id, CaseStatus.COMPLETED)
    check_and_update_batch_progress()





# ══════════════════════════════════════════════════════════════════════════════
# process_nj_case — Block-based pipeline via PipelineOrchestrator
# ══════════════════════════════════════════════════════════════════════════════

@skippable
def process_nj_case(year, docket, case_type, account, driver, driver_pool,
                    files_dir=".", start_index=0, browse_to_a_different_page=False,
                    matching_files=None) -> SearchResult:
    """
    Process a New Jersey court case through the 8-block pipeline.

    Blocks (in order):
      1. PrecheckBlock        — Zillow + SalesWeb eligibility
      2. CourtNavigationBlock — Login + docket entry
      3. CaseCheckingBlock    — Table, case info, skip check, property fetch
      4. FilePickingBlock     — Scan table for matching documents
      5. CourtDownloadingBlock — Download matched files
      6. ObituarySearchBlock  — Background obituary search (fire-and-observe)
      7. DeedSearchBlock      — Background deed search (fire-and-observe)
      8. DatabaseAddingBlock  — Persist final status + release driver
    """
    from pipeline.base import PipelineContext
    from pipeline.blocks import (
        CaseCheckingBlock,
        CourtDownloadingBlock,
        CourtNavigationBlock,
        DatabaseAddingBlock,
        DeedSearchBlock,
        FilePickingBlock,
        ObituarySearchBlock,
        PrecheckBlock,
    )
    from pipeline.orchestrator import PipelineOrchestrator

    case_id = f"f-{docket}-{year}"
    set_download_dir(driver, files_dir)
    driver.files_dir = files_dir

    ctx = PipelineContext(
        case_id=case_id,
        year=year,
        docket=docket,
        case_type=case_type,
        account=account,
        driver=driver,
        driver_pool=state.driver_pool,
        files_dir=files_dir,
        start_index=start_index,
        matching_files=matching_files or [],
    )

    orchestrator = PipelineOrchestrator(
        blocks=[
            PrecheckBlock(),
            CourtNavigationBlock(),
            CaseCheckingBlock(),
            FilePickingBlock(),
            CourtDownloadingBlock(),
            ObituarySearchBlock(),
            DeedSearchBlock(),
            DatabaseAddingBlock(),
        ],
        on_status_change=_emit_block_status,
    )

    return orchestrator.run(ctx)


def _emit_block_status(case_id: str, block_name: str, status, reason: Optional[str] = None) -> None:
    """
    Forwards block-status updates to the Flask/SocketIO layer so the
    case-monitor frontend can display live pipeline progress.
    """
    status_val = status.value if hasattr(status, "value") else str(status)
    try:
        from app import case_status
        if case_id in case_status:
            if "block_statuses" not in case_status[case_id]:
                case_status[case_id]["block_statuses"] = {}
            case_status[case_id]["block_statuses"][block_name] = status_val
            if reason:
                case_status[case_id]["details"] = f"[{block_name}] {status_val}: {reason}"
    except Exception:
        pass

    try:
        payload = {"case_id": case_id, "block": block_name, "status": status_val}
        if reason:
            payload["reason"] = reason
        _socketio.emit(
            "block_status",
            payload,
        )
    except Exception:
        pass



def _write_matching_rows_txt(txt_path, case_id, matching_files):
    """Dump matching rows to a debug txt file. Never raises."""
    try:
        os.makedirs(os.path.dirname(txt_path), exist_ok=True)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"Case: {case_id} | Total matching: {len(matching_files)}\n")
            f.write("=" * 60 + "\n")
            for i, file in enumerate(matching_files):
                f.write(f"[{i + 1}] row_index={file.get('row_index')} | "
                        f"name={file.get('name')} | "
                        f"filename={file.get('filename')}\n")
    except Exception as e:
        print(f"⚠️ Could not save matching rows txt: {e}")


def download_files_nj(driver, year, docket, driver_pool, files_dir, account, start_index=1, matching_files=[]):
    """Download court files for New Jersey cases with improved error handling"""


    case_id = f"f-{docket}-{year}"

    # Initialize tracking
    result = {
        'status': 'pending',
        'matching_rows': [],
        'files_downloaded': [],
        'errors': [],
        'final_judgment': False
    }
    _snoop_log = os.path.join(files_dir, "download_files_nj_case.log")
    with pysnooper.snoop(_snoop_log):
        try:
            # ============ STEP 1: Update Status ============
            update_case_status(driver, case_id, "New Jersey", f"Downloading (Thread {get_thread_number()})",
                               details="Checking for files")
            driver.state = "downloading"
            set_download_dir(driver, files_dir)

            # ============ STEP 2: Find Case Table ============
            table = _find_case_table(driver, case_id)
            if table is None:
                return _handle_no_table(driver, case_id, result)

            # ============ STEP 3: Get Case Information ============
            if matching_files is None:
                result = _get_case_information(driver, case_id, result, state)

                # Check if we should skip this case
                skip_result = _should_skip_case(driver, case_id, result, files_dir)
                if skip_result:
                    return skip_result

            # ============ STEP 4: Process Property Details ============
            property_future = _process_property_details(driver, case_id, result, files_dir)

            # ============ STEP 5: Scan Table for Matching Files ============
            rows = table.find_elements(By.TAG_NAME, "tr")
            total_rows = len(rows) - 1

            matching_rows_lock = threading.Lock()
            matching_rows = []

            matching_files = scan_table_multithreaded(
                driver, case_id, files_dir, state.report_cases, total_rows,
                matching_rows, matching_rows_lock,
                state.keyword_list, state.unwanted_list, "nj",
                start_index=start_index
            )

            # ============ STEP 6: Save Matching Files ============
            txt_path = _save_matching_files(case_id, files_dir, matching_files)
            result['matching_rows'] = matching_rows

            # ============ STEP 7: Process Special Files ============
            special_result = _process_special_files(driver, case_id, files_dir, matching_files, year, docket, account)
            if special_result:
                return special_result

            # ============ STEP 8: Download Files ============
            download_result = _download_files_with_retry(
                driver, case_id, year, docket, account,
                files_dir, matching_files, total_rows
            )

            if download_result['status'] == 'error':
                return download_result['row_index'], matching_rows

            result['final_judgment'] = download_result['final_judgment']

            # ============ STEP 9: Finalize ============
            print(f"property_future : {property_future}")
            _finalize_case(driver, case_id, property_future, result, files_dir)

            return None, matching_rows

        except Exception as e:
            return _handle_critical_error(driver, case_id, e, result)


# ============ HELPER FUNCTIONS ============

def _find_case_table(driver, case_id):
    """Find the case table with error handling"""
    try:
        return WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.ID, "caseActionTbId2")))
    except Exception as e:
        log_message(f"❌ [{case_id}] Table not found: {e}")
        traceback.print_exc()
        return None


def _handle_no_table(driver, case_id, result):
    """Handle case where no table is found"""
    if element_exists_id(driver, "caseSummaryDiv"):
        update_case_status(driver, case_id, "New Jersey", "Completed",
                           details="All files downloaded")
        state.report_cases[case_id]['status'] = "Completed"
        result['status'] = 'completed'
        return None, []

    result['status'] = 'error'
    result['errors'].append('No table found and no summary div')
    return 1, []  # Return start_index and empty list





def _should_skip_case(driver, case_id, result, files_dir):
    """Check if case should be skipped based on settings"""
    case_status_val = (state.report_cases.get(case_id, {}).get("court_case_status") or "").lower()
    main_defendant = (state.report_cases.get(case_id, {}).get("main_defendant") or "").lower()
    description_val = _get_description_value(case_id)

    skip_closed = _settings.get("skip_closed_cases", True)
    skip_business = _settings.get("skip_business", True)

    def _skip(reason):
        log_message(f"⏭️ [{case_id}] Skipping — {reason}")
        update_case_status(driver, case_id, "New Jersey", "Skipped", details=reason)
        state.report_cases[case_id]['status'] = "Skipped"
        check_and_update_batch_progress()
        delete_case_completely_from_supabase(case_id, files_dir)
        return None, []

    if skip_closed and "closed" in case_status_val:
        
        return _skip("case status is closed")

    if skip_business and any(kw in main_defendant for kw in SKIP_DEFENDANT_KEYWORDS):
        return _skip(f"defendant '{main_defendant}' matches skip keyword")

    if skip_business and description_val == "business":
        return _skip("description: business")

    return None


def _get_description_value(case_id):
    """Get description value from report_cases"""
    try:
        return next(
            (v or "" for k, v in state.report_cases.get(case_id, {}).items()
             if k.lower().startswith("description")),
            ""
        ).lower()
    except:
        return ""


def _process_property_details(driver, case_id, result, files_dir):
    """Process property details and submit to deed queue"""
    try:
        property_future = extract_property_details(driver, case_id, state.report_cases, files_dir)

        main_defendant = state.report_cases.get(case_id, {}).get("main_defendant")
        if main_defendant:
            _ensure_deed_worker()
            print(f" state.report_cases[case_id]['County'] putting {state.report_cases[case_id]['county']}")

            supabase_case_id = get_case_id_by_number(case_id)
            try:
                from pipeline.base import BlockStatus
                _emit_block_status(case_id, "Deed Search", BlockStatus.RUNNING)
            except Exception:
                pass
            state.deed_queue.put((
                "", "", files_dir, state.report_cases[case_id]['Block'],
                main_defendant, state.report_cases[case_id]['county'],
                supabase_case_id, case_id
            ))
            log_message(f"📜 [{case_id}] Deed search submitted for {main_defendant} ({state.report_cases[case_id].get('county')})")

        return property_future

    except Exception as e:
        log_message(f"⚠️ [{case_id}] Property details error: {e}")
        traceback.print_exc()
        return None


def _save_matching_files(case_id, files_dir, matching_files):
    """Save matching files to text file"""
    txt_path = os.path.join(files_dir, f"matching_rows_{case_id}.txt")
    try:
        _write_matching_rows_txt(txt_path, case_id, matching_files)
    except Exception as e:
        log_message(f"⚠️ [{case_id}] Failed to write matching rows: {e}")
    return txt_path


def _process_special_files(driver, case_id, files_dir, matching_files, year, docket, account, ):
    """Process special files (order_to_vacate, cancellation, bankruptcy)"""

    for file_info in matching_files:
        filename = file_info['filename'].lower()
        row_index = file_info['row_index']

        # Check for order_to_vacate or cancellation
        if ("order_to_vacate" in filename and "denied" not in filename) or "cancellation" in filename:
            batch_name = _settings.get("batch_name", input_file.get().split("\\")[-1].split(".")[0])
            _record_rip_case()
            mark_case_as_rip(case_id, files_dir, state.report_cases,
                             f"order_to_vacate is present in files: {filename}",
                             batch_name=batch_name)
            update_case_status(driver, case_id, "New Jersey", "Skipped",
                               details=f"Special file: {filename}")
            state.report_cases[case_id]['status'] = "Skipped"
            return None, matching_files

        # Check for bankruptcy
        if "bankruptcy" in filename:
            try:
                result = _handle_bankruptcy_file(driver, case_id, files_dir, file_info, year, docket, account)
                if not result:
                    batch_name = _settings.get("batch_name", input_file.get().split("\\")[-1].split(".")[0])
                    _record_rip_case()
                    mark_case_as_rip(case_id, files_dir, state.report_cases,
                                     f"order_to_vacate is present in files: {filename}",
                                     batch_name=batch_name)
                    update_case_status(driver, case_id, "New Jersey", "Skipped",
                                       details=f"Special file: {filename}")
                    state.report_cases[case_id]['status'] = "Skipped"
                    return None, matching_files
            except Exception as e:
                log_message(f"❌ [{case_id}] Bankruptcy handling error: {e}")
                traceback.print_exc()

    return None


def _handle_bankruptcy_file(driver, case_id, files_dir, file_info, year, docket, account):
    """Handle bankruptcy file processing: download, rename, and check case status."""
    row_index = file_info['row_index']
    filename = file_info['filename']

    try:
        # Find the cell
        try:
            cell = driver.find_element(By.XPATH,
                                       f'//*[@id="caseActionTbId2:tbody_element"]/tr[{row_index + 1}]/td[2]')
        except NoSuchElementException:
            cell = driver.find_element(By.XPATH,
                                       f'//*[@id="caseActionTbId2:tbody_element"]/tr[{row_index + 1}]/td[3]')

        # Click the file
        file_element = WebDriverWait(cell, 5).until(
            EC.element_to_be_clickable((By.XPATH, './/*[starts-with(@id, "caseActionTbId2:")]')))

        driver.execute_script("arguments[0].click();", file_element)

        # Wait for dialog
        while not element_exists_id(driver, "documentsDialog"):
            try:
                driver.execute_script("arguments[0].click();", file_element)
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].scrollIntoView();", file_element)

        # download_filing_link_nj only returns 0/1 — it never tells us the
        # saved path — so snapshot the folder first and diff afterward,
        # exactly like every other file uses wait_for_new_download_and_rename_nj.
        before_files = (set(glob.glob(os.path.join(files_dir, "*.pdf"))) |
                        set(glob.glob(os.path.join(files_dir, "*.crdownload"))))

        # Download filing link
        dfl = download_filing_link_nj(driver, year, docket, account, file_element,
                                      files_dir=files_dir, select="all")
        if dfl:
            return None

        # This was the missing step — actually rename the downloaded file.
        bankruptcy_path = wait_for_new_download_and_rename_nj(
            driver, files_dir, before_files, filename, case_id
        )
        if not bankruptcy_path:
            log_message(f"⚠️ [{case_id}] Bankruptcy file downloaded but never appeared on disk to rename")
            return row_index

        # Ask the LLM whether this bankruptcy is still open/blocking foreclosure.
        try:
            raw_status = get_bankruptcy_case_status(bankruptcy_path)
            status_data = json.loads(raw_status)
        except Exception as e:
            log_message(f"⚠️ [{case_id}] Could not parse bankruptcy status for {bankruptcy_path}: {e}")
            traceback.print_exc()
            return row_index

        bankruptcy_status = status_data.get("bankruptcy_case_status")
        log_message(f"📄 [{case_id}] Bankruptcy status: {bankruptcy_status} "
                    f"({status_data.get('basis', 'no basis given')})")

        if bankruptcy_status == "accepted":
            batch_name = _settings.get("batch_name", input_file.get().split("\\")[-1].split(".")[0])
            reason = f"Bankruptcy case accepted: {status_data.get('basis', '')}".strip()
            _record_rip_case()
            mark_case_as_rip(case_id, files_dir, state.report_cases, reason, batch_name=batch_name)
            update_case_status(driver, case_id, "New Jersey", "Skipped",
                               details=f"Bankruptcy accepted: {filename}")
            state.report_cases[case_id]['status'] = "Skipped"
            return None

        return row_index

    except Exception as e:
        log_message(f"❌ [{case_id}] Bankruptcy download error: {e}")
        traceback.print_exc()
        return None


def _download_files_with_retry(driver, case_id, year, docket, account,
                               files_dir, matching_files, total_rows):
    """Download files with retry logic"""
    _snoop_log = os.path.join(files_dir, "_download_files_with_retry_snoop.log")

    with pysnooper.snoop(_snoop_log):
        MAX_RETRIES = 3
        result = {
            'status': 'success',
            'row_index': None,
            'final_judgment': False,
            'failed_files': []
        }

        files_to_download = list(matching_files)

        for attempt in range(1, MAX_RETRIES + 1):
            if not files_to_download:
                break

            if attempt > 1:
                print(f"🔁 Retry attempt {attempt}/{MAX_RETRIES} — {len(files_to_download)} file(s) remaining")

            failed_files = []

            for file_info in files_to_download:
                # Check if stopped
                if not state.running:
                    log_message("Processing stopped by user")
                    result['status'] = 'stopped'
                    return result

                # Update status
                update_case_status(driver, case_id, "New Jersey",
                                   f"Downloading (Thread {get_thread_number()})",
                                   details=f"Downloading {file_info['filename']} ({case_id})"
                                           + (f" [retry {attempt}]" if attempt > 1 else ""))

                try:
                    # Download the file
                    success = download_file_nj(driver, file_info, files_dir, case_id,
                                               year, docket, account, False)

                    if not success:
                        failed_files.append(file_info)
                        log_message(f"❌ [{case_id}] Failed: {file_info['filename']}")
                    else:
                        # Check for final judgment
                        filename_lower = file_info['filename'].lower()
                        if "final_judgment" in filename_lower or "uncontested" in filename_lower:
                            final_judgment_flag(case_id, flag=True)
                            result['final_judgment'] = True

                except Exception as e:
                    log_message(f"❌ [{case_id}] Exception downloading {file_info['filename']}: {e}")
                    traceback.print_exc()
                    failed_files.append(file_info)

            # Verify files exist on disk
            failed_files = _verify_downloaded_files(files_dir, files_to_download, failed_files)

            # Prepare for next attempt
            files_to_download = failed_files
            result['failed_files'] = failed_files

        # Final attempt - try to recover remaining files
        if files_to_download:
            log_message(f"⚠️ [{case_id}] {len(files_to_download)} files still missing after {MAX_RETRIES} retries")
            _log_missing_files(case_id, files_dir, files_to_download)

            # One final in-place pass
            for file_info in files_to_download:
                try:
                    success = download_file_nj(driver, file_info, files_dir, case_id,
                                               year, docket, account, False)
                    if success:
                        log_message(f"✅ [{case_id}] Final pass recovered: {file_info['filename']}")
                    else:
                        result['status'] = 'error'
                        result['row_index'] = file_info.get('row_index')
                        return result
                except Exception as e:
                    log_message(f"❌ [{case_id}] Final pass failed: {e}")
                    result['status'] = 'error'
                    result['row_index'] = file_info.get('row_index')
                    return result

        return result




def _log_missing_files(case_id, files_dir, files_to_download):
    """Log missing files to text file"""
    txt_path = os.path.join(files_dir, f"matching_rows_{case_id}.txt")
    try:
        with open(txt_path, 'a', encoding='utf-8') as f:
            f.write("\n" + "=" * 60 + "\n")
            f.write(f"STILL MISSING AFTER RETRIES:\n")
            for file_info in files_to_download:
                f.write(f"  row_index={file_info.get('row_index')} | filename={file_info.get('filename')}\n")
    except Exception as e:
        log_message(f"⚠️ [{case_id}] Failed to log missing files: {e}")


def _finalize_case(driver, case_id, property_future, result, files_dir):
    """Finalize case processing"""
    try:
        # Wait for property details
        if property_future is not None:
            try:
                property_future.result(timeout=90)
                log_message(f"✅ [{case_id}] Property details done")
            except Exception as e:
                traceback.print_exc()
                traceback.print_exc()
                log_message(f"⚠️ [{case_id}] Property details failed/timed out: {e}")

        # Update final judgment flag if not set
        if not result['final_judgment']:
            final_judgment_flag(case_id, flag=False)

        # Update status
        update_case_status(driver, case_id, "New Jersey", "Completed",
                           details="All files downloaded")
        state.report_cases[case_id]['status'] = "Completed"


        result['status'] = 'completed'

    except Exception as e:
        log_message(f"❌ [{case_id}] Finalization error: {e}")
        traceback.print_exc()


def _handle_critical_error(driver, case_id, error, result):
    """Handle critical errors"""
    log_message(f"❌ [{case_id}] Critical error: {error}")
    traceback.print_exc()

    update_case_status(driver, case_id, "New Jersey", "Error",
                       details=f"Critical error: {str(error)}")
    state.report_cases[case_id]['status'] = "Error"

    return None, result.get('matching_rows', [])


# ══════════════════════════════════════════════════════════════════════════════
# REMAINING PROCESS_* FUNCTIONS  (legacy / county-specific)
# ══════════════════════════════════════════════════════════════════════════════




# ── NJ helpers ────────────────────────────────────────────────────────────────

def wait_for_new_download_and_rename_nj(driver, download_dir, before_files, new_filename,
                                        case_id, county="", timeout=20):
    end_time = time.time() + timeout
    time.sleep(3)
    while time.time() < end_time:
        if state.force_stop:
            return
        current_files = (set(glob.glob(os.path.join(download_dir, "*.pdf"))) |
                         set(glob.glob(os.path.join(download_dir, "*.crdownload"))))

        new_files = current_files - before_files
        if new_files:
            new_file = sorted(new_files, key=os.path.getctime)[0]
            final_file = new_file[:-len(".crdownload")] if new_file.endswith(".crdownload") else new_file
            while os.path.exists(final_file + ".crdownload"):
                time.sleep(0.5)

            # Generate the path first
            filename = sanitize_filename(new_filename)
            new_path = os.path.join(download_dir, filename)

            # NOW check if new_path has .pdf extension, add if not
            if not new_path.lower().endswith('.pdf'):
                new_path = new_path + '.pdf'

            time.sleep(0.5)
            while True:
                try:
                    shutil.move(final_file, new_path)
                    break
                except FileNotFoundError:
                    return None
            state.report_cases[case_id]['files'].append(os.path.basename(new_path))
            return new_path
    driver.switch_to_window(driver.window_handles[0])
    return None


def login_nj(driver, account, driver_pool, cookie_file="login_cookies1.pkl"):
    try:
        files_dir = driver.files_dir
    except:
        files_dir = "."
    with pysnooper.snoop(os.path.join(files_dir, "login_nj.log")):
        driver.state = "logging in"
        cursor = WebCursor(driver)
        cursor.show_cursor()
        if is_logged_in(driver):
            return
        user_id = account["user_id"]
        password = account["password"]
        for attempt in range(1, 4):
            try:
                captcha = check_main_frame(driver, state.driver_pool)
                if captcha:
                    return 1
                print(f"{threading.current_thread().name}: 🔐 Attempt {attempt} to login...")
                navigate_to_url_nj(driver)
                wait = WebDriverWait(driver, 10)
                username_field = wait.until(EC.presence_of_element_located((By.ID, 'userid')))

                cursor.click_on(username_field, speed=random.uniform(0.4, 1.3))
                human_type(username_field, user_id)
                password_field = wait.until(EC.presence_of_element_located((By.ID, 'passwd')))
                cursor.click_on(password_field, speed=random.uniform(0.4, 1.3))
                human_type(password_field, password)
                login_button = wait.until(EC.presence_of_element_located((By.ID, 'a')))
                cursor.click_on(login_button, speed=random.uniform(0.4, 1.3))
                wait.until(EC.presence_of_element_located((By.ID, "searchByDocForm:idCivilDocketNum")))
                return
            except (TimeoutException, NoSuchElementException, StaleElementReferenceException,
                    ReadTimeoutError, InvalidSessionIdException):
                print(f"{threading.current_thread().name}: ⚠️ Login attempt {attempt} failed. Retrying...")
                navigate_to_url_nj(driver)
        return 1


def enter_docket_number_nj(driver, docket, year, wait):
    cursor = WebCursor(driver)
    cursor.show_cursor()
    docket_num_field = wait.until(EC.presence_of_element_located((By.ID, 'searchByDocForm:idCivilDocketNum')))
    cursor.click_on(docket_num_field)
    human_type(docket_num_field, docket)
    docket_year_field = wait.until(EC.presence_of_element_located((By.ID, 'searchByDocForm:idCivilDocketYear')))
    time.sleep(random.uniform(0.05, 1))
    cursor.click_on(docket_year_field)
    human_type(docket_year_field, year)
    search_button = wait.until(EC.presence_of_element_located((By.ID, 'searchByDocForm:searchBtnDummy')))
    cursor.click_on(search_button)
    wait_for_page_to_load(driver)
    time.sleep(random.uniform(0.5, 1))
    try:
        error_msg = ""
        while not error_msg:
            cursor.click_on(search_button)
            error_msg = wait.until(EC.presence_of_element_located((By.ID, 'errInfoMsg'))).text
    except Exception:
        pass
    time.sleep(random.randint(1, 2))


def search_case_number_nj(driver, year, docket, driver_pool, account) -> SearchResult:
    case_id = f"f-{docket}-{year}"
    driver.state = "entering docket"
    max_resets = random.randint(1, 2)
    max_attempts = random.randint(1, 2)
    wait = WebDriverWait(driver, 6)

    for reset_attempt in range(1, max_resets + 1):
        for attempt in range(1, max_attempts + 1):
            maximize_driver(driver)
            print(f"\n{threading.current_thread().name}: Attempt {attempt}/{max_attempts} to enter f-{docket}-{year}")
            try:
                if check_for_files_page(driver, timeout=10):
                    return SearchResult.SUCCESS
                enter_docket_number_nj(driver, docket, year, wait)

                time.sleep(random.randint(1, 2))
                wait_for_page_to_load(driver)
                cek = check_error_message(driver, 5)
                ct = check_for_files_page(driver)
                if not cek and ct:
                    print(f"{threading.current_thread().name}: ✅ Search completed!")
                    return SearchResult.SUCCESS
                else:
                    wait.until(EC.presence_of_element_located((By.ID, 'errInfoMsg')))
                    error_msg = wait.until(EC.presence_of_element_located((By.ID, 'errInfoMsg'))).text
                    print(f"error_msg : {error_msg}")
                    if "not found" in error_msg.lower():
                        driver.save_screenshot(
                            f"{driver.files_dir}/nj_screenshots/docket_not_found_{year}-{docket}.png")
                        return SearchResult.NOT_FOUND
                    if element_exists_xpath(driver, "/html/body/div[1]/div/div/div[1]/div[2]/div[2]/h2[1]"):
                        if random.random() < 0.5:
                            request_url(driver, "https://portal-cloud.njcourts.gov/prweb/PRAuth/app/ESSOPortal")
                            time.sleep(random.uniform(3, 7))
                        request_url(driver, NJ_LOGIN_PAGE)
                        try:
                            error = driver.find_element('xpath', '/html/body/div[1]/div/div/div[1]/div[1]/div')
                            if error:
                                print("CAPTCHA:", error.text)
                        except Exception:
                            pass
                if element_exists_id(driver, 'searchByDocForm:idCivilDocketNum'):
                    continue
            except (StaleElementReferenceException, ElementNotInteractableException):
                if not check_error_message(driver, 1) and check_for_files_page(driver, timeout=1):
                    return SearchResult.SUCCESS
                make_sure_tab1_is_selected(driver)
            except TimeoutException:
                request_url(driver, NJ_LOGIN_PAGE)
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
                traceback.print_exc()
                navigate_to_url_nj(driver)
                refresh_url(driver)

        simulate_human_browsing2(driver)
        time.sleep(random.uniform(3, 8))
        request_url(driver, NJ_LOGIN_PAGE)

    if state.driver_pool.is_any_downloading():
        return search_case_number_nj(driver, year, docket, state.driver_pool, account)

    final_output_folder = state.current_batch_folder
    file_dir = f"{final_output_folder}/f-{docket}-{year}-new jersey"
    log_message(f"Max resets exceeded for account {account['user_id']}, switching to backup...")
    set_download_dir(driver, file_dir)
    index = account["index"]
    cookie_file = f"cookies{index}.pkl"
    if os.path.exists(cookie_file):
        os.remove(cookie_file)
    backup_accounts = [acc for acc in accounts if acc["type"] == "backup"]
    if backup_accounts:
        backup_account = random.choice(backup_accounts)
        log_message(f"Switching to backup account: {backup_account['user_id']}")
        return SearchResult.RETRY_NEEDED

    log_message("No backup accounts available!")
    return SearchResult.RETRY_NEEDED


def download_filing_link_nj(driver, year, docket, account, file_element, select="all", files_dir=None, _index=0):
    if not hasattr(download_filing_link_nj, "counter"):
        download_filing_link_nj.counter = 0
    download_filing_link_nj.counter += 1
    _snoop_log = os.path.join(files_dir,
                              f"snoop_download_filing_link_{download_filing_link_nj.counter}.log") if files_dir else None
    with pysnooper.snoop(_snoop_log):
        something_is_selected = False
        while not element_exists_id(driver, 'documentDetails:j_id_1m9'):
            file_element.click()
            time.sleep(1)
        checkbox_rows = driver.find_elements('xpath', '/html/body/div[3]/div[2]/form/table[1]/tbody//tr')
        if select == "all":
            while not driver.find_element(By.ID, "documentDetails:j_id_1m9").get_attribute("checked"):
                try:
                    wait_and_click(driver, By.ID, "documentDetails:j_id_1m9")
                except TimeoutException:
                    return
                time.sleep(0.5)
                something_is_selected = True
        else:
            for i, row in enumerate(checkbox_rows):
                try:
                    if select.lower().strip() in row.text.lower().strip():
                        checkbox = row.find_element(By.XPATH, './/input[@type="checkbox"]')
                        while not checkbox.get_attribute("checked"):
                            try:
                                checkbox.click()
                                checkbox = row.find_element(By.XPATH, './/input[@type="checkbox"]')
                                time.sleep(random.uniform(0.1, 0.5))
                                something_is_selected = True
                                break
                            except Exception:
                                print(f"i : {i}")
                                traceback.print_exc()
                except StaleElementReferenceException:
                    print("StaleElementReferenceException")
                    pass
        timeout = 30  # Maximum seconds to wait
        start_time = time.time()

        while not something_is_selected and element_exists_id(driver, "documentDetails:j_id_1m9"):
            # Check if timeout has been exceeded
            if time.time() - start_time > timeout:
                print(f"⚠️ Timeout after {timeout}s - could not select document")
                return 1

            try:
                wait_and_click(driver, By.ID, "documentDetails:j_id_1m9", timeout=5)
                time.sleep(0.5)
                something_is_selected = True
            except Exception:
                file_element.click()
                print("StaleElementReferenceException - retrying...")
                time.sleep(0.5)  # Small delay before retry
                pass
        click_on_save(driver)
        while True:
            try:
                wait_and_click(driver, By.XPATH, '/html/body/div[3]/div[1]/button')

            except TimeoutException:
                break
        return 0





def download_file_nj(driver, file, files_dir, case_id, year, docket, account, rip):
    if not hasattr(download_file_nj, "counter"):
        download_file_nj.counter = 0
    download_file_nj.counter += 1
    _cleanup_prefixed_files(files_dir, "CivilCaseJacket")
    before_files = set(glob.glob(os.path.join(files_dir, "*.pdf")))
    _snoop_log = os.path.join(files_dir, f"download_file_nj_{download_file_nj.counter}.log") if files_dir else None
    with pysnooper.snoop(_snoop_log):
        filename = file['filename']
        row_index = file['row_index']
        name = file['name']
        transaction_id = file['transaction_id']

        MAX_RETRIES = 3
        retry_count = 0
        success = False
        while retry_count < MAX_RETRIES and not success:

            if state.force_stop:
                return
            try:
                # //*[@id="caseActionTbId2:2:singleFilingLink"]
                driver.switch_to_window(driver.window_handles[-1])
                try:
                    cell = driver.find_element(By.XPATH,
                                               f'//*[@id="caseActionTbId2:tbody_element"]/tr[{row_index + 1}]/td[2]')
                except NoSuchElementException:
                    cell = driver.find_element(By.XPATH,
                                               f'//*[@id="caseActionTbId2:tbody_element"]/tr[{row_index + 1}]/td[3]')
                try:
                    file_element = WebDriverWait(cell, 5).until(
                        EC.element_to_be_clickable((By.XPATH, './/*[starts-with(@id, "caseActionTbId2:")]')))
                except TimeoutException:
                    update_case_status(driver, case_id, "New Jersey", "Error", details="All files downloaded")
                    return 0
                cleanup_unwanted_files(files_dir)
                set_download_dir(driver, files_dir)
                new_path = os.path.join(files_dir, filename)
                if os.path.exists(new_path):
                    return True
                if name:
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", file_element)
                    while not element_exists_id(driver, "documentsDialog"):
                        try:
                            driver.execute_script("arguments[0].click();", file_element)
                        except ElementClickInterceptedException:
                            driver.execute_script("arguments[0].scrollIntoView();", file_element)

                    if "complaint" in filename.lower():
                        dfl = download_filing_link_nj(driver, year, docket, account, file_element, files_dir=files_dir,
                                                      select="Complaint")
                    elif "final_judgment" in filename.lower() and not ("uncontested" in filename.lower()):
                        dfl = download_filing_link_nj(driver, year, docket, account, file_element, files_dir=files_dir,
                                                      select="Proposed Judgment")
                    elif "dismissal" in filename.lower():
                        dfl = download_filing_link_nj(driver, year, docket, account, file_element, files_dir=files_dir,
                                                      select="partial dismissal")
                    else:
                        dfl = download_filing_link_nj(driver, year, docket, account, file_element, files_dir=files_dir,
                                                      select="all")
                    if dfl:
                        return row_index
                else:
                    try:
                        file_button = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH,
                                                        f"/html/body/div[1]/div[2]/div/div[2]/div[2]/div[3]/form/div/div[2]/table/tbody/tr[{row_index + 1}]/td[2]/a[1]")))
                    except TimeoutException:
                        update_case_status(driver, case_id, "New Jersey", "Error", details="Error")
                        state.report_cases[case_id]['status'] = "Error"
                        return 0
                    driver.execute_script("arguments[0].click();", file_button)

                path = wait_for_new_download_and_rename_nj(driver, files_dir, before_files, filename, case_id,
                                                           county="New Jersey")
                # delete_case_jacket(files_dir)
                if path:
                    success = True
                    state.report_cases[case_id]['files'].append(filename)

                    if "complaint" in filename.lower():
                        complaint_info = extract_complaint(path)
                        print(f"complaint path : {path}")
                        print(f"complaint_info : {complaint_info}")
                        if isinstance(complaint_info, str):
                            complaint_info = json.loads(complaint_info)

                        if complaint_info:
                            state.report_cases[case_id]['mortgage_execution_date'] = complaint_info.get(
                                'mortgage_execution_date')
                            state.report_cases[case_id]['original_mortgage_amount'] = complaint_info.get(
                                'original_mortgage_amount')
                            state.report_cases[case_id]['interest_rate'] = complaint_info.get('interest_rate')
                            state.report_cases[case_id]['deceased_persons'] = complaint_info.get('deceased_persons')
                            with open(files_dir + f"/complaint_{case_id}.json", 'w') as f:
                                json.dump(complaint_info, f, indent=2, default=str)
                            sync_complaint_extracted_case_data(case_id, complaint_info)
                    elif "final_judgment" in filename.lower() or "uncontested" in filename.lower():

                        final_judgment_info = extract_final_judgment(path)
                        print(f"final_judgment_info : {final_judgment_info}")
                        if isinstance(final_judgment_info, str):
                            final_judgment_info = final_judgment_info.strip()

                            # Remove Markdown code fences if the model returned ```json ... ```
                            if final_judgment_info.startswith("```"):
                                final_judgment_info = final_judgment_info.removeprefix("```json").removeprefix("```")
                                final_judgment_info = final_judgment_info.removesuffix("```").strip()

                            if final_judgment_info:
                                try:
                                    final_judgment_info = json.loads(final_judgment_info)
                                except json.JSONDecodeError as e:
                                    print(f"Warning: Invalid JSON from extract_final_judgment: {e}")
                                    print(f"Content was: {repr(final_judgment_info)}")
                                    final_judgment_info = None
                            else:
                                final_judgment_info = None
                                
                        if final_judgment_info:
                            sync_final_judgment_extracted_case_data(case_id, final_judgment_info)
                            state.report_cases[case_id]['judgment_date'] = final_judgment_info.get("judgment_date")
                            state.report_cases[case_id]['total_final_judgment_amount'] = final_judgment_info.get(
                                "total_final_judgment_amount")
                            if final_judgment_info.get("total_final_judgment_amount") and state.report_cases[case_id][
                                'zestimate'] and not state.report_cases[case_id]['Equity']:
                                zestimate = round(float(state.report_cases[case_id]['zestimate']), 2)
                                final_judg = round(float(
                                    final_judgment_info.get("total_final_judgment_amount").replace('$', '').replace(',',
                                                                                                                    '').strip()),
                                    2)
                                state.report_cases[case_id]['Equity'] = zestimate - final_judg

                else:
                    retry_count += 1
                if rip:
                    update_case_status(driver, case_id, "New Jersey", "Error", details="Error")
                    state.report_cases[case_id]['status'] = "Error"
                    return
            except Exception as e:
                retry_count += 1
                traceback.print_exc()
        return success


def download_files_pin(driver, case_id, files_dir="."):
    matching_rows_lock = threading.Lock()
    table_length = 0
    while table_length == 0:
        files_table = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="eventList"]/tbody')))
        files_rows = files_table.find_elements(By.TAG_NAME, "tr")
        table_length = len(files_rows)
    wait = WebDriverWait(driver, 10)
    original_window = driver.current_window_handle
    time.sleep(5)
    if table_length <= 0:
        return
    matching_rows = []
    matching_rows = scan_table_multithreaded(
        driver=driver, case_id=case_id, files_dir=files_dir, report_cases=state.report_cases,
        total_rows=table_length, matching_rows=matching_rows, matching_rows_lock=matching_rows_lock,
        keyword_list=state.keyword_list, unwanted_list=state.unwanted_list, county="pin", start_index=1)
    for row in list(matching_rows):
        try:
            i = row["row_index"]
            link_xpath = f'//*[@id="eventList"]/tbody/tr[{i}]/td[12]/a'
            filename = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, f'//*[@id="eventList"]/tbody/tr[{i}]/td[2]/a'))).text
            update_case_status(driver, case_id, "New Jersey", "Downloading",
                               details=f"Downloaded file {i + 1}/{table_length}: {filename} ({case_id})")
            if (not any(w.lower() in filename.lower() for w in DEFAULT_KEYWORDS) or
                    any(b.lower() in filename.lower() for b in DEFAULT_UNWANTED)):
                continue
            wait_and_click(driver, By.XPATH, link_xpath)
            wait.until(lambda d: len(d.window_handles) > 1)
            new_tab = [h for h in driver.window_handles if h != original_window][0]
            driver.switch_to.window(new_tab)
            try:
                before_files = set(glob.glob(os.path.join(files_dir, "*.pdf")))
                wait_for_page_to_load(driver)
                while not element_exists_id(driver, 'thumbnail'):
                    time.sleep(0.5)
                time.sleep(1)
                set_download_dir(driver, files_dir)
                download_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, '//*[@id="doc-viewer-id"]/div/div[12]/div[1]/div/div/span[1]/div[6]/div[1]')))
                driver.execute_script("arguments[0].click();", download_button)
                wait_and_click(driver, By.XPATH, link_xpath)
                time.sleep(1)
                wait_for_new_download_and_rename_nj(driver, files_dir, before_files,
                                                    filename, case_id, county="New Jersey")
            except Exception as e:
                print(f"Button not clickable in new tab for row {i}: {e}")
            driver.switch_to.window(driver.window_handles[-1])
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
            time.sleep(1)
        except Exception:
            traceback.print_exc()
            continue


# ── download wait / rename helpers ────────────────────────────────────────────

def wait_for_new_download_and_rename(driver, download_dir, before_files, new_filename,
                                     case_id, county="", timeout=50):
    start_time = time.time()
    end_time = start_time + timeout
    cleanup_unwanted_files(download_dir)
    time.sleep(1.5)
    while time.time() < end_time:
        if _should_stop_download():
            return None
        cancel_all_downloads(driver)
        new_file_path = _detect_new_file(download_dir, before_files)
        if new_file_path:
            state.report_cases[case_id]['files'].append(new_filename)

            return _process_and_rename_file(driver=driver, new_file_path=new_file_path,
                                            download_dir=download_dir, new_filename=new_filename,
                                            case_id=case_id, county=county,
                                            start_time=start_time, timeout=timeout)
        time.sleep(0.5)
    return None


def _should_stop_download():
    return getattr(state, 'force_stop', False)


def _get_current_download_files(download_dir):
    return (set(glob.glob(os.path.join(download_dir, "*.pdf"))) |
            set(glob.glob(os.path.join(download_dir, "*.crdownload"))))


def _detect_new_file(download_dir, before_files):
    current_files = _get_current_download_files(download_dir)
    new_files = current_files - before_files
    if not new_files:
        return None
    safe_files = [f for f in new_files if os.path.exists(f)]
    if not safe_files:
        time.sleep(0.5)
        return None
    return sorted(safe_files, key=os.path.getctime)[0]


def _get_final_file_path(file_path):
    return file_path[:-len(".crdownload")] if file_path.endswith(".crdownload") else file_path


def _wait_for_download_completion(driver, final_file, case_id, county, start_time, timeout):
    crdownload_path = f"{final_file}.crdownload"
    while os.path.exists(crdownload_path):
        if time.time() - start_time > timeout:
            cancel_all_downloads(driver, timeout)
            return False
        timeout = _update_download_progress(driver, case_id, county, timeout)
        time.sleep(0.5)
    return True


def _update_download_progress(driver, case_id, county, timeout=60):
    try:
        file, status, progress, url = get_current_downloads_state(driver)
        updated_timeout = get_timeout(status, timeout)
        if updated_timeout:
            timeout = updated_timeout
        if not status:
            if url:
                request_url(driver, url)
            time.sleep(2)
        thread_num = _get_thread_number()
        update_case_status(driver, case_id, county, f"Downloading (Thread {thread_num})",
                           progress_down=status)
        return timeout
    except NoSuchWindowException:
        pass


def _get_thread_number():
    pattern = r'ThreadPoolExecutor-\d+_(\d+)'
    thread_name = threading.current_thread().name
    match = re.search(pattern, thread_name)
    return int(match.group(1)) + 1 if match else 0


def _ensure_pdf_extension(filename):
    return filename if ".pdf" in filename else f"{filename}.pdf"


def _rename_downloaded_file(source_path, download_dir, new_filename):
    if not os.path.exists(source_path):
        return None
    new_filename = _ensure_pdf_extension(new_filename)
    new_path = os.path.join(download_dir, new_filename)
    while True:
        try:
            shutil.move(source_path, new_path)
            break
        except PermissionError:
            pass
    return new_path


def _process_and_rename_file(driver, new_file_path, download_dir, new_filename,
                             case_id, county, start_time, timeout):
    final_file = _get_final_file_path(new_file_path)
    completed = _wait_for_download_completion(driver=driver, final_file=final_file,
                                              case_id=case_id, county=county,
                                              start_time=start_time, timeout=timeout)
    if not completed:
        return 0
    return _rename_downloaded_file(final_file, download_dir, new_filename)



# ══════════════════════════════════════════════════════════════════════════════
# GUI FUNCTIONS — replaced by web_gui equivalents
# update_case_status, clear_case_status, log_message, update_progress are
# all imported from app at the top of this file.
# The functions below are kept as thin wrappers or no-ops where the web GUI
# handles everything via WebSocket.
# ══════════════════════════════════════════════════════════════════════════════


def remove_selected_cases(case_ids: list):
    """
    Web equivalent of the Tkinter remove_selected_cases().
    Called from app.py's /api/cases/remove endpoint, which passes case_ids.
    """
    ids_to_remove = set(str(i).strip() for i in case_ids)
    for cid in ids_to_remove:
        case_status.pop(cid, None)

    with case_queue.mutex:
        all_items = list(case_queue.queue)
        case_queue.queue.clear()
        case_queue.all_tasks_done.notify_all()
        case_queue.unfinished_tasks = 0

    kept = []
    for item in all_items:
        year, docket, court_type, processor_name = item
        case_obj = Case(year=year, case_number=docket, county=processor_name, case_type=court_type)
        if case_obj.id.strip() not in ids_to_remove:
            kept.append(item)

    for item in kept:
        case_queue.put(item)

    removed_count = len(all_items) - len(kept)
    log_message(f"🗑️ Removed {removed_count} case(s) from queue: {', '.join(ids_to_remove)}")
    return removed_count




def save_batch_folder_to_excel(file_path, batch_folder):
    try:
        df = pd.read_excel(file_path)
        if len(df) > 0 and str(df.iloc[0, 0]).startswith("BATCH_FOLDER:"):
            df.iloc[0, 0] = f"BATCH_FOLDER:{batch_folder}"
        else:
            new_row = pd.DataFrame([[f"BATCH_FOLDER:{batch_folder}", "", ""]], columns=df.columns[:3])
            df = pd.concat([new_row, df], ignore_index=True)
        df.to_excel(file_path, index=False)
        log_message(f"💾 Saved batch folder path to Excel: {batch_folder}")
    except Exception as e:
        log_message(f"Error saving batch folder to Excel: {str(e)}")



# ══════════════════════════════════════════════════════════════════════════════
# LIFECYCLE SUPERVISOR & EMERGENCY SHUTDOWN MECHANICS
# ══════════════════════════════════════════════════════════════════════════════

def run_with_cleanup():
    """Background lifecycle runner and execution supervisor.

    Executes `process_cases()` within a dedicated daemon thread and guarantees
    that the system transitions cleanly into an 'Idle' / 'Ready' state upon
    completion, whether the batch finishes normally or raises an unhandled exception.

    Teardown Workflow:
    ------------------
    - Flips `state.running` and `state.force_stop` flags to False.
    - Broadcasts the updated `processing_state` (running=False) via WebSocket to
      all connected front-end clients.
    - Resets progress bars and status indicators to 'Ready'.
    """
    try:
        process_cases()
    except Exception as e:
        log_message(f"Error in processing: {e}")
        traceback.print_exc()
    finally:
        # Guarantee state flag reset regardless of normal exit or unhandled failure
        state.running = False
        state.force_stop = False
        try:
            _socketio.emit("processing_state", {"running": False})
        except Exception:
            pass
        log_message("🟢 Processing stopped/reset - ready for new batch")
        update_progress(0)
        set_status_text("Ready")


# Spawn the initial lifecycle runner daemon thread on module load
thread = threading.Thread(target=run_with_cleanup, daemon=True)
thread.start()


def kill_all_browser_processes():
    """Scan and forcefully terminate all orphaned Chrome and ChromeDriver processes.

    During high-concurrency browser automation, crashes, hard timeouts, or abrupt
    user stops can leave detached headless Chrome and Chromedriver subprocesses
    running in the background. These orphaned processes tie up system memory and
    lock debugging ports.

    This function leverages `psutil` to iterate through active OS processes and
    terminate any process whose image name matches 'chrome' or 'chromedriver'.
    """
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                name = proc.info['name'] or ""
                if any(b in name.lower() for b in ['chrome', 'chromedriver']):
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        print(f"Error killing processes: {e}")


def terminate_all_threads():
    """Forcefully terminate all background worker threads via CPython asynchronous exceptions.

    Python's standard `threading` library does not expose a public `.stop()` or
    `.kill()` API for worker threads. To achieve immediate halting when the user
    clicks 'Stop', this function calls the CPython C-API function:
    `PyThreadState_SetAsyncExc(thread_id, SystemExit)`.

    How It Works:
    -------------
    1. Iterates over all active threads enumerated by `threading.enumerate()`.
    2. Protects the main execution thread and the calling thread from termination.
    3. Injects a `SystemExit` exception directly into the thread's execution frame.
       The next time the thread acquires the Global Interpreter Lock (GIL) or
       executes an instruction, Python raises `SystemExit`, terminating the thread.
    """
    current_thread = threading.current_thread()
    for thread in threading.enumerate():
        # Never terminate the main thread or the thread running this termination logic
        if thread is threading.main_thread() or thread is current_thread:
            continue
        try:
            if hasattr(thread, '_thread_id'):
                ctypes.pythonapi.PyThreadState_SetAsyncExc(
                    ctypes.c_long(thread._thread_id),
                    ctypes.py_object(SystemExit))
        except Exception:
            try:
                thread.join(0.1)
            except Exception:
                pass


def stop_processing(batch_folder=None):
    """Emergency halt handler: aborts execution, saves partial results, and releases resources.

    Invoked when the operator clicks 'Stop' in the Web UI or an irrecoverable
    system state requires immediate cessation of all background activity.

    Sequential Teardown Steps:
    --------------------------
    1. Sets `state.running = False` and `state.force_stop = True` to signal
       graceful exit loops across all pipelines and blocks.
    2. Flushes the current in-memory `state.report_cases` dataset to an Excel
       spreadsheet on disk so that already-scraped data is not lost.
    3. Deactivates DriverPool background health monitoring.
    4. Kills all Chrome/Chromedriver processes via `kill_all_browser_processes()`.
    5. Force-kills dangling worker threads via `terminate_all_threads()`.
    6. Flushes the thread-safe `case_queue` and clears the web UI status dictionary.
    7. Emits a WebSocket broadcast to notify clients that processing is stopped.

    Args:
        batch_folder (str, optional): Target output directory where partial
            results should be serialized to Excel. Defaults to None.
    """
    try:
        state.running = False
        state.force_stop = True
        set_status_text("Stopping immediately...")
        log_message("Force stopping process - terminating all threads and processes...")

        # 1. Preserve scraped data to disk before terminating
        if batch_folder:
            save_to_excel(state.report_cases, batch_folder)
            log_message(f"📊 Partial Excel report saved to: {batch_folder}")

        # 2. Deactivate browser pool monitor loop
        if state.driver_pool:
            state.driver_pool.monitoring_active = False

        # 3. Terminate external browser executables and internal worker threads
        kill_all_browser_processes()
        terminate_all_threads()

        # 4. Drain queue and clear UI state
        with case_queue.mutex:
            clear_case_status()
            case_queue.queue.clear()

        log_message("All processes terminated forcefully")
        update_progress(0)

        # 5. Notify frontend clients
        try:
            _socketio.emit("processing_state", {"running": False})
        except Exception:
            pass
        state.force_stop = False
    except Exception:
        traceback.print_exc()



# ══════════════════════════════════════════════════════════════════════════════
# APPLICATION ENTRYPOINT — Web Server Startup & SocketIO Configuration
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    """Primary execution entry point.

    Launches the Flask web server with Flask-SocketIO support to provide the
    graphical user interface and REST API endpoints.

    Startup Sequence:
    -----------------
    1. Socket Reuse Configuration:
       - Sets `BaseWSGIServer.allow_reuse_address = True` and socket option
         `SO_REUSEADDR = 1`. This prevents `[Errno 98] / [Errno 10048] Address already in use`
         errors when restarting the process rapidly during development or deployment.
    2. Shared State Injection:
       - Mounts `main.py` state instances (`case_queue`, `case_status`, `state.report_cases`)
         directly onto `app.py` so route handlers read/write the same live references.
    3. Database Sanitization:
       - Calls `bulk_purge_processing_cases()` to clear out orphaned records in
         Supabase whose status remained stuck in 'processing' due to previous crashes.
    4. Server Listening:
       - Runs the SocketIO event loop on `0.0.0.0:5505`.
    """
    from werkzeug.serving import BaseWSGIServer

    # Allow instant socket address reuse on restart
    BaseWSGIServer.allow_reuse_address = True
    import app as _web_app

    # Wire shared application state into Flask API layer
    _web_app.case_queue = case_queue
    _web_app.case_status = case_status
    _web_app.report_cases = state.report_cases

    # Inject this module's namespace into the web app's route handlers
    _web_app._main_module = sys.modules[__name__]

    from app import app, socketio

    print("=" * 60)
    print("  Court Scraper — Web Interface")
    print("  http://localhost:5000")
    print("=" * 60)

    # Cleanse database of unfinalized cases from interrupted previous runs
    bulk_purge_processing_cases()

    # Pre-configure TCP socket reuse option
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Start the Flask-SocketIO WSGI server
    socketio.run(app, host="0.0.0.0", port=5560, debug=False, allow_unsafe_werkzeug=True, use_reloader=False)
