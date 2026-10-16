"""
tasks/case_tasks.py
===================
Celery task for executing court case scraping pipelines.

Queue: "cases"
Concurrency: Configured via Celery worker flags (e.g. --concurrency=4 --pool=threads)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure project root directory is always in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import traceback
from typing import Any, Dict

from state import state
from tasks.celery_app import celery_app


def _get_or_create_worker_driver_pool(max_workers: int = 4):
    """
    Returns the shared in-memory DriverPool for this worker process.
    If one doesn't exist yet, initializes it safely using state/main dependencies.
    """
    if getattr(state, "driver_pool", None) is not None:
        return state.driver_pool

    import main
    from browser.driver_pool import DriverPool

    headless = getattr(state, "headless_mode", True)
    pool = DriverPool(
        max_workers,
        setup_driver_func=main.setup_driver,
        attach_web_monitor_func=main.attach_web_monitor,
        append_driver_log_func=main.append_driver_log,
        reset_vpn_func=main.reset_vpn,
        element_exists_id_func=main.element_exists_id,
        element_exists_xpath_func=main.element_exists_xpath,
        refresh_url_func=main.refresh_url,
        check_js_popup_func=main.check_js_popup,
        request_url_func=main.request_url,
        delete_driver_func=main.delete_driver,
        case_queue=main.case_queue,
        headless_mode=headless,
        get_force_stop=lambda: state.force_stop,
        get_max_workers=lambda: max_workers,
        nj_login_page=main.NJ_LOGIN_PAGE,
    )
    state.driver_pool = pool
    return pool


@celery_app.task(
    bind=True,
    name="tasks.case_tasks.run_case_pipeline",
    queue="cases",
    acks_late=True,
    max_retries=2,
    default_retry_delay=15,
)
def run_case_pipeline(self, case_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes a single court case scraping pipeline:
    1. Precheck (eligibility check via Zillow/SalesWeb)
    2. Court Portal Scraping (via county processor / PipelineOrchestrator)
    3. Triggers deed and obituary background tasks if applicable
    """
    import main
    from app import log_message, update_case_status
    from cache.redis_client import r
    from config.sentry_config import set_sentry_case_context
    from models import Case

    year = str(case_dict.get("year", "")).strip()
    docket = str(case_dict.get("docket", "")).strip()
    county = str(case_dict.get("county", "")).strip()
    court_type = str(case_dict.get("court_type", "")).strip()
    address = str(case_dict.get("address", "")).strip()
    output_folder = str(case_dict.get("output_folder", "")).strip() or getattr(state, "current_batch_folder", "logs")

    case_obj = Case(year=year, case_number=docket, county=county, case_type=court_type)
    case_id = case_obj.id

    set_sentry_case_context(case_id=case_id, county=county, stage="court_scraping")
    log_message(f"🚀 [{case_id}] Case processing started ({county})")

    # Update Redis and Web UI status
    r.hset(f"case:{case_id}:status", mapping={"status": "processing", "county": county})
    update_case_status(None, case_id, county, "Processing", details="Pipeline worker assigned")

    # ── Check Force Stop ──────────────────────────────────────────────────────
    if getattr(state, "force_stop", False) or r.get("scraper:force_stop"):
        log_message(f"⏹️ [{case_id}] Skipped — force stop active")
        update_case_status(None, case_id, county, "Stopped", details="Force stop active")
        return {"case_id": case_id, "status": "stopped"}

    # ── Acquire Driver from the in-memory DriverPool ──────────────────────────
    driver_pool = _get_or_create_worker_driver_pool()

    try:
        with driver_pool.borrow_driver() as driver:
            # ── Check US IP / VPN before touching court sites ─────────────────
            from network.network_helpers import is_us_ip
            if not is_us_ip():
                log_message(f"🌐 [{case_id}] Non-US IP detected — triggering VPN reset")
                driver_pool.reset_vpn_pool(driver)

            # ── Resolve county processor ──────────────────────────────────────
            processor = main._get_county_processor(county.lower().strip())
            if not processor:
                log_message(f"❌ [{case_id}] No processor found for county: {county}")
                update_case_status(None, case_id, county, "Error", details=f"Unknown processor for {county}")
                return {"case_id": case_id, "status": "error", "error": "Unknown processor"}

            # Setup download dir
            file_dir = case_obj.get_file_dir(output_folder)
            os.makedirs(file_dir, exist_ok=True)
            main.set_download_dir(driver, file_dir)
            driver.files_dir = file_dir

            # Main accounts rotation
            accounts = main._get_shuffled_main_accounts()
            account = accounts[0] if accounts else {}

            # Execute processor
            processor_lower = county.lower()
            if "jersey" in processor_lower or processor_lower == "nj":
                result = processor(
                    None, year, docket, court_type, driver, driver_pool, account, file_dir
                )
            else:
                result = processor(
                    None, year, docket, court_type, driver, driver_pool, file_dir
                )

            log_message(f"✅ [{case_id}] Finished processing ({result})")
            r.hset(f"case:{case_id}:status", mapping={"status": "completed"})
            return {"case_id": case_id, "status": "completed", "result": str(result)}

    except Exception as exc:
        traceback.print_exc()
        log_message(f"❌ [{case_id}] Error in run_case_pipeline: {exc}")
        r.hset(f"case:{case_id}:status", mapping={"status": "error", "error": str(exc)})
        update_case_status(None, case_id, county, "Error", details=str(exc))
        raise self.retry(exc=exc)
