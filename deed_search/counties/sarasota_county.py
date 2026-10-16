import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumbase import Driver

from deed_search.county_config import CountyConfig, registry


def _navigate_to_search(driver: Driver) -> None:
    """Click the 'Book & Page' tab to reveal the search form."""
    nav = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '/html/body/div[1]/div[2]/div[3]/a'))
    )
    nav.click()


def _get_to_download_page(driver: Driver,i) -> None:
    """Click the first result row's view button."""
    down = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.XPATH, f'//*[@id="center"]/div/div[4]/div[2]/div/div/div[{i+1}]/div[1]/button'))
    )
    #//*[@id="center"]/div/div[4]/div[2]/div/div/div[1]/div[1]/button
    down.click()

def _return_to_table(driver,i):
    driver.click('/html/body/div[1]/div[3]/ul/li[2]/a')


def _trigger_download(driver: Driver,i) -> None:
    """Click the download button on the deed detail page."""
    driver.click(f'/html/body/form/div[3]/div[1]/div[2]/main/fieldset[2]/div[2]/table/tbody/tr[{i+1}]/td[1]/a')
    time.sleep(2)  # reduced from 100 — just enough to let the download start



registry.register(
    CountyConfig(
        name="sarasota county",
        url="https://secure.sarasotaclerk.com/OfficialRecords.aspx",
        name_url="https://secure.sarasotaclerk.com/OfficialRecords.aspx",
        book_xpath='/html/body/form/div[3]/div[1]/div[2]/main/fieldset[1]/table/tbody/tr[7]/td[2]/span/input[1]',
        page_xpath='/html/body/form/div[3]/div[1]/div[2]/main/fieldset[1]/table/tbody/tr[7]/td[4]/span/input[1]',
        deed_type_xpath=None,
        name_submit_button_xpath='/html/body/form/div[3]/div[1]/div[2]/main/fieldset[1]/div/span[1]/input[1]',
        submit_button_xpath='/html/body/form/div[3]/div[1]/div[2]/main/fieldset[1]/div/span[1]/input[1]',
        last_name_xpath="/html/body/form/div[3]/div[1]/div[2]/main/fieldset[1]/table/tbody/tr[1]/td[2]/span/input[1]",
        first_name_xpath="/html/body/form/div[3]/div[1]/div[2]/main/fieldset[1]/table/tbody/tr[1]/td[4]/span/input[1]",
        deeds_table_xpath='/html/body/form/div[3]/div[1]/div[2]/main/fieldset[2]/div[2]/table',
        row_tag_name="tr",
        #return_to_table_func=_return_to_table,
        get_to_download_page_func=None,
        file_trigger_download_func=_trigger_download,
        #navigate_to_search_func=_navigate_to_search,

        deed_type_values=["All Books"],
        download_timeout=90,
        extra_wait=1.5,
    )
)