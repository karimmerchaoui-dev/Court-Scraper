"""
NJ-specific case processing — login, search, download for New Jersey courts.
"""

import os
import random
import sys
import threading
import time
import traceback

from humancursor import WebCursor
from selenium.common.exceptions import (
    ElementNotInteractableException,
    InvalidSessionIdException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from urllib3.exceptions import MaxRetryError, ReadTimeoutError

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.skip_manager import SkipCase, check_skip

from app import log_message, update_case_status
from browser.browser_helpers import (
    check_error_message,
    element_exists_id,
    element_exists_xpath,
    get_thread_number,
    make_sure_tab1_is_selected,
    maximize_driver,
    refresh_url,
    request_url,
    scroll_randomly,
    set_download_dir,
    simulate_human_browsing2,
    wait_for_page_to_load,
)
from browser.HumanCursorSimulator import HumanCursorSimulator
from config_ import NJ_LOGIN_PAGE, accounts
from counties.nj_helpers import check_case_type_nj, check_main_frame
from download.scanners import scan_table_multithreaded


def navigate_to_url_nj(driver):
    """Fast and reliable navigation without repeatedly checking driver.current_url"""
    if driver.current_url != NJ_LOGIN_PAGE:
        if element_exists_id(driver, 'caseActionTbId2'):
            refresh_url(driver)
        request_url(driver,
                    NJ_LOGIN_PAGE)

def is_logged_in(driver, timeout=5):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.ID, 'searchByDocForm:idCivilDocketNum')))
        return True
    except:
        return False


def human_type(element, text):
    driver = element._parent
    if not hasattr(driver, 'human_cursor'):
        driver.human_cursor = HumanCursorSimulator(driver)
    field_id = element.get_attribute('id') or ''
    if 'password' in field_id.lower():
        typing_speed = "slow"
    else:
        typing_speed = random.choice(["normal", "fast"])
    driver.human_cursor.human_type(element, text, typing_speed=typing_speed)


# ══════════════════════════════════════════════════════════════════════════════
# NJ LOGIN
# ══════════════════════════════════════════════════════════════════════════════

def login_nj(driver, account, driver_pool, cookie_file="login_cookies1.pkl"):
    driver.state = "logging in"
    cursor = WebCursor(driver)
    if is_logged_in(driver):
        return
    user_id = account["user_id"]
    password = account["password"]
    for attempt in range(1, 4):
        try:
            captcha = check_main_frame(driver, driver_pool)
            if captcha:
                return 1
            print(f"{threading.current_thread().name}: 🔐 Attempt {attempt} to login...")
            navigate_to_url_nj(driver)
            wait = WebDriverWait(driver, 10)
            username_field = wait.until(EC.presence_of_element_located((By.ID, 'userid')))
            cursor.show_cursor()
            cursor.click_on(username_field)
            human_type(username_field, user_id)
            password_field = wait.until(EC.presence_of_element_located((By.ID, 'passwd')))
            cursor.click_on(password_field)
            human_type(password_field, password)
            login_button = wait.until(EC.presence_of_element_located((By.ID, 'a')))
            while not login_button.get_attribute('disabled'):
                cursor.click_on(login_button)
            wait.until(EC.presence_of_element_located((By.ID, "searchByDocForm:idCivilDocketNum")))
            return
        except (TimeoutException, NoSuchElementException, StaleElementReferenceException,
                ReadTimeoutError, InvalidSessionIdException):
            print(f"{threading.current_thread().name}: ⚠️ Login attempt {attempt} failed. Retrying...")
            navigate_to_url_nj(driver)
    return 1


# ══════════════════════════════════════════════════════════════════════════════
# NJ NAVIGATION
# ══════════════════════════════════════════════════════════════════════════════

def navigate_to_search_nj(driver, account, cookie_file, driver_pool):
    while not (is_logged_in(driver, 3)):
        login_flag = login_nj(driver, account, driver_pool, cookie_file)
        if login_flag:
            return 1


def navigate_to_files_table_nj():
    pass


# ══════════════════════════════════════════════════════════════════════════════
# NJ DOCKET ENTRY
# ══════════════════════════════════════════════════════════════════════════════

