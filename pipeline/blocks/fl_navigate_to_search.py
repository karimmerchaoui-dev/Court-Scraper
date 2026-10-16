"""
Block 2 — NavigateToSearchBlock (Florida)
===========================================
Navigates to the court record search page on the Florida county website.

Workflow:
---------
1. Credential & Parameter Preparation:
   - Reads `navigate_to_search`, `username`, and `password` from county configuration.
   - If `navigate_to_search` is not defined (county begins directly on search),
     yields `BlockSignal.OK`.
   - Assembles arguments: `(driver, username, password)` for authenticated portals
     or `(driver,)` for public inquiry portals.
2. Step Execution:
   - Updates UI status to "Browsing to search".
   - Invokes `_run_step` with verifier `_get_verifier(county_name, 'navigate_to_search')`
     and configurable timeout watchdog.
3. Outcome Handling:
   - `found is False`: Marks case as "Case Not Found" and yields `BlockSignal.NOT_FOUND`.
   - `StepAbort` / `StepTimeout`: Search navigation failed or stalled; yields
     `BlockSignal.RETRY_DRIVER` to recycle the Selenium browser instance.
   - `VerifyFailed`: Search elements missing from DOM; resets VPN and yields
     `BlockSignal.RETRY_DRIVER`.
   - Normal completion: Yields `BlockSignal.OK` to proceed to case number input.
"""

from __future__ import annotations

import pysnooper

from app import log_message, update_case_status
from pipeline.base import BlockSignal, PipelineBlock
from state import state


class NavigateToSearchBlock(PipelineBlock):
    """Block 2 (Florida): Navigates from portal home to the case search form.

    Supports both anonymous public portals and credentialed portals requiring
    login forms before accessing docket searches.
    """

    def __init__(self) -> None:
        """Initialize Block 2 with standardized human-readable name."""
        super().__init__("Navigate to Search")


    def execute(self, ctx) -> BlockSignal:
        """Executes navigation to the county search interface.

        Parameters
        ----------
        ctx : FloridaPipelineContext
            Current execution context containing driver, county configuration,
            case ID, and driver pool.

        Returns
        -------
        BlockSignal
            - `BlockSignal.OK`: Search page loaded and verified.
            - `BlockSignal.NOT_FOUND`: Search page unreachable or case not found.
            - `BlockSignal.RETRY_DRIVER`: Step timeout or verifier failure requiring
              driver recycling and retry.
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
        navigate_to_search = config['navigate_to_search']
        username = config.get("username")
        password = config.get("password")
        step_timeouts = config.get("step_timeouts", {})

        # Skip step if county workflow does not require a separate search navigation
        if not navigate_to_search:
            return BlockSignal.OK

        # Broadcast progress to desktop GUI / telemetry
        update_case_status(
            ctx.driver, ctx.case_id, county_name,
            "Browsing to search", details="Browsing to search page",
        )

        # Build positional arguments based on portal authentication requirements
        args = (ctx.driver, username, password) if (username and password) else (ctx.driver,)

        try:
            # Execute step through managed runner with verification and timeout limits
            found = _run_step(
                navigate_to_search, args,
                ctx.driver, ctx.driver_pool, county_name, ctx.case_id,
                verify=_get_verifier(county_name, 'navigate_to_search'),
                step_timeout=step_timeouts.get('navigate_to_search', 60),
            )
            # Check user cancellation / pause events
            check_skip()

            # False signifies that the search page could not be located or rendered
            if not found:
                state.report_cases[ctx.case_id]['status'] = "Case Not Found"
                update_case_status(
                    ctx.driver, ctx.case_id, county_name,
                    "Case Not Found", details="Case Not Found"
                )
                return BlockSignal.NOT_FOUND

            return BlockSignal.OK

        except (StepAbort, StepTimeout) as e:
            # Step hung or encountered unrecoverable DOM exception
            cause = getattr(e, "cause", None) or f"Step '{e.step_name}' failed ({type(e).__name__})"
            ctx.last_failed_block = self.name
            ctx.last_failed_verifier = None
            ctx.retry_reason = str(cause)
            log_message(f"❌ [{county_name}] [{self.name}] {cause} for {ctx.case_id} — retrying block")
            update_case_status(
                ctx.driver, ctx.case_id, county_name,
                "Retrying", details=f"Block [{self.name}]: {cause}"
            )
            # Recreate browser session before attempting search navigation again
            return BlockSignal.RETRY_DRIVER

        except VerifyFailed as e:
            # Search input fields or form elements failed verification
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
            # Rotate network VPN in case of rate-limiting or anti-bot challenge
            ctx.driver_pool.reset_vpn_pool(ctx.driver)
            return BlockSignal.RETRY_DRIVER
