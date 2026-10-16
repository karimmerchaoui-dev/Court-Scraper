"""
tests/test_deed_queue.py
========================
Unit tests for database/deed_queue_db.py — SqliteDeedQueue.

Strategy
--------
* Every test receives a fresh, isolated SQLite database via the `queue`
  fixture defined in conftest.py.  No shared state, no leftover rows.
* Tests are grouped into classes that mirror the queue's public interface.
* Concurrency tests use real threads (not mocks) to exercise the
  threading.Condition that notifies waiting get() calls.
"""
from __future__ import annotations

import queue as stdlib_queue
import threading
import time

import pytest

from database.deed_queue_db import MAX_RETRIES, SqliteDeedQueue
from tests.conftest import SAMPLE_JOB


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_job(**overrides) -> tuple:
    """Return a copy of SAMPLE_JOB with any field overridden by keyword."""
    fields = list(SAMPLE_JOB)
    mapping = {
        "book": 0, "page": 1, "files_dir": 2, "block": 3,
        "main_defendant": 4, "county_name": 5,
        "supabase_case_id": 6, "case_id": 7,
    }
    for key, value in overrides.items():
        fields[mapping[key]] = value
    return tuple(fields)


# ══════════════════════════════════════════════════════════════════════════════
# 1. put() — Enqueue
# ══════════════════════════════════════════════════════════════════════════════

class TestPut:
    """Tests for SqliteDeedQueue.put()."""

    def test_put_increases_pending_count(self, queue: SqliteDeedQueue):
        """Putting one item should increase pending() from 0 to 1."""
        assert queue.pending() == 0
        queue.put(SAMPLE_JOB)
        assert queue.pending() == 1

    def test_put_multiple_items_are_all_pending(self, queue: SqliteDeedQueue):
        """All enqueued items should appear in pending() count."""
        for i in range(5):
            queue.put(_make_job(case_id=f"case-{i}"))
        assert queue.pending() == 5

    def test_put_persists_all_fields_correctly(self, queue: SqliteDeedQueue):
        """get() after put() must return the exact same 8-tuple."""
        queue.put(SAMPLE_JOB)
        retrieved = queue.get(block=False)
        assert retrieved == SAMPLE_JOB

    def test_put_raises_on_wrong_tuple_length(self, queue: SqliteDeedQueue):
        """put() with a tuple that is not exactly 8 elements must raise ValueError."""
        with pytest.raises(ValueError, match="8-tuple"):
            queue.put(("too", "few", "args"))

    def test_put_raises_on_empty_tuple(self, queue: SqliteDeedQueue):
        """put() with an empty tuple must raise ValueError."""
        with pytest.raises(ValueError, match="8-tuple"):
            queue.put(())

    def test_put_allows_empty_string_fields(self, queue: SqliteDeedQueue):
        """put() should accept empty strings — the schema uses DEFAULT '' for NULLs."""
        job = _make_job(book="", page="", main_defendant="")
        queue.put(job)
        assert queue.pending() == 1

    def test_put_allows_duplicate_case_ids(self, queue: SqliteDeedQueue):
        """The queue deliberately allows the same case_id multiple times (idempotency
        is the caller's responsibility, not the queue's)."""
        queue.put(SAMPLE_JOB)
        queue.put(SAMPLE_JOB)
        assert queue.pending() == 2


# ══════════════════════════════════════════════════════════════════════════════
# 2. get() — Dequeue
# ══════════════════════════════════════════════════════════════════════════════

class TestGet:
    """Tests for SqliteDeedQueue.get()."""

    def test_get_returns_oldest_item_first(self, queue: SqliteDeedQueue):
        """get() must honour FIFO — the first put() item is returned first."""
        job_a = _make_job(case_id="first")
        job_b = _make_job(case_id="second")
        queue.put(job_a)
        queue.put(job_b)

        assert queue.get(block=False)[7] == "first"
        queue.task_done()
        assert queue.get(block=False)[7] == "second"

    def test_get_transitions_status_to_processing(self, queue: SqliteDeedQueue):
        """After get(), the row status must be 'processing', not 'pending'."""
        queue.put(SAMPLE_JOB)
        queue.get(block=False)

        # pending() counts only 'pending' rows — should now be 0
        assert queue.pending() == 0
        # qsize() counts 'pending' + 'processing' — should still be 1
        assert queue.qsize() == 1

    def test_get_non_blocking_raises_empty_on_empty_queue(self, queue: SqliteDeedQueue):
        """get(block=False) on an empty queue must raise queue.Empty immediately."""
        with pytest.raises(stdlib_queue.Empty):
            queue.get(block=False)

    def test_get_with_timeout_raises_empty_after_deadline(self, queue: SqliteDeedQueue):
        """get(timeout=0.5) must raise queue.Empty after the timeout elapses."""
        start = time.monotonic()
        with pytest.raises(stdlib_queue.Empty):
            queue.get(block=True, timeout=0.5)
        elapsed = time.monotonic() - start
        assert elapsed >= 0.4, f"Timed out too early: {elapsed:.3f}s"

    def test_get_blocking_wakes_up_when_item_arrives(self, queue: SqliteDeedQueue):
        """A blocking get() must return as soon as a concurrent put() enqueues a job."""
        result: list[tuple] = []

        def _consumer():
            result.append(queue.get(block=True, timeout=5.0))

        consumer_thread = threading.Thread(target=_consumer, daemon=True)
        consumer_thread.start()

        time.sleep(0.1)  # Let the consumer block first
        queue.put(SAMPLE_JOB)

        consumer_thread.join(timeout=3.0)
        assert not consumer_thread.is_alive(), "Consumer thread did not wake up in time"
        assert result[0] == SAMPLE_JOB


