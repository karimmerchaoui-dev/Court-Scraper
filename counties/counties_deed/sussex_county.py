import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumbase import Driver

from deed_search.county_config import CountyConfig, registry


def _navigate_to_search(driver: Driver) -> None:
    """Click the 'Book & Page' tab to reveal the search form."""
    nav = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '/html/body/div[2]/div[4]/div/div[1]/div/div/ul/li[4]/a'))
    )
    nav.click()


def navigate_to_search_instruments(driver: Driver) -> None:
    """Click the 'Book & Page' tab to reveal the search form."""
    nav = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '/html/body/div[2]/div[4]/div/div[1]/div/div/ul/li[3]/a'))
    )
    nav.click()


def _get_to_download_page(driver: Driver,i) -> None:
    """Click the first result row's view button."""
    down = WebDriverWait(driver, 5).until(#
        EC.element_to_be_clickable((By.XPATH, f'//*[@id="center"]/div/div[4]/div[2]/div/div/div[{i+1}]/div[1]/button'))
    )
    #//*[@id="center"]/div/div[4]/div[2]/div/div/div[1]/div[1]/button
    down.click()

def _return_to_table(driver,i):
    driver.click('/html/body/div[2]/div[4]/ul/li[2]/a')


def _trigger_download(driver: Driver,i) -> None:
    """Click the download button on the deed detail page."""
    driver.click('//*[@id="documentImage"]/div/div[2]/button[7]')
    time.sleep(5)  # reduced from 100 — just enough to let the download start

    driver.click('//*[@id="pdfLink"]/a')


registry.register(
    CountyConfig(
        name="sussex county",
        url="https://cefile.sussex.nj.us/publicsearch/",

        book_xpath='/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[7]/form/div[2]/div[2]/div[1]/span[1]/input',
        page_xpath='/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[7]/form/div[2]/div[2]/div[1]/span[3]/input',
        deed_type_xpath='/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[7]/form/div[1]/div[2]/span/select',
        submit_button_xpath='/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[7]/form/div[2]/div[3]/button',

        instrument_xpath='/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[6]/form/div/div[2]/div/input',
        instrument_submit_button_xpath='/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[6]/form/div/div[3]/button',
        navigate_to_instrument_search_func=navigate_to_search_instruments,

        deeds_table_xpath='//*[@id="center"]/div/div[4]/div[2]/div/div',
        row_tag_name="div",
        return_to_table_func=_return_to_table,
        get_to_download_page_func=_get_to_download_page,
        file_trigger_download_func=_trigger_download,
        navigate_to_search_func=_navigate_to_search,

        deed_type_values=["All Books"],
        download_timeout=90,
        extra_wait=1.5,
    )
)