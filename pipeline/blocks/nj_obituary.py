"""
==============================================================================
Block 6: ObituarySearchBlock — Asynchronous Deceased Party Obituary Discovery
==============================================================================

Overview:
---------
An asynchronous "fire-and-observe" stage. Scans the case record for identified
deceased defendants, next-of-kin, or heirs, and dispatches online obituary
searches to discover survivor details, probate flags, and death certificates.

Concurrency Architecture:
-------------------------
- Non-Blocking: Does NOT block the main pipeline thread. Dispatches tasks either
  via Celery distributed workers (`tasks.obituary_tasks`) or background daemon threads.
- Returns `BlockSignal.OK` immediately so the pipeline can proceed to Block 7 (Deeds)
  and Block 8 (Database Sync) without latency.
- Independent Telemetry: When the background worker finishes parsing obituaries,
  it independently broadcasts `BlockStatus.SUCCESS` or `BlockStatus.FAILED`
  directly to the web UI and upserts records into Supabase (`case_deceased_persons`).
==============================================================================
"""

from __future__ import annotations

import threading
from typing import Optional

from app import log_message
from pipeline.base import BlockSignal, PipelineBlock, PipelineContext
from state import state


class ObituarySearchBlock(PipelineBlock):
    """Block 6: Fire-and-observe obituary discovery for deceased defendants/parties."""

    def __init__(self, on_status_change=None):
        super().__init__("Obituary Search")
        # Optional callback so the orchestrator can track this block independently
        self._on_status_change = on_status_change

    def execute(self, ctx: PipelineContext) -> BlockSignal:
        """Inspect deceased party lists and dispatch background obituary scraping jobs.

        Args:
            ctx (PipelineContext): Active case execution context.

        Returns:
            BlockSignal: Always returns `BlockSignal.OK` immediately to prevent pipeline stalling.
        """
        case_id = ctx.case_id
        report  = state.report_cases.get(case_id, {})

        deceased_list = (
            report.get("deceased_persons")
            or report.get("deceased persons")
            or []
        )

        state_val = report.get("state") or report.get("county") or "New Jersey"

        # ── Guard: No Deceased Parties Identified ─────────────────────────────
        if not deceased_list:
            log_message(f"ℹ️ [{case_id}] No deceased persons — skipping obituary search")
            return BlockSignal.OK

        # ── Step 1: Dispatch Job via Celery or Background Daemon Thread ───────
        from main import _emit_block_status
        from pipeline.base import BlockStatus
        _emit_block_status(case_id, "Obituary Search", BlockStatus.RUNNING)

        _dispatched_via_celery = False
        try:
            from tasks.obituary_tasks import run_obituary_task
            run_obituary_task.delay(
                case_id=case_id,
                deceased_list=deceased_list,
                state_val=state_val,
            )
            _dispatched_via_celery = True
        except Exception:
            pass  # Celery unavailable or unconfigured -> fall back to local thread

        if not _dispatched_via_celery:
            # Local background worker thread fallback
            t = threading.Thread(
                target=self._run_obituary_searches,
                args=(case_id, deceased_list, state_val),
                name=f"ObituarySearch-{case_id}",
                daemon=True,
            )
            t.start()

        log_message(
            f"📰 [{case_id}] Obituary search dispatched via "
            f"{'Celery' if _dispatched_via_celery else 'background thread'} "
            f"({len(deceased_list)} person(s))"
        )

        # ── Step 2: Record Telemetry in Supabase ──────────────────────────────
        _tracker = getattr(ctx, "tracker", None)
        if _tracker:
            try:
                with _tracker.track_step("obituary", "dispatch_search") as _obit_step:
                    _obit_step.set_metadata("deceased_count", len(deceased_list))
                    _obit_step.set_metadata("names", [
                        p.get("name") or p.get("full_name") for p in deceased_list
                    ])
                    _obit_step.set_metadata(
                        "dispatched_via", "celery" if _dispatched_via_celery else "background_thread"
                    )
            except Exception:
                pass  # Telemetry errors must never crash core pipeline

        # Return immediately — the main pipeline thread continues to Block 7
        return BlockSignal.OK

    # ── Background Daemon Thread Worker ───────────────────────────────────────

    def _run_obituary_searches(self, case_id: str, deceased_list: list, state_val: str) -> None:
        """Execute web searches for obituaries and persist results to Supabase."""
        from main import _emit_block_status
        from pipeline.base import BlockStatus
        try:
            from database.supabase_service import supabase
            from utils.obituary_helpers import get_obituary_info

            for person_entry in deceased_list:
                full_name: Optional[str] = (
                    person_entry.get("name") or person_entry.get("full_name")
                )
                if not full_name:
                    continue

                # Clean alias strings ('John Doe AKA Johnny Doe' -> 'John Doe')
                if "aka" in full_name.lower():
                    full_name = full_name.split("aka")[0].strip()
                elif "a/k/a" in full_name.lower():
                    full_name = full_name.split("a/k/a")[0].strip()

                try:
                    # Normalize jurisdiction
                    if "nj" in str(state_val).lower() or "jersey" in str(state_val).lower():
                        location = "New Jersey"
                    elif "fl" in str(state_val).lower() or "florida" in str(state_val).lower():
                        location = "Florida"
                    else:
                        location = "New Jersey"

                    search_results = get_obituary_info(full_name, location)

                    if search_results:
                        # Fetch the foreign key UUID for this deceased person
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

            _emit_block_status(case_id, "Obituary Search", BlockStatus.SUCCESS)

        except Exception as exc:
            _emit_block_status(case_id, "Obituary Search", BlockStatus.FAILED)
            log_message(f"❌ [{case_id}] ObituarySearchBlock thread error: {exc}")