# ══════════════════════════════════════════════════════════════════════════════
# 3. task_done() — Mark Completed
# ══════════════════════════════════════════════════════════════════════════════

class TestTaskDone:
    """Tests for SqliteDeedQueue.task_done()."""

    def test_task_done_transitions_status_to_done(self, queue: SqliteDeedQueue):
        """task_done() must move the row from 'processing' → 'done'."""
        queue.put(SAMPLE_JOB)
        queue.get(block=False)

        assert queue.qsize() == 1  # 'processing' row counted

        queue.task_done()

        assert queue.qsize() == 0  # 'done' rows are not counted
        assert queue.pending() == 0

    def test_task_done_clears_current_id(self, queue: SqliteDeedQueue):
        """After task_done(), calling it again must not raise (idempotent guard)."""
        queue.put(SAMPLE_JOB)
        queue.get(block=False)
        queue.task_done()

        # Calling task_done() again when _current_id is None should be a no-op
        queue.task_done()  # Must not raise

    def test_task_done_without_prior_get_is_a_noop(self, queue: SqliteDeedQueue):
        """task_done() before any get() has no effect — nothing to mark done."""
        queue.put(SAMPLE_JOB)
        queue.task_done()  # _current_id is None — should be a silent no-op
        assert queue.pending() == 1


# ══════════════════════════════════════════════════════════════════════════════
# 4. mark_failed() — Failure Recording
# ══════════════════════════════════════════════════════════════════════════════

class TestMarkFailed:
    """Tests for SqliteDeedQueue.mark_failed()."""

    def test_mark_failed_transitions_status_to_failed(self, queue: SqliteDeedQueue):
        """mark_failed() must move the row from 'processing' → 'failed'."""
        queue.put(SAMPLE_JOB)
        queue.get(block=False)
        queue.mark_failed(error="Selenium timeout")

        failed = queue.failed_jobs()
        assert len(failed) == 1
        assert failed[0]["status"] == "failed"

    def test_mark_failed_records_error_message(self, queue: SqliteDeedQueue):
        """The error string passed to mark_failed() must be persisted."""
        error_msg = "Connection refused after 3 retries"
        queue.put(SAMPLE_JOB)
        queue.get(block=False)
        queue.mark_failed(error=error_msg)

        failed = queue.failed_jobs()
        assert failed[0]["error"] == error_msg

    def test_mark_failed_increments_retry_count(self, queue: SqliteDeedQueue):
        """Each call to mark_failed() must increment the retries column by 1."""
        queue.put(SAMPLE_JOB)
        queue.get(block=False)
        queue.mark_failed()

        failed = queue.failed_jobs()
        assert failed[0]["retries"] == 1

    def test_mark_failed_removes_item_from_active_count(self, queue: SqliteDeedQueue):
        """After mark_failed(), qsize() must not count the failed row."""
        queue.put(SAMPLE_JOB)
        queue.get(block=False)

        assert queue.qsize() == 1  # 'processing' row still counted

        queue.mark_failed()

        assert queue.qsize() == 0  # 'failed' is not pending or processing

    def test_mark_failed_without_prior_get_is_a_noop(self, queue: SqliteDeedQueue):
        """mark_failed() before any get() has no effect (no current_id)."""
        queue.put(SAMPLE_JOB)
        queue.mark_failed(error="should be ignored")
        assert queue.pending() == 1
        assert queue.failed_jobs() == []


# ══════════════════════════════════════════════════════════════════════════════
# 5. retry_failed() — Retry Logic
# ══════════════════════════════════════════════════════════════════════════════

