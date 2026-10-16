import os
import threading
import time
import traceback

import pysnooper
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from browser.browser_helpers import element_exists_xpath
from download.download_monitor import set_download_dir
from download.files_management import generate_safe_filename
from download.report_generation_helpers import process_all_file_rules
from utils.formatting import parse_date_safe

_scan_log_lock = threading.Lock()


def _write_scan_decision(files_dir, case_id, row_index, filename, decision, reason):
    """
    Append a single scan decision to <files_dir>/<case_id>_scan_decisions.txt.
    decision : "PICKED" | "SKIPPED"
    reason   : human-readable explanation
    """
    if not files_dir or not case_id:
        return
    try:
        log_path = os.path.join(files_dir, f"{case_id}_scan_decisions.txt")
        line = f"[Row {row_index:>4}] [{decision:>7}] {filename!r:60s} | {reason}\n"
        with _scan_log_lock:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass  # never let logging break the scraper


KEYWORDS_TO_PRUNE = [
    "complaint",
    "foreclosure_dismissal_order_notice",
    "final_judgement",
    "final judgment",
    "bankruptcy",
    "stipulation_of_settlement_dismissal",
    "certification_of_mailing",
    "foreclosure_dismissal_warning_notice",
    "vacate",
    "order_for_additional_sums_found",
    "final_judgment", "notice of sale", "notice_of_sale", 'pluries'
]

FILE_TRACKING_RULES = {
    "bankruptcy": {
        "flag_column": "Bankruptcy",
        "recent_column": "Recent Bankruptcy",
        "keywords": ["bankruptcy"],
        "rip_reason": "Bankruptcy Filed"  # Optional: marks case as RIP
    },
    "vacate": {
        "flag_column": "Vacate",
        "recent_column": "Recent Vacate",
        "keywords": ["vacate"],
        "rip_reason": "Motion to Vacate"
    },
    "cancel": {
        "flag_column": "Cancel",
        "recent_column": "Recent Cancel",
        "keywords": ["cancel"],
        "rip_reason": "Cancellation"
    },
    "certification_of_mailing": {
        "flag_column": "Certification of Mailing",
        "recent_column": "Recent Certification",
        "keywords": ["certification_of_mailing"]
    }
}

FIRST_FILE_RULES = [
    {
        "contains": "order_to_vacate",
        "status": "On Hold",
        "reason": "order_to_vacate"
    },
    {
        "contains": "foreclosure_dismissal_warning_notice",
        "status": "On Hold",
        "reason": "foreclosure_dismissal_warning_notice"
    },
    {
        "contains": "foreclosure_dismissal_order_notice",
        "status": "On Hold",
        "reason": "foreclosure_dismissal_order_notice"
    },
    {
        "contains": "stipulation_of_settlement_dismissal",
        "status": "On Hold",
        "reason": "stipulation_of_settlement_dismissal"
    },
    {
        "contains": "dismissal",
        "status": "RIP",
        "reason": "dismissal"
    }
]


def initialize_case_report(case_id, report_cases):
    """Initialize all tracking columns for a case"""

    # Initialize all flag columns
    for rule in FILE_TRACKING_RULES.values():
        report_cases[case_id][rule["flag_column"]] = "❌"
        report_cases[case_id][rule["recent_column"]] = ""


def apply_file_tracking_rules(case_id, matching_files, report_cases):
    """
    Apply file tracking rules: set flags and find most recent file for each keyword.
    Most recent = first in the list (assuming matching_files is sorted newest first)
    """
    lower_files = [f["filename"].lower() for f in matching_files]

    for rule_name, rule in FILE_TRACKING_RULES.items():
        flag_col = rule["flag_column"]
        recent_col = rule["recent_column"]
        keywords = rule["keywords"]
        print(f"recent_col : {recent_col}")
        # Check if any file matches this keyword
        has_match = any(
            any(keyword in filename for keyword in keywords)
            for filename in lower_files
        )

        # Set flag
        report_cases[case_id][flag_col] = "✅" if has_match else "❌"

        # Find most recent file (first match in list)
        if has_match:
            for file_data in matching_files:
                filename = file_data["filename"].lower()
                if any(keyword in filename for keyword in keywords):
                    # Store the actual filename (not lowercase)
                    report_cases[case_id][recent_col] = file_data["filename"]
                    break


def has_paperclip(driver, element_xpath):
    """
    Check if an element or its descendants contain an img with src containing 'paperclip'
    Returns True if found, False otherwise
    """
    try:
        # Try to find an img tag with src containing "paperclip" inside the element
        paperclip = driver.find_element(By.XPATH,
                                        f'{element_xpath}//img[contains(@src, "paperclip")]')
        return True
    except NoSuchElementException:
        return False


def prune_older_keyword_duplicates(matching_rows, keywords, files_dir=None, case_id=None):
    """
    Keeps only the newest occurrence of each keyword,
    with exceptions (e.g., complaint containing 'order').
    """
    seen = {k: False for k in keywords}
    pruned = []
    for row in matching_rows:  # newest → oldest
        name = row["filename"].lower()
        matched_keywords = [k for k in keywords if k in name]

        drop = False
        drop_reason = ""

        for keyword in matched_keywords:
            if seen[keyword]:
                # 🔒 Exception: keep complaint if it contains "order"
                if keyword == "complaint" and "order" in name:
                    continue
                drop = True
                drop_reason = f"duplicate keyword '{keyword}' — a newer occurrence was already kept"

        if drop:
            _write_scan_decision(
                files_dir, case_id,
                row.get("row_index", "?"),
                row["filename"],
                "SKIPPED",
                f"[prune_older_keyword_duplicates] {drop_reason}"
            )
            continue

        # Mark keywords as seen AFTER decision
        for keyword in matched_keywords:
            seen[keyword] = True

        _write_scan_decision(
            files_dir, case_id,
            row.get("row_index", "?"),
            row["filename"],
            "PICKED",
            f"[prune_older_keyword_duplicates] kept as newest match for: {matched_keywords or ['(no prune keyword)']}"
        )
        pruned.append(row)

    return pruned


