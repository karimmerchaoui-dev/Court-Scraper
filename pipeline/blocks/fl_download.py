"""
Block 5 — DownloadFilesBlock (Florida)
========================================
Scans the court docket/document table and downloads case PDF filings.

Workflow:
---------
1. Keyword Matching & Download Invocation:
   - Assembles download parameters (table XPath, row tags, case type paths,
     destination directory `files_dir`, and cached matching rows).
   - Calls `download_files(**download_kwargs)` to scan table rows and download
     foreclosure complaints, lis pendens, judgments, and certificates.
2. Return Code Interpretation:
   - `down_flag == 0` / `None`: Download completed successfully (`BlockSignal.OK`).
   - `down_flag == 2`: Case matches skip criteria (e.g., non-foreclosure case type);
     marks status as "Skipped" and yields `BlockSignal.SKIP`.
   - `down_flag == 3`: CAPTCHA challenge or VPN blockage encountered; calls
     `reset_vpn_pool()` and yields `BlockSignal.RETRY_DRIVER`.
   - `down_flag == 1`: Transient download failure:
     a. Attempts quick re-navigation (`_re_navigate()`) on the SAME driver instance
        to avoid driver tear-down overhead.
     b. Retries `download_files()` with cached matching rows.
     c. If still failing (`down_flag == 1`), yields `BlockSignal.RETRY_FROM_NAV` to
        recycle the driver and re-run navigation from search.
     d. If retry encounters CAPTCHA (`down_flag == 3`), resets VPN and yields
        `BlockSignal.RETRY_DRIVER`.
"""

from __future__ import annotations

from app import log_message, update_case_status
from pipeline.base import BlockSignal, PipelineBlock
from state import state


