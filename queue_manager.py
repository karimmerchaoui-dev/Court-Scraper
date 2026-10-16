"""
queue_manager.py
================
Unified Queue interface for Court Scraper.

SWITCH QUEUE BACKEND BY CHANGING THE SINGLE LINE BELOW:
    USE_REDIS = False  -> Standard Python in-memory queue (no Redis/WSL needed)
    USE_REDIS = True   -> Redis-backed queue (supports multi-process persistence)
"""
from __future__ import annotations

import collections
import json
import queue
import threading
import time
from typing import Any

# ==============================================================================
# ⚙️ QUEUE BACKEND TOGGLE — CHANGE THIS SINGLE LINE TO SWITCH
# ==============================================================================
USE_REDIS: bool = False
# ==============================================================================

# Global in-memory sets for cancellation & processing when running without Redis
_IN_MEMORY_PROCESSING: set[str] = set()
_IN_MEMORY_CANCELLED: set[str] = set()
_MEM_LOCK = threading.Lock()


def is_case_cancelled(case_id: str) -> bool:
    """Check if cancellation was requested for case_id (works in both Redis and Memory modes)."""
    if USE_REDIS:
        try:
            from cache.redis_client import CANCELLED_KEY, r
            return bool(r.sismember(CANCELLED_KEY, case_id))
        except Exception:
            return False
    else:
        with _MEM_LOCK:
            return case_id in _IN_MEMORY_CANCELLED


def ack_case_cancellation(case_id: str) -> None:
    """Acknowledge and clear cancellation request for case_id."""
    if USE_REDIS:
        try:
            from cache.redis_client import CANCELLED_KEY, r
            r.srem(CANCELLED_KEY, case_id)
        except Exception:
            pass
    else:
        with _MEM_LOCK:
            _IN_MEMORY_CANCELLED.discard(case_id)