# td
COUNTY_CONFIGS = {
    "volusia": {
        "filename_xpath_template": '//*[@id="GridDocket"]/tbody/tr[{i}]/td[3]',
        "date_xpath_template": '//*[@id="GridDocket"]/tbody/tr[{i}]/td[1]',
        "table_xpath": '//*[@id="GridDocket"]/tbody',
        "offset": 0,
        "tag_name": "tr"
    },
    "manatee": {
        "filename_xpath_template": '//*[@id="dockets"]/tbody/tr[{i}]/td[3]',
        "date_xpath_template": '//*[@id="dockets"]/tbody/tr[{i}]/td[2]',
        "table_xpath": '//*[@id="dockets"]/tbody',
        "offset": 0,
        "tag_name": "tr",
        "down_button": '//*[@id="dockets"]/tbody/tr[{i}]/td[1]/form/button'
    },
    "brevard": {
        "filename_xpath_template": '//*[@id="tbl-content"]/tbody/tr[{i}]/td[4]/div',
        "date_xpath_template": '//*[@id="tbl-content"]/tbody/tr[{i}]/td[2]/div',
        "table_xpath": '//*[@id="tbl-content"]/tbody',
        "offset": 0,
        "tag_name": "tr"
    },
    "sarasota": {
        "filename_xpath_template": '//*[@id="ctl00_cphBody_rgDocket_ctl00"]/tbody/tr[{i}]/td[4]',
        "date_xpath_template": '//*[@id="ctl00_cphBody_rgDocket_ctl00"]/tbody/tr[{i}]/td[2]',
        "table_xpath": '//*[@id="ctl00_cphBody_rgDocket_ctl00"]/tbody',
        "offset": 0,
        "tag_name": "tr",
        "down_button": '//*[@id="ctl00_cphBody_rgDocket_ctl00"]/tbody/tr[{i}]/td[6]/a'
    },
    "polk": {
        "filename_xpath_template": '//*[@id="doctable"]/tbody/tr[{i}]',
        "date_xpath_template": '//*[@id="doctable"]/tbody/tr[{i}]/td[1]',
        "table_xpath": '//*[@id="doctable"]/tbody',
        "offset": 0,
        "tag_name": "tr"
    },
    "duval": {
        "filename_xpath_template": '//*[@id="c_DocketsPanel"]/div/table/tbody[{i}]/tr/td[4]',
        "date_xpath_template": '//*[@id="c_DocketsPanel"]/div/table/tbody[{i}]/tr/td[3]/span',
        "table_xpath": '//*[@id="c_DocketsPanel"]/div/table/tbody',
        "offset": 0,
        "tag_name": "tr"
    },
    "lee": {
        "filename_xpath_template": '//*[@id="docketCollapse"]/div/div[2]/div[1]/table/tbody/tr[{i}]/td[2]',
        "date_xpath_template": '//*[@id="docketCollapse"]/div/div[2]/div[1]/table/tbody/tr[{i}]/td[1]',
        "table_xpath": '//*[@id="docketCollapse"]/div/div[2]/div[1]/table',
        "offset": 0,
        "tag_name": "tr"
    },
    "osceola": {#
        "filename_xpath_template": '/html/body/div[3]/table/tbody/tr/td[2]/div/table/tbody/tr/td/table[2]/tbody/tr[1]/td[2]/div[2]/div[2]/div/div[7]/div/div/div[2]/div/div/div/table/tbody/tr[{i}]/td[5]',
        "date_xpath_template": '/html/body/div[3]/table/tbody/tr/td[2]/div/table/tbody/tr/td/table[2]/tbody/tr[1]/td[2]/div[2]/div[2]/div/div[7]/div/div/div[2]/div/div/div/table/tbody/tr[{i}]/td[4]',
        "table_xpath": '//*[@id="gridDockets"]/tbody',
        "offset": 0,
        "tag_name": "tr"
    },
    "miami": {  # //*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]/div[39]/div[2]/div/div[2]/p[2]
        "filename_xpath_template": '//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]/div[{i}]/div[2]/div/div[5]/p[2]',
        "filename_xpath_template 2": '//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]/div[{i}]/div[2]/div/div[6]/p[2]',
        "date_xpath_template": '//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]/div[{i}]/div[2]/div/div[2]/p[2]',
        "table_xpath": '//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]',
        "offset": 0,
        "tag_name": 'div'},
    "md": {
        "filename_xpath_template": '//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]/div[{i}]/div[2]/div/div[5]/p[2]',
        "filename_xpath_template 2": '//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]/div[{i}]/div[2]/div/div[6]/p[2]',
        "date_xpath_template": '//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]/div[{i}]/div[2]/div/div[2]/p[2]',
        "table_xpath": '//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]',
        "offset": 0,
        "tag_name": 'div'},
    "bw": {"filename_xpath_template": '//*[@id="tblEvents"]/tbody/tr[{i}]/td[2]',

           "filename_xpath_template 2": '//*[@id="tblDispositionsCV"]/tbody/tr[{i}]/td[2]',
           "date_xpath_template": '//*[@id="tblEvents"]/tbody/tr[{i}]/td[1]',
           "table_xpath": '//*[@id="tblEvents"]/tbody',
           "table_xpath2": '//*[@id="tblDispositionsCV"]/tbody',
           "offset": 0,
           "tag_name": 'tr'},
    "clay": {"filename_xpath_template": '/html/body/div[3]/table/tbody/tr/td[2]/div/table/tbody/tr/td/table[2]/tbody/tr[1]/td[2]/div[2]/div[2]/div/div[5]/div/div/div[2]/div/div/div/table/tbody/tr[{i}]/td[4]',
        "date_xpath_template": '/html/body/div[3]/table/tbody/tr/td[2]/div/table/tbody/tr/td/table[2]/tbody/tr[1]/td[2]/div[2]/div[2]/div/div[5]/div/div/div[2]/div/div/div/table/tbody/tr[{i}]/td[3]',
        "table_xpath": '/html/body/div[3]/table/tbody/tr/td[2]/div/table/tbody/tr/td/table[2]/tbody/tr[1]/td[2]/div[2]/div[2]/div/div[5]/div/div/div[2]/div/div/div/table/tbody',
        "offset": 0,
        "tag_name": 'tr'},
    "stjohns": {
        "filename_xpath_template": '/html/body/div[3]/table/tbody/tr/td[2]/div/table/tbody/tr/td/table[2]/tbody/tr[1]/td[2]/div[2]/div[2]/div/div[5]/div/div/div[2]/div/div/div/table/tbody/tr[{i}]/td[5]',
        "date_xpath_template": '/html/body/div[3]/table/tbody/tr/td[2]/div/table/tbody/tr/td/table[2]/tbody/tr[1]/td[2]/div[2]/div[2]/div/div[5]/div/div/div[2]/div/div/div/table/tbody/tr[{i}]/td[4]',
        "table_xpath": '/html/body/div[3]/table/tbody/tr/td[2]/div/table/tbody/tr/td/table[2]/tbody/tr[1]/td[2]/div[2]/div[2]/div/div[5]/div/div/div[2]/div/div/div/table/tbody',
        "offset": 0,
        "tag_name": 'tr'}
}

