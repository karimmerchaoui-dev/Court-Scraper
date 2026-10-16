import re
import sys
import time
import traceback
from pathlib import Path

import pysnooper
from humancursor import WebCursor
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

from browser.browser_helpers import human_type_helper, request_url_with_timeout

HILLSBOROUGH_URL = "https://hover.hillsclerk.com/html/case/caseSearch.html"


def parse_hillsborough_case_number(case_str):
    """
    Extract (year_2digit, court_type, docket) from Hillsborough / Florida case formats:
      - '2024-CA-001234'        -> ('24', 'CA', '001234')
      - '24-CA-001234'          -> ('24', 'CA', '001234')
      - '24CA001234'            -> ('24', 'CA', '001234')
      - '2924CA001234A001HC'    -> ('24', 'CA', '001234')
    """
    case_str = str(case_str).strip()

    # Clean Florida UCN prefixes/suffixes (e.g., '29' county prefix, 'A001HC' suffix)
    if 'A001HC' in case_str:
        case_str = case_str.split('A001HC')[0]
    if len(case_str) > 10 and case_str.startswith("29"):
        case_str = case_str[2:]

    # 1. Hyphen-separated: '2024-CA-001234' or '24-CA-1234'
    if '-' in case_str:
        parts = case_str.split('-')
        if len(parts) >= 3:
            raw_year = parts[0].strip()
            year_2digit = raw_year[-2:] if len(raw_year) >= 2 else raw_year
            court_type = parts[1].strip().upper()
            docket = parts[2].strip()
            return year_2digit, court_type, docket

    # 2. Regex fallback: e.g. 2024CA001234 or 24CA001234
    match = re.search(r'(?:20)?(\d{2})\s*[-/]?\s*([A-Za-z]{2,3})\s*[-/]?\s*(\d+)', case_str)
    if match:
        year_2digit = match.group(1)
        court_type = match.group(2).upper()
        docket = match.group(3)
        return year_2digit, court_type, docket

    # 3. Last fallback
    year_m = re.search(r'\b(?:20)?(\d{2})\b', case_str)
    year_2digit = year_m.group(1) if year_m else ""
    type_m = re.search(r'([A-Za-z]{2,3})', case_str)
    court_type = type_m.group(1).upper() if type_m else "CA"
    digits = re.findall(r'\d+', case_str)
    docket = digits[-1] if digits else ""

    return year_2digit, court_type, docket


def navigate_to_url_hillsborough(driver, case_id=None):
    """
    Step 1: Open Hillsborough case search page.
    """
    return request_url_with_timeout(driver, HILLSBOROUGH_URL, timeout=30)


def navigate_to_search_hillsborough(driver):
    """
    Step 2: No extra navigation required as the search form is on the main landing page.
    """
    return 0


def search_case_number_hillsborough(driver, case_num):
    """
    Step 3: Enter docket number, select court type, enter 2-digit year, and click submit.
    
    1. Send docket number to:
       /html/body/main/div[2]/div[2]/div[2]/div[1]/div/form/div[2]/div[4]/input
    2. Select court type dropdown at:
       /html/body/main/div[2]/div[2]/div[2]/div[1]/div/form/div[2]/div[3]/select
    3. Enter 2-digit year to:
       /html/body/main/div[2]/div[2]/div[2]/div[1]/div/form/div[2]/div[2]/input
    4. Click submit button at:
       /html/body/main/div[2]/div[2]/div[2]/div[1]/div/form/div[2]/div[7]/button
    """
    docket_input_xpath = "/html/body/main/div[2]/div[2]/div[2]/div[1]/div/form/div[2]/div[4]/input"
    court_type_select_xpath = "/html/body/main/div[2]/div[2]/div[2]/div[1]/div/form/div[2]/div[3]/select"
    year_input_xpath = "/html/body/main/div[2]/div[2]/div[2]/div[1]/div/form/div[2]/div[2]/input"
    submit_btn_xpath = "/html/body/main/div[2]/div[2]/div[2]/div[1]/div/form/div[2]/div[7]/button"

    year_2digit, court_type, docket = parse_hillsborough_case_number(case_num)
    print(f"🔍 [Hillsborough] Parsed '{case_num}' -> Year: '{year_2digit}', Type: '{court_type}', Docket: '{docket}'")

    try:
        # 1. Send docket number
        docket_input = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, docket_input_xpath))
        )
        cursor = WebCursor(driver)
        cursor.show_cursor()
        cursor.click_on(docket_input)
        docket_input.clear()
        human_type_helper(docket_input,str(docket).strip())
        time.sleep(0.3)

        # 2. Select court type
        select_el = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, court_type_select_xpath))
        )
        cursor.click_on(select_el)
        dropdown = Select(select_el)
        selected = False
        # Try selecting by value first
        try:
            dropdown.select_by_value(court_type)
            selected = True
        except Exception:
            pass

        # Try matching visible text or options
        if not selected:
            for option in dropdown.options:
                opt_text = option.text.strip().upper()
                opt_val = option.get_attribute("value") or ""
                if opt_val.upper() == court_type or opt_text.startswith(court_type):
                    dropdown.select_by_visible_text(option.text)
                    selected = True
                    break

        if not selected:
            print(f"⚠️ [Hillsborough] Could not match court type '{court_type}' in select dropdown")

        time.sleep(0.3)

        # 3. Enter 2-digit year
        year_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, year_input_xpath))
        )
        cursor.click_on(year_input)
        year_input.clear()
        human_type_helper(year_input,year_2digit)
        time.sleep(0.3)

        # 4. Click Submit
        submit_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, submit_btn_xpath))
        )
        cursor.click_on(submit_btn)
        time.sleep(1)

        return 0

    except Exception as e:
        print(f"⚠️ [Hillsborough] Error in search_case_number_hillsborough: {e}")
        traceback.print_exc()
        return 1


enter_docket_number_hillsborough = search_case_number_hillsborough

@pysnooper.snoop()
def navigate_to_files_table_hillsborough(driver):
    """
    Step 4: Navigate to files / case details page.
    XPath: /html/body/main/div[2]/div[2]/div/div[2]/div/table/tbody/tr/td[2]/button
    """
    
    btn_xpath = "/html/body/main/div[2]/div[2]/div/div[2]/div/table/tbody/tr/td[2]/button"
    try:
        detail_btn = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, btn_xpath))
        )
        cursor = WebCursor(driver)
        cursor.show_cursor()
        cursor.click_on(detail_btn)
        time.sleep(1)
        return 0
    except TimeoutException:
        print("⚠️ [Hillsborough] Failed to find detail button in results table")
        return 1

from fake_useragent import UserAgent
from seleniumbase import Driver

ua = UserAgent()
random_user_agent = ua.random
driver = Driver(uc=True, agent=random_user_agent,uc_cdp=True)
navigate_to_url_hillsborough(driver)
search_case_number_hillsborough(driver,'26-CA-002876')
navigate_to_files_table_hillsborough(driver)
time.sleep(100)