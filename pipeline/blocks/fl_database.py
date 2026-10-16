"""
Block 8 — FloridaDatabaseBlock (Florida)
==========================================
Final pipeline stage for Florida county processing: verifies downloaded filings,
enriches property data via Zillow, synchronizes records to Supabase, updates GUI
progress counters, and guarantees browser driver release.

Workflow:
---------
1. Complaint File Verification:
   - Scans `files_dir` for files containing the word "complaint" (case-insensitive).
   - If present, case is marked "Completed"; otherwise marked "Error" with
     Flag: "No complaint found".
2. Real Estate / Zillow Enrichment:
   - Identifies best available property address (`property_address` or fallback
     `address` from input CSV).
   - Skips lookup if precheck already fetched Zillow data for the exact address.
   - Otherwise, invokes `_fetch_zillow(address, files_dir)` to retrieve Zestimate,
     property status (e.g. "AUCTION"), property type, and agent listing indicators.
   - Non-fatal: failures update `update_pipeline_status("zillow", "FAILED")` and log warnings.
3. Supabase Cloud Database Ingestion:
   - Calls `add_case_with_files()` to persist case metadata, party lists, and
     upload downloaded PDF court documents to Supabase storage.
   - Reports telemetry status to `update_pipeline_status("database", ...)`.
4. Final Update & GUI Progress Broadcast:
   - Calls `final_update()` to compute case processing duration, advance the progress
     bar, increment total completed cases, and update UI table rows.
5. Resource Cleanup (Guaranteed in `finally`):
   - Releases the Selenium WebDriver instance back to `ctx.driver_pool`.
"""

from __future__ import annotations

import os
import traceback


from app import log_message, update_case_status, update_progress
from database.supabase_service import add_case_with_files
from pipeline.base import BlockSignal, PipelineBlock
from pipeline_tracker import update_pipeline_status
from state import state


class FloridaDatabaseBlock(PipelineBlock):
    """Block 8 (Florida): Complaint verification, property enrichment, DB persistence.

    Acts as the terminal stage in the Florida county pipeline, finalizing data
    and safely reclaiming browser resources back into the driver pool.
    """

    def __init__(self) -> None:
        """Initialize Block 8 with standardized human-readable name."""
        super().__init__("Database Adding")

    def execute(self, ctx) -> BlockSignal:
        """Executes the Florida terminal persistence and cleanup workflow.

        Parameters
        ----------
        ctx : FloridaPipelineContext
            Current execution context containing driver, county configuration,
            case ID, target directory, start timestamp, and driver pool.

        Returns
        -------
        BlockSignal
            Always returns `BlockSignal.OK` to indicate the terminal pipeline
            stage has completed.
        """
        # Late imports avoid circular dependencies with main execution loop
        from main import (
            _settings,
            input_file,
            status_text,
        )
        from utils.gui_helpers import final_update
        from utils.calls_helpers import _fetch_zillow

        case_id = ctx.case_id
        county_name = ctx.config['county_name']
        files_dir = ctx.files_dir

        try:
            # ── 1. Check for complaint file in downloaded folder ──────────────
            has_complaint = False
            if os.path.exists(files_dir):
                has_complaint = any(
                    'complaint' in f.lower()
                    for f in os.listdir(files_dir)
                    if os.path.isfile(os.path.join(files_dir, f))
                )

            final_status = "Completed" if has_complaint else "Error"
            if not has_complaint:
                state.report_cases[case_id]['Flag'] = "No complaint found"

            # ── 2. Zillow Real Estate Data Enrichment ─────────────────────────
            prop_addr = state.report_cases[case_id].get('property_address')
            orig_addr = state.report_cases[case_id].get('address', '')
            address = prop_addr or orig_addr

            if address:
                try:
                    batch_name = _settings.get(
                        "batch_name",
                        input_file.get().split("\\")[-1].split(".")[0],
                    )
                    # Verify if Zillow data was already fetched in precheck for this exact address
                    has_precheck_zillow = (
                        state.report_cases[case_id].get('zestimate') is not None
                        or state.report_cases[case_id].get('zillow_status') is not None
                    ) and (not prop_addr or prop_addr == orig_addr)

                    if not has_precheck_zillow:
                        zest, status, home_type, city, prop_type, is_agent, is_auction = _fetch_zillow(address, files_dir)
                        state.report_cases[case_id]['zestimate'] = zest
                        state.report_cases[case_id]['zillow_status'] = "AUCTION" if is_auction else status
                        state.report_cases[case_id]['property_type'] = prop_type
                        state.report_cases[case_id]['home_type'] = home_type
                        state.report_cases[case_id]['city'] = city
                        state.report_cases[case_id]['is_agent'] = is_agent
                except Exception as zillow_err:
                    update_pipeline_status("zillow", "FAILED", tb_message=traceback.format_exc())
                    log_message(f"⚠️ [{county_name}] Zillow error (non-fatal): {zillow_err}")

            # ── 3. Persist case and upload PDFs to Supabase ───────────────────
            try:
                add_case_with_files(
                    state.report_cases[case_id],
                    file_source=files_dir,
                    batch_name=batch_name,
                    force_replace=True,
                )
                update_pipeline_status("database", "SUCCESS")
            except Exception as db_err:
                update_pipeline_status("database", "FAILED", tb_message=traceback.format_exc())
                log_message(f"⚠️ [{county_name}] DB push error (non-fatal): {db_err}")

            # ── 4. Final update, duration calculation, and UI sync ────────────
            final_update(
                case_id, ctx.start_time, county_name,
                ctx.driver, ctx.driver_pool,
                state.report_cases, final_status,
                state.processed, state.total_cases,
                update_progress, status_text,
                callback_func=update_case_status,
            )

        except Exception as exc:
            log_message(f"❌ [{county_name}] FloridaDatabaseBlock error: {exc}")

        finally:
            # ── 5. Guaranteed driver reclamation back into pool ───────────────
            try:
                ctx.driver_pool.release_driver(ctx.driver)
            except Exception:
                pass

        return BlockSignal.OK
