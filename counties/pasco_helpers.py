import os
import re
import sys
import time
import traceback

import pysnooper
from humancursor import WebCursor
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.path.append(os.path.abspath("c:\\Users\\pc\\PycharmProjects\\Court-Scraper\\court_scraper_basic"))

# Add the court_scraper_basic package to sys.path
from browser.browser_helpers import (
    request_url,
    request_url_with_timeout,
    set_download_dir,
    switch_to_window_by_url_prefix,
)

PASCO_SEARCH_URL = "https://www.civitekflorida.com/ocrs/county/51/disclaimer.xhtml"
PASCO_TURNSTILE_SITEKEY = "0x4AAAAAAAR0Af-5MfzdbO3p"


def parse_pasco_case_number(case_str):
    """
    Extract (year, court_type, docket) from various Florida case formats:
      - '2023-CA-001234' -> ('2023', 'CA', '001234')
      - '23-CA-1234'     -> ('2023', 'CA', '1234')
      - '2023 CA 001234' -> ('2023', 'CA', '001234')
      - 'CA-2023-001234' -> ('2023', 'CA', '001234')
    """
    case_str = str(case_str).strip()

    # 1. Year: 4 digits (e.g. 2023) or 2 digits
    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', case_str)
    if year_match:
        year = year_match.group(1)
    else:
        # Fallback to 2-digit year at start or separated
        m2 = re.search(r'\b(\d{2})\b', case_str)
        year = f"20{m2.group(1)}" if m2 else ""

    # 2. Court Type: 2-3 letters (e.g. CA, CC, CO, CP, CF, SC, DR)
    type_match = re.search(r'([A-Za-z]{2,3})', case_str)
    court_type = type_match.group(1).upper() if type_match else ""

    # 3. Docket: remaining sequence of digits
    # Remove the year digits from candidate digits
    digits = re.findall(r'\d+', case_str)
    docket = None
    for d in digits:
        if d != year and (not year.endswith(d) or len(d) > 2):
            docket = d
            break
    if not docket and digits:
        docket = digits[-1]

    return year, court_type, docket or ""


def navigate_to_url_pasco(driver, case_id=None):
    """
    Step 1: Navigate to the Pasco (Civitek) search URL.
    """
    return request_url_with_timeout(driver, PASCO_SEARCH_URL, timeout=30)

@pysnooper.snoop()
def navigate_to_search_pasco(driver):
    """
    Step 2: Click on the case number search tab.
    XPath: //*[@id="form:search_tab"]/ul/li[2]
    """
    try:
        #
        cursor = WebCursor(driver)
        cursor.show_cursor()

        agree = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, '/html/body/div[1]/div[1]/form/button'))
        )
        cursor.click_on(agree)
        tab_element = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, '//*[@id="form:search_tab"]/ul/li[2]'))
        )
        cursor.click_on(tab_element)
        time.sleep(1)
        return 0
    except TimeoutException:
        print("⚠️ [Pasco] Failed to locate search tab li[2]")
        return 1



