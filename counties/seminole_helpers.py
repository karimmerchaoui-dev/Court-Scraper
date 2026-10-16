import os
import sys
import time

import pysnooper
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from urllib3.exceptions import ReadTimeoutError

sys.path.append(r"C:\Users\pc\PycharmProjects\Court-Scraper")
from browser.browser_helpers import (
    element_exists_id,
    element_exists_xpath,
    human_type,
    request_url,
    wait_and_click,
)
from core.SearchResult import SearchResult
from download.download_monitor import open_downloads_tab, set_download_dir
from utils.formatting import format_seminole_case


def _cleanup_prefixed_files(files_dir, prefix):
    """Delete any file in files_dir whose name starts with prefix."""
    if not prefix or not os.path.isdir(files_dir):
        return
    for fname in os.listdir(files_dir):
        if fname.startswith(prefix):
            fpath = os.path.join(files_dir, fname)
            try:
                os.remove(fpath)
                print(f"🗑️ Deleted prefixed leftover: {fname}")
            except Exception as e:
                log_message(f"⚠️ Could not delete {fname}: {e}")



@pysnooper.snoop()
def trigger_download_seminole(driver,docket_eg,row_index,download_mgr,before_files,matching_row=None):
    href = matching_row['href']
    down_flag=None
    attempt = 0
    while attempt < 5 and not down_flag:
        _cleanup_prefixed_files(download_mgr.download_dir, "20")
        set_download_dir(driver, download_mgr.download_dir)
        
        if href:
            #create_new_tab(driver)
            driver.switch_to.window(driver.window_handles[0])
            set_download_dir(driver, download_mgr.download_dir)
            driver.click(f"/html/body/form/div[3]/div[2]/div/div/div/div/div/div/div[1]/div[4]/div[2]/div/div/div/div[2]/div[3]/table/tbody/tr[{row_index}]/td[6]/span[1]")
            print("CLICKEDDD")
            down_flag = download_mgr.wait_for_download_start(before_files)
            attempt = attempt+1
            try:
                if element_exists_xpath(driver, '//*[contains(@id, "CaptchaImage")]'):
                    return 3
            except ReadTimeoutError:
                continue
        else:
            return 1
        open_downloads_tab(driver)
    if attempt == 5 and not down_flag:
        return 3


def navigate_to_url_seminole(driver,case_id):
    request_url(driver,"https://courtrecords.seminoleclerk.org/civil/")

def navigate_to_files_table_seminole(driver):
    # Optional wait
    if "unexpected error" in driver.page_source.lower():
        return 3
    if element_exists_xpath(driver, '//*[contains(@id, "CaptchaImage")]'):
        return 3
    href = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, 'CaseNum'))).get_attribute('href')
    driver.get(href)
    driver.click("#dock_pan")

def navigate_to_search_seminole(driver, case_id):
    pass

@pysnooper.snoop()
def search_case_number_seminole(driver,docket):
    try:
        # Type the case number
        formatted_docket = format_seminole_case(docket)

        case_input = WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.ID, 'caseNumberTxt')))
        human_type(case_input, formatted_docket)
        # Click submit
        time.sleep(1)
        driver.click("#search")
        if element_exists_id(driver,"CaseGrid"):
            not_found = driver.find_element(By.XPATH, '//*[@id="CaseGrid"]/tbody/tr/td').text
            empty_request = driver.find_element(By.ID, 'MainContent_valSummary').text
            if "no records found" in not_found.lower() or "Empty Request" in empty_request:
                return 2
        return SearchResult.SUCCESS
    except TimeoutException:
        if element_exists_id(driver, 'MainContent_botME'):
            return 3

        return 1


def show_parties_seminole(driver):
    wait_and_click(driver, By.ID, 'party_pan')


