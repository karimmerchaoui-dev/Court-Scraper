import os
import re
import time

import pysnooper
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from browser.browser_helpers import (
    element_exists_id,
    maximize_driver,
    request_url,
    wait_and_click,
    wait_for_page_to_load,
)
from download.download_monitor import open_downloads_tab, set_download_dir


@pysnooper.snoop()
def trigger_download_miami(driver, row, row_index, download_mgr, before_files, matching_row=None):
    href = matching_row['href']
    down_flag = None
    attempt = 0
    while attempt < 5 and not down_flag:
        set_download_dir(driver, download_mgr.download_dir)
        if href:
            driver.switch_to.window(driver.window_handles[0])
            try:
                button = WebDriverWait(driver, 2).until(
                    EC.presence_of_element_located((By.XPATH, f'//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]/div[{row_index}]/div[1]/div'))
                )
            except TimeoutException:
                return 2
            driver.execute_script("arguments[0].scrollIntoView();", button)
            driver.execute_script("arguments[0].click();", button)
            download_single_file_md(driver, button, download_mgr.download_dir)
            down_flag = download_mgr.wait_for_download_start(before_files)
            if element_exists_id(driver, 'c_doc_view2_webcaptcha_CaptchaImageDiv'):
                return 2
        else:
            return 1
        open_downloads_tab(driver)

def navigate_to_url_md(driver,case_id):
    request_url(driver, "https://www2.miamidadeclerk.gov/UserManagementServices")



@pysnooper.snoop()
def navigate_to_files_table_md(driver):
    driver.state = "downloading"
    docket_files = WebDriverWait(driver, 25).until(
        EC.presence_of_element_located((By.XPATH, '//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[1]/div'))
    )
    driver.execute_script("arguments[0].click();", docket_files)
    time.sleep(0.5)



@pysnooper.snoop()
def navigate_to_search_md(driver, username, password):
    userName_field = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.XPATH, '/html/body/div/div/main/form/div[2]/div[1]/div[2]/div[1]/div/input'))
    )
    password_field = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.XPATH, '/html/body/div/div/main/form/div[2]/div[1]/div[2]/div[2]/div/input'))
    )


    userName_field.send_keys(username)
    password_field.send_keys(password)
    wait_and_click(driver, By.XPATH, '/html/body/div/div/main/form/div[2]/div[1]/div[2]/div[4]/input')

    time.sleep(1)
    driver.get("https://www2.miamidadeclerk.gov/ocs")

def parse_miami_case_id(case_str):
    """
    Extract (year, court_type, seq) from Miami case formats:
      - '2022-CA-007845' -> ('2022', 'CA', '007845')
      - '22-CA-7845'     -> ('2022', 'CA', '7845')
      - '2022-007845'    -> ('2022', 'CA', '007845')
    """
    case_str = str(case_str).strip()
    if '-' in case_str:
        parts = [p.strip() for p in case_str.split('-') if p.strip()]
        year, court_type, seq = None, None, None
        for p in parts:
            if re.fullmatch(r'(?:19\d{2}|20\d{2}|\d{2})', p) and not year:
                year = p if len(p) == 4 else f"20{p}"
            elif re.fullmatch(r'[A-Za-z]{2,3}', p) and not court_type:
                court_type = p.upper()
            elif re.fullmatch(r'\d+', p) and not seq:
                seq = p
        if year and seq:
            return year, court_type or "CA", seq

    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', case_str)
    if not year_match:
        year_match = re.search(r'\b(\d{2})\b', case_str)
        year = f"20{year_match.group(1)}" if year_match else ""
    else:
        year = year_match.group(1)

    type_match = re.search(r'([A-Za-z]{2,3})', case_str)
    court_type = type_match.group(1).upper() if type_match else "CA"

    digits = re.findall(r'\d+', case_str)
    seq = next((d for d in digits if d != year and d != year[-2:]), digits[-1] if digits else "")
    return year, court_type, seq