def enter_docket_number_nj(driver, docket, year, wait):
    cursor = WebCursor(driver)
    cursor.show_cursor()
    docket_num_field = wait.until(EC.presence_of_element_located((By.ID, 'searchByDocForm:idCivilDocketNum')))
    cursor.click_on(docket_num_field)
    human_type(docket_num_field, docket)
    docket_year_field = wait.until(EC.presence_of_element_located((By.ID, 'searchByDocForm:idCivilDocketYear')))
    time.sleep(random.uniform(0.05, 1))
    cursor.click_on(docket_year_field)
    human_type(docket_year_field, year)
    search_button = wait.until(EC.presence_of_element_located((By.ID, 'searchByDocForm:searchBtnDummy')))
    cursor.click_on(search_button)
    wait_for_page_to_load(driver)
    time.sleep(random.uniform(0.5, 1))
    try:
        error_msg = ""
        while not error_msg:
            cursor.click_on(search_button)
            error_msg = wait.until(EC.presence_of_element_located((By.ID, 'errInfoMsg'))).text
    except Exception:
        pass
    time.sleep(random.randint(1, 2))


def search_case_number_nj(driver, year, docket, driver_pool, account, get_current_batch_folder):

    case_id = f"f-{docket}-{year}"
    update_case_status(driver, case_id, "New Jersey",
                       f"Entering docket (Thread {get_thread_number()})",
                       details=f"Entering f-{docket}-{year}")
    driver.state = "entering docket"
    max_resets = random.randint(1, 2)
    max_attempts = random.randint(1, 2)
    wait = WebDriverWait(driver, 6)

    for reset_attempt in range(1, max_resets + 1):
        for attempt in range(1, max_attempts + 1):
            maximize_driver(driver)
            print(f"\n{threading.current_thread().name}: Attempt {attempt}/{max_attempts} to enter {year}-{docket}")
            try:
                if check_for_table(driver, timeout=10):
                    return 0
                enter_docket_number_nj(driver, docket, year, wait)
                if element_exists_id(driver, 'searchByDocForm:idCivilDocketNum'):
                    continue
                time.sleep(random.randint(1, 2))
                wait_for_page_to_load(driver)
                cek = check_error_message(driver, 6)
                ct = check_for_table(driver)
                if not cek and ct:
                    print(f"{threading.current_thread().name}: ✅ Search completed!")
                    return 0
                else:
                    wait.until(EC.presence_of_element_located((By.ID, 'errInfoMsg')))
                    if element_exists_xpath(driver, "/html/body/div[1]/div/div/div[1]/div[2]/div[2]/h2[1]"):
                        if random.random() < 0.5:
                            request_url(driver, "https://portal-cloud.njcourts.gov/prweb/PRAuth/app/ESSOPortal")
                            time.sleep(random.uniform(3, 7))
                        request_url(driver, NJ_LOGIN_PAGE)
                        try:
                            error = driver.find_element('xpath', '/html/body/div[1]/div/div/div[1]/div[1]/div')
                            if error:
                                print("CAPTCHA:", error.text)
                        except Exception:
                            pass
            except (StaleElementReferenceException, ElementNotInteractableException):
                if not check_error_message(driver, 1) and check_for_table(driver, timeout=1):
                    return
                make_sure_tab1_is_selected(driver)
            except TimeoutException:
                request_url(driver, NJ_LOGIN_PAGE)
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
                traceback.print_exc()
                navigate_to_url_nj(driver)
                refresh_url(driver)

        error_msg = wait.until(EC.presence_of_element_located((By.ID, 'errInfoMsg'))).text
        if "not found" in error_msg.lower():
            return 5
        simulate_human_browsing2(driver)
        time.sleep(random.uniform(3, 8))
        request_url(driver, NJ_LOGIN_PAGE)

    if driver_pool.is_any_downloading():
        return search_case_number_nj(driver, year, docket, driver_pool, account, current_batch_folder)

    final_output_folder = get_current_batch_folder()
    file_dir = f"{final_output_folder}/f-{docket}-{year}-new jersey"
    log_message(f"Max resets exceeded for account {account['user_id']}, switching to backup...")
    driver = driver_pool.close_and_refill(driver)
    set_download_dir(driver, file_dir)
    index = account["index"]
    cookie_file = f"cookies{index}.pkl"
    if os.path.exists(cookie_file):
        os.remove(cookie_file)
    backup_accounts = [acc for acc in accounts if acc["type"] == "backup"]
    if backup_accounts:
        backup_account = random.choice(backup_accounts)
        log_message(f"Switching to backup account: {backup_account['user_id']}")
        return 1
    log_message("No backup accounts available!")
    return 1





