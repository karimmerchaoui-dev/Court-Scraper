import os
import random
import time
import traceback

import pysnooper
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from browser.browser_helpers import (
    element_exists_id,
    find_element_by_text,
    set_download_dir,
)
from browser.OP import extract_info_from_salesweb
from config_ import SKIP_DEFENDANT_KEYWORDS, accounts
from utils.formatting import safe_int
from utils.map_helpers import autocomplete_address
from utils.zillow_helpers import get_zillow_infos

MAX_DEFENDANTS = 10

# ─────────────────────────────────────────────────────────────────────────
# Precheck cache — lets the eligibility check (SalesWeb + Zillow) done in
# case_executor._check_eligibility() be reused later in
# extract_property_details(), instead of re-querying SalesWeb/Zillow for the
# same case a second time during full processing.
# Not stored on report_cases[case_id] on purpose: report_cases rows get
# written straight to Excel, and this is a raw dict, not a cell value.
# ─────────────────────────────────────────────────────────────────────────
_precheck_cache = {}


def set_precheck_data(case_id, precheck_data):
    """Called by case_executor after a case passes eligibility, to stash the
    SalesWeb/Zillow data already fetched so it isn't fetched again."""
    if precheck_data:
        _precheck_cache[case_id] = precheck_data


def pop_precheck_data(case_id):
    """Retrieve and clear cached precheck data for a case (single-use)."""
    return _precheck_cache.pop(case_id, None)

def get_valid_defendants(driver):
    valid_defendants = []
    table_xpath = '//*[@id="c_PartiesPanel"]/div/table'
    table = driver.find_element(By.XPATH, table_xpath)
    rows = table.find_elements(By.XPATH, ".//tr")
    for i, row in enumerate(rows):
        if i == 0:
            continue
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) < 3:
            continue
        name = cells[0].text.strip()
        party_type = cells[1].text.strip()
        address = cells[2].text.strip()

        name_low = name.lower()
        party_low = party_type.lower()

        if "defendant" not in party_low:
            continue

        banned = ["llc", "unknown", "inc", "united", "county", "housing", "state", "florida", "city",
                  "clerk", "court", "bank", "association", "national", "business", "admin", "corporation",
                  "department", "serivce", "the ", "finance", "secretary"]
        if any(b in name_low for b in banned):
            continue

        valid_defendants.append(name)
    return valid_defendants


def check_main_frame(driver, driver_pool):
    main_iframe = driver.find_element(By.ID, "main-iframe") if element_exists_id(driver, "main-iframe") else None
    if main_iframe and "unsuccessful" in main_iframe.text.lower():
        driver.state = "captcha"
        if driver_pool:
            driver_pool.reset_vpn_pool(driver)
        time.sleep(2)
        return 1


def _get_shuffled_main_accounts():
    main_accounts = [acc for acc in accounts if acc["type"] == "main"]
    return random.sample(main_accounts, k=len(main_accounts))


def get_defendants(driver, case_id, report_cases):
    defendants_tab = find_element_by_text(driver, 'defendants  ', tag='a', parent_xpath='//*[@id="tabs"]/ul')
    if defendants_tab:
        defendants_tab.click()
    party_header = find_element_by_text(driver, "defendants", parent_xpath='//*[@id="tabs"]', tag='a')
    driver.execute_script("arguments[0].click();", party_header)
    time.sleep(0.5)
    first_individual = None
    party_headers = driver.find_elements(By.CSS_SELECTOR, "#defendantsAccordion h3")
    for i, header in enumerate(party_headers, start=1):
        try:
            if i > MAX_DEFENDANTS:
                break

            driver.execute_script("arguments[0].click();", header)
            time.sleep(0.5)
            party_name = header.text.split('(')[0].strip()

            description = find_element_by_text(driver, "Party Description",
                                            parent_xpath='//*[@id="defendantsAccordion"]',
                                            class_name="ValueField",
                                            get_sibling_value=True)
            status = find_element_by_text(driver, "Party Status",
                                        parent_xpath='//*[@id="defendantsAccordion"]',
                                        class_name="ValueField",
                                        get_sibling_value=True, tag='span')
            report_cases[case_id][f"name_{i}"] = party_name
            report_cases[case_id][f"description_{i}"] = description.text.strip()
            report_cases[case_id][f"status_{i}"] = status.text.strip()
            # capture first "Individual"
            if (
                    not first_individual
                    and not("business" in description.text.lower())
                    and not any(
                keyword.lower() in party_name.lower()
                for keyword in SKIP_DEFENDANT_KEYWORDS
            )
            ):
                print(f"main_defendant : {first_individual}")
                print(f"description : {description.text}")
                party_name = party_name.replace("AKA","")
                first_individual = party_name.strip()
        except :
            traceback.print_exc()
            continue
    report_cases[case_id]["main_defendant"] = first_individual
    return report_cases