# x1
# //*[@id="tblEvents"]/tbody/tr[36]/td[3] x2
# date
"""
date_xpath = '//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]/div[2]/div[2]/div/div[2]/p[2]'
    update_case_status(driver,case_id, "Miami Dade", "Downloading", details="Checking for files")
    for i in downloadable_dockets:
        file_button = i.find_element("xpath", "//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]/div[1]/div")
        docket_entry = i.find_element("xpath", "//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]/div[2]/div/div[5]/p[2]")
        comment = i.find_element("xpath", "//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]/div[2]/div/div[6]/p[2]")
"""


def scan_table_multithreaded(driver, case_id, files_dir, report_cases, total_rows, matching_rows, matching_rows_lock,
                             keyword_list, unwanted_list, county, start_index=1, tab2=False):
    with pysnooper.snoop(output=os.path.join(files_dir, "scan_table_multithreaded.log")):
        if not total_rows:
            total_rows = 0
        if total_rows <= 0 or start_index > total_rows:
            return
        matching_rows = []

        # Write a header for this scan run to the decision log
        try:
            from datetime import datetime as _dt
            if files_dir and case_id:
                log_path = os.path.join(files_dir, f"{case_id}_scan_decisions.txt")
                with _scan_log_lock:
                    with open(log_path, "a", encoding="utf-8") as _f:
                        _f.write(f"\n{'=' * 80}\n")
                        _f.write(f"  SCAN RUN  case={case_id}  county={county}  "
                                 f"rows={total_rows}  started={_dt.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        _f.write(f"  keywords   : {keyword_list}\n")
                        _f.write(f"  unwanted   : {unwanted_list}\n")
                        _f.write(f"{'=' * 80}\n\n")
        except Exception:
            pass

        # Adjust total rows to only count rows from start_index onwards
        if start_index > total_rows:
            return

        # Selenium WebDriver is NOT thread-safe: multiple threads calling
        # driver.find_element() / driver.switch_to on the same instance causes
        # race conditions, stale elements, and lost results.  Scan serially.
        try:
            if start_index != 0:
                print(f"Scanning rows {start_index}-{total_rows} for {county}")
        except Exception:
            pass
        print(f"county ::: {county}")

        if county in ("nj", "jersey", "new jersey"):
            scan_rows_nj(driver, start_index, total_rows, keyword_list, unwanted_list,
                         files_dir, matching_rows, matching_rows_lock)
        elif county in ("oc", "orange"):
            scan_rows_oc(driver, start_index, total_rows, keyword_list, unwanted_list,
                         files_dir, matching_rows, matching_rows_lock, case_id=case_id)
        elif county in ("dv", "duval"):
            scan_rows_dv(driver, start_index, total_rows, keyword_list, unwanted_list,
                         files_dir, matching_rows, matching_rows_lock, case_id=case_id)
        elif county == "lee":
            scan_rows_lee(driver, start_index, total_rows, keyword_list, unwanted_list,
                          files_dir, matching_rows, matching_rows_lock, case_id=case_id)
        elif county in ("pb", "palm", "palm beach"):
            scan_rows_pb(driver, start_index, total_rows, keyword_list, unwanted_list,
                         files_dir, matching_rows, matching_rows_lock, case_id=case_id)
        elif county in ("pin", "pinn", "pinellas"):
            scan_rows_pin(driver, start_index, total_rows, keyword_list, unwanted_list,
                          files_dir, matching_rows, matching_rows_lock)
        elif county == "polk":
            scan_rows_polk(driver, start_index, total_rows, keyword_list, unwanted_list,
                           files_dir, matching_rows, matching_rows_lock, case_id=case_id)
        elif county == "seminole":
            scan_rows_seminole(driver, start_index, total_rows, keyword_list, unwanted_list,
                               files_dir, matching_rows, matching_rows_lock, case_id=case_id)
        else:
            config = COUNTY_CONFIGS.get(county) or {}
            scan_rows(driver, start_index, total_rows, keyword_list, unwanted_list, files_dir,
                      config, matching_rows, matching_rows_lock, tab2=tab2, case_id=case_id)

        # 🔽 Filter duplicates: remove uncontested_order if final_judgment exists
        lower_filenames = [r["filename"].lower() for r in matching_rows]

        # --- Uncontested filter ---
        if any("uncontested_order" in f for f in lower_filenames):
            kept = []
            for r in matching_rows:
                fn = r["filename"].lower()
                if "final_judgment" in fn and "uncontested" not in fn:
                    _write_scan_decision(
                        files_dir, case_id, r.get("row_index", "?"), r["filename"],
                        "SKIPPED",
                        "[post-scan filter] final_judgment removed because uncontested_order already exists in this case"
                    )
                else:
                    kept.append(r)
            matching_rows = kept

        # --- Additional sums filter ---
        if any("order_for_additional_sums" in f for f in lower_filenames):
            kept = []
            for r in matching_rows:
                if "motion_for_additional_sums" in r["filename"].lower():
                    _write_scan_decision(
                        files_dir, case_id, r.get("row_index", "?"), r["filename"],
                        "SKIPPED",
                        "[post-scan filter] motion_for_additional_sums removed because order_for_additional_sums is present"
                    )
                else:
                    kept.append(r)
            matching_rows = kept
        if any("order_for_summary_judgment" in f for f in lower_filenames):
            kept = []
            for r in matching_rows:
                if "motion_for_summary_judgment" in r["filename"].lower():
                    _write_scan_decision(
                        files_dir, case_id, r.get("row_index", "?"), r["filename"],
                        "SKIPPED",
                        "[post-scan filter] motion_for_summary_judgment removed because order_for_summary_judgment is present"
                    )
                else:
                    kept.append(r)
            matching_rows = kept
        # --- Pluries writ filter ---
        if any("complaint" in f for f in lower_filenames):
            kept = []
            for r in matching_rows:
                if "pluries_writ" in r["filename"].lower():
                    _write_scan_decision(
                        files_dir, case_id, r.get("row_index", "?"), r["filename"],
                        "SKIPPED",
                        "[post-scan filter] pluries_writ removed because complaint is present"
                    )
                else:
                    kept.append(r)
            matching_rows = kept

        matching_rows.sort(key=lambda r: parse_date_safe(r["date"]), reverse=True)
        matching_rows = prune_older_keyword_duplicates(
            matching_rows,
            KEYWORDS_TO_PRUNE,
            files_dir=files_dir,
            case_id=case_id
        )
        try:
            process_all_file_rules(matching_rows, case_id, report_cases, files_dir)
        except:
            pass

        print(f"pruned len : {len(matching_rows)}")
        return matching_rows


def _get_broward_table(driver):
    """Get files table with automatic fallback"""
    try:
        return WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, 'tblEvents'))
        )
    except TimeoutException:
        # Click viewer and retry
        ca = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.CLASS_NAME, 'bc-casedetail-viewer'))
        )
        ca.click()
        time.sleep(2)
        return WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, 'tblEvents'))
        )


