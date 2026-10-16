
import os
import sys

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    NoSuchWindowException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import time
import traceback

import pysnooper

from app import log_message
from browser.browser_helpers import (
    _cleanup_windows,
    element_exists_id,
    refresh_url,
    request_url,
    request_url_with_timeout,
    wait_and_click,
)
from browser.captcha import turnstile_solver
from download.download_monitor import open_downloads_tab, set_download_dir
from download.DownloadManager import DownloadManager
from download.scanners import KEYWORDS_TO_PRUNE, prune_older_keyword_duplicates
from utils.formatting import parse_date_safe, sanitize_filename


def navigate_to_search_bw(driver):
    log_message("🔍 [Broward] navigate_to_search_bw: Starting...")
    try:
        # Make sure we're on a valid window before doing anything
        current_handle = driver.current_window_handle  # will raise if window is gone
    except NoSuchWindowException:
        log_message("⚠️ [Broward] Window was lost before navigation, switching to available handle...")
        available = driver.window_handles
        if not available:
            log_message("❌ [Broward] No windows left, browser likely crashed")
            return 1
        driver.switch_to.window(available[-1])

    try:
        case_number = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located(
                ("xpath", '//*[@id="myTabStandard"]/div/div/ul/li[3]/a'))
        )
        case_number.click()
        log_message("🔍 [Broward] Clicked search tab, solving captcha...")
        captcha_flag = solve_captcha_bw(driver)
        if captcha_flag:
            log_message("⚠️ [Broward] Captcha solve returned flag 1 (failed/timeout)")
            return 1
        log_message("✅ [Broward] navigate_to_search_bw complete")

    except NoSuchWindowException:
        log_message("⚠️ [Broward] Window closed during navigation, attempting recovery...")
        available = driver.window_handles
        if available:
            driver.switch_to.window(available[-1])
            return 1  # Signal caller to retry
        return 1


@pysnooper.snoop()
def trigger_download_bw(driver, row, index, download_mgr, before_files,matching_row=None):
    down_flag = None
    attempt = 0
    main_window = driver.current_window_handle

    while attempt < 5 and not down_flag:
        set_download_dir(driver,download_mgr.download_dir)
        driver.switch_to.window(driver.window_handles[0])
        # Click download button (opens new window)
        
        file_button = row.find_element(By.TAG_NAME, 'button')
        driver.execute_script("arguments[0].click();", file_button)
        down_flag = download_mgr.wait_for_download_start(before_files)
        # Wait for new window
        WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > 1)
        driver.switch_to.window(driver.window_handles[-1])

        # Click corner button to prepare PDF
        if not _click_broward_corner_button(driver):
            _cleanup_windows(driver, main_window)
            return 1

        # Get download link from iframe
        download_url = _get_broward_download_link(driver)
        if not download_url:
            _cleanup_windows(driver, main_window)
            return 1

        # Track files before download

        # Navigate to download URL
        driver.switch_to.default_content()
        request_url(driver, download_url)










def search_case_number_bw(driver,case_id):

    case_number_input=WebDriverWait(driver, 30).until(
        EC.element_to_be_clickable(
            (By.ID, 'CaseNumber'))
    )
    case_number_input.clear()
    #
    case_number_input.send_keys(case_id)
    while element_exists_id(driver,'CaseNumberSearchResults'):
        print("clicking on search")
        driver.set_window_size(1000, 1000)
        wait_and_click(driver,By.XPATH,'//*[@id="CaseNumberSearchResults"]')
        time.sleep(3)

@pysnooper.snoop()
def solve_captcha_bw(driver):
    log_message("🤖 [Broward] solve_captcha_bw: Waiting for captcha iframe...")
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located(
                (By.XPATH, '//*[@id="RecaptchaField3"]/div/div/iframe'))
        )
    except TimeoutException:
        pass
    res=None
    while not res:
        try:
            log_message("🤖 [Broward] Submitting captcha to 2captcha service...")
            res = turnstile_solver(driver,"0x4AAAAAAD3XKK8DxzWwYii7", "https://www.browardclerk.org/Web2")
        except TimeoutError:
            log_message("⚠️ [Broward] Captcha timed out, refreshing and returning flag 1")
            refresh_url(driver)
            return 1
    log_message(f"✅ [Broward] Captcha solved, injecting response token...")
    driver.execute_script("document.getElementById('cf-chl-widget-98wra_response').innerHTML = " + f"'{res}'")
    log_message("✅ [Broward] solve_captcha_bw complete")


def navigate_to_url_bw(driver,case_id):
    log_message(f"🌐 [Broward] [{case_id}] navigate_to_url_bw: Navigating to Broward portal...")
    while True:
        try:
            request_url_with_timeout(driver, "https://www.browardclerk.org/Web2")
            log_message(f"✅ [Broward] [{case_id}] navigate_to_url_bw complete")
            break
        except WebDriverException:
            time.sleep(2)
            log_message(f"🔄 [Broward] [{case_id}] WebDriverException on URL load, refreshing...")

