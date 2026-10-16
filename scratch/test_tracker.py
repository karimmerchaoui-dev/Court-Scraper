import sys

sys.path.insert(0, ".")

from database.supabase_service import supabase
from pipeline_tracker import PipelineTracker, set_current_tracker

case_num = "f-testapi-24"
tracker = PipelineTracker(supabase, case_num, "test_batch_api")

run_id = tracker.start_run()
set_current_tracker(tracker)
print("Run started for test API, ID:", run_id)

# Test 1: Zillow API call
try:
    from browser.zillow_helpers import get_zillow_infos
    get_zillow_infos("123 Main St, Newark, NJ", "scratch")
except Exception as e:
    print("Zillow call executed (expected exception/result caught):", e)

# Test 2: Skip Trace API call
try:
    from utils.people_data import defendant_skip_trace
    defendant_skip_trace("John Doe", "123 Main St, Newark, NJ")
except Exception as e:
    print("Skip trace call executed:", e)

res_run = supabase.table("pipeline_runs").select("*").eq("id", run_id).execute()
print("Updated pipeline_run record after calls:", res_run.data)

tracker.complete_run(True)

# Cleanup
supabase.table("pipeline_step_logs").delete().eq("run_id", run_id).execute()
supabase.table("pipeline_runs").delete().eq("id", run_id).execute()
supabase.table("cases").delete().eq("case_number", case_num).execute()
print("Cleaned up test records OK.")