def scan_rows_bw(driver, start, end, DEFAULT_KEYWORDS, DEFAULT_UNWANTED, files_dir, matching_rows, matching_rows_lock,
                 case_id=None):
    """Scan the table and return all matching rows based on filename keywords."""
    # Wait until table is loaded
    files_table = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.XPATH, '//*[@id="dockets"]/tbody'))
    )
    files_rows = files_table.find_elements(By.TAG_NAME, "tr")
    table_length = len(files_rows)

    print(f"📄 Found {table_length} rows in event list")

    for i in range(start, end):

        try:
            filename_xpath = f'//*[@id="dockets"]/tbody/tr[{i}]/td[3]'
            filename_elem = driver.find_element(By.XPATH, filename_xpath)
            if filename_elem.get_attribute('class') == "hidden":
                continue
            filename = filename_elem.text.strip()

            if not filename:
                continue

            has_keyword = any(word.lower() in filename.lower() for word in DEFAULT_KEYWORDS)
            has_unwanted = any(bad.lower() in filename.lower() for bad in DEFAULT_UNWANTED)
            if not has_keyword:
                _write_scan_decision(files_dir, case_id, i, filename, "SKIPPED",
                                     f"[scan_rows_bw] no keyword matched")
                continue
            if has_unwanted:
                matched_bad = [b for b in DEFAULT_UNWANTED if b.lower() in filename.lower()]
                _write_scan_decision(files_dir, case_id, i, filename, "SKIPPED",
                                     f"[scan_rows_bw] unwanted word(s) found: {matched_bad}")
                continue

            # Get the date (if exists)
            try:
                date_xpath = f'//*[@id="dockets"]/tbody/tr[{i}]/td[2]'
                date_elem = driver.find_element(By.XPATH, date_xpath)
                date_text = date_elem.text.strip()
            except Exception:
                date_text = ""

            matched_kw = [w for w in DEFAULT_KEYWORDS if w.lower() in filename.lower()]
            with matching_rows_lock:
                matching_rows.append({
                    "row_index": i,
                    "filename": filename,
                    "date": date_text
                })
            _write_scan_decision(files_dir, case_id, i, filename, "PICKED",
                                 f"[scan_rows_bw] keyword(s) matched: {matched_kw}")
        except Exception:
            continue

    # Sort rows by date (if available)
    matching_rows.sort(key=lambda r: parse_date_safe(r["date"]), reverse=True)

    print(f"✅ Found {len(matching_rows)} matching rows")
    return matching_rows


# tblDispositionsCV
# tblEvents
from config_ import DEFAULT_KEYWORDS, DEFAULT_UNWANTED