def extract_table_data(driver):
    table_body = driver.find_element(By.XPATH, "/html/body/div[1]/div[2]/div/div[2]/div[2]/div[2]/div[4]/form/div/div/table/tbody")
    rows = table_body.find_elements(By.TAG_NAME, "tr")
    data_dict = {}
    for row in rows:
        cells = row.find_elements(By.TAG_NAME, "td")
        for cell in cells:
            try:
                label = cell.find_element(By.CLASS_NAME, "ValueField").text.strip()
                value = cell.find_element(By.CLASS_NAME, "LabelField").text.strip()
                data_dict[label] = value
            except:
                continue
    return data_dict

from concurrent.futures import Future, ThreadPoolExecutor

_property_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="PropDetails")


def extract_property_details(driver, case_id, report_cases, files_dir=None):
    """
    Driver-bound part only — fast, stays on main thread.
    Returns a Future for the background network work, or None if early exit.
    """
    log_file = os.path.join(files_dir, f"extract_property_{case_id}.log")

    with pysnooper.snoop(log_file):
        set_download_dir(driver, files_dir)

        # 1. Click Properties tab
        try:
            property_tab = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="tabs"]/ul/li[contains(normalize-space(.), "Properties")]'))
            )
            element_id = property_tab.get_attribute('aria-labelledby')
            property_tab.click()

            content_xpath = f"//div[@id='tabs']//*[@id[starts-with(., 'tabs-')]][@aria-labelledby='{element_id}']"
            for _ in range(3):
                property_details_elem = driver.find_element(By.XPATH, content_xpath)
                property_details_elem.click()
                time.sleep(0.5)
                if "Address:" in property_details_elem.text:
                    property_details = property_details_elem.text
                    break
            else:
                property_details = driver.find_element(By.XPATH, content_xpath).text

        except TimeoutException:
            print(f"Properties tab not found for {case_id}")
            return None  # ← no future, nothing to wait on

        # 2. Extract Block & Lot (driver-bound, must happen here)
        block_and_lot = property_details.split('Street Address:')[0]
        report_cases[case_id]['Block/Lot'] = block_and_lot
        report_cases[case_id]['Block'] = block_and_lot.split('Block:')[1].split('Lot:')[0].strip() if 'Block:' in block_and_lot else ''
        report_cases[case_id]['Lot'] = block_and_lot.split('Lot:')[1].strip().split('(')[0].strip() if 'Lot:' in block_and_lot else ''

        # 3. Read table data (driver-bound)
        table_data = extract_table_data(driver)

        # 4. Initialize default fields now so downstream code can read them safely
        for field in ['court_address', 'address', 'found', 'Upset Price', 'Upset Amount', 'Approx. Judgment', 'Approx. Upset']:
            report_cases[case_id][field] = ''

        # ── Reuse SalesWeb/Zillow data from the eligibility precheck, if any ──
        precheck_data = pop_precheck_data(case_id)
        try:
            address = property_details.split("Address:")[1].split("County")[0].strip() \
                if "Street Address:" not in table_data else table_data.get('Street Address:', '')
        except Exception:
            address = table_data.get('Street Address:', '')

        try:
            extracted_county = (
                property_details.split("County:")[1].split("Municipality")[0].strip()
                if not table_data.get('County:') else table_data.get('County:', '')
            ).strip()
        except Exception:
            extracted_county = (table_data.get('County:') or table_data.get('County', '') or '').strip()

        # Resolve county hierarchy:
        # 1. Initial value in the excel sheet
        # 2. Extracted county from property details / table data
        # 3. Processor name fallback
        processor_name = (
            report_cases.get(case_id, {}).get('processor_name')
            or report_cases.get(case_id, {}).get('processor')
            or "new jersey"
        ).strip()

        initial_county = (
            (precheck_data.get('salesweb_county') if precheck_data else None)
            or report_cases.get(case_id, {}).get('county')
            or report_cases.get(case_id, {}).get('County')
            or ""
        ).strip()

        if initial_county.lower() in [processor_name.lower(), "new jersey", "nj", ""]:
            initial_county = ""

        county = initial_county or extracted_county or processor_name

        report_cases[case_id]['court_address'] = address
        report_cases[case_id]['address'] = address
        report_cases[case_id]['county'] = county
        report_cases[case_id]['County'] = county

        if precheck_data:
            _apply_precheck_data(case_id, report_cases, precheck_data, address, county)
            future = Future()
            future.set_result(precheck_data)
            return future

        # ── Hand off network work to background thread ─────────────────────────
        future = _property_executor.submit(
            _process_property_network, case_id, report_cases, address, county, files_dir
        )
        return future


