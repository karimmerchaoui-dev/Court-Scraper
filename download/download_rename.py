"""
Download wait / rename helpers — used by download_files and download_files_nj.
"""

import glob
import os
import re
import shutil
import threading
import time

from selenium.common.exceptions import NoSuchWindowException

from browser.browser_helpers import cancel_all_downloads, request_url
from download.download_helpers import get_timeout
from download.download_monitor import get_current_downloads_state
from download.files_management import cleanup_unwanted_files


def wait_for_new_download_and_rename(driver, download_dir, before_files, new_filename,
                                     case_id, county="", timeout=50):
    import main

    start_time = time.time()
    end_time = start_time + timeout
    cleanup_unwanted_files(download_dir)
    time.sleep(1.5)
    while time.time() < end_time:
        if _should_stop_download():
            return None
        cancel_all_downloads(driver)
        new_file_path = _detect_new_file(download_dir, before_files)
        if new_file_path:
            main.report_cases[case_id]['files'].append(new_filename)
            return _process_and_rename_file(driver=driver, new_file_path=new_file_path,
                                            download_dir=download_dir, new_filename=new_filename,
                                            case_id=case_id, county=county,
                                            start_time=start_time, timeout=timeout)
        time.sleep(0.5)
    return None


def _should_stop_download():
    import main
    return getattr(main, 'force_stop', False)


def _get_current_download_files(download_dir):
    return (set(glob.glob(os.path.join(download_dir, "*.pdf"))) |
            set(glob.glob(os.path.join(download_dir, "*.crdownload"))))


def _detect_new_file(download_dir, before_files):
    current_files = _get_current_download_files(download_dir)
    new_files = current_files - before_files
    if not new_files:
        return None
    safe_files = [f for f in new_files if os.path.exists(f)]
    if not safe_files:
        time.sleep(0.5)
        return None
    return sorted(safe_files, key=os.path.getctime)[0]


def _get_final_file_path(file_path):
    return file_path[:-len(".crdownload")] if file_path.endswith(".crdownload") else file_path


def _wait_for_download_completion(driver, final_file, case_id, county, start_time, timeout):
    crdownload_path = f"{final_file}.crdownload"
    while os.path.exists(crdownload_path):
        if time.time() - start_time > timeout:
            cancel_all_downloads(driver, timeout)
            return False
        timeout = _update_download_progress(driver, case_id, county, timeout)
        time.sleep(0.5)
    return True


def _update_download_progress(driver, case_id, county, timeout=60):
    from app import update_case_status

    try:
        file, status, progress, url = get_current_downloads_state(driver)
        updated_timeout = get_timeout(status, timeout)
        if updated_timeout:
            timeout = updated_timeout
        if not status:
            if url:
                request_url(driver, url)
            time.sleep(2)
        thread_num = _get_thread_number()
        update_case_status(driver, case_id, county, f"Downloading (Thread {thread_num})",
                           progress_down=status)
        return timeout
    except NoSuchWindowException:
        pass


def _get_thread_number():
    pattern = r'ThreadPoolExecutor-\d+_(\d+)'
    thread_name = threading.current_thread().name
    match = re.search(pattern, thread_name)
    return int(match.group(1)) + 1 if match else 0


def _ensure_pdf_extension(filename):
    return filename if ".pdf" in filename else f"{filename}.pdf"


def _rename_downloaded_file(source_path, download_dir, new_filename):
    if not os.path.exists(source_path):
        return None
    new_filename = _ensure_pdf_extension(new_filename)
    new_path = os.path.join(download_dir, new_filename)
    while True:
        try:
            shutil.move(source_path, new_path)
            break
        except PermissionError:
            pass
    return new_path


def _process_and_rename_file(driver, new_file_path, download_dir, new_filename,
                             case_id, county, start_time, timeout):
    final_file = _get_final_file_path(new_file_path)
    completed = _wait_for_download_completion(driver=driver, final_file=final_file,
                                              case_id=case_id, county=county,
                                              start_time=start_time, timeout=timeout)
    if not completed:
        return 0
    return _rename_downloaded_file(final_file, download_dir, new_filename)