def scan_rows(driver, start, end, dd, d, files_dir, config, matching_rows,
              matching_rows_lock, tab2=False, case_id=None):
    """Scan the table and return all matching rows based on filename keywords."""
    # Wait until table is loaded
    if tab2:
        table_xpath = config['table_xpath2']
    else:
        table_xpath = config['table_xpath']
    filename_xpath_template = config['filename_xpath_template']
    filename_xpath_template2 = config.get("filename_xpath_template 2")
    tag_name = config.get('tag_name')
    date_xpath_template = config['date_xpath_template']
    offset = config['offset']

    # table

    files_table = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.XPATH, table_xpath))
    )
    #
    max_attempt = 3
    time.sleep(1)
    for i in range(start, end):

        attempt = 0
        while attempt < max_attempt:

            try:
                # get/verify file name
                filename_xpath = filename_xpath_template.format(i=i)
                driver.switch_to_window(driver.window_handles[0])
                #

                try:
                    filename_element = driver.find_element(By.XPATH, filename_xpath)
                except NoSuchElementException:
                    attempt += 1
                    continue

                # for broward
                """if filename_element.get_attribute('class') == "hidden":
                    continue"""
                filename = filename_element.text.lower().strip()
                if filename_xpath_template2 and tab2:
                    filename_xpath2 = filename_xpath_template2.format(i=i)
                    filename_element2 = WebDriverWait(driver, 2).until(
                        EC.presence_of_element_located((By.XPATH, filename_xpath2))
                    )
                    filename2 = filename_element2.text.lower().strip()
                    filename = f"filename2 : {filename2}"
                if not filename:
                    break
                # Apply keyword and unwanted word filters
                if ("down_button" in config) and not element_exists_xpath(driver, config['down_button'].format(i=i)):
                    _write_scan_decision(files_dir, case_id, i, filename, "SKIPPED",
                                         "[scan_rows] no download button present for this row")
                    break
                has_keyword = any(word.lower() in filename.lower() for word in DEFAULT_KEYWORDS)
                has_unwanted = any(bad.lower() in filename.lower() for bad in DEFAULT_UNWANTED)
                if not has_keyword:
                    _write_scan_decision(files_dir, case_id, i, filename, "SKIPPED",
                                         f"[scan_rows] no keyword matched")
                    break
                if has_unwanted:
                    matched_bad = [b for b in DEFAULT_UNWANTED if b.lower() in filename.lower()]
                    _write_scan_decision(files_dir, case_id, i, filename, "SKIPPED",
                                         f"[scan_rows] unwanted word(s) found: {matched_bad}")
                    break

                # Get the date (if exists)
                date_xpath = date_xpath_template.format(i=i)
                date_text = driver.find_element('xpath', date_xpath).text.replace('/', '_').strip()
                # table_xpath
                row = files_table.find_element(By.XPATH, f'./{tag_name}[{i}]')

                matched_kw = [w for w in DEFAULT_KEYWORDS if w.lower() in filename.lower()]
                if element_exists_xpath(row, './/a[@href]'):
                    href = row.find_element(By.XPATH, './/a[@href]').get_attribute('href')
                    with matching_rows_lock:
                        matching_rows.append({
                            "row_index": i + offset,
                            "filename": filename,
                            "date": date_text,
                            "href": href,
                            "row": row
                        })
                    _write_scan_decision(files_dir, case_id, i + offset, filename, "PICKED",
                                         f"[scan_rows] keyword(s) matched: {matched_kw}")
                    break
                # append to the matching row
                # Add to matching list
                with matching_rows_lock:
                    matching_rows.append({
                        "row_index": i + offset,
                        "filename": filename,
                        "date": date_text,
                        "row": row
                    })
                _write_scan_decision(files_dir, case_id, i + offset, filename, "PICKED",
                                     f"[scan_rows] keyword(s) matched: {matched_kw}")
                break
            except NoSuchElementException:
                attempt += 1
                print(f"not found {i} for filename {filename}")
                traceback.print_exc()
            except TimeoutException:
                print(f"timeout i : {i}")
                attempt += 1
                break
            except Exception:
                attempt += 1
                traceback.print_exc()
                continue

    # Sort rows by date (if available)

    print(f"✅ Found {len(matching_rows)} matching rows")
    return matching_rows


def scan_rows_pin(driver, start, end, DEFAULT_KEYWORDS, DEFAULT_UNWANTED, files_dir, matching_rows, matching_rows_lock):
    """Scan the table and return all matching rows based on filename keywords."""
    # Wait until table is loaded
    files_table = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.XPATH, '//*[@id="eventList"]/tbody'))
    )
    files_rows = files_table.find_elements(By.TAG_NAME, "tr")
    table_length = len(files_rows)

    print(f"📄 Found {table_length} rows in event list")

    for i in range(start, end):

        try:
            # Get filename text from column 2
            filename_xpath = f'//*[@id="eventList"]/tbody/tr[{i}]/td[2]/a'
            filename_elem = WebDriverWait(driver, 2).until(
                EC.presence_of_element_located((By.XPATH, filename_xpath))
            )
            filename = filename_elem.text.strip()

            # Skip empty filenames
            if not filename:
                continue

            # Apply keyword and unwanted word filters
            if (not any(word.lower() in filename.lower() for word in DEFAULT_KEYWORDS)) or \
                    (any(bad.lower() in filename.lower() for bad in DEFAULT_UNWANTED)):
                continue

            # Get the date (if exists)
            try:

                date_xpath = f'//*[@id="eventList"]/tbody/tr[{i}]/td[1]'
                date_elem = driver.find_element(By.XPATH, date_xpath)
                date_text = date_elem.text.strip()
            except Exception:
                date_text = ""

            # Add to matching list
            with matching_rows_lock:
                matching_rows.append({
                    "row_index": i,
                    "filename": filename,
                    "date": date_text
                })
        except Exception:
            continue

    # Sort rows by date (if available)
    matching_rows.sort(key=lambda r: parse_date_safe(r["date"]), reverse=True)

    print(f"✅ Found {len(matching_rows)} matching rows")
    return matching_rows