def _apply_precheck_data(case_id, report_cases, precheck_data, search_address, county=None):
    """
    Populate report_cases from data already fetched during the eligibility
    precheck (SalesWeb + Zillow), instead of calling those APIs again.
    Mirrors the field mapping in _process_property_network().
    """
    report_cases[case_id]['court_address'] = search_address
    report_cases[case_id]['address'] = search_address
    if county:
        report_cases[case_id]['county'] = county
        report_cases[case_id]['County'] = county

    candidates = [safe_int(report_cases.get(k)) for k in ['Upset Price', 'Upset Amount', 'Approx. Judgment', 'Approx. Upset']]
    unpaid_balance = max([x for x in candidates if x is not None]) if any(candidates) else None

    zestimate = precheck_data.get('zestimate')
    if zestimate:
        report_cases[case_id]['zestimate'] = zestimate
        if unpaid_balance:
            report_cases[case_id]['Equity'] = zestimate - unpaid_balance
    if precheck_data.get('zillow_status'):
        report_cases[case_id]['zillow_status'] = precheck_data['zillow_status']
    if precheck_data.get('home_type'):
        report_cases[case_id]['home_type'] = precheck_data['home_type']
    # Skip 'county' — precheck_data['county'] holds the processor name ("new jersey"),
    # NOT the actual county ("Burlington", "Union", etc.). The real county was already
    # scraped from the NJ court page and set separately via _process_property_network.
    for key, value in precheck_data.items():
        if key in ['county', 'County']:
            continue
        report_cases[case_id][key] = value


def _process_property_network(case_id, report_cases, search_address, county, files_dir):
    """
    Pure network calls — no driver. Safe to run in background thread.
    Runs SalesWeb and Zillow IN PARALLEL with each other too.
    """
    report_cases[case_id]['court_address'] = search_address
    report_cases[case_id]['address'] = search_address
    report_cases[case_id]['county'] = county
    report_cases[case_id]['County'] = county
    with pysnooper.snoop(output=f"{files_dir}/process_property_network_{case_id}.log"):
        try:

            def _fetch_salesweb():
                return extract_info_from_salesweb(search_address, county, 'NJ')

            def _fetch_zillow():
                zest, status, home_type, city, prop_type, is_agent,is_auction = get_zillow_infos(search_address, files_dir)
                if not zest:
                    try:
                        addr2, city2, state2, zip2, county2 = autocomplete_address(search_address)
                        zest, status, home_type, city, prop_type, is_agent,is_auction = get_zillow_infos(f"{addr2},{state2}", files_dir)
                    except Exception:
                        pass
                return zest, status, home_type, city, prop_type, is_agent

            with ThreadPoolExecutor(max_workers=2) as inner:
                salesweb_future = inner.submit(_fetch_salesweb)
                zillow_future   = inner.submit(_fetch_zillow)
                salesweb_data   = salesweb_future.result()
                zillow_result   = zillow_future.result()
            # 3. Apply SalesWeb results
            if salesweb_data:
                for key in ['found','financial_obligation','sales_web_address', 'Upset Price', 'Upset Amount', 'Approx. Judgment', 'Approx. Upset','status_history']:
                    report_cases[case_id][key] = salesweb_data.get(key, '')
                if salesweb_data.get('sales_date'):
                    report_cases[case_id]['sales_date'] = salesweb_data.get('sales_date', '')
            else:
                print(f"[{case_id}] Property Not Found in SalesWeb")

            candidates = [safe_int((salesweb_data or {}).get(k)) for k in ['Upset Price', 'Upset Amount', 'Approx. Judgment', 'Approx. Upset']]
            unpaid_balance = max([x for x in candidates if x is not None]) if any(candidates) else None

            # 4. Apply Zillow results
            zestimate, status, home_type, city, _, is_agent = zillow_result
            if zestimate:
                report_cases[case_id]['zestimate'] = zestimate
                if unpaid_balance:
                    report_cases[case_id]['Equity'] = zestimate - unpaid_balance
            if status:
                report_cases[case_id]['zillow_status'] = status
            if home_type:
                report_cases[case_id]['home_type'] = home_type
            if city:
                report_cases[case_id]['city'] = city
            if is_agent:
                report_cases[case_id]['is_current_signed_in_agent_responsible'] = is_agent

        except Exception:
            traceback.print_exc()

def check_case_type_nj(driver, case_id, report_cases):
    try:
        case_type = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, '/html/body/div[1]/div[2]/div/div[2]/div[2]/table/tbody/tr[2]/td[1]'))
        )
        if case_type and 'case type:' in case_type.text.lower():
            report_cases[case_id]['case_type'] = case_type.text.split(":")[1]
    except TimeoutException:
        pass

def delete_case_jacket(directory_path):
    file_path = os.path.join(directory_path, "CivilCaseJacket.pdf")
    if os.path.isfile(file_path):
        os.remove(file_path)


def _get_case_information(driver, case_id, result, state):
    """Get case information and update report_cases"""
    try:
        # Get defendants
        try:
            state.report_cases = get_defendants(driver, case_id, state.report_cases)
        except Exception as e:
            result['errors'].append(f"Defendant error: {e}")
            traceback.print_exc()

        # Check case type
        check_case_type_nj(driver, case_id, state.report_cases)

        # Get case status
        case_status_div = find_element_by_text(driver, "case status:", tag="span")
        if case_status_div:
            try:
                case_status_value = case_status_div.find_element(
                    By.XPATH, './following-sibling::*[contains(@class, "LabelField")]'
                ).text
                if case_status_value.lower():
                    state.report_cases[case_id]['court_case_status'] = case_status_value
                    print(f"[+] Case status: {case_status_value}")
            except Exception as e:
                result['errors'].append(f"Status error: {e}")

        return result

    except Exception as e:
        traceback.print_exc()
        return result