class DownloadFilesBlock(PipelineBlock):
    """Block 5 (Florida): Downloads case PDF documents from the docket table.

    Manages keyword identification, download monitoring, and an intelligent
    two-tier retry strategy:
      - Tier 1: In-place page re-navigation on the existing driver session.
      - Tier 2: Driver recycling via `RETRY_FROM_NAV` if download continues failing.
    """

    def __init__(self) -> None:
        """Initialize Block 5 with standardized human-readable name."""
        super().__init__("Court Downloading")

    def execute(self, ctx) -> BlockSignal:
        """Executes docket inspection and file downloading.

        Parameters
        ----------
        ctx : FloridaPipelineContext
            Current execution context containing driver, county configuration,
            case ID, target download directory, and driver pool.

        Returns
        -------
        BlockSignal
            - `BlockSignal.OK`: Required court documents downloaded successfully.
            - `BlockSignal.SKIP`: Case is disqualified by county business rules.
            - `BlockSignal.RETRY_DRIVER`: CAPTCHA/VPN failure; requires VPN rotation.
            - `BlockSignal.RETRY_FROM_NAV`: Download failure persisting after in-place
              retry; requires new driver and re-navigation from search.
        """
        # Late imports avoid circular dependencies with main module
        from main import check_skip, download_files

        config = ctx.config
        county_name = config['county_name']
        case_id = ctx.case_id

        # Package parameters required by the county-specific download scanner
        download_kwargs = dict(
            driver=ctx.driver,
            files_dir=ctx.files_dir,
            case_id=case_id,
            county_name=county_name,
            table_path=config['download_table_xpath'],
            row_tag=config['docket_row_tag_name'],
            case_type_xpath=config['case_type_xpath'],
            case_url_prefix=config['files_page_url'],
            case_status_xpath=config.get('case_status_xpath', ''),
            table_xpath2=config.get('table_xpath2'),
            file_prefix=config.get('file_prefix'),
            parties_table_xpath=config.get('parties_table_xpath', ''),
            cached_matching_rows=ctx.cached_matching_rows,
            show_parties_table=config.get('show_parties_table'),
            show_dockets_table=config.get('show_dockets_table'),
        )

        # ── First download attempt ─────────────────────────────────────────────
        result = download_files(**download_kwargs)
        down_flag, returned_rows = self._unpack(result)

        # Cache identified docket rows to bypass table re-scan during retries
        if returned_rows:
            ctx.returned_rows = returned_rows

        # Flag 2: Case disqualified (e.g., probate, dismissed, non-foreclosure)
        if down_flag == 2:
            log_message(f"⏭️ [{county_name}] download_files requested skip for {case_id}")
            state.report_cases[case_id]['status'] = "Skipped"
            update_case_status(
                ctx.driver, case_id, county_name,
                "Skipped", details="Skipped during download"
            )
            return BlockSignal.SKIP

        # Flag 3: Bot detection, CAPTCHA, or IP ban detected by downloader
        if down_flag == 3:
            ctx.last_failed_block = self.name
            ctx.last_failed_verifier = None
            ctx.retry_reason = "Download returned flag 3 (VPN reset / captcha detected)"
            log_message(
                f"🔄 [{county_name}] [{self.name}] Download requested VPN reset (flag 3) "
                f"for {case_id} — retrying from start"
            )
            update_case_status(
                ctx.driver, case_id, county_name,
                "Retrying", details=f"Block [{self.name}]: captcha / VPN reset (flag 3)"
            )
            ctx.driver_pool.reset_vpn_pool(ctx.driver)
            return BlockSignal.RETRY_DRIVER

        # Flag 1: Transient download failure (file didn't save, click failed)
        if down_flag == 1:
            # ── Tier 1 Retry: Re-navigate on the SAME driver without recycling ─
            log_message(f"🔄 [{county_name}] [{self.name}] Download failed (flag 1) for {case_id} — re-navigating and retrying")
            update_case_status(
                ctx.driver, case_id, county_name, "Retrying",
                details=f"Block [{self.name}]: Download failed (flag 1), re-navigating"
            )
            try:
                self._re_navigate(ctx, config)
            except Exception as nav_err:
                ctx.last_failed_block = self.name
                ctx.last_failed_verifier = None
                ctx.retry_reason = f"Re-navigation failed during download retry: {nav_err}"
                log_message(f"⚠️ [{county_name}] [{self.name}] Re-navigation failed: {nav_err} — resetting driver and retrying from nav")
                update_case_status(
                    ctx.driver, case_id, county_name, "Retrying",
                    details=f"Block [{self.name}]: Re-navigation failed ({nav_err})"
                )
                return BlockSignal.RETRY_FROM_NAV

            # Supply previously parsed rows to avoid repeated table scraping
            download_kwargs['cached_matching_rows'] = returned_rows
            result2 = download_files(**download_kwargs)
            down_flag, returned_rows = self._unpack(result2)

            if returned_rows:
                ctx.returned_rows = returned_rows

            # Tier 2 Retry: In-place retry also failed; escalate to driver recycling
            if down_flag == 1:
                ctx.last_failed_block = self.name
                ctx.last_failed_verifier = None
                ctx.retry_reason = "Download still failing after retry re-navigation (flag 1)"
                log_message(f"❌ [{county_name}] [{self.name}] Download still failing after retry (flag 1) — resetting driver and retrying from nav")
                update_case_status(
                    ctx.driver, case_id, county_name, "Retrying",
                    details=f"Block [{self.name}]: Download failed after retry (flag 1)"
                )
                return BlockSignal.RETRY_FROM_NAV

            # Retry hit CAPTCHA / rate-limit
            if down_flag == 3:
                ctx.last_failed_block = self.name
                ctx.last_failed_verifier = None
                ctx.retry_reason = "Download returned flag 3 on retry (VPN reset / captcha detected)"
                log_message(f"🔄 [{county_name}] [{self.name}] Download requested VPN reset (flag 3) for {case_id} — retrying from start")
                update_case_status(
                    ctx.driver, case_id, county_name, "Retrying",
                    details=f"Block [{self.name}]: captcha / VPN reset (flag 3)"
                )
                ctx.driver_pool.reset_vpn_pool(ctx.driver)
                return BlockSignal.RETRY_DRIVER

        ctx.down_flag = down_flag
        # Check user cancellation / stop requested
        check_skip()
        return BlockSignal.OK

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _unpack(result: tuple | int | None) -> tuple[int | None, list | None]:
        """Normalizes the return value from download_files().

        The downloader may return a single int flag (0, 1, 2, 3) or a tuple
        of `(flag, returned_rows)` when docket rows were parsed.

        Parameters
        ----------
        result : tuple or int or None
            Raw return value from `download_files()`.

        Returns
        -------
        tuple[int | None, list | None]
            Normalized pair of (down_flag, returned_rows).
        """
        if isinstance(result, tuple):
            return result
        return result, None

    @staticmethod
    def _re_navigate(ctx, config: dict) -> None:
        """Re-navigates all portal steps on the SAME driver instance.

        Executes the navigation chain directly without the full overhead of
        `_run_step`, re-establishing the browser page state prior to retrying
        the document download.

        Parameters
        ----------
        ctx : FloridaPipelineContext
            Current execution context with active driver.
        config : dict
            County configuration dictionary with navigation callables.
        """
        username = config.get("username")
        password = config.get("password")

        navigate_to_url = config['navigate_to_url']
        navigate_to_search = config['navigate_to_search']
        search_case_number = config['search_case_number']
        navigate_to_files = config['navigate_to_files']

        # Step 1: Portal home URL
        if navigate_to_url:
            navigate_to_url(ctx.driver, ctx.case_id)
        # Step 2: Search page
        if navigate_to_search:
            args = (ctx.driver, username, password) if (username and password) else (ctx.driver,)
            navigate_to_search(*args)
        # Step 3: Case number submission
        if search_case_number:
            search_case_number(ctx.driver, ctx.case_id)
        # Step 4: Documents / docket tab
        if navigate_to_files:
            navigate_to_files(ctx.driver)
