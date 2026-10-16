import time
import traceback
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from supabase import Client


class StepStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class PipelineTracker:
    def __init__(self, supabase_client: Client, case_number: str, batch_name: str = ""):
        self.supabase = supabase_client
        self.case_number = case_number
        self.batch_name = batch_name
        self.run_id: Optional[str] = None

    def start_run(self) -> Optional[str]:
        """Creates a master pipeline run record."""
        try:
            # 1. Ensure foreign key constraint is satisfied by guaranteeing case_number exists in 'cases'
            try:
                self.supabase.table("cases").upsert(
                    {"case_number": self.case_number},
                    on_conflict="case_number"
                ).execute()
            except Exception as _fk_err:
                print(f"⚠️ [PipelineTracker] Warning upserting parent case '{self.case_number}': {_fk_err}")

            # 2. Insert master run record
            res = self.supabase.table("pipeline_runs").insert({
                "case_number": self.case_number,
                "overall_status": "RUNNING"
            }).execute()

            if res.data and len(res.data) > 0:
                self.run_id = res.data[0]["id"]
            return self.run_id
        except Exception as e:
            print(f"⚠️ [PipelineTracker] Error starting run for '{self.case_number}': {e}")
            return None

    def track_step(self, block_name: str, step_name: str):
        """Context manager to time and record a specific block execution."""
        tracker = self

        class StepContext:
            def __init__(self, block: str, step: str):
                self.block = block
                self.step = step
                self.start_time = 0.0
                self.metadata: Dict[str, Any] = {}
                self._explicit_status: Optional[StepStatus] = None
                self._error_type: Optional[str] = None
                self._error_details: Optional[str] = None

            def set_metadata(self, key, value):
                self.metadata[key] = value

            def set_status(self, status: StepStatus):
                self._explicit_status = status

            def set_error(self, error_type: str, details: str):
                """Mark step FAILED without raising."""
                self._explicit_status = StepStatus.FAILED
                self._error_type = error_type
                self._error_details = details

            def __enter__(self):
                self.start_time = time.time()
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                duration_ms = int((time.time() - self.start_time) * 1000)

                if exc_type is not None:
                    # Unhandled exception inside the `with` block
                    tb = traceback.format_exc()
                    tracker._log_step(
                        block=self.block, step=self.step, status=StepStatus.FAILED,
                        duration_ms=duration_ms,
                        error_type=exc_type.__name__,
                        error_details=tb,
                        metadata=self.metadata,
                    )
                    tracker._update_block_status(
                        self.block, StepStatus.FAILED,
                        failed_block=f"{self.block}:{self.step}",
                        error_message=tb,
                    )
                    return False  # re-raise the exception

                # No exception
                final_status = self._explicit_status or StepStatus.SUCCESS
                tracker._log_step(
                    block=self.block, step=self.step, status=final_status,
                    duration_ms=duration_ms,
                    error_type=self._error_type,
                    error_details=self._error_details,
                    metadata=self.metadata,
                )
                if final_status == StepStatus.FAILED:
                    tracker._update_block_status(
                        self.block, final_status,
                        failed_block=f"{self.block}:{self.step}",
                        error_message=self._error_details,
                    )
                else:
                    tracker._update_block_status(self.block, final_status)
                return False  # don't suppress anything

        return StepContext(block_name, step_name)

    def _log_step(self, block: str, step: str, status: StepStatus, duration_ms: int,
                  error_type: str = None, error_details: str = None, metadata: Dict = None):
        if not self.run_id:
            return
        try:
            self.supabase.table("pipeline_step_logs").insert({
                "run_id": self.run_id,
                "case_number": self.case_number,
                "block_name": block,
                "step_name": step,
                "status": status.value,
                "execution_time_ms": duration_ms,
                "error_type": error_type,
                "error_details": error_details,
                "metadata": metadata or {}
            }).execute()
        except Exception as e:
            print(f"⚠️ [PipelineTracker] Error logging step {block}:{step} -> {e}")

    def _update_block_status(self, block: str, status: StepStatus, failed_block: str = None, error_message: str = None):
        if not self.run_id:
            return
        column_map = {
            "salesweb": "salesweb_status",
            "zillow": "zillow_status",
            "tracer": "tracer_status",
            "deed": "deed_status",
            "obituary": "obituary_status",
            "supabase_upload": "supabase_upload_status"
        }

        col_name = column_map.get(block.lower(), f"{block.lower()}_status")
        now_iso = datetime.now(timezone.utc).isoformat()
        update_data = {
            col_name: status.value,
            "updated_at": now_iso
        }

        if status == StepStatus.FAILED:
            update_data["overall_status"] = "FAILED"
            update_data["failed_block"] = failed_block
            update_data["last_error_message"] = error_message

        try:
            q = self.supabase.table("pipeline_runs").update(update_data).eq("id", self.run_id)
            if status != StepStatus.FAILED:
                q = q.neq(col_name, "FAILED")   # don't overwrite a failure
            q.execute()
        except Exception as e:
            traceback.print_exc()
            print(f"⚠️ [PipelineTracker] Error updating block status {block} -> {e}")

    def complete_run(self, success: bool = True):
        if not self.run_id:
            return
        status = "COMPLETED" if success else "FAILED"
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            self.supabase.table("pipeline_runs").update({
                "overall_status": status,
                "updated_at": now_iso,
                "completed_at": now_iso
            }).eq("id", self.run_id).execute()
        except Exception as e:
            print(f"⚠️ [PipelineTracker] Error completing run -> {e}")


