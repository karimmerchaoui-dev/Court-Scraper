"""
==============================================================================
Block 7: DeedSearchBlock — Asynchronous County Deed Registry Query Dispatch
==============================================================================

Overview:
---------
An asynchronous "fire-and-observe" stage. Inspects the case record for property
legal descriptions (Book, Page, Lot, Block) and defendant names extracted
from the foreclosure complaint, then enqueues a background deed search job.

Concurrency Architecture:
-------------------------
- Non-Blocking: Does NOT block the court pipeline. Enqueues the payload into
  ``state.deed_queue`` — a SQLite-backed durable queue (database/deed_queue_db.py).
- Cross-process: Jobs written here survive process restarts and are consumed by
  either the in-process ``_deed_worker_loop`` thread (main.py) or the standalone
  ``deed_worker.py`` process — both read from the same SQLite file.
- Returns ``BlockSignal.OK`` immediately so the pipeline can proceed directly to
  Block 8 (``DatabaseAddingBlock``) and release the expensive browser driver.
- Telemetry: Records deed lookup dispatch events in Supabase (``pipeline_runs``).
==============================================================================
"""

from __future__ import annotations

from app import log_message
from pipeline.base import BlockSignal, PipelineBlock, PipelineContext
from state import state


class DeedSearchBlock(PipelineBlock):
    """Block 7: Enqueue property deed lookup jobs for the background deed worker thread."""

    def __init__(self):
        super().__init__("Deed Search")

    def execute(self, ctx: PipelineContext) -> BlockSignal:
        """Extract deed indexing criteria and push payload to `state.deed_queue`.

        Args:
            ctx (PipelineContext): Active case execution context.

        Returns:
            BlockSignal: Always returns `BlockSignal.OK` immediately.
        """
        from main import _ensure_deed_worker

        case_id = ctx.case_id
        report  = state.report_cases.get(case_id, {})

        # Extract deed indexing attributes parsed from complaint PDFs
        book             = report.get("book", "")
        page             = report.get("page", "")
        block            = report.get("Block", "")
        main_defendant   = report.get("main_defendant_inverse", "") or report.get("main_defendant", "")
        county_name      = report.get("county", "")
        supabase_case_id = report.get("supabase_case_id", "")

        # Guard: Missing minimum required search keys
        if not main_defendant or not county_name:
            log_message(
                f"ℹ️ [{case_id}] Deed search skipped — "
                f"missing main_defendant or county (defendant={main_defendant!r}, county={county_name!r})"
            )
            return BlockSignal.OK

        # ── Step 1: Enqueue Work Tuple for Background Worker ──────────────────
        # Payload consumes: (book, page, files_dir, block, defendant, county, supabase_id, case_id)
        item = (book, page, ctx.files_dir, block, main_defendant, county_name, supabase_case_id, case_id)
        state.deed_queue.put(item)
        _ensure_deed_worker()

        # Emit running status to the UI dashboard
        from main import _emit_block_status
        from pipeline.base import BlockStatus
        _emit_block_status(case_id, "Deed Search", BlockStatus.RUNNING)

        # ── Step 2: Record Telemetry Audit in Supabase ─────────────────────────
        _tracker = getattr(ctx, "tracker", None)
        if _tracker:
            try:
                with _tracker.track_step("deed", "dispatch_search_job") as _deed_step:
                    _deed_step.set_metadata("book", book)
                    _deed_step.set_metadata("page", page)
                    _deed_step.set_metadata("county", county_name)
                    _deed_step.set_metadata("main_defendant", main_defendant)
            except Exception:
                pass  # Telemetry errors must never crash core pipeline

        # Return immediately — pipeline does NOT wait for deed downloads to complete
        return BlockSignal.OK
