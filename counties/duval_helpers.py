

import traceback

from selenium.common.exceptions import (
    ElementNotInteractableException,
    NoSuchElementException,
    UnexpectedAlertPresentException,
)
from selenium.webdriver.common.by import By

from browser.browser_helpers import *
from counties.polk_helpers import *
from download.download_monitor import open_downloads_tab
from download.DownloadManager import DownloadManager
from download.files_management import cleanup_unwanted_files

current_batch_folder = None
driver_pool=None
keyword_list=None
unwanted_list=None



def navigate_to_files_table_dv(driver):
    case_table = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (By.XPATH, '//*[@id="ContentPlaceHolder1_WebTab1"]/div/div[4]'))
    )
    while "Loading the requested case, please wait" in case_table.text:
        case_table = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, '//*[@id="ContentPlaceHolder1_WebTab1"]/div/div[4]'))
        )
    if "could not be found" in case_table.text:
        return 2


def search_case_dv(driver, case_id):
    MAX_ATTEMPTS = 3
    PORTAL_URL = "https://core.duvalclerk.com/CoreCms.aspx?mode=PublicAccess"
    EXPECTED_TITLE = "CORE - Clerk Online Resource ePortal"

    case_id = case_id.strip()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            print(f"[Duval] Searching case: {case_id} (Attempt {attempt})")

            request_url(driver, PORTAL_URL)

            # Validate correct page loaded
            if driver.title != EXPECTED_TITLE:
                print(f"[Duval] Unexpected page title: {driver.title}")
                return 1

            # Wait for case input field
            case_entry = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//*[@id="ContentPlaceHolder1_WebTab1"]/div/div[3]/div/table[1]/tbody/tr[3]/td[1]')
                )
            )


            enter_case_number_dv(driver, case_entry, case_id)

            return 0  # success

        except (TimeoutException, UnexpectedAlertPresentException, ElementNotInteractableException):
            print(f"[Duval] Retry triggered for {case_id}")
            traceback.print_exc()
            refresh_url(driver)

        except Exception as e:
            print(f"[Duval] Unexpected error: {e}")
            traceback.print_exc()
            refresh_url(driver)

    print(f"[Duval] Failed after {MAX_ATTEMPTS} attempts: {case_id}")
    return 1

def enter_case_number_dv(driver, case_entry, case_id):
    force_send_keys(driver, case_entry, case_id)

    # Wait for search button
    search_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (By.XPATH, '//*[@id="ContentPlaceHolder1_WebTab1"]/div/div[3]/div/table[1]/tbody/tr[4]/td//input')
        )
    )

    search_button.click()


def trigger_download_dv(driver,docket_eg,row_index,download_mgr,before_files,matching_row=None):
    down_flag = None
    attempt = 0
    #//*[@id="c_DocketsPanel"]/div/table/tbody[32]/tr/td[6]/div
    print(f"row_index : {row_index}")
    driver.switch_to_window(driver.window_handles[0])
    docket_eg=driver.find_element(By.XPATH, f'//*[@id="c_DocketsPanel"]/div/table/tbody[{row_index}]/tr/td[6]/div')
    print(f'docket_eg : //*[@id="c_DocketsPanel"]/div/table/tbody[{row_index}]/tr/td[6]/div')
    while attempt < 5 and not down_flag:
        set_download_dir(driver, download_mgr.download_dir)
        driver.switch_to_window(driver.window_handles[0])
        file_button=docket_eg.find_element(By.TAG_NAME, "a")
        file_button.click()
        down_flag = download_mgr.wait_for_download_start(before_files)
        attempt+=1


