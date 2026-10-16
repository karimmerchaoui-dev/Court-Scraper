import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumbase import Driver

from deed_search.browser_helpers import (
    _search_iframes,
    find_element_in_iframes,
    html_table_to_dict,
)
from deed_search.county_config import CountyConfig, registry


def navigate_to_name_search_func(driver: Driver) -> None:
    """Click the 'Book & Page' tab to reveal the search form."""
    nav = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr/td/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[2]/tbody/tr[3]/td/div/table/tbody/tr[2]/td/table/tbody/tr[2]/td/div/ul/li[4]'))
    )
    nav.click()

def _navigate_to_search(driver: Driver) -> None:
    """Click the 'Book & Page' tab to reveal the search form."""
    nav = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '/html/body/div[2]/div[4]/div/div[1]/div/div/ul/li[4]/a'))
    )
    nav.click()


def _get_to_download_page(driver: Driver,i) -> None:
    """Click the first result row's view button."""
    down = find_element_in_iframes(driver,f'/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr/td/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[2]/tbody/tr[4]/td/div/table/tbody/tr[3]/td/table/tbody/tr[{i+3}]/td[11]/input')
    #//*[@id="center"]/div/div[4]/div[2]/div/div/div[1]/div[1]/button
    down.click()
    document_table = find_element_in_iframes(driver,f'/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr[16]/td/table/tbody')

    data = html_table_to_dict(document_table.get_attribute("outerHTML"))
    return data


def _return_to_table(driver,i):
    return_to_results = find_element_in_iframes(driver,'/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr/td/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[1]/tbody/tr/td/a[2]')
    return_to_results.click()

def _trigger_download(driver: Driver,i) -> None:
    """Click the download button on the deed detail page."""
    WebDriverWait(driver, 30).until(lambda d: (
            d.execute_script("return document.readyState") == "complete"
    ))
    time.sleep(1)
    down = find_element_in_iframes(driver,'//*[@id="btnImage"]')
    down.click()
    time.sleep(2)
    find_element_in_iframes(driver, '//*[@id="Button_SaveImage"]').click()


def _validate_file(driver):
    #
    error_e = _search_iframes(driver,'//*[@id="noImage"]/div/div/p')

    if not error_e:
        return True
    if ("restricted" in error_e.text) or ("no images" in error_e.text):
        return False



registry.register(
    CountyConfig(
        name="essex county",
        url="https://press.essexregister.com/prodpress/clerk/ClerkHome.aspx?op=basic",
        name_url="https://press.essexregister.com/prodpress/clerk/ClerkHome.aspx?op=basic",
        book_xpath='/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr/td/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[2]/tbody/tr[3]/td/div/table/tbody/tr[2]/td/table/tbody/tr[2]/td/div/div[1]/table/tbody/tr[6]/td[2]/input',
        page_xpath='/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr/td/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[2]/tbody/tr[3]/td/div/table/tbody/tr[2]/td/table/tbody/tr[2]/td/div/div[1]/table/tbody/tr[6]/td[4]/input',
        deed_type_xpath='',
        submit_button_xpath='/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr/td/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[2]/tbody/tr[3]/td/div/table/tbody/tr[2]/td/table/tbody/tr[2]/td/div/div[1]/table/tbody/tr[8]/td/input[1]',
        validate_file_func=_validate_file,
        deeds_table_xpath='//*[@id="ctl00_ContentPlaceHolder1_dgdDeedMort"]/tbody',
        row_tag_name=".//tr[contains(@class,'itemstyle') or contains(@class,'altitemstyle')]",
        return_to_table_func=_return_to_table,
        get_to_download_page_func=_get_to_download_page,
        file_trigger_download_func=_trigger_download,
        navigate_to_name_search_func=navigate_to_name_search_func,
        first_name_xpath='/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr/td/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[2]/tbody/tr[3]/td/div/table/tbody/tr[2]/td/table/tbody/tr[2]/td/div/div[4]/table/tbody/tr[2]/td[4]/input',
        last_name_xpath='/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr/td/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[2]/tbody/tr[3]/td/div/table/tbody/tr[2]/td/table/tbody/tr[2]/td/div/div[4]/table/tbody/tr[2]/td[2]/input',
        name_submit_button_xpath='/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr/td/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[2]/tbody/tr[3]/td/div/table/tbody/tr[2]/td/table/tbody/tr[2]/td/div/div[4]/table/tbody/tr[11]/td/input[1]',
        navigate_to_search_func=None,

        deed_type_values=["All Books"],
        download_timeout=90,
        extra_wait=1.5,
    )
)