def scan_rows_oc(driver, start_idx, end_idx, keyword_list, unwanted_list, files_dir,
                 matching_rows, matching_rows_lock, case_id=None):
    """
    Scans a specific range of rows in the docket table and appends matches to matching_rows.
    """

    table_xpath = '//*[@id="docketTable"]/tbody'
    table = driver.find_element(By.XPATH, table_xpath)

    for i in range(start_idx, end_idx):

        try:
            row_xpath = f'./tr[{i}]'
            row = table.find_element(By.XPATH, row_xpath)

            # Get description
            try:
                raw_desc = row.find_element(By.XPATH, './td[2]/a').text
            except NoSuchElementException:
                continue

            # Filter rows by keywords
            has_keyword = any(word.lower() in raw_desc.lower() for word in keyword_list)
            has_unwanted = any(bad.lower() in raw_desc.lower() for bad in unwanted_list)
            is_docket_rec = row.get_attribute("class") == "docketRec"
            if not is_docket_rec:
                _write_scan_decision(files_dir, case_id, i, raw_desc, "SKIPPED",
                                     "[scan_rows_oc] row class is not 'docketRec' (not a downloadable record)")
                continue
            if not has_keyword:
                _write_scan_decision(files_dir, case_id, i, raw_desc, "SKIPPED",
                                     f"[scan_rows_oc] no keyword matched from {keyword_list}")
                continue
            if has_unwanted:
                matched_bad = [b for b in unwanted_list if b.lower() in raw_desc.lower()]
                _write_scan_decision(files_dir, case_id, i, raw_desc, "SKIPPED",
                                     f"[scan_rows_oc] unwanted word(s) found: {matched_bad}")
                continue

            # Extract date
            try:
                date = row.find_element(By.XPATH, './td[1]').text
            except NoSuchElementException:
                date = "Unknown"

            filename = generate_safe_filename(f"{raw_desc}_{date}")
            matched_kw = [w for w in keyword_list if w.lower() in raw_desc.lower()]

            # Append match to shared list with lock
            with matching_rows_lock:
                matching_rows.append({
                    "row_index": i,
                    "filename": filename,
                    "date": date,
                })
            _write_scan_decision(files_dir, case_id, i, filename, "PICKED",
                                 f"[scan_rows_oc] keyword(s) matched: {matched_kw}")


        except Exception as e:
            print(f"{threading.current_thread().name} → Error processing row {i}: {e}")


def scan_rows_seminole(driver, start, end, DEFAULT_KEYWORDS, DEFAULT_UNWANTED, files_dir, matching_rows,
                       matching_rows_lock, case_id=None):
    """Scan the table and return all matching rows based on filename keywords."""
    files_table = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.XPATH, '//*[@id="docketGrid"]/tbody'))
    )
    files_rows = files_table.find_elements(By.TAG_NAME, "tr")
    table_length = len(files_rows)

    print(f"📄 Found {table_length} rows in event list")

    for i in range(start, end):
        try:
            filename_xpath = f'//*[@id="docketGrid"]/tbody/tr[{i}]/td[4]'
            filename_elem = WebDriverWait(driver, 2).until(
                EC.presence_of_element_located((By.XPATH, filename_xpath))
            )
            filename = filename_elem.text.strip()

            if not filename:
                continue

            has_keyword = any(word.lower() in filename.lower() for word in DEFAULT_KEYWORDS)
            has_unwanted = any(bad.lower() in filename.lower() for bad in DEFAULT_UNWANTED)
            if not has_keyword:
                _write_scan_decision(files_dir, case_id, i, filename, "SKIPPED",
                                     f"[scan_rows_seminole] no keyword matched")
                continue
            if has_unwanted:
                matched_bad = [b for b in DEFAULT_UNWANTED if b.lower() in filename.lower()]
                _write_scan_decision(files_dir, case_id, i, filename, "SKIPPED",
                                     f"[scan_rows_seminole] unwanted word(s) found: {matched_bad}")
                continue

            file_cell = driver.find_element(By.XPATH, f'//*[@id="docketGrid"]/tbody/tr[{i}]/td[6]')
            href = file_cell.find_element(By.TAG_NAME, 'a').get_attribute('href')
            try:
                date_xpath = f'//*[@id="docketGrid"]/tbody/tr[{i}]/td[1]'
                date_elem = driver.find_element(By.XPATH, date_xpath)
                date_text = date_elem.text.strip()
            except Exception:
                date_text = ""

            matched_kw = [w for w in DEFAULT_KEYWORDS if w.lower() in filename.lower()]
            with matching_rows_lock:
                matching_rows.append({
                    "row_index": i,
                    "filename": filename,
                    "date": date_text,
                    "href": href,
                })
            _write_scan_decision(files_dir, case_id, i, filename, "PICKED",
                                 f"[scan_rows_seminole] keyword(s) matched: {matched_kw}")
        except Exception:
            continue

    # Sort rows by date (if available)
    matching_rows.sort(key=lambda r: parse_date_safe(r["date"]), reverse=True)

    print(f"✅ Found {len(matching_rows)} matching rows")
    return matching_rows


def scan_rows_nj(driver, start_idx, end_idx, keyword_list, unwanted_list, files_dir, matching_rows, matching_rows_lock):
    """Scan a range of rows and collect rows that match download criteria"""
    keyword_list = [kw for kw in keyword_list if kw.lower() != "judgement"]
    thread_name = threading.current_thread().name
    try:
        for row_index in range(start_idx, end_idx):

            civil_file = os.path.join(files_dir, "CivilCaseJacket.pdf")
            if os.path.exists(civil_file):
                try:
                    os.remove(civil_file)
                    print(f"🗑️ Deleted leftover {civil_file}")
                except Exception as e:
                    print(f"⚠️ Could not delete {civil_file}: {e}")

            set_download_dir(driver, files_dir)
            try:
                description = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, f'//*[@id="caseActionTbId2:tbody_element"]/tr[{row_index + 1}]/td[3]'))
                ).text
                date = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, f'//*[@id="caseActionTbId2:tbody_element"]/tr[{row_index + 1}]/td[5]'))
                ).text
                transaction_id = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, f'//*[@id="caseActionTbId2:tbody_element"]/tr[{row_index + 1}]/td[4]'))
                ).text
            except TimeoutException:
                print(
                    f"{threading.current_thread().name}: no file attached in {row_index}")
                continue

            if "submitted" in description.lower():
                split_index = description.lower().find("submitted")
                description = description[:split_index]
            elif "granted" in description.lower():
                split_index = description.lower().find("granted")
                description = description[:split_index]

            if (not any(word.lower() in description.lower().strip() for word in keyword_list)) or \
                    (any(bad.lower() in description.lower().strip() for bad in unwanted_list)):
                continue

            if not has_paperclip(driver, f'//*[@id="caseActionTbId2:tbody_element"]/tr[{row_index + 1}]'):
                print(f"{thread_name}: Row {row_index} has no paperclip (file attachment)")
                continue

            filename = generate_safe_filename(f"{date}_{description}")
            file_cell_xpath = f'//*[@id="caseActionTbId2:tbody_element"]/tr[{row_index + 1}]/td[2]'
            cell = driver.find_element(By.XPATH, file_cell_xpath)

            try:
                file_element = WebDriverWait(cell, 5).until(
                    EC.presence_of_element_located((By.XPATH, './/*[starts-with(@id, "caseActionTbId2:")]'))
                )
            except TimeoutException:
                print(f"{threading.current_thread().name}: Element {row_index} has no file attached")
                break
            with matching_rows_lock:
                if "CERTIFICATION_OF_MAILING" not in f"{transaction_id}_{filename}":
                    matching_rows.append({
                        "row_index": row_index,
                        "name": file_element.get_attribute("name"),
                        "filename": f"{transaction_id}_{filename}",
                        "date": date,
                        "transaction_id": transaction_id
                    })
    except Exception as e:
        print(f"[{thread_name}] Error scanning rows: {e}")
        traceback.print_exc()