@pysnooper.snoop()
def search_case_number_md(driver, case_id=None, court_type=None, seq=None):
    """
    Search case in Miami-Dade portal.
    Supports both pipeline call `search_case_number_md(driver, case_id)`
    and legacy `search_case_number_md(driver, year, court_type, seq)`.
    """
    if court_type is None and seq is None:
        year, court_type, seq = parse_miami_case_id(case_id)
    else:
        year = str(case_id).strip()
        court_type = str(court_type).strip().upper()
        seq = str(seq).strip()

    print(f"🔍 [Miami-Dade] Searching -> Year: '{year}', Type: '{court_type}', Seq: '{seq}'")

    while True:
        try:
            maximize_driver(driver)
            loca_case = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, '/html/body/div/div/main/div/div[3]/div[2]/div/div[2]/div[3]/div[1]/span'))
            )
            break
        except TimeoutException:
            driver.get("https://www2.miamidadeclerk.gov/ocs")

    driver.execute_script("arguments[0].click();", loca_case)
    time.sleep(1)

    select = Select(WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, 'caseCode'))))
    caseYear = Select(WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, 'caseYear'))))

    # Select Court Type
    if court_type == "CA":
        try:
            select.select_by_visible_text('CA - Circuit Civil')
        except Exception:
            select.select_by_value('CA')
    elif court_type == "CC":
        try:
            select.select_by_visible_text('CC - County Civil')
        except Exception:
            select.select_by_value('CC')
    else:
        for opt in select.options:
            if court_type in opt.text.upper() or opt.get_attribute('value') == court_type:
                select.select_by_visible_text(opt.text)
                break

    # Select Year (handles both 4-digit and 2-digit options)
    year_str = str(year)
    alt_year = year_str[-2:] if len(year_str) == 4 else f"20{year_str}"
    year_selected = False
    for y_val in (year_str, alt_year):
        try:
            caseYear.select_by_visible_text(y_val)
            year_selected = True
            break
        except Exception:
            pass

    if not year_selected:
        for opt in caseYear.options:
            if opt.text.strip() in (year_str, alt_year):
                caseYear.select_by_visible_text(opt.text)
                break

    # Enter Sequence / Case Number
    seq_input = driver.find_element(By.ID, 'caseSeq')
    seq_input.clear()
    seq_input.send_keys(seq)

    # Click Search Submit
    driver.find_element(By.XPATH, '/html/body/div[1]/div/main/div/div[3]/div[3]/form/div[4]/button[1]').click()
    time.sleep(1)
    return 0

@pysnooper.snoop()
def download_single_file_md(driver,file_button,files_dir):
    driver.execute_script("arguments[0].click();", file_button)
    time.sleep(1)
    downloads_tab = driver.window_handles[-1]
    driver.switch_to.window(downloads_tab)
    wait_for_page_to_load(driver)
    time.sleep(1)
    button_xpath = '//*[@id="content"]/div/div/div[2]/div/div[3]/div/div/div/div[1]/div/div[2]/div[1]/div/div[3]/div[4]/div/div/button'
    set_download_dir(driver, files_dir)
    maximize_driver(driver)
    wait_and_click(driver, By.XPATH, button_xpath)
    time.sleep(1)
    driver.close()
    driver.switch_to.window(driver.window_handles[0])







