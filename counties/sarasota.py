
import sys

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.path.append(r"C:\Users\pc\PycharmProjects\Court-Scraper\court_scraper_basic")

import re
import threading
import time

#from court_repo2.court_repo.test import final_update
from browser.browser_helpers import element_exists_xpath, request_url, set_download_dir


def get_thread_number():
    """Get clean thread number from thread name"""
    thread_name = threading.current_thread().name
    match = re.search(r'ThreadPoolExecutor-\d+_(\d+)', thread_name)
    return int(match.group(1)) + 1 if match else 0


    #driver, row, index, download_mgr, before_files

def trigger_download_sarasota(driver, row, row_index, download_mgr, before_files, matching_row=None):
    attempt = 0
    down_flag = None
    while attempt < 3 and not down_flag:
        try:
            set_download_dir(driver, download_mgr.download_dir)
            driver.switch_to.window(driver.window_handles[0])
            if not element_exists_xpath(row, "./td[6]/a"):
                return 2
            files_rows = row.find_element(By.XPATH, "./td[6]/a")
            files_rows.click()
            time.sleep(2)

            # Dismiss any alert that appeared after the click
            try:
                alert = driver.switch_to.alert
                alert.accept()
            except Exception:
                pass  # No alert present, continue normally

            down_flag = download_mgr.wait_for_download_start(before_files)
        except NoSuchElementException:
            print(f"no element in row {row_index}")
            return 1

def search_case_number_sarasota(driver,case_id):
    try:
        case_number_input = WebDriverWait(driver, 51).until(
            EC.presence_of_element_located((By.ID, 'ctl00_cphBody_tbCaseNumber'))
        )
        case_number_input.send_keys(case_id)
        #ctl00_cphBody_bSearch
        WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, 'ctl00_cphBody_bSearch'))
        ).click()
        #No records to display.

    except Exception:
        return 1


def navigate_to_search_sarasota(driver):
    #
    WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.ID, 'cphBody_bAgree'))
    ).click()

    driver.get("https://secure.sarasotaclerk.com/Search.aspx")




def navigate_to_url_sarasota(driver,case_id):
    request_url(driver, "https://secure.sarasotaclerk.com/AnonLanding.aspx")


def navigate_to_files_table_sarasota(driver):
    WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.XPATH, '//*[@id="ctl00_cphBody_rgCaseList_ctl00__0"]/td[1]/a'))
    ).click()


