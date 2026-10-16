"""
==============================================================================
Block 2: CourtNavigationBlock — NJ Portal Authentication & Docket Search
==============================================================================

Overview:
---------
Responsible for establishing an authenticated session on the New Jersey eCourts
judiciary portal and searching for the target case docket.

Operational Phases:
-------------------
1. Phase 1 (Portal Navigation & Authentication):
   - Navigates to the portal URL (`NJ_LOGIN_PAGE`).
   - Checks cookie session validity. If expired or unauthenticated, inputs
     account credentials via `_navigate_and_login_nj()`, handles 2FA/captchas,
     and verifies that the civil docket search form is displayed.

2. Phase 2 (Docket Entry & Search Execution):
   - Types docket sequence and filing year into the portal search form using
     humanized keystroke delays (`human_type`).
   - Clicks search and evaluates the response:
       * `SearchResult.SUCCESS`: Landed on case details or document table page.
       * `SearchResult.NOT_FOUND`: Court displays 'No records found'. Returns `BlockSignal.NOT_FOUND`.
       * `SearchResult.RETRY_NEEDED`: Session timed out, captcha failed, or DOM state stale.
         Returns `BlockSignal.RETRY_DRIVER` to prompt driver swap.
       * `SearchResult.ERROR`: Fatal unhandled portal error. Returns `BlockSignal.STOP`.
==============================================================================
"""

from __future__ import annotations

from app import update_case_status
from browser.browser_helpers import get_thread_number
from core.SearchResult import SearchResult
from pipeline.base import BlockSignal, PipelineBlock, PipelineContext
from state import state


class CourtNavigationBlock(PipelineBlock):
    """Block 2: Portal login, session validation, and docket number search."""

    def __init__(self):
        super().__init__("Court Navigation")

    def execute(self, ctx: PipelineContext) -> BlockSignal:
        """Authenticate on the court portal and query the docket number.

        Args:
            ctx (PipelineContext): Active case execution context.

        Returns:
            BlockSignal: Directive indicating navigation outcome:
                         - `BlockSignal.OK`: Successfully reached case page.
                         - `BlockSignal.NOT_FOUND`: Case absent from court database.
                         - `BlockSignal.RETRY_DRIVER`: Authentication or search hang.
                         - `BlockSignal.STOP`: Unrecoverable portal error.
        """
        from main import _navigate_and_login_nj, _search_case_nj, check_skip

        driver      = ctx.driver
        case_id     = ctx.case_id
        account     = ctx.account
        driver_pool = ctx.driver_pool
        year        = ctx.year
        docket      = ctx.docket
        thread_num  = get_thread_number()

        # ── Phase 1: Portal Navigation & Credential Authentication ────────────
        login_result = _navigate_and_login_nj(driver, account, driver_pool, case_id, thread_num)
        if login_result == SearchResult.RETRY_NEEDED:
            ctx.last_failed_block = self.name
            ctx.retry_reason = "NJ login / navigation failed (prompting driver swap)"
            return BlockSignal.RETRY_DRIVER
        if login_result == SearchResult.ERROR:
            ctx.last_failed_block = self.name
            ctx.retry_reason = "NJ login / navigation fatal error"
            return BlockSignal.STOP

        # Ensure user cancellation check has not fired
        check_skip()

        # ── Phase 2: Docket Search Submission & Response Evaluation ───────────
        search_result = _search_case_nj(driver, year, docket, driver_pool, account, case_id, thread_num)
        if search_result == SearchResult.NOT_FOUND:
            update_case_status(driver, case_id, "New Jersey", "Case Not Found", details="Case Not Found")
            if case_id in state.report_cases:
                state.report_cases[case_id]["status"] = "Case Not Found"
            return BlockSignal.NOT_FOUND

        if search_result == SearchResult.RETRY_NEEDED:
            ctx.last_failed_block = self.name
            ctx.retry_reason = "NJ search case failed (element missing or stale session)"
            return BlockSignal.RETRY_DRIVER

        if search_result == SearchResult.ERROR:
            ctx.last_failed_block = self.name
            ctx.retry_reason = "NJ search case fatal error"
            return BlockSignal.STOP

        check_skip()

        return BlockSignal.OK
