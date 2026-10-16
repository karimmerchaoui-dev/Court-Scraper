import os
import threading
import traceback

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from browser.browser_helpers import (
    close_extra_tabs,
    close_new_windows,
    random_scroll,
    set_download_dir,
    switch_to_window_by_url_prefix,
)
from download.DownloadManager import DownloadManager
from download.files_management import cleanup_unwanted_files
from download.scanners import scan_table_multithreaded
from utils.formatting import convert_to_kb


def get_timeout(status,init_timeout):
    timeout=init_timeout
    kb_per_second=400
    size=0
    if status and "of" in status:
        total_size_str = status.split("of")[1].split(',')[0].strip()
        try:
            new_size = convert_to_kb(total_size_str)
            if size != new_size:
                size = new_size
                timeout = int(size / kb_per_second )
                if timeout < 10:
                    timeout = 20
                return timeout
        except ValueError:
            return timeout




def download_files(driver,driver_pool, files_dir, case_id,county_name,table_path,case_type_xpath,case_url_prefix,report_cases,max_retry_attempts=5,status_callback=None):
    retry_attempt=0

    #download manager
    download_mgr = DownloadManager(driver, driver_pool, files_dir, case_id, county_name,status_callback=status_callback)
    download_mgr.update_status("Downloading", details="Checking for files")

    #tablee
    table = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, table_path))
    )
    rows = table.find_elements(By.TAG_NAME, "tr")
    total_rows = len(rows)



    # get_type/status
    case_type = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, case_type_xpath))
    ).text

    report_cases[case_id]['case_type']=case_type



    #get mactching rows
    matching_rows_lock = threading.Lock()
    # ✅ Only scan from start_index onwards
    matching_rows = scan_table_multithreaded(driver,case_id, files_dir,report_cases, total_rows, table_path, matching_rows_lock,
                                             keyword_list, unwanted_list,county_name, start_index=0)


    print(f"matching_rows : {matching_rows}")

    #update GUI
    download_mgr.update_status("Downloading", details="Checking for files")


    for file in matching_rows:
        main_window = driver.current_window_handle
        while retry_attempt<max_retry_attempts:
            try:
                #recheck because it causes stale element exception if you use the initial instance
                driver.switch_to.window(main_window)

                table = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, table_path))
                )
                random_scroll(driver)

                # files data
                index = file['row_index']
                filename = file['filename']
                date = file['date']
                print(f"filename : {filename}")
                print(f"index : {index}")
                # close extra tabs
                close_extra_tabs(driver)

                # delete crdownlaod files
                cleanup_unwanted_files(files_dir)

                # get before files
                before_files = download_mgr.get_existing_files()

                # set download dir
                set_download_dir(driver, files_dir)


                #update GUI
                download_mgr.update_status("Downloading", details=f"File {index + 1}/{total_rows}: {filename}")


                switch_to_window_by_url_prefix(driver,case_url_prefix)


                windows_before = driver.window_handles


                row = table.find_element(By.XPATH, f'./tr[{index}]')


                trigger_download_func = DOWNLOAD_FUNCTIONS.get(county_name)
                down_flag = trigger_download_func(driver, row, index, download_mgr, before_files)

                close_new_windows(driver, windows_before, main_window)
                if down_flag:
                    print(f"❌ Failed Attempt {filename}")
                    retry_attempt = +1
                    continue


                new_file = download_mgr.wait_for_file_detection(before_files)

                if not new_file:
                    print(f"❌ No file detected for {filename}")
                    retry_attempt=+1
                    continue
                download_flag = download_mgr.rename_file(f"{filename}_{date}", case_id, report_cases, new_file=new_file)
                driver.switch_to_window(main_window)

                print(f"download_flag : {download_flag}")
                if download_flag:
                    retry_attempt = +1
                    print(f"❌ Failed to rename {filename}")
                    break
                break
            except Exception:
                traceback.print_exc()
    return



def cleanup_failed_download(download_mgr, before_files):
    """
    Delete any files that were downloaded since before_files was captured.

    Args:
        download_mgr: DownloadManager instance
        before_files: Set of files that existed before download attempt
        files_dir: Directory where files are downloaded
    """
    try:
        current_files = download_mgr.get_existing_files()
        unwanted_files = current_files - before_files

        if unwanted_files:
            print(f"🗑️ Cleaning up {len(unwanted_files)} failed download file(s)")
            for file_path in unwanted_files:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        print(f"   Deleted: {os.path.basename(file_path)}")
                except Exception as e:
                    print(f"   ⚠️ Could not delete {file_path}: {e}")
        else:
            print("✓ No orphaned files to clean up")

    except Exception as e:
        print(f"⚠️ Error during cleanup: {e}")
        traceback.print_exc()