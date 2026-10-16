"""
==============================================================================
Block 8: DatabaseAddingBlock — Database Synchronization & Resource Teardown
==============================================================================

Overview:
---------
The final terminal block in the New Jersey scraping pipeline. Responsible for:
1. Validating whether required legal documents (Complaint & Final Judgment) were secured.
2. Synchronizing the aggregated case dictionary, OCR extractions, and PDF file paths
   into PostgreSQL / Supabase via `add_case_with_files`.
3. Releasing the Selenium browser driver back to the `DriverPool` so it can immediately
   service subsequent queued cases.
==============================================================================
"""

from __future__ import annotations

from app import log_message
from pipeline.base import BlockSignal, PipelineBlock, PipelineContext
from state import state


class DatabaseAddingBlock(PipelineBlock):
    """Block 8: Persist final case report to Supabase and return browser driver to pool."""

    def __init__(self):
        super().__init__("Database Adding")

    def execute(self, ctx: PipelineContext) -> BlockSignal:
        """Finalize the case record, sync files to Supabase, and release browser resources.

        Args:
            ctx (PipelineContext): Active case execution context.

        Returns:
            BlockSignal: Always returns `BlockSignal.OK` indicating pipeline completion.
        """
        from main import _finalize_nj_case

        case_id = ctx.case_id

        try:
            # ── Step 1: Finalize Case, Validate PDFs, & Upload to Supabase ─────
            # Computes total execution duration, checks for complaint/judgment presence,
            # sets the valid_flag, and invokes add_case_with_files().
            _finalize_nj_case(
                case_id,
                ctx.files_dir,
                ctx.start_time,
                tracker=getattr(ctx, "tracker", None),
            )
        except Exception as exc:
            log_message(f"⚠️ [{case_id}] DatabaseAddingBlock — _finalize_nj_case error: {exc}")
            # Non-fatal: continue into finally to guarantee the browser driver is never leaked
        finally:
            # ── Step 2: Release Browser Driver to Pool ────────────────────────
            try:
                state.driver_pool.release_driver(ctx.driver)
            except Exception:
                pass

        return BlockSignal.OK
