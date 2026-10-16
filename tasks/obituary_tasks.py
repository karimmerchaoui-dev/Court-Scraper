"""
tasks/obituary_tasks.py
========================
Celery task that wraps the existing obituary search logic.

What changes:
    nj_obituary.py  → instead of  threading.Thread(target=self._run_obituary_searches).start()
                      calls        run_obituary_task.delay(...)

What does NOT change:
    - get_obituary_info() in utils/obituary_helpers.py  (untouched)
    - Supabase upsert logic  (untouched)
    - All obituary parsing  (untouched)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root directory is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import traceback
from typing import Optional

from tasks.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="tasks.obituary_tasks.run_obituary_task",
    queue="obituary",
    max_retries=3,
    default_retry_delay=20,
    acks_late=True,
)
def run_obituary_task(
    self,
    case_id: str,
    deceased_list: list,
    state_val: str,
) -> dict:
    """
    Wraps the existing _run_obituary_searches() method that previously ran
    inside a daemon threading.Thread.

    Arguments:
        case_id      — the full case identifier string
        deceased_list — list of dicts, each with at least a "name" or "full_name" key
        state_val    — state string, e.g. "NJ" or "Florida"
    """
    try:
        from app import log_message
        from cache.redis_client import r
        from config.sentry_config import set_sentry_case_context
        from database.supabase_service import supabase
        from utils.obituary_helpers import get_obituary_info

        set_sentry_case_context(case_id=case_id, stage="obituary_search")
        log_message(f"📰 [{case_id}] Obituary task started ({len(deceased_list)} person(s))")
        try:
            from cache.redis_client import r
            r.hset(f"case:{case_id}:blocks", "Obituary Search", "running")
        except Exception:
            pass

        for person_entry in deceased_list:
            full_name: Optional[str] = (
                person_entry.get("name") or person_entry.get("full_name")
            )
            if not full_name:
                continue

            # Strip AKA aliases — UNCHANGED from nj_obituary.py
            if "aka" in full_name.lower():
                full_name = full_name.split("aka")[0].strip()
            elif "a/k/a" in full_name.lower():
                full_name = full_name.split("a/k/a")[0].strip()

            try:
                # Determine location — UNCHANGED from nj_obituary.py
                if "nj" in state_val.lower() or "jersey" in state_val.lower():
                    location = "New Jersey"
                elif "fl" in state_val.lower() or "florida" in state_val.lower():
                    location = "Florida"
                else:
                    location = "New Jersey"

                # ── Call UNCHANGED obituary logic ─────────────────────────────
                search_results = get_obituary_info(full_name, location)

                if search_results:
                    person_db = (
                        supabase.table("case_deceased_persons")
                        .select("id")
                        .eq("case_id", case_id)
                        .eq("full_name", full_name)
                        .execute()
                    )
                    if person_db.data:
                        deceased_uuid = person_db.data[0]["id"]
                        for obit in search_results:
                            obit["deceased_person_id"] = deceased_uuid
                            supabase.table("obituaries").upsert(
                                obit,
                                on_conflict="deceased_person_id,source_url",
                            ).execute()
                        log_message(
                            f"✅ [{case_id}] Obituary synced for {full_name} "
                            f"({len(search_results)} result(s))"
                        )
            except Exception as person_exc:
                log_message(f"❌ [{case_id}] Obituary error for {full_name}: {person_exc}")

        try:
            from cache.redis_client import r
            r.hset(f"case:{case_id}:blocks", "Obituary Search", "success")
        except Exception:
            pass
        return {"status": "ok", "case_id": case_id}

    except Exception as exc:
        try:
            from cache.redis_client import r
            r.hset(f"case:{case_id}:blocks", "Obituary Search", "failed")
        except Exception:
            pass
        traceback.print_exc()
        raise self.retry(exc=exc)

