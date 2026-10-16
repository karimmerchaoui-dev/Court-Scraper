"""
Block 3 — SearchCaseNumberBlock (Florida)
===========================================
Inputs the target case number into the search form and executes the query.

Workflow:
---------
1. Status Update:
   - Updates UI status to "Entering docket" with the active case identifier.
2. Form Input & Submission:
   - Invokes `_run_step(search_case_number, (driver, case_id), ...)` using the
     county-specific search routine.
   - Evaluates DOM response via `_get_verifier(county_name, 'search_case_number')`
     to confirm search results or case detail view loaded.
3. Outcome Handling:
   - `found is False`: Case ID was not recognized by the court portal; sets status
     to "Case Not Found" and yields `BlockSignal.NOT_FOUND`.
   - `StepAbort` / `StepTimeout`: Search form submission timed out or crashed;
     yields `BlockSignal.RETRY_DRIVER` to recycle the browser.
   - `VerifyFailed`: Search result page failed DOM checks (e.g., CAPTCHA barrier);
     resets VPN and yields `BlockSignal.RETRY_DRIVER`.
   - Normal completion: Yields `BlockSignal.OK` to proceed to file navigation.
"""

from __future__ import annotations

import pysnooper

from app import log_message, update_case_status
from pipeline.base import BlockSignal, PipelineBlock
from state import state


class SearchCaseNumberBlock(PipelineBlock):
    """Block 3 (Florida): Types and submits the case number in the search form.

    Translates county-specific docket formatting and executes search actions,
    verifying that the portal transitions to the case summary or results table.
    """

    def __init__(self) -> None:
        """Initialize Block 3 with standardized human-readable name."""
        super().__init__("Search Case Number")


    def execute(self, ctx) -> BlockSignal:
        """Executes case query submission on the court portal.

        Parameters
        ----------
        ctx : FloridaPipelineContext
            Current execution context containing driver, county configuration,
            case ID, and driver pool.

        Returns
        -------
        BlockSignal
            - `BlockSignal.OK`: Case search succeeded and results page loaded.
            - `BlockSignal.NOT_FOUND`: Case number does not exist in court records.
            - `BlockSignal.RETRY_DRIVER`: Submission error, timeout, or failed verifier.
        """
        # Late imports avoid circular dependencies with main module
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
        search_case_number = config['search_case_number']
        step_timeouts = config.get("step_timeouts", {})
        
        # If county has no dedicated search routine, proceed immediately
        if not search_case_number:
            return BlockSignal.OK

        # Broadcast active step to desktop UI
        update_case_status(
            ctx.driver, ctx.case_id, county_name,
            "Entering docket", details=f"Entering {ctx.case_id}",
        )

        try:
            # Type case number and submit search with timeout and verifier enforcement
            found = _run_step(
                search_case_number, (ctx.driver, ctx.case_id),
                ctx.driver, ctx.driver_pool, county_name, ctx.case_id,
                verify=_get_verifier(county_name, 'search_case_number'),
                step_timeout=step_timeouts.get('search_case_number', 60),
            )
            # Evaluate user stop/pause flag
            check_skip()

            # Portal explicitly signaled that 0 matching records were found
            if not found:
                state.report_cases[ctx.case_id]['status'] = "Case Not Found"
                update_case_status(
                    ctx.driver, ctx.case_id, county_name,
                    "Case Not Found", details="Case Not Found"
                )
                return BlockSignal.NOT_FOUND

            return BlockSignal.OK

        except (StepAbort, StepTimeout) as e:
            # Search submission stalled or failed unexpectedly
            cause = getattr(e, "cause", None) or f"Step '{e.step_name}' failed ({type(e).__name__})"
            ctx.last_failed_block = self.name
            ctx.last_failed_verifier = None
            ctx.retry_reason = str(cause)
            log_message(f"❌ [{county_name}] [{self.name}] {cause} for {ctx.case_id} — retrying block")
            update_case_status(
                ctx.driver, ctx.case_id, county_name,
                "Retrying", details=f"Block [{self.name}]: {cause}"
            )
            # Cycle browser session and retry search
            return BlockSignal.RETRY_DRIVER

        except VerifyFailed as e:
            # Result page verifier failed (e.g., CAPTCHA presented or table missing)
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
            # Reset VPN connection to bypass IP rate limits or bot-detection barriers
            ctx.driver_pool.reset_vpn_pool(ctx.driver)
            return BlockSignal.RETRY_DRIVER