@pysnooper.snoop()
def enter_docket_number_pasco(driver, case_id):
    """
    Step 3: Enter docket number, select case type, solve turnstile, and submit.
    
    1. Enter year at:
       /html/body/div[1]/div[1]/form[2]/div[1]/div/div[2]/span/div/div/div/div[1]/input
    2. Click dropdown label to open case type menu:
       /html/body/div[1]/div[1]/form[2]/div[1]/div/div[2]/span/div/div/div/div[2]/div[1]/label
    3. Select matching <li> inside /html/body/div[4]/div/ul based on (type) abbreviation
    4. Enter docket number at:
       /html/body/div[1]/div[1]/form[2]/div[1]/div/div[2]/span/div/div/div/div[3]/input
    5. Solve Turnstile (sitekey: 0x4AAAAAAAR0Af-5MfzdbO3p) and inject into:
       /html/body/div[1]/div[1]/form[2]/div[3]/div/div/input
    6. Click submit button:
       /html/body/div[1]/div[1]/form[2]/div[4]/button[1]/span
    """
    cursor = WebCursor(driver)
    cursor.show_cursor()
    year, court_type, docket = parse_pasco_case_number(case_id)
    print(f"🔍 [Pasco] Parsed case '{case_id}' -> Year: '{year}', Type: '{court_type}', Docket: '{docket}'")

    try:
        # --- 1. Enter Year ---
        year_input_xpath = "/html/body/div[1]/div[1]/form[2]/div[1]/div/div[2]/span/div/div/div/div[1]/input"
        year_input = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, year_input_xpath))
        )
        cursor.click_on(year_input)
        year_input.clear()

        year_input.send_keys(year)

        # --- 2. Open Case Type Dropdown ---
        case_type_label_xpath = "/html/body/div[1]/div[1]/form[2]/div[1]/div/div[2]/span/div/div/div/div[2]/div[1]/label"
        case_type_label = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, case_type_label_xpath))
        )
        cursor.click_on(case_type_label)
        time.sleep(0.5)

        # --- 3. Select Case Type Option ---
        # Look for li elements in /html/body/div[4]/div/ul (or PrimeFaces dropdown panel)
        options_xpath = "/html/body/div[4]/div/ul/li"
        try:
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, options_xpath)))
            options = driver.find_elements(By.XPATH, options_xpath)
        except TimeoutException:
            # Fallback for dynamic PrimeFaces panel id
            options = driver.find_elements(By.XPATH, "//div[contains(@class, 'ui-selectonemenu-panel')]//ul/li")

        target_str = f"({court_type.upper()})"
        matched_option = None
        for opt in options:
            opt_text = opt.text.strip().upper()
            if target_str in opt_text:
                matched_option = opt
                break

        if matched_option:
            driver.execute_script("arguments[0].click();", matched_option)
        else:
            print(f"⚠️ [Pasco] Case type '{court_type}' not found in dropdown options. Available: {[o.text for o in options[:5]]}")

        time.sleep(0.5)

        # --- 5. Solve Turnstile Captcha ---
        print("🤖 [Pasco] Solving Cloudflare Turnstile...")
        #
        cloudflare_div = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "gvvP2"))
        )
        cursor.click_on(cloudflare_div)
        time.sleep(0.5)

        # --- 4. Enter Docket Number ---
        docket_input_xpath = "/html/body/div[1]/div[1]/form[2]/div[1]/div/div[2]/span/div/div/div/div[3]/input"
        docket_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, docket_input_xpath))
        )
        cursor.click_on(docket_input)

        docket_input.clear()
        docket_input.send_keys(docket)


        
        

        



        # --- 6. Click Submit ---
        submit_btn_xpath = "/html/body/div[1]/div[1]/form[2]/div[4]/button[1]"
        submit_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, submit_btn_xpath))
        )
        cursor.click_on(submit_btn)



        return 0

    except Exception as e:
        print(f"⚠️ [Pasco] Error in enter_docket_number_pasco: {e}")
        traceback.print_exc()
        return 1

search_case_number_pasco = enter_docket_number_pasco

def trigger_download_pasco(driver,docket_eg,row_index,download_mgr,before_files,matching_row=None):
    print(f"docket_eg_button : {docket_eg_button.get_attribute('onclick')}")
    attempt=0
    while attempt<5:
        set_download_dir(driver,download_mgr.download_dir)
        switch_to_window_by_url_prefix(driver, "https://ccms.clerk.org/caseCM")
        driver.execute_script("arguments[0].scrollIntoView();", docket_eg_button)
        down_flag=None
        while not down_flag:
            set_download_dir(driver,download_mgr.download_dir)
            if doc_url:
                create_new_tab(driver)
                request_url(driver,doc_url)
                down_flag = download_mgr.wait_for_download_start(before_files)
            else:
                return 1
        switch_to_window_by_url_prefix(driver,"https://ccms.clerk.org/viewDocument.aspx")
        driver.close()
        return
    switch_to_window_by_url_prefix(driver, "https://ccms.clerk.org/viewDocument.aspx")





#/html/body/div[1]/div[1]/form[2]/div[6]/div[2]/div/div[2]/table/tbody/tr[2]/td[1]/a
#/html/body/div[1]/div[1]/form[2]/div[6]/div[2]/div/div[2]/table/tbody/tr[4]/td[1]/a