"""
==============================================================================
pipeline/orchestrator.py — Finite-State Pipeline Orchestration Engine
==============================================================================

Overview:
---------
This module provides the execution runtime (`PipelineOrchestrator`) that drives
a case through an ordered sequence of `PipelineBlock` stages. It functions as
a finite-state machine (FSM) managing execution order, browser lifecycle,
driver recycling, dynamic retries, telemetry tracking, and UI progress streaming.

Architecture & State Transitions:
---------------------------------
1. Dynamic Signal Routing:
   - Blocks execute sequentially (index 0 -> index N).
   - Upon block completion, its return signal (`BlockSignal`) governs the next transition:
       * `OK`: Advance to next block (`i += 1`).
       * `RETRY_DRIVER`: Recycle browser instance via DriverPool; re-run current block.
       * `RETRY_FROM_START`: Recycle driver; rewind execution to Block 0.
       * `RETRY_FROM_NAV`: Recycle driver; rewind to Block 1 (`CourtNavigationBlock`).
       * `RETRY_FROM_ROW`: Recycle driver; rewind to Block 2 (`CaseCheckingBlock`) with `start_index`.
       * `NOT_FOUND`: Case does not exist in court records; abort and mark `NOT_FOUND`.
       * `SKIP`: Case fails eligibility or user requested skip; abort and mark `SKIPPED`.
       * `STOP`: Unrecoverable error; abort and mark `FAILED`.

2. Failure Escalation & Recovery:
   - Driver/network crashes (`_DRIVER_ERRORS`) trigger automatic VPN rotation
     and driver recycling up to `_MAX_DRIVER_RETRIES` times.
   - Unexpected Python exceptions are logged with stack traces and current browser URLs,
     safely releasing the driver back to the pool to prevent resource starvation.

3. Telemetry & Front-End Synchronization:
   - Integrates with `PipelineTracker` to write audit trails to Supabase (`pipeline_runs`).
   - Invokes `on_status_change()` on every block state transition to power the web UI.
==============================================================================
"""

from __future__ import annotations

import time
import traceback
from typing import Callable, List, Optional

from selenium.common.exceptions import InvalidSessionIdException
from urllib3.exceptions import MaxRetryError, ReadTimeoutError

from app import log_message
from core.SearchResult import SearchResult
from database.supabase_service import supabase as _supabase_client
from pipeline_tracker import PipelineTracker

from .base import BlockSignal, BlockStatus, PipelineBlock, PipelineContext

# ── Transient Driver & Network Errors Eligible for Automatic Retry ────────────
# When these exceptions occur during block execution, the orchestrator does not
# treat them as fatal case failures; instead, it recycles the driver, resets the
# VPN connection, and retries from the court navigation stage.
_DRIVER_ERRORS = (
    ConnectionError,
    MaxRetryError,
    InvalidSessionIdException,
    AttributeError,
    ReadTimeoutError,
)

# Safety threshold: maximum number of driver swaps allowed per case before aborting
_MAX_DRIVER_RETRIES = 10


