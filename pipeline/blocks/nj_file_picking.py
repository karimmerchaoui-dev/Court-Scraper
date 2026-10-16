"""
==============================================================================
Block 4: FilePickingBlock — Table Scanning & Document Target Selection
==============================================================================

Overview:
---------
Inspects the court case document table, parses document descriptions, and
identifies which rows contain target instruments (Complaints, Lis Pendens,
Final Judgments, Writs of Execution) while filtering out unwanted filings.

Operational Steps:
------------------
1. Row-Retry Shortcut:
   - If `ctx.matching_files` is already populated (because the orchestrator is
     retrying a specific failed download row), the expensive DOM scan is bypassed.

2. Concurrent Table Scanning:
   - Invokes `scan_table_multithreaded` to evaluate table rows against `state.keyword_list`
     and `state.unwanted_list`.
   - Records matching rows (row index, document title, date filed, download element).

3. Audit Trail Persistence:
   - Serializes the target download manifest to a text file in `ctx.files_dir`
     (`_save_matching_files`) for diagnostics and downstream processing.
==============================================================================
"""

from __future__ import annotations

import threading

from selenium.webdriver.common.by import By

from app import log_message
from download.scanners import scan_table_multithreaded
from pipeline.base import BlockSignal, PipelineBlock, PipelineContext
from state import state


class FilePickingBlock(PipelineBlock):
    """Block 4: Parse docket table rows and select files matching target keywords."""

    def __init__(self):
        super().__init__("File Picking")

    def execute(self, ctx: PipelineContext) -> BlockSignal:
        """Scan docket table rows and populate `ctx.matching_files`.

        Args:
            ctx (PipelineContext): Active case execution context.

        Returns:
            BlockSignal: Always returns `BlockSignal.OK` to transition to downloading.
        """
        from main import _save_matching_files

        case_id = ctx.case_id
        table   = getattr(ctx, "_table", None)

        if table is None:
            # Table absent (e.g. empty case) -> nothing to download
            log_message(f"ℹ️ [{case_id}] No table for file picking — skipping scan")
            return BlockSignal.OK

        # ── Step 1: Reuse Existing File Manifest on Row-Retry ─────────────────
        # When recovering from a single failed file download, avoid re-scanning the DOM
        if ctx.matching_files:
            log_message(f"ℹ️ [{case_id}] Reusing existing matching_files (row-retry)")
            return BlockSignal.OK

        # ── Step 2: Concurrently Scan Docket Rows ─────────────────────────────
        rows       = table.find_elements(By.TAG_NAME, "tr")
        total_rows = len(rows) - 1

        matching_rows_lock = threading.Lock()
        matching_rows: list = []

        log_message(f"🔍 [{case_id}] Scanning {total_rows} rows  keywords={state.keyword_list}")

        # Scan rows, matching keywords while filtering unwanted keywords (e.g. proof of mailing)
        matching_files = scan_table_multithreaded(
            ctx.driver,
            case_id,
            ctx.files_dir,
            state.report_cases,
            total_rows,
            matching_rows,
            matching_rows_lock,
            state.keyword_list,
            state.unwanted_list,
            "nj",
            start_index=ctx.start_index,
        )

        ctx.matching_files = matching_files
        ctx.matching_rows  = matching_rows

        # ── Step 3: Save Matching Files Manifest ──────────────────────────────
        _save_matching_files(case_id, ctx.files_dir, matching_files)
        ctx.case_result["matching_rows"] = matching_rows

        return BlockSignal.OK
