import random
import threading
import time
import traceback

import pysnooper
from humancursor import WebCursor
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from urllib3.exceptions import MaxRetryError

from browser.browser_helpers import (
    element_exists_id,
    element_exists_xpath,
    get_thread_number,
    human_type,
    request_url,
    wait_for_page_to_load,
)
from browser.captcha import captcha_solver
from download.download_monitor import cancel_all_downloads, set_download_dir
from download.DownloadManager import DownloadManager
from download.files_management import generate_safe_filename
from download.scanners import scan_table_multithreaded
from network.network_helpers import reset_vpn


def trigger_download_pb(driver,row,row_index,download_mgr,before_files,matching_row=None):
    down_flag = None
    attempt = 0
    driver.switch_to.window(driver.window_handles[0])
    row = driver.find_element(By.XPATH, f'//*[@id="docketTable"]/tbody/tr[{row_index}]')
    cursor = WebCursor(driver)
    cursor.show_cursor()
    while attempt < 5 and not down_flag:
        if element_exists_xpath(driver,'//*[@id="caseinfo"]/div[3]/div'):
            return 3
        set_download_dir(driver, download_mgr.download_dir)
        driver.switch_to_window(driver.window_handles[0])
        icon = row.find_element(By.XPATH, './td[1]/button/img')
        if "lock" in icon.get_attribute('src'):
            return 1
        button = row.find_element(By.XPATH, './td[1]/button')

        cursor.move_to(button)
        cursor = WebCursor(driver)
        cursor.show_cursor()
        cursor.click_on(button,speed=random.uniform(0.4,1.3))
        driver.execute_script("arguments[0].click();", button)
        down_flag = download_mgr.wait_for_download_start(before_files)
        if driver.find_element(By.ID, 'downloadModal').get_attribute('tabindex') == '-1':
            try:
                driver.find_element(By.ID, 'rememberChoice').click()
            except:
                return
            driver.find_element(By.ID, 'downloadBtn').click()
        attempt+=1



def navigate_to_search_pb(driver):
    SEARCH_URL = 'https://appsgp.mypalmbeachclerk.com/eCaseView/search'
    MAINTENANCE_XPATH = '//*[@id="form1"]/div[5]/div/div[1]/span'
    GUEST_BTN_XPATH = '//*[@id="divLogin"]/div[1]/button'
    # Early exits
    if driver.title.strip() == "Search - eCaseView":
        return 0
    if element_exists_xpath(driver, MAINTENANCE_XPATH):
        el_text = WebDriverWait(driver, 1).until(
            EC.presence_of_element_located((By.XPATH, MAINTENANCE_XPATH))
        ).text
        if "eCaseView Unavailable for Maintenance" in el_text:
            return 2

    # Ensure page is loaded, retrying URL on timeout
    while True:
        try:
            wait_for_page_to_load(driver)
            break
        except TimeoutException:
            request_url(driver, SEARCH_URL)

    refresh_count = 0
    while True:
        try:
            if driver.title.strip() != "Homepage - eCaseView":
                refresh_count += 1
                if refresh_count >= 2:
                    print(f"⚠️ Title mismatch after {refresh_count} refreshes, resetting VPN...")
                    reset_vpn(wait=True)
                    refresh_count = 0
                if element_exists_xpath(driver,'//*[@id="main-message"]/div[2]'):
                    return 3
                request_url(driver, SEARCH_URL)
                continue

            refresh_count = 0
            cursor = WebCursor(driver)
            cursor.show_cursor()
            
            guest_button = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, GUEST_BTN_XPATH))
            )
            cursor.click_on(guest_button,speed=random.uniform(0.4,1.3))
            print(f"page with title '{driver.title}' went through")
            break

        except (TimeoutException, StaleElementReferenceException):
            request_url(driver, SEARCH_URL)


def navigate_to_files_pb(driver):
    try:
        
        try:
            first_case = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="searchResults"]/tbody/tr/td[1]/button'))
            )

            cursor = WebCursor(driver)
            cursor.show_cursor()
            cursor.click_on(first_case,speed=random.uniform(0.4,1.3))
        except TimeoutException:
            

            return 2
        except ElementClickInterceptedException:
            pass
        docket_button = WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.ID, 'liDocket')))

        wait_for_page_to_load(driver)
        while not (docket_button.get_attribute("aria-selected") == "true"):
            try:

                cursor.click_on(docket_button,speed=random.uniform(0.4,1.3))
                break
            except (StaleElementReferenceException, ElementNotInteractableException):
                pass
        wait_for_page_to_load(driver)
        select_page_size_pb(driver, "All")
        ActionChains(driver).send_keys(Keys.END).perform()
    except TimeoutException:
        return 1


