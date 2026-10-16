import sys
import time
import traceback

sys.path.append(r"C:\Users\pc\PycharmProjects\Court-Scraper")

import pysnooper
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

from browser.browser_helpers import element_exists_xpath, request_url, wait_and_click
from download.download_monitor import set_download_dir


@pysnooper.snoop()
def trigger_download_osceola(driver,row,row_index,download_mgr,before_files,matching_row=None):
    down_flag = None
    attempt = 0
    #//*[@id="c_DocketsPanel"]/div/table/tbody[{row_index}]/tr/td[6]/div
    #//*[@id="cphBody_dDockets_gvDocket"]/tbody/tr[6]
    #//*[@id="cphBody_dDockets_gvDocket"]/tbody/tr[84]
    #//*[@id="cphBody_dDockets_gvDocket"]/tbody/tr[6]/td[1]
    while attempt < 3 and not down_flag:
        try:
            driver.switch_to_window(driver.window_handles[0])
            file_button = row.find_element(By.XPATH, f'/html/body/div[3]/table/tbody/tr/td[2]/div/table/tbody/tr/td/table[2]/tbody/tr[1]/td[2]/div[2]/div[2]/div/div[7]/div/div/div[2]/div/div/div/table/tbody/tr[{row_index}]/td[3]/a')
            file_button.click()
            time.sleep(1)
            driver.switch_to_window(driver.window_handles[-1])
            set_download_dir(driver, download_mgr.download_dir)
            print(f"download_mgr.download_dir : {download_mgr.download_dir}")
            WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.ID, 'open-button'))).click()
            down_flag = download_mgr.wait_for_download_start(before_files)
            attempt+=1
        except TimeoutException:
            down_flag = download_mgr.wait_for_download_start(before_files)
            if down_flag:
                return
            attempt+=1
        except Exception as e:
            if 2 < len(driver.window_handles):
                driver.switch_to_window(driver.window_handles[-1])
                driver.close()
                driver.switch_to_window(driver.window_handles[0])
            traceback.print_exc()
            attempt+=1


#https://courts.osceolaclerk.com/BenchmarkWeb/Home.aspx/Search
def navigate_to_url_osceola(driver,case_id):
    request_url(driver,'https://courts.osceolaclerk.com/BenchmarkWeb/Home.aspx/Search')

def navigate_to_search_osceola(driver):
    #
    wait_and_click(driver, By.XPATH, '//*[@id="mainTableContent"]/tbody/tr/td/table/tbody/tr[2]/td[2]/div/div/div[1]/div/div[2]')


def search_case_number_osceola(driver,case_num):
    #
    case_num_field = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable(
            (By.ID, 'caseNumber'))
    )
    case_num_field.send_keys(case_num)
    wait_and_click(driver, By.ID, 'searchButton')

    #
    WebDriverWait(driver, 5).until(
        EC.presence_of_element_located(
            (By.XPATH, '//*[@id="mainTableContent"]/tbody/tr/td/table/tbody'))
    )
    #
    if element_exists_xpath(driver,'//*[@id="mainTableContent"]/tbody/tr/td/table/tbody/tr[2]/td[2]/table/tbody/tr/td/div/div[1]/div[1]/div[3]') and "0" in driver.find_element("xpath", '//*[@id="mainTableContent"]/tbody/tr/td/table/tbody/tr[2]/td[2]/table/tbody/tr/td/div/div[1]/div[1]/div[3]').text:
        return 1

import pysnooper


@pysnooper.snoop()
def navigate_to_files_table_osceola(driver):
    time.sleep(1)
    try:
        WebDriverWait(driver, 10).until(lambda d: (
                d.execute_script("return document.readyState") == "complete"
                and "loading" not in (
                            d.execute_script("return document.body ? document.body.innerText : ''") or "").lower()
        ))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

    except Exception:
        pass
    pass

