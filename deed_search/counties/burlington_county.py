import time
import traceback

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumbase import Driver

from deed_search.browser_helpers import (
    element_exists_xpath,
    find_element_in_iframes,
    html_table_to_dict,
)
from deed_search.county_config import CountyConfig, registry


def _navigate_to_search(driver: Driver) -> None:
    WebDriverWait(driver, 5).until(  #
        EC.element_to_be_clickable((By.XPATH,
                                    f'/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[2]/tbody/tr[3]/td/div/table/tbody/tr[2]/td/table/tbody/tr[2]/td/div/div[1]/table'))
    )
    pass




def _get_to_download_page(driver: Driver,i) -> None:
    """Click the first result row's view button."""
    

    print(f"tr[3]/td/table/tbody/tr[{i+3}]/td[12]/input")
    down = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.XPATH, f'/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[2]/tbody/tr[4]/td/div/table/tbody/tr[3]/td/table/tbody/tr[{i+3}]/td[12]/input'))
    )
    #
    down.click()
    document_table = find_element_in_iframes(driver,'/html/body/form/table/tbody/tr[1]/td/table/tbody/tr[16]/td/table/tbody/tr[2]')
    data = html_table_to_dict(document_table.get_attribute("outerHTML"))
    if data:
        first_key = next(iter(data))
        del data[first_key]
    key_mapping = {
    "inst_number": "instrument_no",
    "recording_date": "date",
    "direct_party": "grantor",
    "indirect_party": "grantee",
    }
    data = {
        key_mapping.get(k, k): v
        for k, v in data.items()
    }
    return data

def _return_to_table(driver,i):
    search_result = find_element_in_iframes(driver,'/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr[3]/td/table/tbody/tr/td/table/tbody/tr/td/table[1]/tbody/tr/td/a[2]')
    search_result.click()

def _trigger_download(driver: Driver,i) -> None:
    """Click the download button on the deed detail page."""
    while True: 
        try:
            time.sleep(2)
            display_image = find_element_in_iframes(driver,'//*[@id="btnImage"]')
            print(display_image)
            if not display_image:
                continue
            display_image.click()
            time.sleep(2)
            Button_SaveImage = find_element_in_iframes(driver, '//*[@id="Button_SaveImage"]')
            Button_SaveImage.click()
            break
        except Exception as e:
            traceback.print_exc()


def _show_related_table(driver):
    #//*[@id="btnInst"]
    while not element_exists_xpath(driver, '//*[@id="dgdRelatedInst"]'):
        btnInst = find_element_in_iframes(driver, '//*[@id="btnInst"]')
        btnInst.click()
        time.sleep(3)

def _trigger_related_download(driver,i):
    
    driver.find_element(By.XPATH, f'//*[@id="dgdRelatedInst"]/tbody/tr[{i+1}]/td[3]/input').click()
    WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.XPATH, '//*[@id="btnImage"]'))
    )
    _trigger_download(driver,i)

def _return_to_related_table(driver,i):
    driver.back()
    time.sleep(1)
    _show_related_table(driver)

def navigate_to_name_search(driver):
    name = find_element_in_iframes(driver,'/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[2]/tbody/tr[3]/td/div/table/tbody/tr[2]/td/table/tbody/tr[2]/td/div/ul/li[4]/a')
    name.click()


registry.register(
    CountyConfig(
        name="burlington county",
        url="https://press.co.burlington.nj.us/press/clerk/ClerkHome.aspx?op=basic",
        name_url="https://press.co.burlington.nj.us/press/clerk/ClerkHome.aspx?op=basic",
        book_xpath='/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[2]/tbody/tr[3]/td/div/table/tbody/tr[2]/td/table/tbody/tr[2]/td/div/div[1]/table/tbody/tr[3]/td[3]/input',
        page_xpath='/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[2]/tbody/tr[3]/td/div/table/tbody/tr[2]/td/table/tbody/tr[2]/td/div/div[1]/table/tbody/tr[3]/td[4]/input',
        deed_type_xpath='',
        instrument_xpath='//*[@id="ctl00_ContentPlaceHolder1_txtInstrumentTab3"]',
        instrument_submit_button_xpath='//*[@id="ctl00_ContentPlaceHolder1_btnSearchTab3"]',
        submit_button_xpath='/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[2]/tbody/tr[3]/td/div/table/tbody/tr[2]/td/table/tbody/tr[2]/td/div/div[1]/table/tbody/tr[5]/td/input[1]',
        deeds_table_xpath='/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[2]/tbody/tr[4]/td/div/table/tbody/tr[3]/td/table/tbody',
        row_tag_name="/tr[contains(@class,'itemstyle')]",
        return_to_table_func=_return_to_table,
        get_to_download_page_func=_get_to_download_page,
        navigate_to_name_search_func=navigate_to_name_search,
        first_name_xpath="/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[2]/tbody/tr[3]/td/div/table/tbody/tr[2]/td/table/tbody/tr[2]/td/div/div[4]/table/tbody/tr[4]/td[3]/input",
        last_name_xpath="/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[2]/tbody/tr[3]/td/div/table/tbody/tr[2]/td/table/tbody/tr[2]/td/div/div[4]/table/tbody/tr[4]/td[2]/input",
        name_submit_button_xpath='/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[2]/tbody/tr[3]/td/div/table/tbody/tr[2]/td/table/tbody/tr[2]/td/div/div[4]/table/tbody/tr[18]/td[2]/input[1]',
        file_trigger_download_func=_trigger_download,
        navigate_to_search_func=_navigate_to_search,
        related_docs_make_table_visible_func=_show_related_table,
        related_docs_table_xpath='//*[@id="dgdRelatedInst"]/tbody',
        related_docs_row_tag_name="tr[contains(@class,'newitemstyle')]",
        # related_docs_trigger_download_func=_trigger_related_download,
        related_docs_return_to_table_func=_return_to_related_table,
        deed_type_values=["All Books"],
        download_timeout=90,
        extra_wait=1.5,
    )
)