class RedisQueue:
    """
    Unified Queue class satisfying the standard queue.Queue interface:
        .empty()     -> bool
        .qsize()     -> int
        .get()       -> item (blocking or non-blocking)
        .put()       -> None
        .task_done() -> None
        .clear()     -> None

    Plus dynamic management methods for web UI:
        .put_priority(item)      -> push to front of queue
        .remove(case_id)         -> remove pending item by case ID
        .peek()                  -> list all pending items without consuming
        .cancel_running(case_id) -> request immediate stop
        .is_cancelled(case_id)   -> check stop request
        .mark_processing(case_id)
        .mark_done(case_id)
        .currently_processing()  -> list of running case IDs
        .status_snapshot()       -> full queue overview
    """

    def __init__(self, key: str = "court:case_queue", fallback: bool = True):
        self._key = key
        self._use_redis = False

        if USE_REDIS:
            try:
                from cache.redis_client import ensure_redis_running, is_redis_available
                if not is_redis_available():
                    ensure_redis_running()
                self._use_redis = is_redis_available()
            except Exception:
                self._use_redis = False

        # In-memory backing queue and lock
        self._lock = threading.Condition()
        self._deque: collections.deque = collections.deque()
        self._unfinished_tasks = 0

    def __repr__(self) -> str:
        backend = "redis" if self._use_redis else "in-memory (Python queue)"
        return f"<CaseQueue backend='{backend}' size={self.qsize()}>"

    def __str__(self) -> str:
        return self.__repr__()

    # ── Standard queue.Queue interface ────────────────────────────────────────


    def empty(self) -> bool:
        if self._use_redis:
            try:
                from cache.redis_client import r
                return r.llen(self._key) == 0
            except Exception:
                pass
        with self._lock:
            return len(self._deque) == 0

    def qsize(self) -> int:
        if self._use_redis:
            try:
                from cache.redis_client import r
                return r.llen(self._key)
            except Exception:
                pass
        with self._lock:
            return len(self._deque)

    def put(self, item: Any, block: bool = True, timeout: float | None = None) -> None:
        """Push to the back of the queue (FIFO)."""
        if self._use_redis:
            try:
                from cache.redis_client import r
                payload = json.dumps(item) if not isinstance(item, str) else item
                r.rpush(self._key, payload)
                return
            except Exception:
                pass

        with self._lock:
            self._deque.append(item)
            self._unfinished_tasks += 1
            self._lock.notify()

    def get(self, block: bool = True, timeout: float | None = None) -> Any:
        """Pop from the front of the queue."""
        if self._use_redis:
            try:
                from cache.redis_client import r
                deadline = (time.time() + timeout) if timeout else None
                while True:
                    raw = r.lpop(self._key)
                    if raw is not None:
                        try:
                            return json.loads(raw)
                        except (json.JSONDecodeError, TypeError):
                            return raw
                    if not block:
                        raise queue.Empty
                    if deadline and time.time() >= deadline:
                        raise queue.Empty
                    time.sleep(0.2)
            except queue.Empty:
                raise
            except Exception:
                pass

        with self._lock:
            if not block:
                if not self._deque:
                    raise queue.Empty
                return self._deque.popleft()
            elif timeout is None:
                while not self._deque:
                    self._lock.wait()
                return self._deque.popleft()
            elif timeout < 0:
                raise ValueError("'timeout' must be a non-negative number")
            else:
                endtime = time.time() + timeout
                while not self._deque:
                    remaining = endtime - time.time()
                    if remaining <= 0.0:
                        raise queue.Empty
                    self._lock.wait(remaining)
                return self._deque.popleft()

    def task_done(self) -> None:
        """No-op / decrements in-memory task count."""
        with self._lock:
            if self._unfinished_tasks > 0:
                self._unfinished_tasks -= 1

    def clear(self) -> None:
        """Clear all items from the queue."""
        if self._use_redis:
            try:
                from cache.redis_client import r
                r.delete(self._key)
            except Exception:
                pass
        with self._lock:
            self._deque.clear()
            self._unfinished_tasks = 0

    # ── Dynamic Queue Management ──────────────────────────────────────────────

    def put_priority(self, item: Any) -> None:
        """Push to the front of the queue (runs next)."""
        if self._use_redis:
            try:
                from cache.redis_client import r
                payload = json.dumps(item) if not isinstance(item, str) else item
                r.lpush(self._key, payload)
                return
            except Exception:
                pass

        with self._lock:
            self._deque.appendleft(item)
            self._unfinished_tasks += 1
            self._lock.notify()

    def remove(self, case_id: str) -> bool:
        """Remove a pending case by its case_id before it starts running."""
        if self._use_redis:
            try:
                from cache.redis_client import r
                items = r.lrange(self._key, 0, -1)
                for raw in items:
                    try:
                        payload = json.loads(raw)
                        if _extract_case_id(payload) == case_id:
                            return r.lrem(self._key, 1, raw) > 0
                    except Exception:
                        continue
                return False
            except Exception:
                pass

        with self._lock:
            for item in list(self._deque):
                if _extract_case_id(item) == case_id:
                    self._deque.remove(item)
                    if self._unfinished_tasks > 0:
                        self._unfinished_tasks -= 1
                    return True
        return False

    def peek(self) -> list:
        """Return a copy of all pending items without consuming them."""
        if self._use_redis:
            try:
                from cache.redis_client import r
                items = r.lrange(self._key, 0, -1)
                result = []
                for raw in items:
                    try:
                        result.append(json.loads(raw))
                    except Exception:
                        result.append(raw)
                return result
            except Exception:
                pass

        with self._lock:
            return list(self._deque)

    # ── Cancellation ──────────────────────────────────────────────────────────

    def cancel_running(self, case_id: str) -> None:
        """Signal that a currently-running case should stop."""
        if self._use_redis:
            try:
                from cache.redis_client import CANCELLED_KEY, r
                r.sadd(CANCELLED_KEY, case_id)
                return
            except Exception:
                pass

        with _MEM_LOCK:
            _IN_MEMORY_CANCELLED.add(case_id)

    def is_cancelled(self, case_id: str) -> bool:
        return is_case_cancelled(case_id)

    def ack_cancellation(self, case_id: str) -> None:
        ack_case_cancellation(case_id)

    # ── Processing Set ────────────────────────────────────────────────────────

    def mark_processing(self, case_id: str) -> None:
        """Record that a case is actively being worked on."""
        if self._use_redis:
            try:
                from cache.redis_client import PROCESSING_KEY, r
                r.sadd(PROCESSING_KEY, case_id)
                return
            except Exception:
                pass

        with _MEM_LOCK:
            _IN_MEMORY_PROCESSING.add(case_id)

    def mark_done(self, case_id: str) -> None:
        """Remove from the actively-processing set when a case finishes."""
        if self._use_redis:
            try:
                from cache.redis_client import PROCESSING_KEY, r
                r.srem(PROCESSING_KEY, case_id)
                return
            except Exception:
                pass

        with _MEM_LOCK:
            _IN_MEMORY_PROCESSING.discard(case_id)

    def currently_processing(self) -> list[str]:
        """Return all case_ids that are currently being processed."""
        if self._use_redis:
            try:
                from cache.redis_client import PROCESSING_KEY, r
                return list(r.smembers(PROCESSING_KEY))
            except Exception:
                pass

        with _MEM_LOCK:
            return list(_IN_MEMORY_PROCESSING)

    def status_snapshot(self) -> dict:
        """Full snapshot for the UI's /api/queue/status endpoint."""
        return {
            "pending": self.peek(),
            "processing": self.currently_processing(),
            "cancelled": list(r.smembers("court:cancelled")) if self._use_redis else list(_IN_MEMORY_CANCELLED),
            "total_pending": self.qsize(),
            "backend": "redis" if self._use_redis else "in-memory (python)",
        }


# ── Helper ────────────────────────────────────────────────────────────────────

def _extract_case_id(payload) -> str | None:
    """Extract a case_id from dict or tuple."""
    if isinstance(payload, dict):
        return payload.get("case_id")
    if isinstance(payload, (list, tuple)) and len(payload) >= 2:
        year = payload[0]
        docket = payload[1]
        return f"f-{docket}-{year}" if year else docket
    return None
