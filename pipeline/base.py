"""
==============================================================================
pipeline/base.py — Core Abstractions for the Block-Based Pipeline Architecture
==============================================================================

Overview:
---------
This module defines the foundational domain models and architectural contracts
for the Court Scraper's pipeline engine. The architecture models case scraping
as a directed sequence of decoupled, reusable, and testable stages called "Blocks".

Key Design Principles:
----------------------
1. Separation of Concerns:
   - Blocks contain ONLY the operational logic for their step (e.g., Zillow lookup,
     login, table scraping, downloading, database sync).
   - The Orchestrator (`pipeline/orchestrator.py`) manages driver lifecycle, retries,
     error escalation, cancellation, and UI event broadcasting.

2. Explicit Control Signaling (`BlockSignal`):
   - Blocks never call `sys.exit()` or perform uncontrolled retries internally.
   - Blocks return a `BlockSignal` enum (e.g., `OK`, `RETRY_DRIVER`, `NOT_FOUND`, `SKIP`)
     to instruct the orchestrator how to route subsequent execution.

3. Centralized Context Passing (`PipelineContext` & `FloridaPipelineContext`):
   - Rather than passing dozens of positional arguments across functions, a single
     mutable `PipelineContext` dataclass travels from block to block.
   - Any data produced by early blocks (e.g., extracted addresses, case metadata,
     downloaded file paths) is recorded on the context for downstream blocks to consume.
==============================================================================
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

# ── Lifecycle Status (Drives Real-time Front-End UI) ──────────────────────────

class BlockStatus(str, Enum):
    """Visual lifecycle status of an individual block within the pipeline.

    Used by `PipelineOrchestrator` to stream live execution state updates over
    WebSockets to the web dashboard (resembling modern workflow engines like n8n or Temporal).

    Attributes:
        PENDING:  The block is queued and awaiting execution.
        RUNNING:  The block is currently executing operations on this thread.
        SUCCESS:  The block executed successfully without recoverable errors.
        FAILED:   The block experienced an unrecoverable failure or exceeded retry limits.
        RETRYING: The block encountered a recoverable error and is currently restarting.
        SKIPPED:  The block was bypassed (e.g. case marked ineligible or canceled).
    """
    PENDING  = "pending"
    RUNNING  = "running"
    SUCCESS  = "success"
    FAILED   = "failed"
    RETRYING = "retrying"
    SKIPPED  = "skipped"


# ── Control Signals (Block -> Orchestrator Communication) ─────────────────────

class BlockSignal(str, Enum):
    """Control-flow signal returned by a block's `execute()` method.

    Informs the `PipelineOrchestrator` how to transition the state machine
    after a block completes its attempt.

    Attributes:
        OK:
            Normal success. Advances the pipeline to the next sequential block (index + 1).
        RETRY_DRIVER:
            Driver corrupted or hung. Asks orchestrator to recycle/replace the browser
            driver and re-run this exact block.
        RETRY_FROM_START:
            State mismatch requiring a full reset. Asks orchestrator to refresh or
            swap driver and restart execution from Block 1 (index 0).
        RETRY_FROM_NAV:
            Session expired or navigation lost. Asks orchestrator to swap driver
            and rewind execution to Block 2 (CourtNavigationBlock / re-auth).
        RETRY_FROM_ROW:
            Specific file download failure. Asks orchestrator to swap driver,
            rewind to Block 3 (`CaseCheckingBlock`), and resume at `ctx.row_index_to_retry`.
        NOT_FOUND:
            Court record does not exist for the docket number. Ceases execution,
            releases driver, and marks case as 'Case Not Found'.
        SKIP:
            Case is disqualified (e.g., failed RIP/Zillow criteria, auction, or user skip).
            Halts downstream blocks immediately.
        STOP:
            Unrecoverable error encountered. Halts pipeline and marks case as 'Error'.
    """
    OK               = "ok"          # Normal success — advance to next block
    RETRY_DRIVER     = "retry_driver"  # Replace driver, re-run THIS block
    RETRY_FROM_START = "retry_from_start"  # Replace driver, restart from Block 1 (index 0)
    RETRY_FROM_NAV   = "retry_from_nav"  # Replace driver, restart from Block 2 (CourtNav)
    RETRY_FROM_ROW   = "retry_from_row"  # Row-level retry — restart from Block 3 (CaseChecking)
    NOT_FOUND        = "not_found"   # Case not found — stop pipeline
    SKIP             = "skip"        # Case should be skipped — stop pipeline
    STOP             = "stop"        # Hard stop (error) — stop pipeline


# ── Per-Case Context Container (New Jersey Pipeline) ──────────────────────────

@dataclass
class PipelineContext:
    """Encapsulates all mutable state, telemetry, and accumulated data for one case.

    Passed sequentially through all blocks in the New Jersey pipeline. Blocks
    inspect input fields and attach their generated results directly onto this object.

    Fields:
        case_id (str): Formatted canonical identifier (e.g. 'f-1234-24').
        year (str): Case filing year string (e.g. '24').
        docket (str): Docket sequence number (e.g. '1234').
        case_type (str): Jurisdiction court code (e.g. 'civil' or 'foreclosure').
        account (dict): Credentials dictionary allocated from the account rotation pool.
        driver (Any): Active Selenium WebDriver instance bound to this execution thread.
        driver_pool (Any): Parent `DriverPool` managing browser allocations and recycling.
        files_dir (str): Target filesystem directory where downloaded PDFs and logs reside.
        start_index (int): Row index offset for resuming partial table downloads (defaults to 0).
        precheck_data (dict): Output payload from `PrecheckBlock` (Zillow/SalesWeb/Equity details).
        case_result (dict): Metadata scraped by `CaseCheckingBlock` (defendants, case status).
        matching_files (list): Filtered document records identified by `FilePickingBlock`.
        matching_rows (list): Table DOM row descriptors identified by `FilePickingBlock`.
        property_future (Any): Background `concurrent.futures.Future` for async property lookups.
        row_index_to_retry (Optional[int]): Specific row index requiring retry if a download fails.
        last_failed_block (Optional[str]): Name of the block that triggered the last retry.
        last_failed_verifier (Optional[str]): Description of the page verifier that failed.
        retry_reason (Optional[str]): Human-readable message or exception explaining the retry.
        start_time (float): Epoch timestamp recording when case processing initiated.
        block_statuses (dict): Mapping of `{block_name: BlockStatus}` tracking progress for the UI.
        batch_name (str): Active batch identifier for Supabase grouping.
        tracker (Any): Optional `PipelineTracker` instance recording telemetry and audit logs.
    """
    # ── Identity ──────────────────────────────────────────────────────────────
    case_id:   str
    year:      str
    docket:    str
    case_type: str
    account:   dict

    # ── Driver state (may be swapped on retry) ────────────────────────────────
    driver:      Any   # selenium WebDriver
    driver_pool: Any   # DriverPool

    # ── Filesystem ───────────────────────────────────────────────────────────
    files_dir:   str
    start_index: int = 0

    # ── Data accumulated across blocks ────────────────────────────────────────
    precheck_data:   dict = field(default_factory=dict)   # from PrecheckBlock
    case_result:     dict = field(default_factory=dict)   # from CaseCheckingBlock
    matching_files:  list = field(default_factory=list)   # from FilePickingBlock
    matching_rows:   list = field(default_factory=list)   # from FilePickingBlock
    property_future: Any  = None                          # from CaseCheckingBlock

    # ── Retry bookkeeping (set by orchestrator / blocks) ─────────────────────
    row_index_to_retry:   Optional[int] = None
    last_failed_block:    Optional[str] = None
    last_failed_verifier: Optional[str] = None
    retry_reason:         Optional[str] = None

    # ── Timing ───────────────────────────────────────────────────────────────
    start_time: float = field(default_factory=time.time)

    # ── Per-block status map (for UI / event emission) ───────────────────────
    block_statuses: dict = field(default_factory=dict)

    # ── Pipeline telemetry tracker (injected by orchestrator) ────────────────
    batch_name: str = ""
    tracker:    Any = None  # PipelineTracker instance


# ── Per-Case Context Container (Florida / Generic County Pipeline) ─────────────

@dataclass
class FloridaPipelineContext:
    """Encapsulates all mutable state for Florida and generic county cases.

    Similar in role to `PipelineContext`, but tailored to county portals that
    rely on configuration maps (`COUNTY_CONFIGS`) rather than fixed NJ forms.

    Fields:
        case_id (str): Formatted case identifier (e.g. '2023-CA-001234-O').
        config (dict): County-specific locator mappings and URL configuration dictionary.
        driver (Any): Active Selenium WebDriver instance.
        driver_pool (Any): Parent `DriverPool` instance.
        files_dir (str): Target directory for downloaded case files.
        cached_matching_rows (Optional[list]): Cache of table rows for resuming interrupted downloads.
        down_flag (Optional[int]): Status indicator flag returned by the download routine.
        returned_rows (Optional[list]): Actual rows scraped from the court document table.
        last_failed_block (Optional[str]): Name of the block that triggered the last retry.
        last_failed_verifier (Optional[str]): Description of the failed page state verifier.
        retry_reason (Optional[str]): Human-readable reason for the retry attempt.
        start_time (float): Epoch timestamp when case execution began.
        block_statuses (dict): Mapping of `{block_name: BlockStatus}` for UI monitoring.
        batch_name (str): Active batch name for database sync.
        tracker (Any): Optional `PipelineTracker` instance for Supabase telemetry.
    """
    # ── Identity ──────────────────────────────────────────────────────────────
    case_id:    str
    config:     dict          # full county config dict

    # ── Driver state (may be swapped on retry) ────────────────────────────────
    driver:      Any          # selenium WebDriver
    driver_pool: Any          # DriverPool

    # ── Filesystem ───────────────────────────────────────────────────────────
    files_dir:   str

    # ── Data accumulated across blocks ────────────────────────────────────────
    cached_matching_rows: Optional[list] = None   # for download resume
    down_flag:            Optional[int]  = None    # download result flag
    returned_rows:        Optional[list] = None    # rows returned from download

    # ── Retry bookkeeping (set by orchestrator / blocks) ─────────────────────
    last_failed_block:    Optional[str] = None
    last_failed_verifier: Optional[str] = None
    retry_reason:         Optional[str] = None

    # ── Timing ───────────────────────────────────────────────────────────────
    start_time: float = field(default_factory=time.time)

    # ── Per-block status map (for UI / event emission) ───────────────────────
    block_statuses: dict = field(default_factory=dict)

    # ── Pipeline telemetry tracker (injected by orchestrator) ────────────────
    batch_name: str = ""
    tracker:    Any = None  # PipelineTracker instance


# ── Abstract Base Class (The Block Contract) ──────────────────────────────────

class PipelineBlock(ABC):
    """Abstract Base Class defining the contract for all modular pipeline blocks.

    Every operation in the pipeline (login, search, table reading, download,
    enrichment, database upload) inherits from this class and implements `execute()`.

    Implementation Guidelines:
    --------------------------
    - Pure Step Execution: The block should perform only its specific designated responsibility.
    - Non-Fatal Failure Handling: When expected anomalies occur (bad captcha, temporary
      network blip, stale element), return a `BlockSignal` rather than raising unhandled exceptions.
    - Idempotency & Resumability: Blocks should be designed so that re-executing
      them during a retry does not corrupt state or cause unintended duplicate side-effects.
    """

    def __init__(self, name: str):
        """Initialize the block with a human-readable display name.

        Args:
            name (str): The name of the block displayed in UI monitors and logs.
        """
        self.name = name

    @abstractmethod
    def execute(self, ctx: PipelineContext) -> BlockSignal:
        """Execute this block's logic using the provided case context.

        Args:
            ctx (PipelineContext): The mutable context object holding drivers,
                case metadata, and state accumulated from previous blocks.

        Returns:
            BlockSignal: Directive instructing the orchestrator how to route
                the next stage of execution (e.g. `BlockSignal.OK`, `BlockSignal.RETRY_FROM_NAV`).
        """
        ...

    def __repr__(self) -> str:
        return f"<Block: {self.name}>"