# (driver, start_idx, end_idx, keyword_list, unwanted_list,files_dir,matching_rows,matching_rows_lock)
def scan_rows_pb(driver, start_idx, end_idx, keyword_list, unwanted_list, files_dir,
                 matching_rows, matching_rows_lock, case_id=None):
    """
    Scans a specific range of rows in the Palm Beach docket table and appends matches to matching_rows.
    Follows the same structure as scan_rows_nj, scan_rows_oc, scan_rows_dv, and scan_rows_lee.
    """
    thread_name = threading.current_thread().name

    try:
        files_table = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.ID, "docketTable"))
        )
    except TimeoutException:
        print(f"[{thread_name}] Timeout waiting for table")
        return

    files_rows = files_table.find_elements(By.TAG_NAME, "tr")

    for row_index in range(start_idx, end_idx):

        if row_index >= len(files_rows):
            break

        try:
            row = files_rows[row_index]

            # Check if row has downloadable icon
            if not element_exists_xpath(driver, f'//*[@id="docketTable"]/tbody/tr[{row_index}]/td[1]/button'):
                continue

            # Extract description
            try:
                desc_text = driver.find_element(By.XPATH,
                                                f'//*[@id="docketTable"]/tbody/tr[{row_index}]/td[5]').text.strip()
            except NoSuchElementException:
                desc_text = ""
            # Filter by keywords
            has_keyword = any(word.lower() in desc_text.lower() for word in keyword_list)
            has_unwanted = any(bad.lower() in desc_text.lower() for bad in unwanted_list)
            if not has_keyword:
                _write_scan_decision(files_dir, case_id, row_index + 1, desc_text, "SKIPPED",
                                     f"[scan_rows_pb] no keyword matched from {keyword_list}")
                continue
            if has_unwanted:
                matched_bad = [b for b in unwanted_list if b.lower() in desc_text.lower()]
                _write_scan_decision(files_dir, case_id, row_index + 1, desc_text, "SKIPPED",
                                     f"[scan_rows_pb] unwanted word(s) found: {matched_bad}")
                continue

            # Extract date
            try:
                date_text = row.find_element(By.XPATH,
                                             f'//*[@id="docketTable"]/tbody/tr[{row_index}]/td[4]').text.strip()
            except NoSuchElementException:
                date_text = "Unknown"

            # Generate filename
            filename = generate_safe_filename(f'{desc_text}_{date_text}')
            matched_kw = [w for w in keyword_list if w.lower() in desc_text.lower()]

            # Append match to shared list with lock
            with matching_rows_lock:
                matching_rows.append({
                    "row_index": row_index,
                    "filename": filename,
                    "description": desc_text,
                    "date": date_text
                })
            _write_scan_decision(files_dir, case_id, row_index + 1, filename, "PICKED",
                                 f"[scan_rows_pb] keyword(s) matched: {matched_kw}")

        except Exception as e:
            print(f"[{thread_name}] Error processing row {row_index}: {e}")
            traceback.print_exc()


def scan_rows_dv(driver, start_idx, end_idx, keyword_list, unwanted_list, files_dir,
                 matching_rows, matching_rows_lock, case_id=None):
    """
    Scans a specific range of rows for DV counties.
    Similar structure to OC but tailored for DV table layout.
    """

    table_xpath = '//*[@id="c_DocketsPanel"]/div/table'
    table = WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.XPATH, table_xpath)))

    for i in range(start_idx, end_idx):

        try:
            row_xpath = f'./tbody[{i}]/tr'
            # //*[@id="c_DocketsPanel"]/div/table/tbody[39]/tr/td[4] filanme
            # //*[@id="c_DocketsPanel"]/div/table/tbody[2]/tr/td[6]/div button
            # //*[@id="c_DocketsPanel"]/div/table/tbody[39]/tr/td[3]/span date
            row = table.find_element(By.XPATH, row_xpath)

            # Ensure row is visible
            driver.execute_script("arguments[0].scrollIntoView();", row)

            row_text = row.get_attribute("textContent")
            # Skip if no "Available" text or header
            if i == 0 or "Available" not in row_text:
                continue

            #
            try:
                description_cell = row.find_element(By.CLASS_NAME, 'docketDescription')
                description = description_cell.text.strip()
            except NoSuchElementException:
                continue

            # Filter using keywords
            has_keyword = any(word.lower() in description.lower() for word in keyword_list)
            has_unwanted = any(bad.lower() in description.lower() for bad in unwanted_list)
            if not has_keyword:
                _write_scan_decision(files_dir, case_id, i, description, "SKIPPED",
                                     f"[scan_rows_dv] no keyword matched from {keyword_list}")
                continue
            if has_unwanted:
                matched_bad = [b for b in unwanted_list if b.lower() in description.lower()]
                _write_scan_decision(files_dir, case_id, i, description, "SKIPPED",
                                     f"[scan_rows_dv] unwanted word(s) found: {matched_bad}")
                continue

            # Extract date
            try:
                date = row.find_element(By.XPATH, './td[3]/span').text.strip()
            except NoSuchElementException:
                date = "Unknown"

            filename = generate_safe_filename(f"{description}_{date}")
            matched_kw = [w for w in keyword_list if w.lower() in description.lower()]

            # Append results thread-safely
            with matching_rows_lock:
                matching_rows.append({
                    "row_index": i,
                    "filename": filename,
                    "description": description,
                    "date": date
                })
            _write_scan_decision(files_dir, case_id, i, filename, "PICKED",
                                 f"[scan_rows_dv] keyword(s) matched: {matched_kw}")

        except TimeoutException:
            print(f"[DV] Timeout while processing row {i}")
        except Exception as e:
            print(f"[DV] Error in row {i}: {e}")
            traceback.print_exc()


