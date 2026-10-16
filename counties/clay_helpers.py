import os
import sys
import time
from pathlib import Path

import pysnooper
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.path.append(str(Path(__file__).parent.parent))
from browser.browser_helpers import request_url, set_download_dir

try:
    from app import log_message
except Exception:
    def log_message(msg):
        print(msg)


CLAY_SEARCH_URL = "https://inquiry.clayclerk.com/Home.aspx/Search"
CLAY_EMAIL_XPATH = "/html/body/div[3]/table/tbody/tr/td[1]/div/table/tbody/tr/td[1]/div/table/tbody/tr[2]/td/div[1]/div[4]/div/div[1]/input"
CLAY_PASSWORD_XPATH = "/html/body/div[3]/table/tbody/tr/td[1]/div/table/tbody/tr/td[1]/div/table/tbody/tr[2]/td/div[1]/div[4]/div/div[3]/input"
CLAY_SEARCH_LABEL_XPATH = "/html/body/div[3]/table/tbody/tr/td[1]/div/table/tbody/tr/td[1]/div/table/tbody/tr[2]/td/div[1]/div[4]/a"
CLAY_DOCKET_INPUT_XPATH = "/html/body/div[3]/table/tbody/tr/td[2]/div/table/tbody/tr/td/table/tbody/tr[2]/td[2]/div/div[2]/div[1]/div/div[3]/label"
CLAY_SEARCH_BUTTON_XPATH = "/html/body/div[3]/table/tbody/tr/td[2]/div/table/tbody/tr/td/table/tbody/tr[2]/td[2]/div/div[2]/div[4]/form/button"
CLAY_DOCKET_INPUT_XPATH_2 = "/html/body/div[3]/table/tbody/tr/td[2]/div/table/tbody/tr/td/table/tbody/tr[2]/td[2]/div/div[2]/div[1]/div/div[3]/input[2]"

def navigate_to_url_clay(driver, case_id=None):
    """
    Step 1: Navigate to the Clay county Benchmark search portal.
    """
    log_message(f"🌐 [Clay] Navigating to {CLAY_SEARCH_URL}...")
    request_url(driver, CLAY_SEARCH_URL)
    log_message("✅ [Clay] navigate_to_url_clay complete")
    return 0


@pysnooper.snoop()
def navigate_to_search_clay(driver, username=None, password=None):
    """
    Step 2: Login to Clay county portal and select the search mode.
    """
    email = username or os.getenv("CLAY_CLERK_USER", "")
    pwd = password or os.getenv("CLAY_CLERK_PASS", "")

    log_message("🔑 [Clay] Entering login credentials...")

    # Wait for email input and enter email
    email_elem = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.XPATH, CLAY_EMAIL_XPATH))
    )
    email_elem.clear()
    email_elem.send_keys(email)

    # Wait for password input and enter password
    pwd_elem = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.XPATH, CLAY_PASSWORD_XPATH))
    )
    pwd_elem.clear()
    pwd_elem.send_keys(pwd)


    # Click on the search label
    log_message("🔍 [Clay] Clicking search label...")
    try:
        label_elem = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, CLAY_SEARCH_LABEL_XPATH))
        )
        label_elem.click()
    except (ElementClickInterceptedException, TimeoutException):
        label_elem = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, CLAY_SEARCH_LABEL_XPATH))
        )
        driver.execute_script("arguments[0].click();", label_elem)

    time.sleep(5)
    log_message("✅ [Clay] navigate_to_search_clay complete")
    return 0


@pysnooper.snoop()
def search_case_number_clay(driver, case_id):
    """
    Step 3: Enter docket number and submit case search.
    """
    docket_number = str(case_id).strip()
    log_message(f"🔍 [Clay] Searching docket number: '{docket_number}'...")

    # Enter docket number into the input field
    docket_input = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.XPATH, CLAY_DOCKET_INPUT_XPATH))
    )
    docket_input.click()
    docket_input2 = driver.find_element(By.XPATH, CLAY_DOCKET_INPUT_XPATH_2)
    docket_input2.send_keys(docket_number)

    time.sleep(0.5)

    # Click on search button
    try:
        search_btn = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, CLAY_SEARCH_BUTTON_XPATH))
        )
        search_btn.click()
    except (ElementClickInterceptedException, TimeoutException):
        search_btn = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, CLAY_SEARCH_BUTTON_XPATH))
        )
        driver.execute_script("arguments[0].click();", search_btn)

    time.sleep(1)
    log_message(f"✅ [Clay] Search submitted for {docket_number}")
    return 0


def navigate_to_files_table_clay(driver):
    """
    Step 4: No navigation needed for files in Clay county.
    """
    return 0

@pysnooper.snoop()
def trigger_download_clay(driver,row,row_index,download_mgr,before_files,matching_row=None):
    down_flag = None
    attempt = 0
    #//*[@id="c_DocketsPanel"]/div/table/tbody[{row_index}]/tr/td[6]/div
    #//*[@id="cphBody_dDockets_gvDocket"]/tbody/tr[6]
    #//*[@id="cphBody_dDockets_gvDocket"]/tbody/tr[84]
    #//*[@id="cphBody_dDockets_gvDocket"]/tbody/tr[6]/td[1]
    while attempt < 3 and not down_flag:
        driver.switch_to_window(driver.window_handles[0])
        try:
            file_button = row.find_element(By.XPATH, f'/html/body/div[3]/table/tbody/tr/td[2]/div/table/tbody/tr/td/table[2]/tbody/tr[1]/td[2]/div[2]/div[2]/div/div[5]/div/div/div[2]/div/div/div/table/tbody/tr[{row_index}]/td[2]/a')
        except NoSuchElementException:
            return 2
        file_button.click()
        driver.switch_to_window(driver.window_handles[-1])
        set_download_dir(driver, download_mgr.download_dir)
        print(f"download_mgr.download_dir : {download_mgr.download_dir}")

        driver.switch_to_window(driver.window_handles[0])
        down_flag = download_mgr.wait_for_download_start(before_files)
        attempt+=1