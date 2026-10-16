"""
database/deed_queue_db.py
=========================
SQLite-backed durable queue for deed worker jobs.

Why SQLite instead of Redis / in-memory:
- Zero new services needed — SQLite ships with Python.
- Survives process restarts and crashes (jobs are not lost).
- Cross-process safe on a single Windows machine (WAL mode).
- Drop-in replacement: exposes the same .put() / .get() / .task_done()
  interface as stdlib queue.Queue so all existing call sites remain untouched.

Schema (single table deed_jobs):
    id          INTEGER PRIMARY KEY AUTOINCREMENT
    status      TEXT    -- 'pending' | 'processing' | 'done' | 'failed'
    book        TEXT
    page        TEXT
    files_dir   TEXT
    block       TEXT
    main_defendant TEXT
    county_name TEXT
    supabase_case_id TEXT
    case_id     TEXT
    created_at  REAL    -- Unix timestamp
    updated_at  REAL
    error       TEXT    -- last exception if status='failed'
    retries     INTEGER DEFAULT 0
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

# ── Location of the SQLite file ───────────────────────────────────────────────
_DEFAULT_DB_PATH: str = os.getenv(
    "DEED_QUEUE_DB",
    str(Path(__file__).resolve().parent.parent / "deed_queue.db"),
)

_FIELDS = (
    "book", "page", "files_dir", "block",
    "main_defendant", "county_name", "supabase_case_id", "case_id",
)

_DDL = """
CREATE TABLE IF NOT EXISTS deed_jobs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    status           TEXT    NOT NULL DEFAULT 'pending',
    book             TEXT    NOT NULL DEFAULT '',
    page             TEXT    NOT NULL DEFAULT '',
    files_dir        TEXT    NOT NULL DEFAULT '',
    block            TEXT    NOT NULL DEFAULT '',
    main_defendant   TEXT    NOT NULL DEFAULT '',
    county_name      TEXT    NOT NULL DEFAULT '',
    supabase_case_id TEXT    NOT NULL DEFAULT '',
    case_id          TEXT    NOT NULL DEFAULT '',
    created_at       REAL    NOT NULL,
    updated_at       REAL    NOT NULL,
    error            TEXT,
    retries          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_deed_jobs_status ON deed_jobs(status);