def scan_rows_lee(driver, start_idx, end_idx, keyword_list, unwanted_list, files_dir,
                  matching_rows, matching_rows_lock, case_id=None):
    """
    Scans rows in the Lee county docket table and adds matches to matching_rows.
    """
    table_xpath = '//*[@id="docketCollapse"]/div/div[2]/div[1]/table/tbody'
    table = driver.find_element(By.XPATH, table_xpath)

    for i in range(start_idx, end_idx + 1):

        try:
            # Extract description and date
            desc_xpath = f'./tr[{i}]/td[2]'
            date_xpath = f'./tr[{i}]/td[1]'
            file_xpath = f'./tr[{i}]/td[5]/a'

            try:
                raw_desc = table.find_element(By.XPATH, desc_xpath).text
            except NoSuchElementException:
                continue

            try:
                date = table.find_element(By.XPATH, date_xpath).text
            except NoSuchElementException:
                date = "Unknown"

            # Filter rows based on keywords
            raw_lower = raw_desc.lower()

            # Find matches
            found_keywords = [word for word in keyword_list if word.lower() in raw_lower]
            found_unwanted = [bad for bad in unwanted_list if bad.lower() in raw_lower]

            # Apply the filter logic
            if not found_keywords:
                _write_scan_decision(files_dir, case_id, i, raw_desc, "SKIPPED",
                                     f"[scan_rows_lee] no keyword matched from {keyword_list}")
                continue
            if found_unwanted:
                _write_scan_decision(files_dir, case_id, i, raw_desc, "SKIPPED",
                                     f"[scan_rows_lee] unwanted word(s) found: {found_unwanted}")
                continue

            filename = generate_safe_filename(f"{raw_desc}_{date}")
            row_xpath = f'//*[@id="docketCollapse"]/div/div[2]/div[1]/table/tbody/tr[{i}]/td[5]/a'
            row_element = driver.find_element(By.XPATH, row_xpath)
            # Append match safely
            with matching_rows_lock:
                matching_rows.append({
                    "row_index": i,
                    "description": raw_desc,
                    "filename": filename,
                    "date": date,
                    "row_element": row_element
                })
            _write_scan_decision(files_dir, case_id, i, filename, "PICKED",
                                 f"[scan_rows_lee] keyword(s) matched: {found_keywords}")

        except Exception as e:
            print(f"[Lee] Error scanning row {i}: {e}")


def scan_rows_polk(driver, start_idx, end_idx, keyword_list, unwanted_list, files_dir,
                   matching_rows, matching_rows_lock, case_id=None):
    table_xpath = '//*[@id="doctable"]/tbody'

    for i in range(start_idx, end_idx):
        try:
            # Re-fetch table each iteration to avoid stale element
            table = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.XPATH, table_xpath))
            )

            row = table.find_element(By.XPATH, f'./tr[{i}]')
            driver.execute_script("arguments[0].scrollIntoView();", row)

            download_button = row.find_element(By.XPATH, './td[5]/div/img')
            if "blank" in download_button.get_attribute('src').lower():
                continue

            date = WebDriverWait(row, 10).until(
                EC.presence_of_element_located((By.XPATH, './td[1]'))
            ).text
            description = WebDriverWait(row, 10).until(
                EC.presence_of_element_located((By.XPATH, './td[2]'))
            ).text


            has_keyword = any(word.lower() in description.lower() for word in keyword_list)
            has_unwanted = any(bad.lower() in description.lower() for bad in unwanted_list)

            if not has_keyword:
                _write_scan_decision(files_dir, case_id, i, description, "SKIPPED",
                                     f"[scan_rows_polk] no keyword matched from {keyword_list}")
                continue

            if has_unwanted:
                matched_bad = [b for b in unwanted_list if b.lower() in description.lower()]
                _write_scan_decision(files_dir, case_id, i, description, "SKIPPED",
                                     f"[scan_rows_polk] unwanted word(s) found: {matched_bad}")
                continue

            filename = generate_safe_filename(f"{description}_{date}")
            matched_kw = [w for w in keyword_list if w.lower() in description.lower()]

            with matching_rows_lock:
                matching_rows.append({
                    "row_index": i,
                    "filename": filename,
                    "description": description,
                    "date": date
                })

            _write_scan_decision(files_dir, case_id, i, filename, "PICKED",
                                 f"[scan_rows_polk] keyword(s) matched: {matched_kw}")

        except TimeoutException:
            print(f"[POLK] Row {i} - timeout")
        except NoSuchElementException as e:
            print(f"[POLK] Row {i} - element not found: {e}")
            continue
        except Exception as e:
            print(f"[POLK] Row {i} - unexpected error: {e}")
            traceback.print_exc()

    return matching_rows  # ← return once, after the full loop