def navigate_to_url_pb(driver,case_id):
    request_url(driver, "https://appsgp.mypalmbeachclerk.com/eCaseView/search")
#@auto_driver_snoop

def solve_pb_captcha(driver):
    max_retries = 5
    retry_count = 0
    start_time = time.time()
    res = None

    while retry_count < max_retries:
        if time.time() - start_time > 60:
            return 1
            
        try:
            # get the sitekeyRF
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, 'g-recaptcha-response')))
            sitekey = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="cphBody_pnlGoogle"]/div[1]/div'))).get_attribute(
                "data-sitekey")
            print(sitekey)

            # generate token
            res = captcha_solver(driver, sitekey, driver.current_url, timeout=15)
            if not res:
                retry_count += 1
                if time.time() - start_time > 60:
                    return 1
                if retry_count >= max_retries:
                    return 1
                request_url(driver, 'https://appsgp.mypalmbeachclerk.com/eCaseView/search')
                continue

            # Success - break out of retry loop
            break

        except (TimeoutException, TimeoutError):
            retry_count += 1
            if time.time() - start_time > 60:
                return 1
            if retry_count >= max_retries:
                return 1
            request_url(driver, 'https://appsgp.mypalmbeachclerk.com/eCaseView/search')
            
    if res:
        # inject token
        driver.execute_script("document.getElementById('g-recaptcha-response').innerHTML = " + f"'{res}'")

    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.ID, 'cphBody_cmdContinue'))
    ).click()
    return


@pysnooper.snoop()
def enter_docket_number_pb(driver, case_id):
    MAX_RETRIES = 5

    cursor = WebCursor(driver)
    cursor.show_cursor()

    for attempt in range(MAX_RETRIES):
        try:
            username_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "SearchRequest_CaseNumber"))
            )

            cursor.click_on(username_field,speed=random.uniform(0.4,1.3))
            human_type(username_field, case_id)
            break  # Success

        except (TimeoutException, MaxRetryError):
            if element_exists_xpath(driver, '//*[@id="mainContent"]/div/div[1]'):
                return 1
            if attempt == MAX_RETRIES - 1:
                raise  # Give up after the last attempt

            request_url(driver, "https://appsgp.mypalmbeachclerk.com/eCaseView/search")
    
    while element_exists_id(driver, "btnBeginSearch"):
        if element_exists_xpath(driver, '//*[@id="caseinfo"]/div'):
            return 3

        search_button = driver.find_element(By.ID, "btnBeginSearch")

        driver.execute_script("""
            document.getElementById('btnBeginSearch').dispatchEvent(new MouseEvent('click', {
                bubbles: true,
                cancelable: true,
                view: window
            }));
        """)

        cursor.click_on(search_button, number_of_clicks=random.randint(1, 2))
        time.sleep(2)
        print(f"element_exists_xpath(driver,'/html/body/div[1]/main/div[2]/div[2]/div/p[2]'): {element_exists_xpath(driver,'/html/body/div[1]/main/div[2]/div[2]/div/p[2]')}")
        print(f"\"No cases found\" in driver.find_element(By.XPATH,'/html/body/div[1]/main/div[2]/div[2]/div/p[2]').text: {driver.find_element(By.XPATH,'/html/body/div[1]/main/div[2]/div[2]/div/p[2]').text}")
        if element_exists_xpath(driver,'/html/body/div[1]/main/div[2]/div[2]/div/p[2]') and "No cases found" in driver.find_element(By.XPATH,'/html/body/div[1]/main/div[2]/div[2]/div/p[2]').text:
            return 2


def select_page_size_pb(driver, value_to_select, max_retries=4):
    select_xpath = '//*[@id="dt-length-0"]'

    for attempt in range(max_retries):
        try:
            select_el = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, select_xpath))
            )

            Select(select_el).select_by_visible_text(str(value_to_select))

            # Wait until the dropdown actually reflects the selected value
            WebDriverWait(driver, 5).until(
                lambda d: Select(
                    d.find_element(By.XPATH, select_xpath)
                ).first_selected_option.text.strip() == str(value_to_select)
            )

            print(f"Page size set to {value_to_select}.")
            return True

        except (TimeoutException, StaleElementReferenceException):
            print(f"Attempt {attempt + 1}/{max_retries} failed.")
            time.sleep(1)

    raise Exception(f"Failed to select page size '{value_to_select}' after {max_retries} attempts.")


