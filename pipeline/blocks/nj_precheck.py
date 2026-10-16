"""
==============================================================================
Block 1: PrecheckBlock — Pre-Scrape Case Eligibility & Market Valuation
==============================================================================

Overview:
---------
Evaluates property market conditions and sheriff foreclosure sales listings
BEFORE navigating or authenticating on the New Jersey court portal.

Operational Logic:
------------------
1. Precheck Cache Reuse:
   - In standard execution, `CaseExecutor._submit_all_cases()` runs prechecks in
     parallel using an eligibility thread pool. If cached precheck data already
     exists in `_precheck_cache`, this block immediately reuses it to avoid
     duplicate API calls and billing.

2. Live Evaluation (Fallback):
   - Zillow Lookup: Queries Apify Zillow actor (`_fetch_zillow`) to retrieve
     property Zestimate, listing status (FOR_SALE, PENDING, SOLD), and auction flags.
   - SalesWeb Lookup: Queries CivilView/SalesWeb (`extract_info_from_salesweb`)
     to retrieve foreclosure sale upset prices, upset amounts, and judgment balances.

3. Disqualification (RIP Check):
   - If the property is currently listed FOR_SALE or AUCTION with insufficient equity,
     it is marked "Ineligible" / "RIP", releases the browser driver, and signals
     `BlockSignal.SKIP` to bypass court scraping.
==============================================================================
"""

from __future__ import annotations

import os
import traceback

import pysnooper

from app import log_message, update_case_status
from pipeline.base import BlockSignal, PipelineBlock, PipelineContext
from state import state


class _NullCtx:
    """No-op context manager fallback used when telemetry tracking is inactive."""
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def set_metadata(self, *a): pass


class PrecheckBlock(PipelineBlock):
    """Block 1: Pre-court eligibility validation via Zillow and SalesWeb."""

    def __init__(self):
        super().__init__("Precheck")

    @pysnooper.snoop()
    def execute(self, ctx: PipelineContext) -> BlockSignal:
        """Run eligibility checks and populate `ctx.precheck_data`.

        Args:
            ctx (PipelineContext): Active case execution context.

        Returns:
            BlockSignal: `BlockSignal.OK` if eligible or missing address;
                         `BlockSignal.SKIP` if disqualified.
        """
        case_id   = ctx.case_id
        report    = state.report_cases.get(case_id, {})
        address   = report.get("address", "")
        county    = report.get("county", "")
        processor = report.get("county", "New Jersey")

        # ── Step 1: Check for Cached Precheck Results ─────────────────────────
        # CaseExecutor runs parallel eligibility prechecks prior to dispatching
        # drivers. If results are cached, reuse them and advance immediately.
        from counties.nj_helpers import pop_precheck_data
        cached_precheck = pop_precheck_data(case_id)
        if cached_precheck:
            log_message(f"⚡ [{case_id}] Reusing cached precheck data (skipping duplicate Zillow/SalesWeb calls)")
            ctx.precheck_data = cached_precheck
            update_case_status(
                ctx.driver, case_id, "New Jersey",
                "Precheck",
                details="Reused cached eligibility data",
            )
            return BlockSignal.OK

        # ── Step 2: Fallback Live Eligibility Check ───────────────────────────
        update_case_status(
            ctx.driver, case_id, "New Jersey",
            "Checking Eligibility",
            details=f"Running RIP check for {address}",
        )

        # Fail-open: If no property address was supplied in the input, proceed with scraping
        if not address or not processor:
            log_message(f"ℹ️ [{case_id}] Skipping eligibility — missing address or processor")
            ctx.precheck_data = {}
            return BlockSignal.OK

        try:
            from browser.OP import extract_info_from_salesweb
            from utils.calls_helpers import _fetch_zillow
            from utils.formatting import safe_int

            files_dir = ctx.files_dir or ""
            os.makedirs(files_dir, exist_ok=True)

            if "jersey" in processor.lower() and "nj" not in address.lower():
                address = f"{address}, NJ"

            # ── Zillow Property Valuation ─────────────────────────────────────
            _tracker = getattr(ctx, "tracker", None)
            with (_tracker.track_step("zillow", "fetch_property_estimate") if _tracker else _NullCtx()) as _z:
                zest, status, home_type, city, prop_type, is_agent, is_auction = _fetch_zillow(address, files_dir)
                if _tracker:
                    _z.set_metadata("zestimate", zest)
                    _z.set_metadata("listing_status", status)
                    _z.set_metadata("is_auction", is_auction)
                    _z.set_metadata("address", address)

            precheck = {
                "zestimate":  zest,
                "zillow_status": "AUCTION" if is_auction else status,
                "home_type":  home_type,
            }

            # ── SalesWeb Foreclosure Search ───────────────────────────────────
            try:
                county_clean = county.split("County")[0].strip()
                with (_tracker.track_step("salesweb", "matching_address") if _tracker else _NullCtx()) as _sw_match:
                    sw = extract_info_from_salesweb(address, county_clean, "NJ")
                    if _tracker:
                        _sw_match.set_metadata("address_queried", address)
                        _sw_match.set_metadata("matched", bool(sw))
                        _sw_match.set_metadata("sales_web_address", sw.get("sales_web_address") if sw else None)

                if sw:
                    precheck["salesweb"] = sw
                    with (_tracker.track_step("salesweb", "extract_financial_obligations") if _tracker else _NullCtx()) as _fin:
                        financial_obligations = sw.get("financial_obligations") or []
                        unpaid_amounts = [
                            safe_int(o.get("amount"))
                            for o in financial_obligations
                            if isinstance(o, dict) and o.get("category") == "unpaid_amount"
                        ]
                        valid_amounts = [x for x in unpaid_amounts if x is not None]
                        precheck["unpaid_balance"] = max(valid_amounts) if valid_amounts else None
                        if _tracker:
                            _fin.set_metadata("obligations_count", len(financial_obligations))
                            _fin.set_metadata("unpaid_balance", precheck["unpaid_balance"])
                            _fin.set_metadata("approx_judgment", sw.get("approx_judgment"))
            except Exception as sw_exc:
                traceback.print_exc()
                log_message(f"⚠️ [{case_id}] SalesWeb error (non-fatal): {sw_exc}")

            ctx.precheck_data = precheck

            # ── Disqualification Decision ─────────────────────────────────────
            zillow_status = precheck.get("zillow_status", "")
            if isinstance(zillow_status, str) and "rip" in zillow_status.lower():
                log_message(f"🚫 [{case_id}] Ineligible — Zillow status: {zillow_status}")
                update_case_status(
                    ctx.driver, case_id, "New Jersey", "Ineligible",
                    details=f"Zillow RIP: {zillow_status}",
                )
                ctx.driver_pool.release_driver(ctx.driver)
                return BlockSignal.SKIP

            log_message(f"✅ [{case_id}] Eligible — Zillow: {zillow_status}")
            return BlockSignal.OK

        except Exception as exc:
            # Precheck exceptions are non-fatal: fail-open and allow scraping
            log_message(f"⚠️ [{case_id}] Precheck error (proceeding anyway): {exc}")
            ctx.precheck_data = {}
            return BlockSignal.OK
