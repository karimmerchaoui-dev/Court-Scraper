"""
Block 4 — NavigateToFilesBlock (Florida)
==========================================
Navigates to the documents / docket entries tab on the case details view.

Workflow:
---------
1. Configuration Check:
   - Evaluates `navigate_to_files` in the county configuration.
   - If unconfigured (docket entries appear directly on the main case view),
     yields `BlockSignal.OK`.
2. Navigation & DOM Verification:
   - Invokes `_run_step(navigate_to_files, (driver,), ...)` to click or switch
     to the documents tab/iframe.
   - Runs `_get_verifier(county_name, 'navigate_to_files')` to verify that the
     documents table is visible in the DOM.
3. Outcome Handling:
   - `found is False`: Documents tab unreachable; sets status to "Case Not Found"
     and yields `BlockSignal.NOT_FOUND`.
   - `StepAbort` / `StepTimeout`: Tab click or render failed; yields
     `BlockSignal.RETRY_DRIVER`.
   - `VerifyFailed`: Docket table not present; resets VPN and yields
     `BlockSignal.RETRY_FROM_START`.
   - Normal completion: Yields `BlockSignal.OK` to transition to file downloading.
"""

from __future__ import annotations

from app import log_message, update_case_status
from pipeline.base import BlockSignal, PipelineBlock
from state import state


class NavigateToFilesBlock(PipelineBlock):
    """Block 4 (Florida): Navigates to the case documents / docket table tab.

    Ensures the court portal has transitioned from the general case summary
    to the specific tab or view containing downloadable PDF records.
    """

    def __init__(self) -> None:
        """Initialize Block 4 with standardized human-readable name."""
        super().__init__("Navigate to Files")

    def execute(self, ctx) -> BlockSignal:
        """Executes the tab switch to the court documents interface.

        Parameters
        ----------
        ctx : FloridaPipelineContext
            Current execution context containing driver, county configuration,
            case ID, and driver pool.

        Returns
        -------
        BlockSignal
            - `BlockSignal.OK`: Documents table is visible and ready for download.
            - `BlockSignal.NOT_FOUND`: Case documents tab could not be opened.
            - `BlockSignal.RETRY_DRIVER`: Navigation step aborted or timed out.
            - `BlockSignal.RETRY_FROM_START`: Verifier failed; restarts with fresh VPN.
        """
        # Late imports avoid circular dependencies with main execution loop
        from main import (
            StepAbort,
            StepTimeout,
            VerifyFailed,
            _get_verifier,
            _run_step,
            check_skip,
        )

        config = ctx.config
        county_name = config['county_name']
        navigate_to_files = config['navigate_to_files']
        step_timeouts = config.get("step_timeouts", {})

        # Skip if docket files are displayed directly on the primary case page
        if not navigate_to_files:
            return BlockSignal.OK

        try:
            # Switch to documents view and verify presence of document rows/table
            found = _run_step(
                navigate_to_files, (ctx.driver,),
                ctx.driver, ctx.driver_pool, county_name, ctx.case_id,
                verify=_get_verifier(county_name, 'navigate_to_files'),
                step_timeout=step_timeouts.get('navigate_to_files', 60),
            )
            # Evaluate user stop/pause flag
            check_skip()

            # False indicates the documents view could not be rendered
            if not found:
                state.report_cases[ctx.case_id]['status'] = "Case Not Found"
                update_case_status(
                    ctx.driver, ctx.case_id, county_name,
                    "Case Not Found", details="Case Not Found"
                )
                return BlockSignal.NOT_FOUND

            return BlockSignal.OK

        except (StepAbort, StepTimeout) as e:
            # Navigation step stalled, element not clickable, or timeout reached
            cause = getattr(e, "cause", None) or f"Step '{e.step_name}' failed ({type(e).__name__})"
            ctx.last_failed_block = self.name
            ctx.last_failed_verifier = None
            ctx.retry_reason = str(cause)
            log_message(f"❌ [{county_name}] [{self.name}] {cause} for {ctx.case_id} — retrying block")
            update_case_status(
                ctx.driver, ctx.case_id, county_name,
                "Retrying", details=f"Block [{self.name}]: {cause}"
            )
            # Recreate browser session and retry file navigation
            return BlockSignal.RETRY_DRIVER

        except VerifyFailed as e:
            # Verifier detected missing document table (session expiration or bot challenge)
            v_desc = getattr(e, "verifier_desc", str(e))
            cause = f"Verifier failed on '{e.step_name}': {v_desc}"
            ctx.last_failed_block = self.name
            ctx.last_failed_verifier = v_desc
            ctx.retry_reason = cause
            log_message(
                f"🔄 [{county_name}] [{self.name}] Verifier failed on '{e.step_name}' "
                f"({v_desc}) for {ctx.case_id} — resetting VPN and retrying from start"
            )
            update_case_status(
                ctx.driver, ctx.case_id, county_name,
                "Retrying", details=f"Block [{self.name}] failed verifier: {v_desc}"
            )
            # Reset VPN connection and restart from beginning
            ctx.driver_pool.reset_vpn_pool(ctx.driver)
            return BlockSignal.RETRY_FROM_START
