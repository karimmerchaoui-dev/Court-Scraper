import os
import sys
import time

import pysnooper

# Ensure project root is in sys.path for standalone script execution
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_current_dir, ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
_basic_root = os.path.join(_project_root, "court_scraper_basic")
if os.path.exists(_basic_root) and _basic_root not in sys.path:
    sys.path.insert(0, _basic_root)

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from browser.browser_helpers import request_url
from browser.captcha import hcaptcha_solver

try:
    from app import log_message
except Exception:
    def log_message(msg):
        print(msg)


STJOHNS_SEARCH_URL = "https://apps.stjohnsclerk.com/Benchmark/Home.aspx/Search"
STJOHNS_SEARCH_TAB_XPATH = "/html/body/div[3]/table/tbody/tr/td[2]/div/table/tbody/tr/td/table/tbody/tr[2]/td[2]/div/div[2]/div[1]/div/div[2]"
STJOHNS_DOCKET_INPUT_XPATH = "/html/body/div[3]/table/tbody/tr/td[2]/div/table/tbody/tr/td/table/tbody/tr[2]/td[2]/div/div[2]/div[1]/div/div[2]/input[2]"
STJOHNS_SEARCH_BUTTON_XPATH = "/html/body/div[3]/table/tbody/tr/td[2]/div/table/tbody/tr/td/table/tbody/tr[2]/td[2]/div/div[2]/div[4]/form/button"
STJOHNS_HCAPTCHA_SITEKEY = "53a34568-fd9e-4e09-b1ae-39f2df80c319"


def navigate_to_url_stjohns(driver, case_id=None):
    """
    Step 1: Navigate to the St. Johns County Benchmark search portal.
    """
    log_message(f"🌐 [St. Johns] Navigating to {STJOHNS_SEARCH_URL}...")
    request_url(driver, STJOHNS_SEARCH_URL)
    log_message("✅ [St. Johns] navigate_to_url_stjohns complete")
    return 0


@pysnooper.snoop()
def navigate_to_search_stjohns(driver, username=None, password=None):
    """
    Step 2: Navigate to the search tab in St. Johns county portal.
    """
    log_message("🔍 [St. Johns] Clicking search tab...")
    try:
        tab_elem = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.XPATH, STJOHNS_SEARCH_TAB_XPATH))
        )
        tab_elem.click()
    except (ElementClickInterceptedException, TimeoutException):
        tab_elem = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, STJOHNS_SEARCH_TAB_XPATH))
        )
        driver.execute_script("arguments[0].click();", tab_elem)

    time.sleep(3)
    log_message("✅ [St. Johns] navigate_to_search_stjohns complete")
    return 0


def _inject_hcaptcha_response(driver, token):
    """
    Injects the solved hCaptcha token into [name='g-recaptcha-response'],
    [name='h-captcha-response'], and sets the 'data-hcaptcha-response' attribute.
    """
    script = """
    var token = arguments[0];
    
    // Set value and innerHTML on g-recaptcha-response element(s)
    var gElems = document.getElementsByName('g-recaptcha-response');
    for (var i = 0; i < gElems.length; i++) {
        gElems[i].innerHTML = token;
        gElems[i].value = token;
    }
    
    // Set value on h-captcha-response element(s)
    var hElems = document.getElementsByName('h-captcha-response');
    for (var j = 0; j < hElems.length; j++) {
        hElems[j].innerHTML = token;
        hElems[j].value = token;
    }
    
    // Set data-hcaptcha-response attribute on relevant elements and body
    var targets = document.querySelectorAll('[data-hcaptcha-response], iframe[src*="hcaptcha"], div[class*="h-captcha"], [data-sitekey]');
    for (var k = 0; k < targets.length; k++) {
        targets[k].setAttribute('data-hcaptcha-response', token);
    }
    document.body.setAttribute('data-hcaptcha-response', token);
    """
    driver.execute_script(script, token)


@pysnooper.snoop()
def search_case_number_stjohns(driver, case_id):
    """
    Step 3: Enter docket number, solve hCaptcha via 2captcha, inject token, and submit search.
    """
    docket_number = str(case_id).strip()
    log_message(f"🔍 [St. Johns] Searching docket number: '{docket_number}'...")

    # Enter docket number into the input field
    docket_input = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.XPATH, STJOHNS_DOCKET_INPUT_XPATH))
    )
    docket_input.clear()
    docket_input.send_keys(docket_number)
    time.sleep(0.5)

    # Solve hCaptcha using 2captcha
    current_url = driver.current_url or STJOHNS_SEARCH_URL
    log_message(f"🤖 [St. Johns] Solving hCaptcha with sitekey: {STJOHNS_HCAPTCHA_SITEKEY}...")
    token = hcaptcha_solver(driver, STJOHNS_HCAPTCHA_SITEKEY, current_url)

    if not token:
        log_message("⚠️ [St. Johns] Failed to solve hCaptcha (returned empty token) — triggering retry")
        return 1

    log_message("✅ [St. Johns] hCaptcha solved. Injecting response token...")
    _inject_hcaptcha_response(driver, token)
    time.sleep(0.5)

    # Click on search button
    log_message("🔍 [St. Johns] Submitting search...")
    try:
        search_btn = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, STJOHNS_SEARCH_BUTTON_XPATH))
        )
        search_btn.click()
    except (ElementClickInterceptedException, TimeoutException):
        search_btn = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, STJOHNS_SEARCH_BUTTON_XPATH))
        )
        driver.execute_script("arguments[0].click();", search_btn)

    time.sleep(1)
    log_message(f"✅ [St. Johns] Search submitted for {docket_number}")
    return 0


def navigate_to_files_table_stjohns(driver):
    """
    Step 4: No navigation needed for files in St. Johns county.
    """
    return 0


if __name__ == "__main__":
    print(sys.path)
    from seleniumbase import Driver

    driver = Driver(uc=True)

    navigate_to_url_stjohns(driver)
    navigate_to_search_stjohns(driver)
    search_case_number_stjohns(driver, "CA25-0351")
    time.sleep(100)
