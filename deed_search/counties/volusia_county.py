from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumbase import Driver

from deed_search.county_config import CountyConfig, registry


def _navigate_to_search(driver: Driver) -> None:
    """Click the 'Book & Page' tab to reveal the search form."""
    nav = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '//*[@id="accept"]'))
    )
    nav.click()


def _return_to_table(driver,i):
    if len(driver.window_handles) > 1:
        driver.switch_to_window(driver.window_handles[-1])
        driver.close()
    driver.switch_to_window(driver.window_handles[0])

def _trigger_download(driver: Driver,i) -> None:
    """Click the download button on the deed detail page."""
    down = WebDriverWait(driver, 5).until(  #/html/body/form/div[5]/div[1]/div[5]/div/div/table/tbody
        EC.element_to_be_clickable(
            (By.XPATH, f'/html/body/form/div[5]/div[1]/div[5]/div/div/table/tbody/tr[{i + 3}]/td[1]/a'))
    )
    down.click()


registry.register(
    CountyConfig(
        name="volusia county",
        url="https://app02.clerk.org/or_m/",
        name_url="https://app02.clerk.org/or_m/",
        name_submit_button_xpath='//*[@id="search"]',
        last_name_xpath='//*[@id="name"]',
        first_name_xpath='//*[@id="name"]',
        navigate_to_name_search_func=_navigate_to_search,
        book_xpath='//*[@id="book"]',
        page_xpath='//*[@id="tb_page"]',
        deed_type_xpath='',
        submit_button_xpath='//*[@id="search"]',
        deeds_table_xpath='/html/body/form/div[5]/div[1]/div[5]/div/div/table/tbody',
        row_tag_name="tr",
        return_to_table_func=_return_to_table,
        get_to_download_page_func=None,
        file_trigger_download_func=_trigger_download,
        navigate_to_search_func=_navigate_to_search,
        navigate_to_instrument_search_func=_navigate_to_search,
        instrument_xpath='//*[@id="instrument"]',
        instrument_submit_button_xpath='//*[@id="search"]',
        instrument_url="https://app02.clerk.org/or_m/",

        deed_type_values=["All Books"],
        download_timeout=90,
        extra_wait=1.5,
    )
)