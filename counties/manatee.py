import threading

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from browser.browser_helpers import (
    close_download_frame,
    close_extra_tabs,
    request_url,
    wait_and_click,
)
from config_ import DEFAULT_KEYWORDS, DEFAULT_UNWANTED
from download.download_monitor import set_download_dir
from download.DownloadManager import DownloadManager
from download.files_management import cleanup_unwanted_files
from download.scanners import scan_table_multithreaded


def trigger_download_manatee(driver, row, index, download_mgr, before_files, matching_row=None, max_retries=3):
    set_download_dir(driver, download_mgr.download_dir)
    down_flag = None
    driver.switch_to.window(driver.window_handles[0])

    try:
        download_button = driver.find_element(By.XPATH, f'//*[@id="dockets"]/tbody/tr[{index}]/td[1]/form/button')
    except NoSuchElementException:
        return 2

    download_button.click()

    attempt = 0
    while not down_flag and attempt < max_retries:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="delivery-options"]/li[1]/a'))).click()
        down_flag = download_mgr.wait_for_download_start(before_files)
        attempt += 1
        if not down_flag and "inactivity" in driver.text:
            print("INACTIVITY ISSUE")
            return 1


    if not down_flag:
        print(f"❌ Download failed after {max_retries} attempts for row {index}")
        return 1

    driver.back()

def navigate_to_url_manatee(driver,case_id):
    request_url(driver,f"https://records.manateeclerk.com/CourtRecords/Search/CaseNumber?caseNumber={case_id}&page=1&pageSize=25&myCases=False")

def navigate_to_search_manatee(driver,case_id):
    wait = WebDriverWait(driver, 6)
    result = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="results-table"]/tbody[2]/tr/td'))).text
    if "NO RECORDS FOUND" in result:
        return 2
    wait_and_click(driver, By.XPATH, '//*[@id="results-table"]/tbody[2]/tr/td[2]/form/button')

    pass
def navigate_to_search():
    pass



def navigate_to_files_table_manatee(driver):
    pass




def download_files_manatee(driver,driver_pool, files_dir, case_id,report_cases,default_keyword=DEFAULT_KEYWORDS,default_unwanted=DEFAULT_UNWANTED,status_callback=None):
    #download manager
    download_mgr = DownloadManager(driver, driver_pool, files_dir, case_id, "Manatee",status_callback=status_callback)
    download_mgr.update_status("Downloading", details="Checking for files")

    #tablee
    table = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, '//*[@id="dockets"]/tbody'))
    )
    rows = table.find_elements(By.TAG_NAME, "tr")
    total_rows = len(rows)

    # get_type/status


    #get current window
    main_frame = driver.current_window_handle


    #get mactching rows

    matching_rows = scan_table_multithreaded(
        driver=driver, case_id=case_id,
        files_dir=files_dir,
        total_rows=total_rows,
        report_cases=report_cases,
        matching_rows=[],
        matching_rows_lock=threading.Lock(),
        keyword_list=default_keyword,
        unwanted_list=default_unwanted,
        county="manatee",
        start_index=1
    )
    print(f"matching_rows : {matching_rows}")



    #update GUI
    download_mgr.update_status("Downloading", details="Checking for files")


    for file in matching_rows:
        while True:
            # files data
            index = file['row_index']
            filename = file['filename']
            date = file['date']

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

            row = driver.find_element(By.XPATH, f'//*[@id="dockets"]/tbody/tr[{index}]')

            # trigger download
            #//*[@id="dockets"]/tbody/tr[19]/td[1]/form/button
            down_flag = trigger_download_manatee(driver,row,index,files_dir)
            if down_flag:
                driver.switch_to.window(main_frame)
                continue
            new_file = download_mgr.wait_for_file_detection(before_files)

            if not new_file:
                print(f"❌ No file detected for {filename}")
                close_download_frame(driver, main_frame)
                driver.switch_to.window(main_frame)
                continue
            download_flag = download_mgr.rename_file(f"{filename}_{date}",case_id, report_cases, new_file=new_file)

            if download_flag:
                print(f"✅ Successfully downloaded: {filename}")
                close_download_frame(driver, main_frame)
                driver.switch_to.window(main_frame)
                break
            close_download_frame(driver,main_frame)
            driver.switch_to.window(main_frame)
    return