def navigate_to_files_table_bw(driver):
    case = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located(
            (By.XPATH, '//*[@id="SearchResultsGrid"]/div[3]/span'))
    )

    if "No items" in case.text:
        return 2
    wait_and_click(driver, By.CLASS_NAME, 'bc-casedetail-viewer')



def _download_single_broward_file(driver,driver_pool, file_info, files_dir, case_id,
                                  main_window, update_case_status=None):
    """Download one file from Broward with error handling"""
    filename = file_info['filename']


    # download manager
    download_mgr = DownloadManager(driver, driver_pool, files_dir, case_id, "Broward",status_callback=update_case_status)
    download_mgr.update_status("Downloading", details="Checking for files")

    try:

        # Click download button (opens new window)
        driver.execute_script("arguments[0].click();", file_info['button'])

        # Wait for new window
        WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > 1)
        driver.switch_to.window(driver.window_handles[-1])

        # Click corner button to prepare PDF
        if not _click_broward_corner_button(driver):
            _cleanup_windows(driver, main_window)
            return False

        # Get download link from iframe
        download_url = _get_broward_download_link(driver)
        if not download_url:
            _cleanup_windows(driver, main_window)
            return False

        # Track files before download
        before_files = download_mgr.get_existing_files()

        # Navigate to download URL
        driver.switch_to.default_content()
        request_url(driver, download_url)


        # Open downloads tab and wait for completion
        open_downloads_tab(driver)
        driver.switch_to.window(driver.window_handles[-1])



        new_file = download_mgr.wait_for_file_detection(before_files)

        # Close downloads tab
        if len(driver.window_handles) > 1:
            driver.close()

        # Close file viewer window and return to main
        _cleanup_windows(driver, main_window)
        download_flag = download_mgr.rename_file(filename,case_id,report_cases, new_file=new_file)
        if not download_flag:
            return True
        else:
            return False

    except Exception as e:
        _cleanup_windows(driver, main_window)
        return False


def _click_broward_corner_button(driver, max_attempts=3):
    """Click the corner button in Broward PDF viewer"""
        #//*[@id="rdToolBar"]/div/div/div/ul/li[1]/a/span/span/span
    button_xpath = '//*[@id="rdToolBar"]/div/div/div/ul/li[1]/a/span/span/span'

    for attempt in range(max_attempts):
        try:
            button = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(("xpath", button_xpath))
            )

            # Check if button says "view all" - need to refresh if so
            button_text = button.text.lower()
            if not("view all" in button_text):
                driver.refresh()
                time.sleep(1)
                continue

            # Click the button
            driver.execute_script("arguments[0].click();", button)
            time.sleep(2)  # Wait for PDF to prepare
            return True

        except NoSuchElementException:
            driver.refresh()
            if attempt < max_attempts - 1:
                time.sleep(1)
        except TimeoutException:
            driver.refresh()
            if attempt < max_attempts - 1:
                time.sleep(1)
        except ElementClickInterceptedException:
            driver.refresh()
            time.sleep(1)

    return False


def _get_broward_download_link(driver):
    """Extract download link from Broward PDF iframe"""
    try:
        # Switch to PDF iframe
        iframe = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, 'RAD_SPLITTER_PANE_EXT_CONTENT_pdfview'))
        )
        driver.switch_to.frame(iframe)

        # Get download link
        link = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(('xpath', '//*[@id="main-content"]/a'))
        )
        href = link.get_attribute("href")

        return href

    except TimeoutException:
        return None
    except Exception as e:
        return None





def download_files_bw(driver, case_id, files_dir):
    """Download files from Broward County with optimized performance"""
    try:
        driver.state = "downloading"
        driver.implicitly_wait(2)  # Faster element checks

        set_download_dir(driver, files_dir)

        # Get table with fallback
        files_table = _get_broward_table(driver)
        files_rows = files_table.find_elements(By.TAG_NAME, "tr")[1:]  # Skip header
        # STEP 1: Quick scan - find matching files WITHOUT opening windows

        files_to_download = _scan_broward_files(files_rows)

        #
        files_table_dispos = _get_broward_table_dispos(driver)
        files_rows_dispos = files_table_dispos.find_elements(By.TAG_NAME, "tr")  # Skip header
        files_to_download_dispos=_scan_broward_files_dispos(files_rows_dispos)

        files_to_download = files_to_download + files_to_download_dispos
        files_to_download.sort(key=lambda r: parse_date_safe(r["date"]), reverse=True)
        files_to_download = prune_older_keyword_duplicates(
            files_to_download,
            KEYWORDS_TO_PRUNE
        )

        log_message(f"📥 [Broward] [{case_id}] Files to download: {[f['filename'] for f in files_to_download]}")

        if not files_to_download:
            return


        # STEP 2: Download each matching file
        main_window = driver.current_window_handle
        successful_downloads = 0

        for idx, file_info in enumerate(files_to_download, 1):
            success = _download_single_broward_file(
                driver, file_info, files_dir, case_id,
                main_window, idx, len(files_to_download)
            )
            if success:
                successful_downloads += 1

    except TimeoutException:
        refresh_url(driver)
    except Exception as e:
        traceback.print_exc()