def scrape_table_pb(driver,driver_pool,download_dir,case_id,report_cases,keyword_list, unwanted_list,status_back=None):
    driver.state = "downloading"
    print(download_dir)
    # Wait for table
    files_table = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.XPATH, '//*[@id="docketTable"]/tbody'))
    )
    files_rows = files_table.find_elements(By.TAG_NAME, "tr")

    matching_rows = []
    matching_rows_lock = threading.Lock()

    # Get all rows
    total_rows = len(files_rows) - 1
    files_table = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.ID, "cphBody_dDockets_gvDocket"))
    )
    matching_files = scan_table_multithreaded(driver,case_id, download_dir,report_cases, total_rows, matching_rows, matching_rows_lock,
                                             keyword_list, unwanted_list, "pb", 2)
    files_rows = files_table.find_elements(By.TAG_NAME, "tr")
    last_row = files_rows[total_rows]
    desc_text = last_row.find_element(By.CLASS_NAME, "datadetailtextnormal").text.strip()
    #check_first_files(case_id,desc_text)
    if matching_files:
        print(f"last file {matching_files[-1]} \n for case {case_id}")
    lower_files = [f["filename"].lower() for f in matching_files]

    main_window = driver.current_window_handle

    # Process only files found starting at start_index
    if any("order_vacating_book" in f for f in lower_files):
        report_cases[case_id]['Case status'] = "RIP"
    if any("motion_to_cancel" in f for f in lower_files):
        report_cases[case_id]['Case status'] = "On hold"
    if any("satisfaction_book" in f for f in lower_files):
        report_cases[case_id]['Case status'] = "On hold"
    for file in matching_files:
        print(f"ATTEMPTING {file}")
        try:
            row_index = file['row_index']
            description = file['description']

            row = files_table.find_element(By.XPATH, f'//*[@id="docketTable"]/tbody/tr[{row_index+1}]')
            if row.get_attribute('class') != "datarow" and row.get_attribute('class') != "dataalternate":
                continue
        except NoSuchElementException:
            print(f"index {row_index} not found")
            continue
        download_mgr = DownloadManager(driver, driver_pool, download_dir, case_id, "Palm Beach",status_callback=status_back)
        download_mgr.update_status("Downloading", details="Checking for files")
        while True:
            try:
                # Extract date (if exists)
                cancel_all_downloads(driver)

                if description:
                    desc_text = description
                else:
                    desc_text="desc_text"

                try:
                    date_text = row.find_element(By.CLASS_NAME, "datadetaildate").text.strip()
                except NoSuchElementException:
                    date_text = "datadetaildate"

                filename=generate_safe_filename(f'{desc_text}_{date_text}')

                # Extract description (if exists)

                before_files = download_mgr.get_existing_files()


                thread_num = get_thread_number()
                status_back(driver,case_id, "Palm Beach", f"Downloading (Thread {thread_num})",
                                   details=f"Downloaded file {row_index + 1}/{len(files_rows) - 1} : {filename}")
                set_download_dir(driver,download_dir)
                # Find clickable icon (id startswith…)
                driver.switch_to_window(main_window)
                icon = row.find_element(By.CSS_SELECTOR, "[id^='docketTable']")
                if "lock" in icon.get_attribute('src'):
                    break

                cursor = WebCursor(driver)
                cursor.show_cursor()
                cursor.click_on(icon,speed=random.uniform(0.4,1.3))  # click the icon
                new_file = download_mgr.wait_for_file_detection(before_files, driver=driver,timeout=300)

                if not new_file:
                    print(f"❌ No file detected for {filename}")
                    continue

                success = download_mgr.rename_file(filename, case_id,report_cases,new_file=new_file)


                report_cases[case_id]['files'].append(filename)
                # Wait for file to appear



                if success:
                    driver.switch_to_window(main_window)
                    break

            except NoSuchElementException:
                break
            except Exception as e:

                traceback.print_exc()

    driver.switch_to_window(main_window)
def show_parties_pb(driver):
    icon = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, 'liParty'))
    )
    cursor = WebCursor(driver)
    cursor.show_cursor()
    cursor.click_on(icon,speed=random.uniform(0.4,1.3))  # click the icon


def show_docket_pb(driver):
    icon = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, 'liDocket'))
    )
    cursor = WebCursor(driver)
    cursor.show_cursor()
    cursor.click_on(icon,speed=random.uniform(0.4,1.3))  # click the icon