# ══════════════════════════════════════════════════════════════════════════════
# NJ DOWNLOAD FILES
# ══════════════════════════════════════════════════════════════════════════════

def download_files_nj(driver, year, docket, driver_pool, files_dir, account, start_index=1,
                      keyword_list=None, unwanted_list=None, report_cases=None, running=True):

    case_id = f"f-{docket}-{year}"
    update_case_status(driver, case_id, "New Jersey", f"Downloading (Thread {get_thread_number()})",
                       details="Checking for files")
    driver.state = "downloading"
    matching_rows = []
    matching_rows_lock = threading.Lock()

    try:
        table = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "caseActionTbId2")))
    except Exception:
        traceback.print_exc()
        return start_index

    rows = table.find_elements(By.TAG_NAME, "tr")
    total_rows = len(rows) - 1
    driver.state = "downloading"

    print(f"get_keywords : {keyword_list}")
    matching_files = scan_table_multithreaded(
        driver, case_id, files_dir, report_cases, total_rows,
        matching_rows, matching_rows_lock,
        keyword_list, unwanted_list, "nj",
        start_index=start_index
    )

    check_case_type_nj(driver, case_id, report_cases)
    print(f" matching files {matching_files}")

    for file in matching_files:
        check_skip()  # ← between NJ files
        row_index = file['row_index']
        name = file['name']
        filename = file['filename']
        rip = False

        update_case_status(driver, case_id, "New Jersey",
                           f"Downloading (Thread {get_thread_number()})",
                           details=f"Downloaded file {row_index + 1}/{total_rows}: {filename} ({case_id})")

        start_time = time.time()
        if not running:
            log_message("Processing stopped by user")
            break

        try:
            current_time = time.time()
            if len(driver.window_handles) > 3 and (current_time - start_time) > 13:
                print("More than one tab open for over 13 seconds. Closing and refreshing.")
                while True:
                    try:
                        refresh_url(driver)
                        break
                    except ReadTimeoutError:
                        time.sleep(1)
                break

            success = download_file_nj(driver, filename, files_dir, row_index, case_id,
                                       year, docket, account, rip, name)
            if not success:
                print(f"{threading.current_thread().name}: ❌ Failed to download → returning index {row_index}")
                return row_index

        except Exception:
            traceback.print_exc()
            driver_pool.release_driver(driver)
            return row_index

    update_case_status(driver, case_id, "New Jersey", "Completed", details="All files downloaded")
    report_cases[case_id]['status'] = "Completed"
    return None


# ══════════════════════════════════════════════════════════════════════════════
# NJ PROCESS CASE
# ══════════════════════════════════════════════════════════════════════════════




