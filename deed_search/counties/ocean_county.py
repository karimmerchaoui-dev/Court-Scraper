import time

import pysnooper
from selenium.common.exceptions import TimeoutException

#/html/body/div[2]/div[4]/div/div[2]/section[3]/div[6]/div/div/div/div[1]/div[2]/div/div[1]/div/div[4]/div[2]/div/div/div[1]/div[8] block
#/html/body/div[2]/div[4]/div/div[2]/section[3]/div[6]/div/div/div/div[1]/div[2]/div/div[1]/div/div[4]/div[2]/div/div/div[1]/div[9] page
#
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumbase import Driver

from deed_search.browser_helpers import find_element_in_iframes, html_table_to_dict
from deed_search.county_config import CountyConfig, registry


@pysnooper.snoop()
def check_filter_checkbox(driver, target_value):
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
            print(f"value : {value}")
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
    submit = find_element_in_iframes(driver, '//*[@id="center"]/div/div[1]/div[2]/div/div[12]/span')
    driver.execute_script("arguments[0].scrollIntoView();", submit)
    driver.execute_script("arguments[0].click();", submit)
    submit = find_element_in_iframes(driver, '//*[@id="selectAll"]')
    driver.execute_script("arguments[0].scrollIntoView();", submit)
    driver.execute_script("arguments[0].click();", submit)
    check_filter_checkbox(driver, block)


def accept_alert_if_present(driver, timeout=3):
    try:
        WebDriverWait(driver, timeout).until(EC.alert_is_present())
        alert = driver.switch_to.alert
        print(f"⚠️ Alert found: {alert.text}")
        alert.accept()
        print("✅ Alert accepted")
        return True
    except TimeoutException:
        # No alert appeared
        return False

def _navigate_to_instrument_search(driver: Driver) -> None:
    time.sleep(2)
    """Click the 'Book & Page' tab to reveal the search form."""
    accept_alert_if_present(driver)
    nav = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '/html/body/div[2]/div[4]/div/div[1]/div/div/ul/li[3]/a'))
    )
    nav.click()
    

def _navigate_to_search(driver: Driver) -> None:
    time.sleep(2)
    """Click the 'Book & Page' tab to reveal the search form."""
    accept_alert_if_present(driver)
    nav = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '/html/body/div[2]/div[4]/div/div[1]/div/div/ul/li[4]/a'))
    )
    nav.click()
    


def _get_to_download_page(driver: Driver,i) -> None:
    """Click the first result row's view button."""
    down = WebDriverWait(driver, 5).until(#
        EC.element_to_be_clickable((By.XPATH, f'//*[@id="center"]/div/div[4]/div[2]/div/div/div[{i+1}]/div[1]/button'))
    )
    driver.execute_script("""
        arguments[0].scrollIntoView({
            block: 'center'
        });
    """, down)
    #//*[@id="center"]/div/div[4]/div[2]/div/div/div[1]/div[1]/button
    down.click()
    document_table = WebDriverWait(driver, 3).until(
        EC.element_to_be_clickable((By.XPATH, '//*[@id="documentDetail"]/div[2]/table/tbody[1]')))
    data = html_table_to_dict(document_table.get_attribute("outerHTML"))
    return data

def _return_to_table(driver,i):
    driver.click('/html/body/div[2]/div[4]/ul/li[2]/a')


def _trigger_download(driver: Driver, i) -> dict:
    """Click the download button on the deed detail page."""
    driver.click('//*[@id="documentImage"]/div/div[2]/button[7]')
    time.sleep(2)
    driver.click('//*[@id="pdfLink"]/a')

def navigate_to_name_search_func(driver):
    time.sleep(2)
    """Click the 'Book & Page' tab to reveal the search form."""
    accept_alert_if_present(driver)
    nav = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '/html/body/div[2]/div[4]/div/div[1]/div/div/ul/li[1]/a'))
    )
    nav.click()


def _scroll_to_load_rows(driver) -> None:
    """Scroll gradually inside AG-Grid so all rows render."""

    grid = driver.find_element(
        "css selector",
        ".ag-body-viewport"
    )

    last_scroll = -1

    while True:

        current_scroll = driver.execute_script("""
            return arguments[0].scrollTop;
        """, grid)

        # scroll down gradually
        driver.execute_script("""
            arguments[0].scrollTop += 300;
        """, grid)

        # give AG-Grid time to render rows
        time.sleep(0.2)

        new_scroll = driver.execute_script("""
            return arguments[0].scrollTop;
        """, grid)

        # reached bottom
        if new_scroll == current_scroll or new_scroll == last_scroll:
            break

        last_scroll = current_scroll


registry.register(
    CountyConfig(
        name="ocean county",
        url="https://sng.co.ocean.nj.us/publicsearch/",
        name_url="https://sng.co.ocean.nj.us/publicsearch/",
        book_xpath='/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[7]/form/div[2]/div[2]/div[1]/span[1]/input',
        page_xpath='/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[7]/form/div[2]/div[2]/div[1]/span[3]/input',
        deed_type_xpath='/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[7]/form/div[1]/div[2]/span/select',
        submit_button_xpath='/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[7]/form/div[2]/div[3]/button',

        instrument_xpath="/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[6]/form/div/div[2]/div/input",
        instrument_submit_button_xpath="/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[6]/form/div/div[3]/button",
        navigate_to_instrument_search_func=_navigate_to_instrument_search,

        
        navigate_to_name_search_func=navigate_to_name_search_func,
        first_name_xpath="/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[4]/form/div[1]/div[2]/div/input",
        last_name_xpath="/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[4]/form/div[1]/div[2]/div/input",
        deeds_table_xpath='//*[@id="center"]/div/div[4]/div[2]/div/div',
        name_submit_button_xpath="/html/body/div[2]/div[4]/div/div[1]/div/div/div/div[4]/form/div[1]/div[3]/button",
        row_tag_name="div",
        return_to_table_func=_return_to_table,
        get_to_download_page_func=_get_to_download_page,
        file_trigger_download_func=_trigger_download,
        navigate_to_search_func=_navigate_to_search,
        scroll_to_load_rows_func=_scroll_to_load_rows,
        filter_rows_func=_filter_rows_by_block_lot,  # ✅ add
        deed_type_values=["All Books"],
        download_timeout=90,
        extra_wait=1.5,
    )
)