def _get_broward_table(driver):
    """Get files table with automatic fallback"""
    try:
        return WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, 'tblEvents'))
        )
    except TimeoutException:
        # Click viewer and retry
        wait_and_click(driver, By.CLASS_NAME, 'bc-casedetail-viewer')
        time.sleep(2)
        return WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, 'tblEvents'))
        )

def _get_broward_table_dispos(driver):
    """Get files table with automatic fallback"""
    try:
        return WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, 'tblDispositionsCV'))
        )
    except TimeoutException:
        # Click viewer and retry
        wait_and_click(driver, By.CLASS_NAME, 'bc-casedetail-viewer')
        time.sleep(2)
        return WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, 'tblDispositionsCV'))
        )



def _scan_broward_files(files_rows):
    """Scan table and return list of files to download (optimized)"""
    files_to_download = []
    #//*[@id="tblEvents"]/tbody/tr[1]/td[2]/b
    #//*[@id="tblEvents"]/tbody/tr[1]/td[3]
    #//*[@id="tblEvents"]/tbody/tr[1]/td[1]
    for i, row in enumerate(files_rows, start=1):
        try:
            # Get all cells at once (single query instead of 4)
            cells = row.find_elements(By.TAG_NAME, "td")

            if len(cells) < 3:
                continue

            # Extract data from cells (no additional XPath queries)
            date = cells[0].text.strip()
            desc_cell = cells[1]
            file_cell = row.find_element(By.ID,'docViewer')


            # Get description
            try:
                raw_desc = desc_cell.find_element(By.TAG_NAME, "b").text.strip()
            except NoSuchElementException:
                raw_desc = desc_cell.text.strip()

            # Filter by keywords
            if not _should_download_file(raw_desc):
                continue
            # Get button
            try:

                file_button = file_cell.find_element(By.TAG_NAME, 'button')
            except NoSuchElementException:
                print("NoSuchElementException")
                continue

            # Generate filename
            filename = sanitize_filename(f"{raw_desc}_{date}")

            files_to_download.append({
                'index': i,
                'filename': filename,
                'description': raw_desc,
                'date': date,
                'button': file_button
            })

        except Exception as e:
            continue

    return files_to_download


def _scan_broward_files_dispos(files_rows):
    """Scan table and return list of files to download (optimized)"""
    files_to_download = []
    #//*[@id="tblEvents"]/tbody/tr[1]/td[2]/b
    #//*[@id="tblEvents"]/tbody/tr[1]/td[3]
    #//*[@id="tblEvents"]/tbody/tr[1]/td[1]
    for i, row in enumerate(files_rows, start=1):
        try:
            # Get all cells at once (single query instead of 4)
            cells = row.find_elements(By.TAG_NAME, "td")

            if len(cells) < 3:
                continue

            # Extract data from cells (no additional XPath queries)
            date = cells[0].text.strip()
            desc_cell = cells[1]
            file_cell = row.find_element(By.ID,'docViewer')


            # Get description
            try:
                raw_desc = desc_cell.find_element(By.TAG_NAME, "b").text.strip()
            except NoSuchElementException:
                raw_desc = desc_cell.text.strip()
            print(f"desc_cell : {desc_cell}")

            # Filter by keywords
            if not _should_download_file(raw_desc):
                continue
            # Get button
            try:

                file_button = file_cell.find_element(By.TAG_NAME, 'button')
            except NoSuchElementException:
                print("NoSuchElementException")
                continue

            # Generate filename
            filename = sanitize_filename(f"{raw_desc}_{date}")

            files_to_download.append({
                'index': i,
                'filename': filename,
                'description': raw_desc,
                'date': date,
                'button': file_button
            })

        except Exception as e:
            continue

    return files_to_download

def _should_download_file(description):
    """Check if file matches download criteria"""
    desc_lower = description.lower()

    # Must have at least one keyword
    has_keyword = any(keyword.lower() in desc_lower for keyword in keyword_list)

    # Must not have unwanted keywords
    has_unwanted = any(unwanted.lower() in desc_lower for unwanted in unwanted_list)

    return has_keyword and not has_unwanted




