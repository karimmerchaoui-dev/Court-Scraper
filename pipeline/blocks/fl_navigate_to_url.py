"""
Block 1 — NavigateToUrlBlock (Florida)
========================================
Opens the primary county court portal URL to begin Florida case processing.

Workflow:
---------
1. Configuration Lookup:
   - Retrieves county configuration parameters: `county_name`, `navigate_to_url`
     callable, and configured timeout thresholds.
   - If `navigate_to_url` is unconfigured (some counties start directly at search),
     the block gracefully returns `BlockSignal.OK`.
2. Navigation Execution:
   - Invokes `_run_step()` wrapping the county's specific navigation helper.
   - Attaches DOM verifier (`_get_verifier(county_name, 'navigate_to_url')`)
     to confirm portal elements rendered properly.
3. Outcome Handling:
   - `found is False`: Marks case as "Case Not Found" and yields `BlockSignal.NOT_FOUND`.
   - `StepAbort` / `StepTimeout`: Court portal timed out or crashed; resets VPN/driver
     pool and yields `BlockSignal.RETRY_FROM_START`.
   - `VerifyFailed`: Portal loaded unexpected DOM (e.g., Cloudflare block / maintenance);
     resets VPN and yields `BlockSignal.RETRY_FROM_START`.
   - Normal completion: Yields `BlockSignal.OK` to transition to search navigation.
"""
from __future__ import annotations

import pysnooper

from app import log_message, update_case_status
from pipeline.base import BlockSignal, PipelineBlock
from state import state


class NavigateToUrlBlock(PipelineBlock):
    """Block 1 (Florida): Loads the county court portal entry URL.

    Wraps step 1 of Florida county processing, executing the county-specific
    navigation callable with automated verifiers, timeout monitoring, and
    VPN rotation on network/portal failures.
    """

    def __init__(self) -> None:
        """Initialize Block 1 with standardized human-readable name."""
        super().__init__("Navigate to URL")

    def execute(self, ctx) -> BlockSignal:
        """Executes the court website navigation step.

        Parameters
        ----------
        ctx : FloridaPipelineContext
            State context containing driver, county configuration, case ID,
            and driver pool reference.

        Returns
        -------
        BlockSignal
            - `BlockSignal.OK`: Portal loaded and verified successfully.
            - `BlockSignal.NOT_FOUND`: Target portal returned no case/landing match.
            - `BlockSignal.RETRY_FROM_START`: Navigation timed out or failed verifier;
              initiates driver/VPN rotation and restarts the workflow.
        """
        # Late imports avoid circular dependency cycles with main orchestration module
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
        navigate_to_url = config['navigate_to_url']
        step_timeouts = config.get("step_timeouts", {})

        # Some Florida counties bypass the general landing page and open search directly
        if not navigate_to_url:
            return BlockSignal.OK

        try:
            # Execute step with dedicated verifier and timeout watchdog
            found = _run_step(
                navigate_to_url, (ctx.driver, ctx.case_id),
                ctx.driver, ctx.driver_pool, county_name, ctx.case_id,
                verify=_get_verifier(county_name, 'navigate_to_url'),
                step_timeout=step_timeouts.get('navigate_to_url', 60),
            )
            # Check if user requested pause, stop, or skip during navigation
            check_skip()

            # False indicates the case ID / URL could not be resolved by the portal
            if not found:
                state.report_cases[ctx.case_id]['status'] = "Case Not Found"
                update_case_status(
                    ctx.driver, ctx.case_id, county_name,
                    "Case Not Found", details="Case Not Found"
                )
                return BlockSignal.NOT_FOUND

            return BlockSignal.OK

        except (StepAbort, StepTimeout) as e:
            # Handle driver crash, navigation freeze, or portal network timeout
            cause = getattr(e, "cause", None) or f"Step '{e.step_name}' failed ({type(e).__name__})"
            ctx.last_failed_block = self.name
            ctx.last_failed_verifier = None
            ctx.retry_reason = str(cause)
            log_message(f"❌ [{county_name}] [{self.name}] {cause} for {ctx.case_id} — retrying from start")
            update_case_status(
                ctx.driver, ctx.case_id, county_name,
                "Retrying", details=f"Block [{self.name}]: {cause}"
            )
            # Rotate VPN and cycle network connection before restarting pipeline
            ctx.driver_pool.reset_vpn_pool(ctx.driver)
            return BlockSignal.RETRY_FROM_START

        except VerifyFailed as e:
            # Verifier detected unexpected page state (anti-bot challenge, session timeout, etc.)
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
