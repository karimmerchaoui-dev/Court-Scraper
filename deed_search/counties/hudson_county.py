import time

import pysnooper
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumbase import Driver

from deed_search.browser_helpers import _search_iframes
from deed_search.county_config import CountyConfig, registry


def _navigate_to_search(driver: Driver) -> None:
    """Click the 'Book & Page' tab to reveal the search form."""
    try:
        nav = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, 'btnButton'))
        )
        nav.click()
        nav = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, 'RecordDateFrom'))
        )
    except TimeoutException:
        pass
    nav.clear()
    nav.send_keys("1/1/2000")
    time.sleep(5)

def _return_to_table(driver,i):

    if len(driver.window_handles) >= 2:
        driver.switch_to_window(driver.window_handles[-1])
        driver.close()
    driver.switch_to_window(driver.window_handles[0])


@pysnooper.snoop()
def _trigger_download(driver: Driver,i) -> None:
    """Click the download button on the deed detail page."""
    row = WebDriverWait(driver, 8).until(
        EC.element_to_be_clickable((By.XPATH, f'//*[@id="RsltsGrid"]/div[4]/table/tbody/tr[{i+1}]/td[1]'))
    )
    driver.execute_script("arguments[0].click();", row)
    driver.switch_to_window(driver.window_handles[-1])
    time.sleep(2)  # reduced from 100 — just enough to let the download start
    open_button = _search_iframes(driver,'//*[@id="open-button"]')
    open_button.click()


registry.register(
    CountyConfig(
        name="hudson county",
        url="https://acclaim.hcnj.us/AcclaimWeb/search/SearchTypeBookPage",
        name_url="https://acclaim.hcnj.us/AcclaimWeb/search/SearchTypeName",
        name_submit_button_xpath='/html/body/main/div[1]/div[2]/div/div/form/div[2]/input[2]',
        first_name_xpath='/html/body/main/div[1]/div[2]/div/div/form/div[1]/div[3]/div[2]/input',
        last_name_xpath="/html/body/main/div[1]/div[2]/div/div/form/div[1]/div[3]/div[2]/input",
        book_xpath='//*[@id="BookNumber"]',
        page_xpath='//*[@id="PageNumber"]',
        deed_type_xpath='',
        submit_button_xpath='//*[@id="btnSearch"]',
        deeds_table_xpath='//*[@id="RsltsGrid"]/div[4]/table/tbody',
        row_tag_name="tr",
        return_to_table_func=_return_to_table,
        get_to_download_page_func=None,
        file_trigger_download_func=_trigger_download,
        navigate_to_search_func=_navigate_to_search,
        navigate_to_name_search_func=_navigate_to_search,
        instrument_xpath='//*[@id="InstrumentNumber"]',
        instrument_submit_button_xpath='//*[@id="btnSearch"]',
        navigate_to_instrument_search_func=_navigate_to_search,
        instrument_url='https://acclaim.hcnj.us/AcclaimWeb/search/SearchTypeInstrumentNumber',
        deed_type_values=["All Books"],
        download_timeout=90,
        extra_wait=1.5,
    )
)