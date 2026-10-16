
from humancursor import WebCursor
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from browser.browser_helpers import (
    element_exists_id,
    element_exists_xpath,
    human_type_helper,
    load_cookies,
    refresh_url,
    request_url,
    save_cookies,
    set_download_dir,
    wait_and_click,
    wait_for_page_to_load,
)
from browser.captcha import captcha_solver
from browser.HumanCursorSimulator import *
from utils.formatting import *


def trigger_download_lee(driver, row, index, download_mgr, before_files, matching_row=None):
    down_flag = None
    attempt = 0
    while attempt < 5 and not down_flag:
        set_download_dir(driver, download_mgr.download_dir)
        row_xpath = f'//*[@id="docketCollapse"]/div/div[2]/div[1]/table/tbody/tr[{index}]/td[5]/a'
        driver.switch_to.window(driver.window_handles[0])
        file_element = driver.find_element(By.XPATH, row_xpath)
        try:
            driver.execute_script("arguments[0].click();", file_element)
            down_flag = download_mgr.wait_for_download_start(before_files)
        except NoSuchElementException:
            time.sleep(6)
            print(f"[Lee] No clickable file element found for row {index}")
            return 1



def check_for_error_lee(driver):
    if element_exists_id(driver,"/html/body/div[3]/div/div/h2"):
        error_label=driver.find_element('xpath','/html/body/div[3]/div/div/h2')
        if error_label:
            if "Error Encountered!" in error_label.text.lower():
                return True
    return False

def solve_lee_captcha(driver):
    print("captchaV2submitButton")
    continue_button = driver.find_element(By.ID, 'captchaV2submitButton')
    while True:
        try:
            res = captcha_solver(driver, "6LeKIk4nAAAAAHE9Ozur9gVZ_6HMnYI6x3IGvQAJ", driver.current_url)
            save_cookies(driver, "lee.pkl")
            break
        except TimeoutError:
            print("captcha timed out, retrying")
            refresh_url(driver)
    print(res)
    driver.execute_script("document.getElementById('g-recaptcha-response').innerHTML = " + f"'{res}'")
    driver.execute_script("arguments[0].removeAttribute('disabled');", continue_button)
    while (element_exists_id(driver, 'captchaV2submitButton')):
        driver.execute_script("arguments[0].click();", continue_button)
        time.sleep(1)

def solve_lee_captcha_acamai(driver):
    iframe = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (By.ID, 'sec-cpt-if'))
    )
    driver.switch_to.frame(iframe)
    driver.find_element(By.ID, 'robot-checkbox').click()
    btn = driver.find_element("xpath", '//*[@id="sec-if-cpt-container"]/div/div[2]/div')
    driver.execute_script("arguments[0].className = 'behavioral-button progress-btn';", btn)
    driver.find_element(By.ID, 'progress-button').click()
    while element_exists_id(driver, 'progress-button'):
        wait_and_click(driver,By.ID, 'progress-button')
        time.sleep(2)
    try:
        wait_for_page_to_load(driver)
    except TimeoutException:
        driver.find_element(By.ID, 'progress-button').click()
        time.sleep(5)



def navigate_to_search_lee(driver):
    while (element_exists_id(driver, 'captchaV2submitButton') or element_exists_id(driver,
                                                                                   "sec-cpt-if") or check_for_error_lee(
            driver) or element_exists_id(driver, 'byCaseNumber_CaseNumber')):
        if element_exists_id(driver, 'byCaseNumber_CaseNumber'):
            # Fill the case number field
            return
        if element_exists_id(driver, 'captchaV2submitButton'):
            solve_lee_captcha(driver)

        if element_exists_id(driver, "sec-cpt-if"):
            solve_lee_captcha_acamai(driver)
        if check_for_error_lee(driver):
            driver.refresh()
    return
def navigate_to_url_lee(driver,case_id):
    request_url(driver, "https://matrix.leeclerk.org")
    if not hasattr(driver, 'human_cursor'):
        driver.human_cursor = WebCursor(driver)
    if os.path.exists("lee.pkl"):
        load_cookies(driver, "lee.pkl")

def search_case_number_lee(driver,case_id):
    input_case = driver.find_element(By.ID, 'byCaseNumber_CaseNumber')
    driver.human_cursor.show_cursor()
    human_type_helper(input_case, case_id)
    start_button = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (By.XPATH, '//*[@id="t1"]/div/div/div[1]/form/div[7]/button[2]'))
    )
    driver.human_cursor.click_on(start_button)
    time.sleep(2)
    if element_exists_xpath(driver, '/html/body/div[3]/div/div[1]/ul/li[1]') and "0" in driver.find_element("xpath",'/html/body/div[3]/div/div[1]/ul/li[1]').text:
        return 0
    if element_exists_xpath(driver, '/html/body/h1') and "Access Denied" in driver.find_element("xpath",'/html/body/h1').text:
        print("Access Denied")
        return 3

def navigate_to_files_table_lee(driver):
    if element_exists_id(driver, "sec-cpt-if"):
        solve_lee_captcha_acamai(driver)


