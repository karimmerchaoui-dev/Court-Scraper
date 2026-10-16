import time

import pysnooper
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumbase import Driver

from deed_search.browser_helpers import find_element_in_iframes
from deed_search.county_config import CountyConfig, registry


def _navigate_to_search(driver: Driver) -> None:
    """Click the 'Book & Page' tab to reveal the search form."""
    nav = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '//*[@id="btnButton"]'))
    )
    nav.click()


def _get_to_download_page(driver: Driver,i) -> None:
    """Click the first result row's view button."""
    down = WebDriverWait(driver, 5).until(#
        EC.element_to_be_clickable((By.XPATH, f'/html/body/main/div[5]/div[1]/div[1]/div[3]/div[4]/div/div[1]/div[3]/table/tbody/tr'))
    )
    #//*[@id="center"]/div/div[4]/div[2]/div/div/div[1]/div[1]/button
    down.click()

def _return_to_table(driver,i):
    driver.switch_to_window(driver.window_handles[-1])
    driver.close()
    driver.switch_to_window(driver.window_handles[0])


@pysnooper.snoop()
def _trigger_download(driver: Driver,i) -> None:
    """Click the download button on the deed detail page."""
    driver.switch_to_window(driver.window_handles[-1])
    time.sleep(2)  # reduced from 100 — just enough to let the download start
    find_element_in_iframes(driver,"/html/body/div/div/a/button").click()
    #


registry.register(
    CountyConfig(
        name="duval county",
        url="https://or.duvalclerk.com/search/SearchTypeBookPage",

        book_xpath='//*[@id="BookNumber"]',
        page_xpath='//*[@id="PageNumber"]',
        deed_type_xpath='',
        submit_button_xpath='/html/body/div[1]/div[3]/div/div[1]/div/div/div/div[5]/form/div[2]/div[3]/button[2]',
        deeds_table_xpath='//table[@role="grid"]/tbody',
        row_tag_name='tr',
        return_to_table_func=_return_to_table,
        get_to_download_page_func=_get_to_download_page,
        file_trigger_download_func=_trigger_download,
        navigate_to_search_func=_navigate_to_search,

        deed_type_values=["All Books"],
        download_timeout=90,
        extra_wait=1.5,
    )
)