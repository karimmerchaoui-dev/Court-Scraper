import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumbase import Driver

from deed_search.browser_helpers import find_element_in_iframes
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
    #
    filter_element = driver.find_element(By.XPATH, "/html/body/form/div[5]/div[38]/div[1]/div[1]/table/tbody/tr/td[8]/table/tbody/tr/td[6]/a[1]")
    driver.execute_script("arguments[0].click();", filter_element)

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
    time.sleep(5)
    down = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.XPATH, f'/html/body/form/div[5]/div[38]/div[1]/div[2]/table/tbody/tr[1]/td/div/div[2]/table/tbody/tr[{i}]/td[9]/input'))
    )
    driver.execute_script("arguments[0].click();", down)
    time.sleep(1)
    print(f"driver.window_handles : {driver.window_handles}")
    driver.switch_to.window(driver.window_handles[-1])
    WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.XPATH, f'/html/body/form/div[2]/div[2]/div[2]/table/tbody/tr[1]/td/div/table/tbody/tr/td[7]/div/table/tbody/tr/td[2]/table/tbody/tr/td[2]/input'))
    ).click()
    driver.switch_to.window(driver.window_handles[-1])
    WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.XPATH, f'/html/body/form/div[2]/div[4]/div[2]/div[2]/div/table/tbody/tr[2]/td/div/input'))
    ).click()
    WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.XPATH, f'/html/body/form/div[2]/div[4]/div[2]/div[2]/table/tbody/tr[1]/td[1]/input'))
    ).click()
    driver.switch_to.window(driver.window_handles[-1])
    WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.XPATH, f'/html/body/form/div[2]/div[5]/div/div/table/tbody/tr[3]/td/table/tbody/tr/td[2]/input'))
    ).click()


def _return_to_table(driver,i):
    while len(driver.window_handles) > 1:
        driver.switch_to.window(driver.window_handles[-1])
        driver.close()
    driver.switch_to.window(driver.window_handles[0])
    pass

#/html/body/form/div[5]/div[29]/div/div/table/tbody/tr/td[2]/div/table[1]/tbody/tr/td[3]/table/tbody/tr[2]/td[2]/a
#/html/body/form/div[5]/div[38]/div[1]/div[1]/table/tbody/tr/td[8]/table/tbody/tr/td[6]/a
def _trigger_download(driver: Driver,i) -> None:
    """Click the download button on the deed detail page."""
    pass
    


registry.register(
    CountyConfig(
        name="gloucester county",
        url="https://i2e.uslandrecords.com/NJ/Gloucester/D/Default.aspx",
        name_url="https://i2e.uslandrecords.com/NJ/Gloucester/D/Default.aspx",
        book_xpath='/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[7]/form/div[2]/div[2]/div[1]/span[1]/input',
        page_xpath='/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[7]/form/div[2]/div[2]/div[1]/span[3]/input',
        deed_type_xpath='/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[7]/form/div[1]/div[2]/span/select',
        submit_button_xpath='/html/body/form/div[5]/div[26]/div/div/table/tbody/tr[2]/td/div/table/tbody/tr[1]/td[1]/table/tbody/tr/td/input',

        instrument_xpath="/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[6]/form/div/div[2]/div/input",
        instrument_submit_button_xpath="/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[6]/form/div/div[3]/button",
        navigate_to_instrument_search_func=_navigate_to_instrument_search,
        last_name_xpath="/html/body/form/div[5]/div[26]/div/div/table/tbody/tr[1]/td/div/table/tbody/tr[2]/td[1]/input",
        first_name_xpath="/html/body/form/div[5]/div[26]/div/div/table/tbody/tr[1]/td/div/table/tbody/tr[2]/td[2]/input",
        deeds_table_xpath='/html/body/form/div[5]/div[38]/div[1]/div[2]/table/tbody/tr[1]/td/div/div[2]/table/tbody',
        name_submit_button_xpath="/html/body/form/div[5]/div[26]/div/div/table/tbody/tr[2]/td/div/table/tbody/tr[1]/td[1]/table/tbody/tr/td/input",
        row_tag_name="tr",
        return_to_table_func=_return_to_table,
        get_to_download_page_func=_get_to_download_page,
        file_trigger_download_func=_trigger_download,
        filter_rows_func=_filter_rows_by_block_lot,  # ✅ add
        deed_type_values=["All Books"],
        download_timeout=90,
        extra_wait=1.5,
    )
)