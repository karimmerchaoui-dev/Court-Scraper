import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumbase import Driver

from deed_search.browser_helpers import find_element_in_iframes, html_table_to_dict
from deed_search.county_config import CountyConfig, registry


def check_filter_checkbox(driver, target_value):
    #
    checkboxes_div = find_element_in_iframes(driver, '//*[@id="borderLayout_eRootPanel"]/div[3]/div/div[3]')
    items = checkboxes_div.find_elements(
        By.CSS_SELECTOR,
        ".ag-filter-item"
    )
    print(f"number of items : {len(items)}")
    for item in items:
        try:

            label = item.find_element(
                By.TAG_NAME,
                "label"
            )

            value = label.find_element(
                By.CSS_SELECTOR,
                ".ag-filter-value"
            ).text.strip()

            if value == target_value:

                checkbox = item.find_element(
                    By.CSS_SELECTOR,
                    "input[type='checkbox']"
                )

                if not checkbox.is_selected():

                    # AG-Grid-safe click
                    checkbox.click()

                return True

        except Exception:
            continue

def _filter_rows_by_block_lot(driver, rows, block, lot):
    filter_button = find_element_in_iframes(driver, '//*[@id="center"]/div/div[1]/div[2]/div/div[11]/span')
    driver.execute_script("arguments[0].scrollIntoView();", filter_button)
    driver.execute_script("arguments[0].click();", filter_button)

    submit = find_element_in_iframes(driver, '//*[@id="selectAll"]')
    driver.execute_script("arguments[0].scrollIntoView();", submit)
    driver.execute_script("arguments[0].click();", submit)
    check_filter_checkbox(driver, block)


def _navigate_to_instrument_search(driver: Driver) -> None:
    """Switch to Instrument Search tab."""
    nav = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "/html/body/div[2]/div[4]/div/div[1]/div/div/ul/li[3]/a"))
    )
    nav.click()

def navigate_to_instrument_search(driver: Driver):
    nav = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '/html/body/div[1]/div[2]/div/div[1]/div/div[1]/ul/li[4]/a'))
    )
    nav.click()

def _navigate_to_search(driver: Driver) -> None:
    """Click the 'Book & Page' tab to reveal the search form."""
    nav = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '/html/body/div[1]/div[2]/div/div[1]/div/div[1]/ul/li[5]/a'))
    )
    nav.click()


def _get_to_download_page(driver: Driver,i) -> None:
    """Click the first result row's view button."""
    down = WebDriverWait(driver, 5).until(#
        EC.element_to_be_clickable((By.XPATH, f'//*[@id="center"]/div/div[4]/div[2]/div/div/div[{i+1}]/div[1]/button'))
    )
    #//*[@id="center"]/div/div[4]/div[2]/div/div/div[1]/div[1]/button
    down.click()
    document_table = WebDriverWait(driver, 3).until(
        EC.element_to_be_clickable((By.XPATH, '//*[@id="documentDetail"]/div/table/tbody')))
    data = html_table_to_dict(document_table.get_attribute("outerHTML"))
    return data

def _return_to_table(driver,i):
    driver.click('/html/body/div[1]/div[2]/ul/li[2]/a')


def _trigger_download(driver: Driver,i) -> None:
    """Click the download button on the deed detail page."""
    driver.click('//*[@id="documentImage"]/div/div[2]/button[7]')
    time.sleep(5)  # reduced from 100 — just enough to let the download start

    driver.click('//*[@id="pdfLink"]/a')

def _validate_file(driver):
    error_e = WebDriverWait(driver, 3).until(  #
        EC.element_to_be_clickable(
            (By.XPATH, f'//*[@id="restrictedImage"]/div/div/p'))
    )
    #
    if "restricted" in error_e.text:
        return False


registry.register(
    CountyConfig(
        name="mercer county",
        url="https://records.mercercounty.org/publicsearch/",
        name_url="https://records.mercercounty.org/publicsearch/",
        book_xpath='/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[7]/form/div[2]/div[2]/div[1]/span[1]/input',
        page_xpath='/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[7]/form/div[2]/div[2]/div[1]/span[3]/input',
        deed_type_xpath='/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[7]/form/div[1]/div[2]/span/select',
        submit_button_xpath='/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[7]/form/div[2]/div[3]/button',

        instrument_xpath="/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[6]/form/div/div[2]/div/input",
        instrument_submit_button_xpath="/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[6]/form/div/div[3]/button",
        navigate_to_instrument_search_func=_navigate_to_instrument_search,

        first_name_xpath="/html/body/div[1]/div[2]/div/div[1]/div/div[1]/div/div[1]/form/div[1]/div[2]/div/input",
        last_name_xpath="/html/body/div[1]/div[2]/div/div[1]/div/div[1]/div/div[1]/form/div[1]/div[2]/div/input",
        deeds_table_xpath='//*[@id="center"]/div/div[4]/div[2]/div/div',
        name_submit_button_xpath="/html/body/div[1]/div[2]/div/div[1]/div/div[1]/div/div[1]/form/div[1]/div[3]/button[2]",
        row_tag_name="div",
        return_to_table_func=_return_to_table,
        get_to_download_page_func=_get_to_download_page,
        file_trigger_download_func=_trigger_download,
        navigate_to_search_func=_navigate_to_search,
        filter_rows_func=_filter_rows_by_block_lot,  # ✅ add
        deed_type_values=["All Books"],
        download_timeout=90,
        extra_wait=1.5,
    )
)