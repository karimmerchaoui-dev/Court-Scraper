"""
Pinellas county — process_pin_case and download_files_pin.
"""

import os
import sys
import threading
import time
import traceback
from pathlib import Path

import pysnooper
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

from app import update_case_status

parent_dir = Path(__file__).resolve().parent
sys.path.append(str(parent_dir))

from browser.browser_helpers import (
    element_exists_id,
    request_url,
    set_download_dir,
    wait_and_click,
    wait_for_page_to_load,
)
from browser.captcha import captcha_solver
from config_ import DEFAULT_KEYWORDS, DEFAULT_UNWANTED
from download.scanners import scan_table_multithreaded


def download_files_pin(driver, case_id, files_dir="."):
    import main

    matching_rows_lock = threading.Lock()
    table_length = 0
    while table_length == 0:
        files_table = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="eventList"]/tbody')))
        files_rows = files_table.find_elements(By.TAG_NAME, "tr")
        table_length = len(files_rows)
    wait = WebDriverWait(driver, 10)
    original_window = driver.current_window_handle
    time.sleep(5)
    if table_length <= 0:
        return
    matching_rows = []
    matching_rows = scan_table_multithreaded(
        driver=driver, case_id=case_id, files_dir=files_dir, report_cases=main.report_cases,
        total_rows=table_length, matching_rows=matching_rows, matching_rows_lock=matching_rows_lock,
        keyword_list=main.keyword_list, unwanted_list=main.unwanted_list, county="pin", start_index=1)
    for row in list(matching_rows):
        try:
            i = row["row_index"]
            link_xpath = f'//*[@id="eventList"]/tbody/tr[{i}]/td[12]/a'
            filename = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, f'//*[@id="eventList"]/tbody/tr[{i}]/td[2]/a'))).text
            update_case_status(driver, case_id, "New Jersey", "Downloading",
                               details=f"Downloaded file {i + 1}/{table_length}: {filename} ({case_id})")
            if (not any(w.lower() in filename.lower() for w in DEFAULT_KEYWORDS) or
                    any(b.lower() in filename.lower() for b in DEFAULT_UNWANTED)):
                continue
            wait_and_click(driver, By.XPATH, link_xpath)
            wait.until(lambda d: len(d.window_handles) > 1)
            new_tab = [h for h in driver.window_handles if h != original_window][0]
            driver.switch_to.window(new_tab)
            try:
                import glob
                before_files = set(glob.glob(os.path.join(files_dir, "*.pdf")))
                wait_for_page_to_load(driver)
                while not element_exists_id(driver, 'thumbnail'):
                    time.sleep(0.5)
                time.sleep(1)
                set_download_dir(driver, files_dir)
                download_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, '//*[@id="doc-viewer-id"]/div/div[12]/div[1]/div/div/span[1]/div[6]/div[1]')))
                driver.execute_script("arguments[0].click();", download_button)
                wait_and_click(driver, By.XPATH, link_xpath)
                time.sleep(1)
                wait_for_new_download_and_rename_nj(driver, files_dir, before_files,
                                                    filename, case_id, county="New Jersey")
            except Exception as e:
                print(f"Button not clickable in new tab for row {i}: {e}")
            driver.switch_to.window(driver.window_handles[-1])
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
            time.sleep(1)
        except Exception:
            traceback.print_exc()
            continue


PINELLAS_URL = "https://courtrecords.mypinellasclerk.gov"
PINELLAS_SITEKEY = "6LcCmw0oAAAAAD-KMLDuq6YmUBN5VD4l-5vvSM2Z"


def navigate_to_url_pin(driver, case_id=None):
    """
    Step 1: Navigate to the Pinellas court records portal.
    """
    request_url(driver, PINELLAS_URL)
    wait_for_page_to_load(driver)
    return 0


def navigate_to_search_pin(driver):
    """
    Step 2: Navigate to search tab.
    XPath: /html/body/div[2]/section/main/div[2]/div[1]/div/div[2]/form/div/div[6]/div[1]/div/div/ul/li[2]/a
    """
    tab_xpath = "/html/body/div[2]/section/main/div[2]/div[1]/div/div[2]/form/div/div[6]/div[1]/div/div/ul/li[2]/a"
    try:
        tab_btn = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, tab_xpath))
        )
        driver.execute_script("arguments[0].click();", tab_btn)
        time.sleep(0.5)
        return 0
    except TimeoutException:
        print("⚠️ [Pinellas] Failed to locate search tab li[2]")
        return 1


