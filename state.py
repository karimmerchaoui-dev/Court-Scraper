"""
state.py -- All mutable application state in one place.

Clean in-memory application state:
    - report_cases: dict[case_id -> dict]
    - skip_requested_cases: set[case_id]
    - processing flags & counters (running, processed, total_cases, etc.)
    - configuration & settings (headless_mode, max_workers, etc.)
    - driver_pool, driver_monitor, active_threads, deed_queue

Import and use:
    from state import state

    state.running = True
    state.report_cases[case_id] = {...}
"""
from __future__ import annotations

import json
import os
import queue as _queue
import threading
import time
import traceback
from datetime import datetime
from typing import Any

from database.deed_queue_db import SqliteDeedQueue


class _AppState:
    """
    Thread-safe in-memory container for all global state.
    """

    def __init__(self):
        # ── Processing Flags & Counters ──────────────────────────────────────
        self.running: bool = False
        self.force_stop: bool = False
        self.halfway_report_sent: bool = False
        self.processed: int = 0
        self.total_cases: int = 0
        self.current_batch_folder: str | None = None

        # ── Configuration & Keywords ─────────────────────────────────────────
        self.keyword_list: list[str] | None = None
        self.unwanted_list: list[str] | None = None
        self.keywords_str: str = ""
        self.unwanted_str: str = ""
        self.input_file: str = ""
        self.output_folder: str = ""
        self.headless_mode: bool = False
        self.max_workers: int = 5
        self.deed_search_enabled: bool = True

        # ── Case Data & Skip Set ─────────────────────────────────────────────
        self.report_cases: dict[str, dict] = {}
        self.skip_requested_cases: set[str] = set()

        # ── Driver & Thread Management ───────────────────────────────────────
        self.driver_pool: Any = None
        self.driver_monitor: Any = None
        self.active_threads: list = []

        # ── Case Queue, Deed Queue & Worker Lock ─────────────────────────────
        # case_queue stays in-memory (no cross-process need)
        self.case_queue: _queue.Queue = _queue.Queue()
        # deed_queue uses SQLite for durability & cross-process support
        self.deed_queue: SqliteDeedQueue = SqliteDeedQueue()
        self.deed_worker_started: bool = False
        self.deed_worker_lock: threading.Lock = threading.Lock()

        # ── Secrets / API Keys ────────────────────────────────────────────────
        self.api_key: str = os.getenv("ATTOM_API_KEY", "")

    # ── State Reset & Settings Sync ──────────────────────────────────────────

    def reset(self):
        """Call before starting a new batch to wipe all mutable state."""
        self.running = False
        self.force_stop = False
        self.halfway_report_sent = False
        self.processed = 0
        self.total_cases = 0
        self.report_cases.clear()
        self.current_batch_folder = None
        self.driver_pool = None
        self.active_threads = []
        self.keyword_list = None
        self.unwanted_list = None
        self.skip_requested_cases.clear()
        self.case_queue = _queue.Queue()
        # Reuse the same SqliteDeedQueue — pending/failed rows persist across batches
        self.deed_queue = SqliteDeedQueue()
        self.deed_worker_started = False
        self.deed_worker_lock = threading.Lock()

    def sync_settings(self, settings: Any = None):
        """Pull live values from config.settings or passed dict/Settings object."""
        if settings is None:
            from config import settings as _cfg
            settings = _cfg
        if hasattr(settings, "get"):
            if settings.get("keywords"):
                self.keywords_str = settings.get("keywords", "")
            if settings.get("unwanted_keywords"):
                self.unwanted_str = settings.get("unwanted_keywords", "")
            if settings.get("input_file"):
                self.input_file = settings.get("input_file", "")
            if settings.get("output_folder"):
                self.output_folder = settings.get("output_folder", "")
            if "headless_mode" in settings:
                self.headless_mode = bool(settings.get("headless_mode"))
            if settings.get("max_workers"):
                self.max_workers = int(settings.get("max_workers"))
        else:
            if getattr(settings, "keywords", None):
                self.keywords_str = settings.keywords
            if getattr(settings, "unwanted_keywords", None):
                self.unwanted_str = settings.unwanted_keywords
            if getattr(settings, "input_file", None):
                self.input_file = settings.input_file
            if getattr(settings, "output_folder", None):
                self.output_folder = settings.output_folder
            if hasattr(settings, "headless_mode"):
                self.headless_mode = bool(settings.headless_mode)
            if getattr(settings, "max_workers", None):
                self.max_workers = int(settings.max_workers)

    # ── Debug / inspection ───────────────────────────────────────────────────

    _SERIALIZABLE_FIELDS = (
        "running", "force_stop", "halfway_report_sent",
        "processed", "total_cases",
        "current_batch_folder",
        "input_file", "output_folder",
        "headless_mode", "max_workers",
        "deed_search_enabled",
    )

    _REDACTED_FIELDS = {"api_key"}

    def snapshot(self, redact_secrets: bool = True) -> dict:
        """
        Return a JSON-serializable dict representing the current state.
        Never raises — best-effort on every field.
        """
        snap = {
            "captured_at": datetime.utcnow().isoformat() + "Z",
            "pid": os.getpid(),
        }

        # 1. Simple scalar fields
        for name in self._SERIALIZABLE_FIELDS:
            try:
                snap[name] = getattr(self, name)
            except Exception as e:
                snap[name] = f"<error: {e}>"

        # 2. Lists / sets
        try:
            snap["keyword_list"] = list(self.keyword_list) if self.keyword_list else []
        except Exception:
            snap["keyword_list"] = None

        try:
            snap["unwanted_list"] = list(self.unwanted_list) if self.unwanted_list else []
        except Exception:
            snap["unwanted_list"] = None

        try:
            snap["skip_requested_cases"] = sorted(list(self.skip_requested_cases))
        except Exception:
            snap["skip_requested_cases"] = []

        # 3. Non-serializable objects -> summaries
        snap["driver_pool"] = self._summarize_driver_pool()
        snap["driver_monitor"] = type(self.driver_monitor).__name__ if self.driver_monitor else None
        snap["deed_queue_size"] = self._safe_queue_size(self.deed_queue)
        snap["deed_worker_started"] = self.deed_worker_started

        # 4. report_cases -> safe dict
        snap["report_cases"] = self._safe_dict(dict(self.report_cases))
        snap["report_cases_count"] = len(self.report_cases)

        # 5. Redact secrets
        if redact_secrets:
            for field in self._REDACTED_FIELDS:
                if hasattr(self, field):
                    snap[field] = "<redacted>"
        else:
            snap["api_key"] = getattr(self, "api_key", None)

        return snap

    @staticmethod
    def _safe_queue_size(q) -> int:
        try:
            return q.qsize()
        except Exception:
            return -1

    def _summarize_driver_pool(self):
        dp = self.driver_pool
        if dp is None:
            return None
        summary = {"type": type(dp).__name__}
        for attr in ("drivers", "pool", "all_drivers", "monitoring_active"):
            try:
                val = getattr(dp, attr, None)
                if val is None:
                    continue
                if isinstance(val, (list, tuple, set)):
                    summary[attr] = {
                        "count": len(val),
                        "types": sorted({type(x).__name__ for x in val}),
                    }
                elif isinstance(val, bool):
                    summary[attr] = val
                else:
                    summary[attr] = type(val).__name__
            except Exception:
                pass
        return summary

    @staticmethod
    def _safe_dict(d) -> dict:
        """Serialize a dict, replacing any non-JSON value with its repr."""
        out = {}
        if not isinstance(d, dict):
            return {"_not_a_dict": repr(d)}
        for k, v in d.items():
            try:
                json.dumps(v)
                out[str(k)] = v
            except Exception:
                try:
                    out[str(k)] = _safe_dict(v) if isinstance(v, dict) else repr(v)
                except Exception as e:
                    out[str(k)] = f"<unserializable: {e}>"
        return out

    def dump_to_file(self, path: str | None = None, redact_secrets: bool = True) -> str:
        """
        Write a JSON snapshot to *path*. If path is None, derive one from
        output_folder / current_batch_folder / cwd.
        """
        if path is None:
            base = self.current_batch_folder or self.output_folder or os.getcwd()
            os.makedirs(base, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            path = os.path.join(base, f"state_snapshot_{ts}.json")

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        try:
            snap = self.snapshot(redact_secrets=redact_secrets)
        except Exception:
            snap = {"error": "snapshot failed", "traceback": traceback.format_exc()}

        with open(path, "w", encoding="utf-8") as f:
            json.dump(snap, f, indent=2, default=str)

        return path


state = _AppState()
