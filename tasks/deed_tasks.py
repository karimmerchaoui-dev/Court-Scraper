"""
tasks/deed_tasks.py
===================
Celery task that wraps the existing deed search logic.

What changes:
    nj_deed.py  → instead of  state.deed_queue.put(item)
                  calls       run_deed_job_task.delay(...)

What does NOT change:
    - run_deed_job() in deed_search/deed_api.py  (untouched)
    - upload_deeds_to_case() in supabase_service.py  (untouched)
    - add_deeds_to_report() in ai/llm_helper.py  (untouched)
    - All county deed logic  (untouched)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root directory is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import traceback

from tasks.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="tasks.deed_tasks.run_deed_job_task",
    queue="deed",
    max_retries=5,
    default_retry_delay=15,
    acks_late=True,
)
def run_deed_job_task(
    self,
    book: str,
    page: str,
    files_dir: str,
    block: str,
    main_defendant: str,
    county_name: str,
    supabase_case_id: str,
    case_id: str,
) -> dict:
    """
    Wraps the existing run_deed_job() call that lives inside _deed_worker_loop.

    Arguments mirror the tuple that was previously put on state.deed_queue:
        (book, page, files_dir, block, main_defendant, county_name, supabase_case_id, case_id)
    """
    try:
        # ── Import here to avoid circular imports at module load time ────────
        from app import log_message
        from cache.redis_client import r
        from config.sentry_config import set_sentry_case_context
        from deed_search.deed_api import run_deed_job

        set_sentry_case_context(case_id=case_id, county=county_name, stage="deed_search")
        log_message(f"📜 [{case_id}] Deed task started — county={county_name} book={book} page={page}")

        # ── Mark block status (if Redis is enabled) ──────────────────────
        try:
            from cache.redis_client import r
            r.hset(f"case:{case_id}:blocks", "Deed Search", "running")
        except Exception:
            pass

        # ── Call the UNCHANGED deed logic ─────────────────────────────────────
        run_deed_job(
            book=book,
            page=page,
            files_dir=files_dir,
            block=block,
            main_defendant=main_defendant,
            county_name=county_name,
            supabase_case_id=supabase_case_id,
            case_id=case_id,
        )

        try:
            from cache.redis_client import r
            r.hset(f"case:{case_id}:blocks", "Deed Search", "success")
        except Exception:
            pass
        log_message(f"✅ [{case_id}] Deed task completed")
        return {"status": "ok", "case_id": case_id}

    except Exception as exc:
        try:
            from cache.redis_client import r
            r.hset(f"case:{case_id}:blocks", "Deed Search", "retrying")
        except Exception:
            pass
        traceback.print_exc()
        raise self.retry(exc=exc)

