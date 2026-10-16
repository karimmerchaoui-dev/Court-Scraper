"""
==============================================================================
Block 5: CourtDownloadingBlock — Multi-Threaded Court File Downloading
==============================================================================

Overview:
---------
Coordinates the physical retrieval, streaming, and verification of target PDF
court filings from the New Jersey judiciary portal.

Operational Steps:
------------------
1. Special File Pre-Processing:
   - Processes any multi-part or multi-docket instruments via `_process_special_files`.
   - If an element interaction or download fails on a specific row, captures
     the failed row index and returns `BlockSignal.RETRY_FROM_ROW`.

2. File Download Loop:
   - Triggers browser clicks on target PDF download icons (`_download_files_with_retry`).
   - Uses `DownloadManager` to monitor the filesystem until `.crdownload` temporary
     files complete, then sanitizes and renames the file according to case schema.
   - On error: signals `BlockSignal.RETRY_FROM_ROW` with `ctx.row_index_to_retry`.

3. Synchronous Finalization:
   - Awaits the background property lookup (`ctx.property_future`) initiated
     in Block 3 (`CaseCheckingBlock`).
   - Merges property details into `state.report_cases` via `_finalize_case`.
==============================================================================
"""

from __future__ import annotations

from app import log_message
from pipeline.base import BlockSignal, PipelineBlock, PipelineContext


class CourtDownloadingBlock(PipelineBlock):
    """Block 5: Automate document downloads and merge asynchronous property data."""

    def __init__(self):
        super().__init__("Court Downloading")

    def execute(self, ctx: PipelineContext) -> BlockSignal:
        """Download identified documents and join background property futures.

        Args:
            ctx (PipelineContext): Active case execution context.

        Returns:
            BlockSignal: Directive indicating download outcome:
                         - `BlockSignal.OK`: All targeted files downloaded.
                         - `BlockSignal.RETRY_FROM_ROW`: Download interrupted on a row,
                           instructing the orchestrator to resume at `ctx.row_index_to_retry`.
        """
        from main import (
            _download_files_with_retry,
            _finalize_case,
            _process_special_files,
        )

        case_id       = ctx.case_id
        matching_files = ctx.matching_files

        # ── Guard: No Files Matched Keywords ──────────────────────────────────
        if not matching_files:
            log_message(f"ℹ️ [{case_id}] No matching files to download")
            # Finalize property future and write initial report entry even if 0 files found
            _finalize_case(ctx.driver, case_id, ctx.property_future, ctx.case_result, ctx.files_dir)
            return BlockSignal.OK

        # ── Step 1: Handle Multi-Part or Special Document Types ───────────────
        special_result = _process_special_files(
            ctx.driver, case_id, ctx.files_dir,
            matching_files, ctx.year, ctx.docket, ctx.account,
        )
        if special_result:
            # special_result returns (row_index, matching_rows) when a retry is required
            if isinstance(special_result, tuple):
                row_index, _ = special_result
                if row_index is not None and row_index >= 0:
                    ctx.last_failed_block = self.name
                    ctx.retry_reason = f"Download special handling failed on row {row_index}"
                    ctx.row_index_to_retry = row_index
                    return BlockSignal.RETRY_FROM_ROW
            return BlockSignal.OK

        # ── Step 2: Main Document Download Loop with Auto-Retry ───────────────
        rows = getattr(ctx, "_table", None)
        total_rows = len(rows.find_elements("tag name", "tr")) - 1 if rows else 0

        download_result = _download_files_with_retry(
            ctx.driver, case_id, ctx.year, ctx.docket, ctx.account,
            ctx.files_dir, matching_files, total_rows,
        )

        # Handle row-level download failures
        if download_result.get("status") == "error":
            row_index = download_result.get("row_index")
            if row_index is not None and row_index >= 0:
                ctx.last_failed_block = self.name
                ctx.retry_reason = f"Download failed on row {row_index}"
                ctx.row_index_to_retry = row_index
                return BlockSignal.RETRY_FROM_ROW

        ctx.case_result["final_judgment"] = download_result.get("final_judgment", False)
        print(f"ctx.property_future : {ctx.property_future}")

        # ── Step 3: Await Background Property Search & Finalize Report ────────
        # Blocks until property_future completes or times out, then writes metadata
        _finalize_case(ctx.driver, case_id, ctx.property_future, ctx.case_result, ctx.files_dir)

        return BlockSignal.OK