"""

MAX_RETRIES: int = 3
_POLL_INTERVAL: float = 0.3   # seconds between DB polls in get()


def _connect(db_path: str) -> sqlite3.Connection:
    """Open a WAL-mode connection — safe for concurrent writers."""
    conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


class SqliteDeedQueue:
    """
    Drop-in replacement for queue.Queue backed by a local SQLite file.

    Usage (identical to queue.Queue)::

        q = SqliteDeedQueue()
        q.put((book, page, files_dir, block, defendant, county, sb_id, case_id))
        item = q.get()          # blocks until a row is available
        q.task_done()           # marks the row as 'done'

    Extra helpers::

        q.qsize()               -> int   (pending + processing count)
        q.pending()             -> int   (pending only)
        q.retry_failed()        -> int   (re-queues failed jobs <= MAX_RETRIES)
        q.failed_jobs()         -> list  (rows with status='failed')
    """

    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._current_id: int | None = None   # row id of the item returned by get()

        # ── Bootstrap schema ─────────────────────────────────────────────────
        conn = _connect(db_path)
        conn.executescript(_DDL)
        conn.commit()
        # Re-queue any jobs stuck in 'processing' from a previous crashed run
        conn.execute(
            "UPDATE deed_jobs SET status='pending', updated_at=? WHERE status='processing'",
            (time.time(),),
        )
        conn.commit()
        conn.close()

    # ── queue.Queue-compatible interface ──────────────────────────────────────

    def put(self, item: tuple, block: bool = True, timeout: float | None = None) -> None:
        """Persist a deed job tuple to the SQLite queue."""
        if len(item) != 8:
            raise ValueError(
                f"SqliteDeedQueue.put() expects an 8-tuple "
                f"(book, page, files_dir, block, main_defendant, county_name, "
                f"supabase_case_id, case_id), got {len(item)} elements."
            )
        book, page, files_dir, blk, main_defendant, county_name, supabase_case_id, case_id = item
        now = time.time()

        conn = _connect(self._db_path)
        try:
            conn.execute(
                """
                INSERT INTO deed_jobs
                    (status, book, page, files_dir, block, main_defendant,
                     county_name, supabase_case_id, case_id, created_at, updated_at)
                VALUES ('pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (book, page, files_dir, blk, main_defendant,
                 county_name, supabase_case_id, case_id, now, now),
            )
            conn.commit()
        finally:
            conn.close()

        # Wake up any waiting get() call
        with self._not_empty:
            self._not_empty.notify_all()

    def get(self, block: bool = True, timeout: float | None = None) -> tuple:
        """
        Claim and return the oldest pending deed job as an 8-tuple.
        Blocks until a job is available (mirrors queue.Queue.get semantics).
        """
        deadline = (time.time() + timeout) if (block and timeout is not None) else None

        while True:
            row = self._claim_next()
            if row is not None:
                self._current_id = row["id"]
                return (
                    row["book"], row["page"], row["files_dir"], row["block"],
                    row["main_defendant"], row["county_name"],
                    row["supabase_case_id"], row["case_id"],
                )

            if not block:
                import queue as _q
                raise _q.Empty

            if deadline is not None and time.time() >= deadline:
                import queue as _q
                raise _q.Empty

            # Efficient wait: sleep briefly, let put() wake us early
            with self._not_empty:
                self._not_empty.wait(timeout=_POLL_INTERVAL)

    def task_done(self) -> None:
        """Mark the last get()-returned job as 'done'."""
        if self._current_id is not None:
            self._update_status(self._current_id, "done")
            self._current_id = None

    def mark_failed(self, error: str = "") -> None:
        """Mark the current job as 'failed' with an optional error message."""
        if self._current_id is not None:
            conn = _connect(self._db_path)
            try:
                conn.execute(
                    """
                    UPDATE deed_jobs
                    SET status='failed', error=?, updated_at=?,
                        retries = retries + 1
                    WHERE id=?
                    """,
                    (error, time.time(), self._current_id),
                )
                conn.commit()
            finally:
                conn.close()
            self._current_id = None

    # ── Introspection helpers ─────────────────────────────────────────────────

    def qsize(self) -> int:
        """Return count of pending + processing rows."""
        conn = _connect(self._db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM deed_jobs WHERE status IN ('pending','processing')"
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def pending(self) -> int:
        """Return count of pending-only rows."""
        conn = _connect(self._db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM deed_jobs WHERE status='pending'"
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def empty(self) -> bool:
        return self.pending() == 0

    def failed_jobs(self) -> list:
        """Return all failed jobs as a list of dicts."""
        conn = _connect(self._db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM deed_jobs WHERE status='failed' ORDER BY id"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def retry_failed(self) -> int:
        """
        Re-queue failed jobs that have not exceeded MAX_RETRIES.
        Returns number of jobs re-queued.
        """
        now = time.time()
        conn = _connect(self._db_path)
        try:
            cur = conn.execute(
                """
                UPDATE deed_jobs
                SET status='pending', updated_at=?
                WHERE status='failed' AND retries < ?
                """,
                (now, MAX_RETRIES),
            )
            conn.commit()
            count = cur.rowcount
        finally:
            conn.close()

        if count:
            with self._not_empty:
                self._not_empty.notify_all()
        return count

    # ── Internal ──────────────────────────────────────────────────────────────

    def _claim_next(self) -> sqlite3.Row | None:
        """Atomically grab the oldest pending row and mark it 'processing'."""
        now = time.time()
        conn = _connect(self._db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM deed_jobs WHERE status='pending' ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                return None
            conn.execute(
                "UPDATE deed_jobs SET status='processing', updated_at=? WHERE id=?",
                (now, row["id"]),
            )
            conn.execute("COMMIT")
            return row
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            return None
        finally:
            conn.close()

    def _update_status(self, row_id: int, status: str) -> None:
        conn = _connect(self._db_path)
        try:
            conn.execute(
                "UPDATE deed_jobs SET status=?, updated_at=? WHERE id=?",
                (status, time.time(), row_id),
            )
            conn.commit()
        finally:
            conn.close()
