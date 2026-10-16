import time


def final_update(case_id,t1,county,driver,driver_pool,report_cases,status,processed,total_cases,update_progress,status_text,callback_func=None):
    t2 = time.time()
    # Extract file count and other interesting row info from report_cases
    case_report = report_cases.get(case_id, {})
    files_downloaded = len(case_report.get('files', []))
    
    # Grab additional info (e.g. Recent Bankruptcy, Vacate flags, etc.) ignoring standard structural keys
    ignore_keys = {'files', 'status', 'Case number', 'County', 'processing_duration', 'case_type', 'court_case_status', 'failed_files'}
    extra_info = []
    for k, v in case_report.items():
        if k not in ignore_keys and v and v != "❌":
            # Just format cleanly, e.g., "Bankruptcy: ✅" or "Recent Vacate: filename.pdf"
            extra_info.append(f"{k}: {v}")
            
    info_str = f"Downloaded {files_downloaded} files."
    if extra_info:
        info_str += "\nInfo: " + ", ".join(extra_info)

    if status == "Completed":
        callback_func(driver, case_id, county, status, details=info_str)
        report_cases[case_id]['status'] = "Completed"
    else:
        callback_func(driver, case_id, county, status, details=f"Finished. {info_str}")
        report_cases[case_id]['status'] = status
    report_cases[case_id]['processing_duration'] = f"{t2 - t1:.2f}"
    if processed:
        try:
            import main
            main.processed += 1
            processed_val = main.processed
        except ImportError:
            # Fallback if called in a context where main isn't importing
            processed_val = processed + 1

        progress = processed_val / total_cases
        update_progress(progress)
        status_text.set(f"Processing... {processed_val}/{total_cases}")
        print(f"available : {driver_pool.available}")
        print(f"in use : {driver_pool.in_use}")