@pysnooper.snoop()
def process_md_case(year,case_number,case_type, driver, driver_pool, files_dir):

    case_id = f"{year}-{case_type}-{case_number}-O"
    try:
        update_case_status(driver,case_id, "Miami Dade", "Starting", details="Navigating to miamidadeclerk.gov")
        # 1
        navigate_to_url_md(driver)

        miami_user = os.getenv("MIAMI_CLERK_USER", "")
        miami_pass = os.getenv("MIAMI_CLERK_PASS", "")
        navigate_to_search_md(driver, miami_user, miami_pass)
        # 2
        time.sleep(10)
        search_case_number_md(driver, year, case_type, case_number)
        time.sleep(1)
        set_download_dir(driver, files_dir)

        navigate_to_files_table_md(driver)
        #table :
        #case type :
        #//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]/div
        download_files(driver, files_dir, case_id,"miami",'//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]','div','//*[@id="content"]/div/div[5]/div/div[2]/div[1]/div/div[5]/div[2]',"https://www2.miamidadeclerk.gov/")

    except (TimeoutException, StaleElementReferenceException, MaxRetryError) as e:
        print(f"{type(e).__name__}")
        time.sleep(1)

    except ReadTimeoutError:
        print("ReadTimeoutError")
        #//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]/div[37]/div[1]/p
        #//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]/div[3]/div/div[5]/p[2]
        driver_pool.reset_vpn_pool(driver)
        reset_and_retry(process_md_case, driver, driver_pool)
        return
    except Exception:
        traceback.print_exc()

    finally:
        # ✅ Always release the driver, even on exceptions
        driver_pool.release_driver(driver)
        global processed, total_cases
        processed += 1
        progress = processed / total_cases
        update_progress(progress)
        status_text.set(f"Processing... {processed}/{total_cases}")



@pysnooper.snoop()
def download_files_md(driver, case_id, files_dir, max_retries=3):

    downloadable_dockets = WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located(
            (By.XPATH,
             '//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]/div[starts-with(@class, "TitleSearchTab")]')
        )
    )


    date_xpath = '//*[@id="content"]/div/div[5]/div/div[2]/div[5]/div/div[2]/div[3]/div[2]/div[2]/div/div[2]/p[2]'
    update_case_status(driver,case_id, "Miami Dade", "Downloading", details="Checking for files")
    for i in downloadable_dockets:
        file_button = i.find_element("xpath", "./div[1]/div")
        docket_entry = i.find_element("xpath", "./div[2]/div/div[5]/p[2]")
        comment = i.find_element("xpath", "./div[2]/div/div[6]/p[2]")
        date = i.find_element("xpath", date_xpath)
        # Retry loop per file
        attempt = 0
        while attempt < max_retries:
            attempt += 1
            try:
                raw_desc=generate_safe_filename(f"{docket_entry.text}_{comment.text}")

                if not _should_download_file(raw_desc):
                    break  # Skip this file, no need to retry


                download_single_file_md(driver,file_button,files_dir)

                filename = generate_safe_filename(f"{raw_desc}_{date}")
                update_case_status(driver,case_id, "Miami Dade", "Downloading",
                                   details=f"Downloading file {i + 1}/{len(downloadable_dockets) - 1}: {filename} ({case_id})")

                main_window = driver.current_window_handle
                new_window = [w for w in driver.window_handles if w != main_window][0]
                driver.switch_to.window(new_window)

                try:

                    before_files = set(glob.glob(os.path.join(files_dir, "*.pdf")))

                    open_downloads_tab(driver)
                    downloads_tab = driver.window_handles[-1]
                    driver.switch_to_window(downloads_tab)
                    success = wait_for_new_download_and_rename(driver, files_dir, before_files, filename,case_id,county="Miami Dade")
                    driver.close()


                    if not success:
                        print(f"❌ Failed to download {filename}")
                except Exception:
                    traceback.print_exc()
                    raise  # To retry on exceptions inside popup handling
                finally:
                    driver.switch_to.window(main_window)

                # If everything succeeded, break retry loop and continue to next file
                break

            except (TimeoutException, WebDriverException, StaleElementReferenceException,
                    ElementClickInterceptedException, NoSuchElementException, ElementNotInteractableException) as e:
                print(f"⚠️ Exception on file {i+1}, attempt {attempt}/{max_retries}: {e}")
                if attempt == max_retries:
                    print(f"❌ Max retries reached for file {i+1}, skipping...")
                else:
                    time.sleep(3)  # Wait before retry
            except Exception as e:
                print(f"❌ Unexpected error on file {i}: {e}")
                traceback.print_exc()
                break  # Skip to next file on unexpected error
    update_case_status(driver,case_id, "Miami Dade", "Completed", details="All files downloaded")

