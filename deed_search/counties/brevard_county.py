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


def _get_to_download_page_name(driver: Driver,i) -> None:
    """Click the first result row's view button."""
    #/tr[1]
    down = WebDriverWait(driver, 5).until(#
        EC.element_to_be_clickable((By.XPATH, f'/html/body/div[2]/div[5]/div/div/strong/div/div[4]/div/div[1]/div[4]/table/tbody/tr[{i+1}]'))
    )
    #//*[@id="center"]/div/div[4]/div[2]/div/div/div[1]/div[1]/button
    down.click()

def _get_to_download_page(driver: Driver,i) -> None:
    """Click the first result row's view button."""
    #
    down = WebDriverWait(driver, 5).until(#
        EC.element_to_be_clickable((By.XPATH, f'/html/body/div[2]/div[5]/div[1]/div[1]/div[3]/div[4]/div/div[1]/div[4]/table/tbody/tr[{i+1}]'))
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
    WebDriverWait(driver, 35).until(
        lambda d: (
                (el := EC.presence_of_element_located((By.ID, "imgFrame1"))(d)) and
                el.get_attribute("src") not in ("", "about:blank")
        )
    )
    find_element_in_iframes(driver,"/html/body/div/div/a/button").click()

def _navigate_to_name_table(driver) -> None:
    # whatever clicking/waiting gets you to the results table after a name search
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '//*[@id="frmSchTarget"]/form/div[3]/input'))
    ).click()




registry.register(
    CountyConfig(
        name="brevard county",
        url="https://vaclmweb1.brevardclerk.us/AcclaimWeb/search/SearchTypeBookPage",
        name_url = "https://vaclmweb1.brevardclerk.us/AcclaimWeb/search/Disclaimer?st=/AcclaimWeb/search/SearchTypeName",
        first_name_xpath = "/html/body/div[2]/div[1]/div[2]/div/div/form/div[1]/div[2]/div[1]/div[2]/input",
        last_name_xpath = "/html/body/div[2]/div[1]/div[2]/div/div/form/div[1]/div[2]/div[1]/div[2]/input",
        name_submit_button_xpath="/html/body/div[2]/div[1]/div[2]/div/div/form/div[2]/input[2]",
        navigate_to_table_func = _navigate_to_name_table,
        book_xpath='//*[@id="BookNumber"]',
        page_xpath='//*[@id="PageNumber"]',
        deed_type_xpath='',
        submit_button_xpath='/html/body/div[2]/div[1]/div[2]/div/div/form/div[2]/input[2]',
        deeds_table_xpath='//*[@id="RsltsGrid"]/div[4]/table/tbody',
        row_tag_name='tr',
        return_to_table_func=_return_to_table,
        get_to_download_page_name_func=_get_to_download_page_name,
        get_to_download_page_func=_get_to_download_page,
        file_trigger_download_func=_trigger_download,
        navigate_to_search_func=_navigate_to_search,

        deed_type_values=["All Books"],
        download_timeout=90,
        extra_wait=1.5,
    )
)