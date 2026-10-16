"""
Pipeline Package — Block-Based Court Scraping Architecture
============================================================
This package provides a modular, finite-state-machine (FSM) driven pipeline
architecture for legal case scrapers across both New Jersey statewide portals
and Florida individual county courts.

Core Components:
----------------
- `PipelineBlock`: Abstract base class implementing the single-responsibility
  execution contract for each processing phase.
- `BlockStatus`: UI telemetry states representing the life cycle of each block.
- `BlockSignal`: Finite state machine signals governing inter-block routing,
  retries, skips, and transitions.
- `PipelineContext`: Mutable data transfer object encapsulating the operational
  state of a New Jersey case.
- `FloridaPipelineContext`: Mutable data transfer object encapsulating county
  configs, driver instances, and operational state for Florida cases.
- `PipelineOrchestrator`: Multi-level retry engine and workflow coordinator.
"""

from .base import (
    BlockSignal,
    BlockStatus,
    FloridaPipelineContext,
    PipelineBlock,
    PipelineContext,
)
from .orchestrator import PipelineOrchestrator

__all__ = [
    "BlockStatus",
    "BlockSignal",
    "PipelineContext",
    "FloridaPipelineContext",
    "PipelineBlock",
    "PipelineOrchestrator",
]

