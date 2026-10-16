"""
==============================================================================
Block 3: CaseCheckingBlock — Court Record Validation & Metadata Extraction
==============================================================================

Overview:
---------
Executes once the browser arrives at the case details page. Verifies presence
of the docket table, scrapes case metadata (defendants, case status, judge),
evaluates business skip rules, and kicks off an asynchronous property search.

Operational Steps:
------------------
1. Docket Table Discovery:
   - Locates the main docket events/documents table (`_find_case_table`).
   - If missing, calls `_handle_no_table`. If a reload error occurs, returns
     `BlockSignal.RETRY_FROM_NAV` to prompt the orchestrator to rewind and re-enter.

2. Case Metadata Extraction:
   - Scrapes party/defendant listings (`_get_case_information`), court case status,
     and filing dates, storing them in `ctx.case_result`.

3. Business Disqualification Check:
   - Evaluates `_should_skip_case` (e.g. dismissed cases, non-foreclosure types,
     or corporate commercial entities). If triggered, returns `BlockSignal.SKIP`.

4. Asynchronous Property Details Worker:
   - Dispatches `_process_property_details` into the background (`ctx.property_future`)
     so property parcel data is fetched concurrently while the main thread downloads files.
==============================================================================
"""

from __future__ import annotations

import pysnooper

from app import update_case_status
from browser.browser_helpers import get_thread_number, set_download_dir
from pipeline.base import BlockSignal, PipelineBlock, PipelineContext
from state import state


@pysnooper.snoop()
class CaseCheckingBlock(PipelineBlock):
    """Block 3: Validate court page structure, scrape party data, and check skip criteria."""

    def __init__(self):
        super().__init__("Case Checking")

    def execute(self, ctx: PipelineContext) -> BlockSignal:
        """Inspect the case page and extract preliminary party and docket information.

        Args:
            ctx (PipelineContext): Active case execution context.

        Returns:
            BlockSignal: Directive indicating table discovery outcome:
                         - `BlockSignal.OK`: Table validated and metadata stored.
                         - `BlockSignal.SKIP`: Case matched business skip criteria.
                         - `BlockSignal.RETRY_FROM_NAV`: Table DOM elements failed to render.
        """
        from main import (
            _find_case_table,
            _get_case_information,
            _handle_no_table,
            _process_property_details,
            _should_skip_case,
        )

        case_id = ctx.case_id
        driver  = ctx.driver

        update_case_status(
            driver, case_id, "New Jersey",
            f"Downloading (Thread {get_thread_number()})",
            details="Checking for files",
        )
        driver.state = "downloading"
        set_download_dir(driver, ctx.files_dir)

        # ── Step 1: Locate Docket Table on Court Page ─────────────────────────
        table = _find_case_table(driver, case_id)
        if table is None:
            result_tuple = _handle_no_table(driver, case_id, {})
            row_index, _ = result_tuple
            if row_index is None:
                # Table legitimately absent (e.g., zero documents filed) -> OK to complete
                return BlockSignal.OK
            # Table loading error: rewind to Block 2 to re-enter docket
            ctx.last_failed_block = self.name
            ctx.retry_reason = "Docket table not found or error loading case table"
            return BlockSignal.RETRY_FROM_NAV

        # Cache reference to the Selenium table element for Block 4 (FilePickingBlock)
        ctx._table = table

        # ── Step 2: Scrape Parties & Evaluate Skip Rules ──────────────────────
        # Only parse case info on initial pass (skip on subsequent row-retries)
        if not ctx.matching_files:
            result = {
                "status": "pending",
                "matching_rows": [],
                "files_downloaded": [],
                "errors": [],
                "final_judgment": False,
            }
            result = _get_case_information(driver, case_id, result, state)
            ctx.case_result = result

            # Evaluate dismissal, closed status, or commercial defendant skip rules
            skip_result = _should_skip_case(driver, case_id, result, ctx.files_dir)
            if skip_result:
                return BlockSignal.SKIP

        # ── Step 3: Launch Background Property Parcel Lookup ──────────────────
        # Spawns concurrent deed/parcel query so it runs in parallel with file downloading
        ctx.property_future = _process_property_details(
            driver, case_id, ctx.case_result, ctx.files_dir
        )

        return BlockSignal.OK