@pysnooper.snoop()
def search_case_number_pin(driver, case_num):
    """
    Step 3: Enter case number, solve captcha, and submit search.
    
    1. Send keys to:
       /html/body/div[2]/section/main/div[2]/div[1]/div/div[2]/form/div/div[6]/div[2]/div/div[2]/div[1]/div/input
    2. Solve captcha with sitekey '6LcCmw0oAAAAAD-KMLDuq6YmUBN5VD4l-5vvSM2Z' and driver.current_url
    3. Click submit at:
       /html/body/div[2]/section/main/div[2]/div[1]/div/div[2]/form/div/div[6]/div[4]/div[1]/button[1]
    """
    input_xpath = "/html/body/div[2]/section/main/div[2]/div[1]/div/div[2]/form/div/div[6]/div[2]/div/div[2]/div[1]/div/input"
    submit_xpath = "/html/body/div[2]/section/main/div[2]/div[1]/div/div[2]/form/div/div[6]/div[4]/div[1]/button[1]"

    try:
        case_input = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, input_xpath))
        )
        case_input.clear()
        case_input.send_keys(str(case_num).strip())
        time.sleep(0.5)

        print(f"🤖 [Pinellas] Solving reCAPTCHA for case {case_num}...")
        res = captcha_solver(driver, PINELLAS_SITEKEY, driver.current_url, timeout=20)
        if not res:
            print("⚠️ [Pinellas] Captcha solver failed to return token")
            return 1

        print(f"✅ [Pinellas] Captcha solved: {str(res)[:25]}...")

        # Inject token into reCAPTCHA response fields
        driver.execute_script("""
            var el = document.getElementById('g-recaptcha-response');
            if (el) { el.innerHTML = arguments[0]; el.value = arguments[0]; }
            var els = document.querySelectorAll('[name="g-recaptcha-response"]');
            els.forEach(function(e) { e.innerHTML = arguments[0]; e.value = arguments[0]; });
        """, res)

        time.sleep(0.5)
        driver.execute_script("""
window.__mutationLogs = [];

window.__mutationObserver = new MutationObserver((mutations) => {
    for (const m of mutations) {

        if (m.type === "attributes") {
            window.__mutationLogs.push({
                timestamp: new Date().toISOString(),
                type: "ATTRIBUTE_CHANGED",
                attribute: m.attributeName,
                oldValue: m.oldValue,
                newValue: m.target.getAttribute(m.attributeName),
                element: m.target.outerHTML
            });
        }

        else if (m.type === "childList") {
            for (const node of m.addedNodes) {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    window.__mutationLogs.push({
                        timestamp: new Date().toISOString(),
                        type: "ADDED",
                        target: m.target.outerHTML,
                        node: node.outerHTML
                    });
                }
            }

            for (const node of m.removedNodes) {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    window.__mutationLogs.push({
                        timestamp: new Date().toISOString(),
                        type: "REMOVED",
                        target: m.target.outerHTML,
                        node: node.outerHTML
                    });
                }
            }
        }

        else if (m.type === "characterData") {
            window.__mutationLogs.push({
                timestamp: new Date().toISOString(),
                type: "TEXT_CHANGED",
                oldValue: m.oldValue,
                newValue: m.target.textContent
            });
        }
    }
});

window.__mutationObserver.observe(document.documentElement, {
    subtree: true,
    childList: true,
    attributes: true,
    characterData: true,
    attributeOldValue: true,
    characterDataOldValue: true
});
""")
        # Click submit button
        submit_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, submit_xpath))
        )
        driver.execute_script("arguments[0].click();", submit_btn)
        time.sleep(1)
        return 0

    except Exception as e:
        print(f"⚠️ [Pinellas] Error in search_case_number_pin: {e}")
        traceback.print_exc()
        return 1


enter_docket_number_pin = search_case_number_pin


def navigate_to_files_table_pin(driver):
    """
    Step 4: Navigate to case details / files page.
    XPath: /html/body/div[2]/section/main/div[1]/div/div[2]/div/div/div[2]/table/tbody/tr/td[2]/a
    """
    case_link_xpath = "/html/body/div[2]/section/main/div[1]/div/div[2]/div/div/div[2]/table/tbody/tr/td[2]/a"
    try:
        case_link = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, case_link_xpath))
        )
        driver.execute_script("arguments[0].click();", case_link)
        time.sleep(1)
        return 0
    except TimeoutException:
        print("⚠️ [Pinellas] Failed to find case link in results table")
        return 1



from seleniumbase import Driver

driver = Driver(uc=True)
navigate_to_url_pin(driver)
navigate_to_search_pin(driver)
search_case_number_pin(driver, case_num="26-000101-CO")
time.sleep(200)