def process_nj_case(year, docket, case_type, account, driver, driver_pool,
                    files_dir=".", start_index=0, browse_to_a_different_page=False,
                    state=None,
                    keyword_list=None, unwanted_list=None,
                    force_stop=False, running=True,
                    report_cases=None, input_file=None,
                    total_cases=0, get_current_batch_folder=None,
                    update_progress=None, set_status_text=None,processed=None,skip_current=None,_skip_target_thread_id=None,
                    current_batch_folder=None,update_progress_func=None,set_status_text_func=None
                    ,log_message_func=None,update_case_status_func=None,mark_case_as_processed_func=None):
    """
    Process a single NJ case with dependency injection.
    All dependencies are passed as parameters instead of importing main.
    """
    
    # Import here to avoid circular imports
    
    # Set defaults for injected dependencies if None
    report_cases = report_cases or {}
    keyword_list = keyword_list or []
    unwanted_list = unwanted_list or []
    running = running or False
    force_stop = force_stop or False
    input_file = input_file or ""
    processed = processed or 0
    total_cases = total_cases or 0
    current_batch_folder = current_batch_folder or "."
    skip_current = skip_current or False
    _skip_target_thread_id = _skip_target_thread_id or None
    
    # Set default callback functions if None
    if log_message_func is None:
        log_message_func = print
    if update_case_status_func is None:
        update_case_status_func = lambda driver, case_id, county, status, details="": print(f"{case_id}: {status} - {details}")
    if update_progress_func is None:
        update_progress_func = lambda value: None
    if set_status_text_func is None:
        set_status_text_func = lambda text: None
    if mark_case_as_processed_func is None:
        mark_case_as_processed_func = lambda file, case: None
    
    # Set local references to mutable objects
    skip_current = skip_current
    _skip_target_thread_id = threading.current_thread().ident
    
    print(f"keyword_list : {keyword_list}")
    
    if force_stop:
        return
    
    case_id = f"{year}-{docket}"
    t1 = time.time()
    
    if not running:
        return
    
    print(f"processing {year, docket}")
    user_id = account["user_id"]
    password = account["password"]
    index = account["index"]
    cookie_file = f"cookies{index}.pkl"
    thread_num = get_thread_number()
    
    try:
        update_case_status_func(driver, case_id, "New Jersey", f"Starting (Thread {thread_num})",
                               details="Navigating to NJ Courts portal...")
        navigate_to_url_nj(driver)
        try:
            wait_for_page_to_load(driver)
        except TimeoutException:
            pass
        
        check_skip()  # ← after initial navigation
        
        update_case_status_func(driver, case_id, "New Jersey", f"Logging in (Thread {thread_num})",
                               details="Attempting login")
        navigate_flag = navigate_to_search_nj(driver, account, cookie_file, driver_pool)
        if navigate_flag:
            new_driver = driver_pool.close_and_refill(driver)
            backup_accounts = [acc for acc in accounts if acc["type"] == "backup"]
            if backup_accounts:
                backup_account = random.choice(backup_accounts)
                process_nj_case(
                    year, docket, case_type, backup_account, new_driver, driver_pool,
                    files_dir=files_dir, start_index=start_index,
                    browse_to_a_different_page=True,
                    report_cases=report_cases,
                    keyword_list=keyword_list,
                    unwanted_list=unwanted_list,
                    running=running,
                    force_stop=force_stop,
                    input_file=input_file,
                    processed=processed,
                    total_cases=total_cases,
                    current_batch_folder=current_batch_folder,
                    skip_current=skip_current,
                    _skip_target_thread_id=_skip_target_thread_id,
                    update_progress_func=update_progress_func,
                    set_status_text_func=set_status_text_func,
                    log_message_func=log_message_func,
                    update_case_status_func=update_case_status_func,
                    mark_case_as_processed_func=mark_case_as_processed_func
                )
                return
            process_nj_case(
                year, docket, case_type, account, driver, driver_pool,
                files_dir=files_dir, start_index=start_index,
                browse_to_a_different_page=True,
                report_cases=report_cases,
                keyword_list=keyword_list,
                unwanted_list=unwanted_list,
                running=running,
                force_stop=force_stop,
                input_file=input_file,
                processed=processed,
                total_cases=total_cases,
                current_batch_folder=current_batch_folder,
                skip_current=skip_current,
                _skip_target_thread_id=_skip_target_thread_id,
                update_progress_func=update_progress_func,
                set_status_text_func=set_status_text_func,
                log_message_func=log_message_func,
                update_case_status_func=update_case_status_func,
                mark_case_as_processed_func=mark_case_as_processed_func
            )
            return
        
        check_skip()  # ← after login
        
        scroll_randomly(driver)
        
        try:
            enter_flag = search_case_number_nj(driver, year, docket, driver_pool, account, current_batch_folder)
            if enter_flag == 5:
                return
            if enter_flag:
                process_nj_case(
                    year, docket, case_type, account, driver, driver_pool,
                    files_dir=files_dir, browse_to_a_different_page=True,
                    report_cases=report_cases,
                    keyword_list=keyword_list,
                    unwanted_list=unwanted_list,
                    running=running,
                    force_stop=force_stop,
                    input_file=input_file,
                    processed=processed,
                    total_cases=total_cases,
                    current_batch_folder=current_batch_folder,
                    skip_current=skip_current,
                    _skip_target_thread_id=_skip_target_thread_id,
                    update_progress_func=update_progress_func,
                    set_status_text_func=set_status_text_func,
                    log_message_func=log_message_func,
                    update_case_status_func=update_case_status_func,
                    mark_case_as_processed_func=mark_case_as_processed_func
                )
                return
            
            check_skip()  # ← after docket entry
            
            navigate_to_files_table_nj()
            row_index = download_files_nj(driver, year, docket, driver_pool, files_dir, account, start_index,
                              keyword_list=keyword_list, unwanted_list=unwanted_list,
                              report_cases=report_cases, running=running)
        except TimeoutException:
            process_nj_case(
                year, docket, case_type, account, driver, driver_pool,
                files_dir=files_dir, start_index=start_index,
                report_cases=report_cases,
                keyword_list=keyword_list,
                unwanted_list=unwanted_list,
                running=running,
                force_stop=force_stop,
                input_file=input_file,
                processed=processed,
                total_cases=total_cases,
                current_batch_folder=current_batch_folder,
                skip_current=skip_current,
                _skip_target_thread_id=_skip_target_thread_id,
                update_progress_func=update_progress_func,
                set_status_text_func=set_status_text_func,
                log_message_func=log_message_func,
                update_case_status_func=update_case_status_func,
                mark_case_as_processed_func=mark_case_as_processed_func
            )
            return
        
        if row_index or row_index == 0:
            print(f"there was an issue in index {row_index}")
            driver = driver_pool.close_and_refill(driver)
            process_nj_case(
                year, docket, case_type, account, driver, driver_pool,
                files_dir=files_dir, start_index=row_index,
                report_cases=report_cases,
                keyword_list=keyword_list,
                unwanted_list=unwanted_list,
                running=running,
                force_stop=force_stop,
                input_file=input_file,
                processed=processed,
                total_cases=total_cases,
                current_batch_folder=current_batch_folder,
                skip_current=skip_current,
                _skip_target_thread_id=_skip_target_thread_id,
                update_progress_func=update_progress_func,
                set_status_text_func=set_status_text_func,
                log_message_func=log_message_func,
                update_case_status_func=update_case_status_func,
                mark_case_as_processed_func=mark_case_as_processed_func
            )
            return
        
        driver_pool.release_driver(driver)
        t2 = time.time()
        report_cases[case_id]['processing_duration'] = f"{t2 - t1:.2f}"
        log_message_func(f"✔️ Took {t2 - t1:.2f}s to process {case_id}")
        mark_case_as_processed_func(input_file, f"f-{docket}-{year}")
        
        if processed:
            processed += 1
            update_progress_func(processed / total_cases)
            set_status_text_func(f"Processing... {processed}/{total_cases}")
        
    except SkipCase:
        log_message_func(f"⏭️  Skipped NJ case: {case_id}")
        if case_id in report_cases:
            report_cases[case_id]['status'] = "Skipped"
        update_case_status_func(driver, case_id, "New Jersey", "Skipped", details="Skipped by user")
        try:
            driver_pool.release_driver(driver)
        except Exception:
            pass
        finally:
            skip_current = False
            _skip_target_thread_id = None
    
    except (ConnectionError, MaxRetryError) as net_err:
        driver_pool.reset_vpn_pool(driver)
        new_driver = driver_pool.close_and_refill(driver)
        process_nj_case(
            year, docket, case_type, account, new_driver, driver_pool,
            files_dir, start_index,
            report_cases=report_cases,
            keyword_list=keyword_list,
            unwanted_list=unwanted_list,
            running=running,
            force_stop=force_stop,
            input_file=input_file,
            processed=processed,
            total_cases=total_cases,
            current_batch_folder=current_batch_folder,
            skip_current=skip_current,
            _skip_target_thread_id=_skip_target_thread_id,
            update_progress_func=update_progress_func,
            set_status_text_func=set_status_text_func,
            log_message_func=log_message_func,
            update_case_status_func=update_case_status_func,
            mark_case_as_processed_func=mark_case_as_processed_func
        )
        return
    
    except AttributeError:
        new_driver = driver_pool.close_and_refill(driver)
        process_nj_case(
            year, docket, case_type, account, new_driver, driver_pool,
            files_dir, start_index,
            report_cases=report_cases,
            keyword_list=keyword_list,
            unwanted_list=unwanted_list,
            running=running,
            force_stop=force_stop,
            input_file=input_file,
            processed=processed,
            total_cases=total_cases,
            current_batch_folder=current_batch_folder,
            skip_current=skip_current,
            _skip_target_thread_id=_skip_target_thread_id,
            update_progress_func=update_progress_func,
            set_status_text_func=set_status_text_func,
            log_message_func=log_message_func,
            update_case_status_func=update_case_status_func,
            mark_case_as_processed_func=mark_case_as_processed_func
        )
        return
    
    except Exception as e:
        error = str(e)
        if "Stacktrace" in error:
            error = error.split("Stacktrace")[0]
        update_case_status_func(driver, case_id, "New Jersey", f"Error (Thread {thread_num + 1})", details=error)
        traceback.print_exc()
        driver_pool.release_driver(driver)
        raise