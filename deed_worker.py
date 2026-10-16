"""
deed_worker.py
==============
Standalone deed-download worker process.

Run this as a *separate process* alongside the main scraper:

    python deed_worker.py

The main scraper (main.py / pipeline/blocks/nj_deed.py) writes jobs to the
shared SQLite file via SqliteDeedQueue.put().  This process consumes them
one at a time and writes results to Supabase.

Signals:
    Ctrl-C or SIGTERM -> graceful shutdown (finishes the current job first).

Environment variables:
    DEED_QUEUE_DB   Path to the SQLite queue file (default: deed_queue.db at
                    project root).  Must match the path used by the producer.
"""
from __future__ import annotations

import os
import signal
import sys
import time
import traceback
from pathlib import Path

# ── Ensure project root is on sys.path so all local imports resolve ───────────
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env before any config/settings imports
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=False)

# ── Local imports ─────────────────────────────────────────────────────────────
from database.deed_queue_db import SqliteDeedQueue
from database.supabase_service import sync_deed_dictionary_to_documents
from deed_search.deed_api import run_deed_job

# ── Logging helper ────────────────────────────────────────────────────────────
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [DeedWorker]  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("deed_worker")

# ── Build a minimal payload dict expected by run_deed_job ────────────────────

def _build_payload(main_defendant: str, county_name: str, block: str = "") -> dict:
    """
    Mirror the payload structure that build_payload() in main.py produces.
    All LLM / deed config is pulled from environment variables.
    """
    if isinstance(county_name, dict):
        county_name = county_name.get("County:", county_name).lower()

    return {
        "county": county_name,
        "owner_name": main_defendant,
        "first_name": "",
        "last_name": main_defendant,
        "download_file": False,
        "search_mode": "name",
        "block": block,
        "llm_service": os.getenv("LLM_SERVICE", "groq"),
        "llm_api_key": os.getenv("GROQ_API_KEY", ""),
        "llm_model": os.getenv("LLM_MODEL", ""),
    }


# ── Worker loop ───────────────────────────────────────────────────────────────

_SHUTDOWN = False   # set by signal handler


def _handle_signal(signum, frame):  # noqa: ANN001
    global _SHUTDOWN
    log.info("Shutdown signal received — will exit after current job.")
    _SHUTDOWN = True


signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


def run_worker(queue: SqliteDeedQueue) -> None:
    """Consume deed jobs from the SQLite queue until shutdown is requested."""
    log.info("Deed worker started.  Listening for jobs on %s", queue._db_path)

    while not _SHUTDOWN:
        try:
            # Blocking get with a short timeout so we can check _SHUTDOWN
            item = queue.get(block=True, timeout=2.0)
        except Exception:
            # queue.Empty or any other transient error — just loop
            continue

        book, page, files_dir, block, main_defendant, county_name, supabase_case_id, case_id = item
        log.info(
            "Processing job  case=%s  county=%s  defendant=%s  book=%s  page=%s",
            case_id, county_name, main_defendant, book, page,
        )

        try:
            payload = _build_payload(main_defendant, county_name, block=block)
            result = run_deed_job(payload)

            if "extracted_data" in result:
                sync_deed_dictionary_to_documents(case_id, result["extracted_data"])

            log.info("Done  case=%s", case_id)
            queue.task_done()

        except Exception as exc:
            log.error("Failed  case=%s  error=%s", case_id, exc)
            traceback.print_exc()
            queue.mark_failed(error=str(exc))

    log.info("Deed worker exiting cleanly.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    db_path = os.getenv("DEED_QUEUE_DB", str(PROJECT_ROOT / "deed_queue.db"))
    q = SqliteDeedQueue(db_path=db_path)

    # On startup: re-queue any jobs that were stuck 'processing' (crash recovery)
    log.info("Queue ready.  Pending jobs: %d", q.pending())

    # Optionally retry previously failed jobs on startup
    retried = q.retry_failed()
    if retried:
        log.info("Re-queued %d previously failed job(s).", retried)

    run_worker(q)
