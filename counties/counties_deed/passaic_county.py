import time

from browser_helpers import _search_iframes
from county_config import CountyConfig, registry
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumbase import Driver


def _navigate_to_search(driver: Driver) -> None:
    """Click the 'Book & Page' tab to reveal the search form."""
    nav = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '//*[@id="_ctl0_PageContent_imgTab3"]'))
    )
    nav.click()


def _get_to_download_page(driver: Driver,i) -> None:
    """Click the first result row's view button."""
    down = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.XPATH, f'//*[@id="_ctl0_PageContent_dgdDeedMort"]/tbody/tr[{i+3}]/td[11]/input'))
    )
    #//*[@id="center"]/div/div[4]/div[2]/div/div/div[1]/div[1]/button
    down.click()



def _return_to_table(driver,i):
    driver.back()


def _trigger_download(driver: Driver,i) -> None:
    """Click the download button on the deed detail page."""
    time.sleep(2)
    display_image = WebDriverWait(driver, 3).until(
        EC.element_to_be_clickable((By.XPATH, '/html/body/form/table[1]/tbody/tr[2]/td/table/tbody/tr/td/div/table/tbody/tr/td/div/div/table/tbody/tr/td[1]/div/table/tbody/tr[11]/td/input'))
    )
    display_image.click()
    time.sleep(3)  # reduced from 100 — just enough to let the download start
    save_pdf = _search_iframes(driver,'//*[@id="pdfLink"]/a')
    save_pdf.click()


registry.register(
    CountyConfig(
        name="passaic county",
        url="https://records.passaiccountynj.org/PRESS/Clerk/ClerkHome.aspx?op=basic",

        book_xpath='//*[@id="_ctl0_PageContent_txtBookNumberTab3"]',
        page_xpath='//*[@id="_ctl0_PageContent_txtPageNumberTab3"]',
        deed_type_xpath="",
        submit_button_xpath='//*[@id="_ctl0_PageContent_btnSearchTab3"]',

        deeds_table_xpath='//*[@id="_ctl0_PageContent_dgdDeedMort"]/tbody',
        row_tag_name=".//tr/td[11]//input",
        return_to_table_func=_return_to_table,
        get_to_download_page_func=_get_to_download_page,
        file_trigger_download_func=_trigger_download,
        navigate_to_search_func=_navigate_to_search,

        deed_type_values=[],
        download_timeout=90,
        extra_wait=1.5,
    )
)