class PipelineOrchestrator:
    """
    Runs an ordered sequence of PipelineBlocks for a single case.

    Retry model
    -----------
    * RETRY_DRIVER     → swap driver, re-run the SAME block
    * RETRY_FROM_START → swap driver, restart from block index 0 (first block)
    * RETRY_FROM_NAV   → swap driver, restart from block index 1 (CourtNavigationBlock)
    * RETRY_FROM_ROW   → swap driver, restart from block index 2 (CaseCheckingBlock)
                         (carries ctx.start_index = ctx.row_index_to_retry)
    * Driver-level exceptions (ConnectionError, MaxRetry, etc.)
                       → reset VPN pool, swap driver, restart from block index 1

    UI events
    ---------
    on_status_change(case_id, block_name, BlockStatus) is called whenever
    a block transitions state.  Pass None to disable.
    """

    def __init__(
        self,
        blocks: List[PipelineBlock],
        on_status_change: Optional[Callable[[str, str, BlockStatus, Optional[str]], None]] = None,
    ):
        """Initialize the orchestrator with an ordered list of pipeline blocks.

        Args:
            blocks (list[PipelineBlock]): Sequential list of stages to execute.
            on_status_change (Callable, optional): Callback invoked whenever a block
                transitions state (signature: `(case_id, block_name, status, reason=None)`).
        """
        self.blocks = blocks
        self.on_status_change = on_status_change

    # ── Public Entry Point ────────────────────────────────────────────────────

    def run(self, ctx: PipelineContext) -> SearchResult:
        """Execute all blocks in sequence for the provided case context.

        Args:
            ctx (PipelineContext): Active case execution context.

        Returns:
            SearchResult: High-level outcome enum (`SUCCESS`, `NOT_FOUND`, or `ERROR`).
        """
        # Step 1: Pre-populate all blocks as PENDING in the front-end dashboard
        for block in self.blocks:
            self._emit(ctx, block, BlockStatus.PENDING)

        # Step 2: Initialize or attach the Supabase pipeline telemetry tracker
        if ctx.tracker is None:
            try:
                ctx.tracker = PipelineTracker(
                    supabase_client=_supabase_client,
                    case_number=ctx.case_id,
                    batch_name=getattr(ctx, "batch_name", ""),
                )
                ctx.tracker.start_run()
                from pipeline_tracker import set_current_tracker
                set_current_tracker(ctx.tracker)
            except Exception as _te:
                log_message(f"⚠️ [{ctx.case_id}] Tracker init failed (non-fatal): {_te}")
                ctx.tracker = None
        else:
            from pipeline_tracker import set_current_tracker
            set_current_tracker(ctx.tracker)

        driver_retries = 0
        i = 0  # Pointer to the currently executing block index

        # Main State Machine Execution Loop
        while i < len(self.blocks):
            block = self.blocks[i]

            # ── Cooperative Cancellation Checkpoint ───────────────────────────
            # Checks whether an operator flagged this case for cancellation in Redis/UI.
            # Checked at every block boundary for near-instant responsiveness.
            try:
                from queue_manager import ack_case_cancellation, is_case_cancelled
                if is_case_cancelled(ctx.case_id):
                    log_message(f"⏹️ [{ctx.case_id}] Cancellation requested — stopping pipeline at block [{block.name}]")
                    ack_case_cancellation(ctx.case_id)
                    self._skip_remaining(ctx, i)
                    self._release_driver(ctx)
                    return SearchResult.ERROR
            except Exception:
                pass

            # Update UI state to RUNNING and record block execution start time
            self._emit(ctx, block, BlockStatus.RUNNING)
            block_start_time = time.time()
            log_message(f"📦 [{ctx.case_id}] [Block {i + 1}/{len(self.blocks)}: {block.name}] Starting execution...")

            try:
                # Execute the block's operational logic
                signal = block.execute(ctx)
                elapsed = time.time() - block_start_time
                log_message(f"🏁 [{ctx.case_id}] [Block: {block.name}] Finished with signal: {signal.value} ({elapsed:.2f}s)")

            # ── Transient Driver / Network Exceptions (Automatic Recovery) ───
            except _DRIVER_ERRORS as exc:
                exc_desc = f"Driver/Network error ({type(exc).__name__}: {exc})"
                ctx.last_failed_block = block.name
                ctx.retry_reason = exc_desc

                # Abort if the case has exceeded the maximum allowable driver retries
                if driver_retries >= _MAX_DRIVER_RETRIES:
                    log_message(f"❌ [{ctx.case_id}] Max driver retries reached in block [{block.name}]: {exc_desc}")
                    self._emit(ctx, block, BlockStatus.FAILED, reason=exc_desc)
                    self._skip_remaining(ctx, i + 1)
                    self._release_driver(ctx)
                    return SearchResult.ERROR

                driver_retries += 1
                log_message(f"⚠️ [{ctx.case_id}] Driver error in block [{block.name}]: {exc_desc} — retry {driver_retries}/{_MAX_DRIVER_RETRIES}")
                self._emit(ctx, block, BlockStatus.RETRYING, reason=exc_desc)

                # Reset VPN IP address and swap driver instance from pool
                ctx.driver_pool.reset_vpn_pool(ctx.driver)
                ctx.driver = ctx.driver_pool.close_and_refill(ctx.driver)

                # Rewind pointer back to CourtNavigationBlock (re-auth on new driver)
                i = 1
                continue

            # ── Truly Unexpected Python Exceptions (Fatal) ───────────────────
            except Exception as exc:
                exc_desc = f"Unexpected error in block [{block.name}]: {type(exc).__name__} ({exc})"
                ctx.last_failed_block = block.name
                ctx.retry_reason = exc_desc
                self._emit(ctx, block, BlockStatus.FAILED, reason=exc_desc)
                _log_unexpected_error(ctx, block, exc)
                traceback.print_exc()

                # Mark telemetry run as failed in Supabase
                if getattr(ctx, "tracker", None):
                    try:
                        ctx.tracker.complete_run(success=False)
                    except Exception:
                        pass
                return SearchResult.ERROR

            # ── Signal Routing & State Machine Transitions ───────────────────
            if signal == BlockSignal.OK:
                # Background blocks manage their own terminal statuses asynchronously
                if block.name not in ("Deed Search", "Obituary Search"):
                    self._emit(ctx, block, BlockStatus.SUCCESS)
                i += 1  # Advance to next block

            elif signal in (
                BlockSignal.RETRY_DRIVER,
                BlockSignal.RETRY_FROM_START,
                BlockSignal.RETRY_FROM_NAV,
                BlockSignal.RETRY_FROM_ROW,
            ):
                driver_retries += 1
                failed_block = getattr(ctx, "last_failed_block", None) or block.name
                failed_verifier = getattr(ctx, "last_failed_verifier", None)
                reason = getattr(ctx, "retry_reason", None) or f"Block requested {signal.value}"

                if failed_verifier:
                    log_info = f"Block [{failed_block}] failed verifier '{failed_verifier}' — Cause: {reason}"
                else:
                    log_info = f"Block [{failed_block}] — Cause: {reason}"

                log_message(f"🔄 [{ctx.case_id}] Retry ({signal.value}) {driver_retries}/{_MAX_DRIVER_RETRIES}: {log_info}")
                self._emit(ctx, block, BlockStatus.RETRYING, reason=log_info)

                # Handle specific rewind targets
                if signal == BlockSignal.RETRY_FROM_START:
                    ctx.driver.refresh()
                    # Re-run current block

                elif signal == BlockSignal.RETRY_DRIVER:
                    ctx.driver = ctx.driver_pool.close_and_refill(ctx.driver)
                    i = 0  # Restart from Block 0 (PrecheckBlock)

                elif signal == BlockSignal.RETRY_FROM_NAV:
                    ctx.driver = ctx.driver_pool.close_and_refill(ctx.driver)
                    i = 1  # Rewind to Block 1 (CourtNavigationBlock)

                elif signal == BlockSignal.RETRY_FROM_ROW:
                    if ctx.row_index_to_retry is not None:
                        ctx.start_index = ctx.row_index_to_retry
                    ctx.driver = ctx.driver_pool.close_and_refill(ctx.driver)
                    i = 2  # Rewind to Block 2 (CaseCheckingBlock) with offset

            elif signal in (BlockSignal.NOT_FOUND, BlockSignal.SKIP):
                # Case does not exist or disqualified: mark current block and remaining as skipped
                self._emit(ctx, block, BlockStatus.SKIPPED)
                self._skip_remaining(ctx, i + 1)
                self._release_driver(ctx)
                if getattr(ctx, "tracker", None):
                    try:
                        ctx.tracker.complete_run(success=False)
                    except Exception:
                        pass
                return SearchResult.NOT_FOUND

            elif signal == BlockSignal.STOP:
                # Fatal block stop signal: mark failed, skip downstream blocks, release driver
                self._emit(ctx, block, BlockStatus.FAILED)
                self._skip_remaining(ctx, i + 1)
                self._release_driver(ctx)
                if getattr(ctx, "tracker", None):
                    try:
                        ctx.tracker.complete_run(success=False)
                    except Exception:
                        pass
                return SearchResult.ERROR

            # Safety valve check against runaway retry loops
            if driver_retries >= _MAX_DRIVER_RETRIES:
                self._skip_remaining(ctx, i + 1)
                self._release_driver(ctx)
                if getattr(ctx, "tracker", None):
                    try:
                        ctx.tracker.complete_run(success=False)
                    except Exception:
                        pass
                return SearchResult.ERROR

        # ── Pipeline Completion ───────────────────────────────────────────────
        # All sequential blocks succeeded: finalize the Supabase telemetry record
        if getattr(ctx, "tracker", None):
            try:
                ctx.tracker.complete_run(success=True)
            except Exception:
                pass
        return SearchResult.SUCCESS

    # ── Internal Resource & Event Helpers ─────────────────────────────────────

    def _release_driver(self, ctx: PipelineContext) -> None:
        """Safely return driver to the driver pool on early termination."""
        try:
            if hasattr(ctx, "driver_pool") and getattr(ctx, "driver", None):
                ctx.driver_pool.release_driver(ctx.driver)
        except Exception:
            pass

    def _skip_remaining(self, ctx: PipelineContext, from_index: int) -> None:
        """Mark all unreached downstream pipeline blocks as SKIPPED in the UI."""
        for rem_block in self.blocks[from_index:]:
            self._emit(ctx, rem_block, BlockStatus.SKIPPED)

    def _emit(
        self,
        ctx: PipelineContext,
        block: PipelineBlock,
        status: BlockStatus,
        reason: Optional[str] = None
    ) -> None:
        """Record block status in context and invoke listener callback with error shielding."""
        ctx.block_statuses[block.name] = status
        if self.on_status_change:
            try:
                import inspect
                sig = inspect.signature(self.on_status_change)
                if len(sig.parameters) >= 4:
                    self.on_status_change(ctx.case_id, block.name, status, reason)
                else:
                    self.on_status_change(ctx.case_id, block.name, status)
            except Exception:
                try:
                    self.on_status_change(ctx.case_id, block.name, status)
                except Exception:
                    pass  # Never let UI callback exceptions interrupt core pipeline scraping


def _log_unexpected_error(ctx, block: PipelineBlock, exc: Exception) -> None:
    """Best-effort diagnostics logger capturing case context, URL, and stack trace."""
    try:
        from app import log_message, update_case_status
        county = (
            getattr(ctx, 'config', {}).get('county_name')
            or getattr(ctx, 'account', {}).get('county', 'Unknown')
            or 'Unknown'
        )
        curr_url = "unknown"
        if hasattr(ctx, "driver") and ctx.driver:
            try:
                curr_url = getattr(ctx.driver, "current_url", "unknown")
            except Exception:
                pass
        msg = str(exc)
        if "Stacktrace" in msg:
            msg = msg.split("Stacktrace")[0]
        log_message(
            f"❌ [{ctx.case_id}] [{block.name}] Unexpected error ({type(exc).__name__}: {msg}) at URL: {curr_url}\n{traceback.format_exc()}"
        )
        update_case_status(ctx.driver, ctx.case_id, county, "Error", details=msg)
        if hasattr(ctx, "driver_pool") and ctx.driver:
            ctx.driver_pool.release_driver(ctx.driver)
    except Exception:
        pass