class TestRetryFailed:
    """Tests for SqliteDeedQueue.retry_failed()."""

    def _fail_job(self, queue: SqliteDeedQueue) -> None:
        """Helper: put → get → mark_failed."""
        queue.put(SAMPLE_JOB)
        queue.get(block=False)
        queue.mark_failed()

    def test_retry_failed_requeues_eligible_job(self, queue: SqliteDeedQueue):
        """A failed job with retries < MAX_RETRIES must be re-queued as 'pending'."""
        self._fail_job(queue)
        assert queue.pending() == 0

        requeued = queue.retry_failed()

        assert requeued == 1
        assert queue.pending() == 1

    def test_retry_failed_returns_count_of_requeued_jobs(self, queue: SqliteDeedQueue):
        """retry_failed() must return the exact number of jobs re-queued."""
        for i in range(3):
            queue.put(_make_job(case_id=f"case-{i}"))
            queue.get(block=False)
            queue.mark_failed()

        requeued = queue.retry_failed()
        assert requeued == 3

    def test_retry_failed_does_not_requeue_exhausted_jobs(self, queue: SqliteDeedQueue):
        """Jobs that have been failed MAX_RETRIES times must NOT be re-queued."""
        # Fail the job exactly MAX_RETRIES times
        queue.put(SAMPLE_JOB)
        for _ in range(MAX_RETRIES):
            queue.get(block=False)
            queue.mark_failed()
            # Each retry re-queues it; fail again
            if _ < MAX_RETRIES - 1:
                queue.retry_failed()

        requeued = queue.retry_failed()
        assert requeued == 0
        assert queue.pending() == 0

    def test_retry_failed_returns_zero_when_nothing_to_retry(self, queue: SqliteDeedQueue):
        """retry_failed() on an empty queue returns 0 without error."""
        assert queue.retry_failed() == 0


# ══════════════════════════════════════════════════════════════════════════════
# 6. qsize() & pending() & empty() — Introspection
# ══════════════════════════════════════════════════════════════════════════════

class TestIntrospection:
    """Tests for qsize(), pending(), and empty()."""

    def test_qsize_counts_pending_and_processing(self, queue: SqliteDeedQueue):
        """qsize() must include both 'pending' and 'processing' rows."""
        queue.put(SAMPLE_JOB)
        queue.put(_make_job(case_id="case-2"))
        queue.get(block=False)  # Moves first item to 'processing'

        # 1 pending + 1 processing = 2
        assert queue.qsize() == 2

    def test_qsize_excludes_done_and_failed_rows(self, queue: SqliteDeedQueue):
        """qsize() must not count 'done' or 'failed' rows."""
        queue.put(SAMPLE_JOB)
        queue.get(block=False)
        queue.task_done()  # → 'done'

        queue.put(_make_job(case_id="case-2"))
        queue.get(block=False)
        queue.mark_failed()  # → 'failed'

        assert queue.qsize() == 0

    def test_pending_counts_only_pending_rows(self, queue: SqliteDeedQueue):
        """pending() must not count 'processing', 'done', or 'failed' rows."""
        queue.put(SAMPLE_JOB)
        queue.put(_make_job(case_id="case-2"))
        queue.get(block=False)  # First item → 'processing'

        assert queue.pending() == 1  # Only the second item remains 'pending'

    def test_empty_returns_true_when_no_pending_rows(self, queue: SqliteDeedQueue):
        """empty() must return True when there are no 'pending' rows."""
        assert queue.empty() is True

    def test_empty_returns_false_when_pending_rows_exist(self, queue: SqliteDeedQueue):
        """empty() must return False when at least one 'pending' row exists."""
        queue.put(SAMPLE_JOB)
        assert queue.empty() is False

    def test_empty_returns_true_when_only_processing_rows_exist(self, queue: SqliteDeedQueue):
        """empty() is based on pending() only — a processing row does not prevent empty=True."""
        queue.put(SAMPLE_JOB)
        queue.get(block=False)
        assert queue.empty() is True


# ══════════════════════════════════════════════════════════════════════════════
# 7. Crash Recovery — Processing → Pending on Restart
# ══════════════════════════════════════════════════════════════════════════════

class TestCrashRecovery:
    """
    Validates the startup recovery logic: any row stuck in 'processing'
    (i.e. from a previous crashed run) is reset to 'pending' when a new
    SqliteDeedQueue instance is created pointing at the same DB file.
    """

    def test_processing_rows_are_reset_to_pending_on_restart(self, tmp_path):
        """
        Simulate a crash: leave a job in 'processing', then instantiate a
        new SqliteDeedQueue on the same file and verify it becomes 'pending'.
        """
        db_path = str(tmp_path / "crash_recovery.db")

        # Session 1: put + get (leaves item in 'processing')
        q1 = SqliteDeedQueue(db_path=db_path)
        q1.put(SAMPLE_JOB)
        q1.get(block=False)
        # Simulate crash: do NOT call task_done() or mark_failed()

        assert q1.pending() == 0  # Still in 'processing'

        # Session 2: restart — new instance on the same DB
        q2 = SqliteDeedQueue(db_path=db_path)

        # The stuck 'processing' row must have been reset to 'pending'
        assert q2.pending() == 1

    def test_done_rows_are_not_affected_by_restart(self, tmp_path):
        """
        'done' rows must stay 'done' across restarts — only 'processing'
        rows are reset.
        """
        db_path = str(tmp_path / "done_preserved.db")

        q1 = SqliteDeedQueue(db_path=db_path)
        q1.put(SAMPLE_JOB)
        q1.get(block=False)
        q1.task_done()  # Properly completed

        q2 = SqliteDeedQueue(db_path=db_path)
        assert q2.pending() == 0
        assert q2.qsize() == 0
