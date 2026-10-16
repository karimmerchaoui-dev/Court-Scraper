
import threading
import time

import pysnooper
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from browser.browser_helpers import (
    close_extra_tabs,
    request_url_with_timeout,
    wait_and_click,
)
from browser.captcha import captcha_solver
from download.download_helpers import cleanup_failed_download, cleanup_unwanted_files
from download.download_monitor import set_download_dir
from download.DownloadManager import DownloadManager
from download.scanners import scan_table_multithreaded


@pysnooper.snoop()
def solve_captcha_oc(driver):
    # Step 3: Solve captcha
    res=None
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, 'g-recaptcha-response'))
        )
        res = captcha_solver(driver,
                             "6LdtOBETAAAAABvi0Md4UUqb7GKfkRiUR6AsrFX-",
                             driver.current_url
                             )
    except TimeoutError:
        return 1
    if not res:
        return 1
    print(f"res : {res}")
    driver.execute_script("document.getElementById('g-recaptcha-response').innerHTML = arguments[0];", res)
    driver.execute_script("document.getElementById('g-recaptcha-response-100000').innerHTML = arguments[0];", res)

    #driver.execute_script("document.getElementById('caseSearch').removeAttribute('disabled');")
    driver.execute_script("$('#caseSearch').removeAttr('disabled');")




def navigate_to_url_oc(driver,case_id):
    return request_url_with_timeout(driver, "https://myeclerk.myorangeclerk.com/Cases/search", timeout=30)

@pysnooper.snoop()
def navigate_to_search_oc(driver):

    captcha_flag = solve_captcha_oc(driver)
    if captcha_flag:
        return 1

def navigate_to_files_table_oc(driver):
    wait_and_click(driver, By.XPATH, '//*[@id="caseList"]/tbody/tr/td[2]/a')

@pysnooper.snoop()
def trigger_download_oc(driver,row,row_index,download_mgr,before_files,matching_row=None):
    set_download_dir(driver, download_mgr.download_dir)
    switch_to_main_oc(driver)
    try:
        link_element = row.find_element(
            By.XPATH,
            f'./td[9]/a'
        )
        #
    except NoSuchElementException:
        return 1
    driver.execute_script("arguments[0].click();", link_element)
    time.sleep(2)


def get_case_type_oc(driver):
    return WebDriverWait(driver, 5).until(EC.presence_of_element_located(("xpath", '//*[@id="headerCollapse"]/div/div[1]/div[2]'))).text


def switch_to_main_oc(driver):
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        if "myeclerk.myorangeclerk.com" in driver.current_url:
            break



def download_files_oc(driver,driver_pool,case_id, files_dir,table_xpath,report_cases,keyword_list,unwanted_list,update_case_status=None):
    """Download all matching files from Orange County case."""
    driver.state = "downloading"

    #download manager
    download_mgr = DownloadManager(driver, driver_pool, files_dir, case_id, "Orange",status_callback=update_case_status)
    download_mgr.update_status("Downloading", details="Checking for files")

    # Find files table
    # tablee
    files_table = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located(("xpath", table_xpath))
    )
    files_rows = files_table.find_elements(By.TAG_NAME, "tr")
    total_rows = len(files_rows) - 1



    # Get case type
    case_type = get_case_type_oc(driver)
    report_cases[case_id]['case_type'] = case_type

    main_frame = driver.current_window_handle

    #get mactching rows
    matching_rows_lock = threading.Lock()
    matching_rows = scan_table_multithreaded(
        driver,case_id, files_dir,report_cases, total_rows, [], matching_rows_lock,
        keyword_list, unwanted_list, "oc", start_index=1
    )

    print(f"matching_rows : {matching_rows}")
    # Download each matching file
    for file_info in matching_rows:
        start_time = time.time()
        row_index = file_info['row_index']
        filename = file_info['filename']
        date = file_info['date']

        # Retry loop for individual file
        switch_to_main_oc(driver)
        while time.time() - start_time < download_mgr.max_retry_seconds:
            # close extra tabs
            close_extra_tabs(driver)

            # get before files
            before_files = download_mgr.get_existing_files()

            # delete crdownlaod files
            cleanup_unwanted_files(files_dir)

            # set download dir
            set_download_dir(driver, files_dir)

            # update GUI
            download_mgr.update_status("Downloading", details=f"File {row_index + 1}/{total_rows}: {filename}")

            #
            driver.switch_to.window(driver.window_handles[0])
            row = driver.find_element(By.XPATH, f'//*[@id="docketTable"]/tbody/tr[{row_index}]')

            download_flag = trigger_download_oc(driver,row,row_index,case_id)
            if download_flag:
                continue

            # Wait for file to appear
            new_file = download_mgr.wait_for_file_detection(before_files,driver=driver)

            if not new_file:
                print(f"❌ No file detected for {filename}")
                cleanup_failed_download(download_mgr, before_files)

                continue

            # Download and rename
            fail = download_mgr.rename_file(f"{filename}_{date}",case_id,report_cases, new_file=new_file)

            # Cleanup extra windows
            close_extra_tabs(driver)

            if not fail:
                print(f"✅ Successfully downloaded: {filename}")
                break
            else:
                cleanup_failed_download(download_mgr, before_files)
@pysnooper.snoop()
def search_case_number_oc(driver,case_id):

    case_number_input = WebDriverWait(driver, 60).until(
        EC.presence_of_element_located((By.XPATH, '//*[@id="caseNumber"]'))
    )
    case_number_input.clear()
    case_number_input.send_keys(case_id)


    # Step 4: Click search
    search = driver.find_element(By.ID, "caseSearch")
    driver.execute_script("arguments[0].removeAttribute('disabled');", search)
    wait_and_click(driver, By.ID, 'caseSearch')

    # Step 5: Wait for results
    case = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.XPATH, '//*[@id="caseList"]/tbody/tr/td'))
    )

    if "No data" in case.text:
        return 2
