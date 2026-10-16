import time

import pysnooper
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from urllib3.exceptions import MaxRetryError

from browser.browser_helpers import element_exists_id, request_url, set_download_dir
from browser.captcha import captcha_solver
from network.network_helpers import reset_vpn


@pysnooper.snoop()
def solve_captcha_polk(driver):
    try:
        #body
        body = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'body')))
        if "blocked" in body.text:
            return 1
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, 'g-recaptcha-response')))
        sitekey = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="myCaptcha"]/div'))).get_attribute(
            "data-sitekey")
        # generate token
        res = captcha_solver(driver, sitekey, driver.current_url)
        print(res)
        if not res:
            return 1
        if element_exists_id(driver,'body'):
            body = driver.find_element(By.ID, 'body')
            if "has been blocked" in body.text:
                reset_vpn(wait=True)
                return 1
            #has been blocked
        driver.execute_script("document.getElementById('g-recaptcha-response').innerHTML = arguments[0];", res)
        return
    except:
        return 1
import pysnooper


def navigate_to_search_polk(driver):
    if element_exists_id(driver,'UCN'):
        return
    try:
        WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.ID, "imgPublicAccess"))
                        ).click()
    except TimeoutException:
        pass

    flag=solve_captcha_polk(driver)
    if flag:
        return 1
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '//*[@id="frmvalidatecaptcha"]/input'))
    ).click()
    time.sleep(15)
    return

def navigate_to_url_polk(driver,case_id):
    try:
        request_url(driver,"https://pro.polkcountyclerk.net/PRO/PublicSearch/PublicSearch")
    except MaxRetryError:
        return 1





def search_case_number_polk(driver,case_number):
    WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.ID, "UCN"))
    ).send_keys(case_number)
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (By.ID, "checkuncheck"))
    ).click()
    WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.ID, "btnSubmit"))
                    ).click()

#
def navigate_to_files_table_polk(driver):
    #
    #
    if "No data" in WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.XPATH, '//*[@id="gridtable"]/tbody/tr/td'))).text:
        return 1
    href=WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="gridtable"]/tbody/tr/td[6]/a'))).get_attribute('href')
    request_url(driver,href)

def open_file_iframe_polk(driver,files_dir):
    set_download_dir(driver, files_dir)
    try:
        iframe_source = WebDriverWait(driver, 1).until(
            EC.presence_of_element_located((By.ID, 'pdfSource')))
        driver.switch_to.frame(iframe_source)
        iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'pdfBinary')))
        driver.switch_to.frame(iframe)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'open-button'))
        ).click()
    except TimeoutException:
        return



@pysnooper.snoop()
def click_on_download_polk(driver,row,download_button):
    
    before_handles = driver.window_handles
    driver.execute_script("arguments[0].click();", download_button)
    time.sleep(1)
    after_handles = driver.window_handles
    while not len(after_handles) - len(before_handles):
        if len(driver.window_handles) > 1:
            driver.switch_to.window(driver.window_handles[-1])
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
            before_handles = driver.window_handles
        driver.execute_script("arguments[0].click();", download_button)
        time.sleep(1)
        after_handles = driver.window_handles
    return set(after_handles) - set(before_handles)


@pysnooper.snoop()
def trigger_download_polk(driver,row,index,download_mgr,before_files,matching_row=None):
    attempts=0
    max_attempts=2
    driver.switch_to.window(driver.window_handles[0])
    download_button = driver.find_element(By.XPATH, f'/html/body/div[1]/section/div[2]/div[1]/table/tbody/tr[{index}]/td[5]/div/img')
    if "blank" in download_button.get_attribute('src').lower() or "not" in download_button.get_attribute('src').lower():
        return 1
    while attempts<max_attempts:
        down_flag = None
        while not down_flag:
            downlaod_handle = click_on_download_polk(driver, row, download_button)
            driver.switch_to.window(downlaod_handle.pop())
            set_download_dir(driver, download_mgr.download_dir)
            open_file_iframe_polk(driver, download_mgr.download_dir)
            down_flag = download_mgr.wait_for_download_start(before_files)
        return


def show_parties_polk(driver):
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '//*[@id="ui-id-2"]'))
    ).click()

def show_dockets_polk(driver):
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '//*[@id="ui-id-1"]'))
    ).click()