def download_files_dv(driver, download_dir, case_id,table_xpath,max_retry_attempts=5):
    try:
        """
        Downloads files for DV county using scan_table_multithreaded
        to avoid scanning multiple times.
        """
        global report_cases

        retry_attempt=0


        download_dir=download_dir.strip()

        # download manager
        download_mgr = DownloadManager(driver, driver_pool, download_dir, case_id, "Duval",status_callback=update_case_status)
        download_mgr.update_status("Downloading", details="Checking for files")


        #case navigation
        case_table = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, '//*[@id="ContentPlaceHolder1_WebTab1"]/div/div[4]'))
        )

        while "Loading the requested case, please wait" in case_table.text:
            case_table = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//*[@id="ContentPlaceHolder1_WebTab1"]/div/div[4]'))
            )
        if "could not be found" in case_table.text:
            traceback.print_exc()
            report_cases[case_id]['Case Status'] = "Case Not Found"
            return 1


        #tablee
        files_table = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, table_xpath))
        )
        files_rows = files_table.find_elements(By.TAG_NAME, "tr")
        total_rows = len(files_rows)


        #get_type/status
        case_status = WebDriverWait(case_table, 3).until(
            EC.presence_of_element_located((By.XPATH, './div/div[1]/table/tbody/tr[2]/td[2]'))).text
        print(f"report_cases: {report_cases}")
        print(f"report_cases[case_id] {report_cases[case_id]}")
        report_cases[case_id]['Case Status'] = case_status



        main_handle=driver.current_window_handle


        #get mactching rows
        print("] Scanning rows for matches using multithreading...")
        matching_rows_lock = threading.Lock()
        matching_rows = scan_table_multithreaded(
            driver=driver,case_id=case_id,
            files_dir=download_dir,
            report_cases=report_cases,
            total_rows=total_rows,
            matching_rows=[],
            matching_rows_lock=matching_rows_lock,
            keyword_list=keyword_list,
            unwanted_list=unwanted_list,
            county="dv",  # specify DV so scan_rows_dv is used
            start_index=1
        )

        #update GUI
        download_mgr.update_status("Downloading", details="Checking for files")


        # ----------------------------
        # STEP 2: Download files
        # ----------------------------

        for matchin_row in matching_rows:
            while retry_attempt<max_retry_attempts:
                # files data
                row_index = matchin_row["row_index"]
                description = matchin_row["description"]
                filename = matchin_row["filename"]
                date = matchin_row["date"]
                print(f"filename : {filename}")
                download_retry = 0

                #close any extra tabs
                close_extra_tabs(driver)

                # get before files


                #delete crdownlaod files
                cleanup_unwanted_files(download_dir)

                #set download dir
                set_download_dir(driver,download_dir)


                #update GUI
                download_mgr.update_status("Downloading", details=f"File {row_index + 1}/{total_rows}: {filename}")


                # Locate the table row again for clicking
                # get before files
                before_files = download_mgr.get_existing_files()
                try:
                    driver.switch_to_window(main_handle)
                    cell_xpath = f'//*[@id="c_DocketsPanel"]/div/table/tbody[{row_index}]/tr'
                    try:
                        file_row = driver.find_element(By.XPATH, cell_xpath)
                    except ConnectionRefusedError:
                        print("ConnectionRefusedError")
                        continue
                    except NoSuchElementException:
                        refresh_url(driver)
                        driver.switch_to_window(main_handle)
                        time.sleep(0.1)
                        download_retry=download_retry+1
                        if download_retry > 5:
                            break
                        continue
                    except Exception:
                        traceback.print_exc()
                        return 1
                    driver.execute_script("arguments[0].scrollIntoView();", file_row)

                    # Track files before download

                    # Ensure browser download dir is correct
                    set_download_dir(driver, download_dir)
                    # Click to download
                    driver.switch_to_window(main_handle)
                    maximize_driver(driver)
                    time.sleep(0.5)

                    trigger_download_dv(driver,file_row,row_index,download_mgr,before_files)
                    # Wait for new file and rename
                    open_downloads_tab(driver)
                    timeout = _update_download_progress(driver, case_id, "Duval")
                    print(f"timeout : {timeout}")
                    time.sleep(5)
                    new_file = download_mgr.wait_for_file_detection(before_files,timeout=timeout,driver=driver)

                    print(f"new_file : {new_file}")

                    if not new_file:
                        retry_attempt+=1
                        print(f"❌ No file detected for {filename}")
                        continue

                    # Download and rename
                    download_flag = download_mgr.rename_file(f"{filename}_{date}",case_id,report_cases, new_file=new_file)


                    print(f"download_flag : {download_flag}")
                    if download_flag:
                        retry_attempt+=1
                        print(f"❌ Failed to rename {filename}")
                        continue
                    break
                except Exception as e:
                    traceback.print_exc()
        return
    except Exception:
        return 1