# ── Thread-local context and decorator for API calls ──────────────────────────
import functools
import threading

_thread_trackers = threading.local()
_global_tracker: Optional[PipelineTracker] = None  # fallback for worker threads


def set_current_tracker(tracker: Optional[PipelineTracker]):
    """Set active PipelineTracker for current thread AND as global fallback.

    The thread-local copy takes priority. The global fallback allows worker
    threads (e.g. ThreadPoolExecutor) that never called set_current_tracker
    themselves to still reach the active tracker.
    """
    global _global_tracker
    _thread_trackers.tracker = tracker
    _global_tracker = tracker  # visible to all threads


def get_current_tracker() -> Optional[PipelineTracker]:
    """Retrieve active PipelineTracker — thread-local first, global fallback."""
    return getattr(_thread_trackers, "tracker", None) or _global_tracker


def track_api_call(block_name: str, step_name: Optional[str] = None):
    """
    Standard reusable decorator for API functions (extract_info_from_salesweb, get_zillow_infos, etc.)
    Logs duration, status, and traceback errors into pipeline_step_logs & updates pipeline_runs.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tracker = kwargs.pop("tracker", None) or get_current_tracker()
            step = step_name or func.__name__

            if not tracker:
                print(f"⚠️ No tracker for {block_name}:{step} (wrong thread?)")
                return func(*args, **kwargs)

            with tracker.track_step(block_name, step) as ctx:
                result = func(*args, **kwargs)
                if isinstance(result, dict) and (
                    "error" in result or str(result.get("status", "")).lower() == "error"
                ):
                    msg = str(result.get("error") or result)
                    ctx.set_metadata("returned_error", msg)
                    ctx.set_error("ReturnedError", msg)
                return result

        return wrapper
    return decorator


# ── Simple standalone helper ───────────────────────────────────────────────────

def update_pipeline_status(
    block: str,
    status: str,
    tb_message: str = None,
    tracker: Optional["PipelineTracker"] = None,
):
    """
    Simple, reusable function to update a pipeline step status in the DB.

    Usage (import and call anywhere):
        from pipeline_tracker import update_pipeline_status

        # Mark a step as SUCCESS
        update_pipeline_status("zillow", "SUCCESS")

        # Mark a step as FAILED with traceback
        update_pipeline_status("deed", "FAILED", tb_message=traceback.format_exc())

    Args:
        block:      One of: salesweb | zillow | tracer | deed | obituary | supabase_upload
        status:     "SUCCESS", "FAILED", or "SKIPPED"
        tb_message: Optional traceback string written to pipeline_step_logs.
        tracker:    Optional explicit PipelineTracker. Falls back to the
                    thread-local tracker set via set_current_tracker().
    """
    t = tracker or get_current_tracker()
    if not t:
        print(f"⚠️ [update_pipeline_status] No active tracker — skipping update for '{block}'.")
        return

    try:
        step_status = StepStatus(status.upper())
    except ValueError:
        print(f"⚠️ [update_pipeline_status] Unknown status '{status}'. Use SUCCESS/FAILED/SKIPPED.")
        return

    # Write a log entry to pipeline_step_logs when there is a message
    if tb_message:
        t._log_step(
            block=block,
            step="manual_update",
            status=step_status,
            duration_ms=0,
            error_type="ManualUpdate" if step_status == StepStatus.FAILED else None,
            error_details=tb_message,
        )

    # Update the matching column in pipeline_runs
    t._update_block_status(
        block=block,
        status=step_status,
        failed_block=block if step_status == StepStatus.FAILED else None,
        error_message=tb_message,
    )
