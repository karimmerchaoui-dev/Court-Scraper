import time

from county_config import CountyConfig, registry
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumbase import Driver


def find_element_in_iframes(driver, xpath: str):
    """
    Search for an element by xpath across all iframes on the page.
    Automatically switches to the correct iframe and returns the element.
    Returns None if not found anywhere.
    """
    # Try main document first
    driver.switch_to.default_content()
    try:
        return WebDriverWait(driver, 2).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
    except Exception:
        pass

    # Recursively search all iframes
    return _search_iframes(driver, xpath)


def _search_iframes(driver, xpath: str):
    """Recursively search through all iframes including nested ones."""
    iframes = driver.find_elements(By.TAG_NAME, "iframe")

    for iframe in iframes:
        try:
            driver.switch_to.frame(iframe)

            # Try to find the element in this iframe
            try:
                element = WebDriverWait(driver, 2).until(
                    EC.presence_of_element_located((By.XPATH, xpath))
                )
                # Found it — driver is now switched to the correct iframe
                return element
            except Exception:
                pass

            # Not found directly — search nested iframes inside this one
            nested_result = _search_iframes(driver, xpath)
            if nested_result:
                return nested_result

            # Not found in this iframe or its children — go back up one level
            driver.switch_to.parent_frame()

        except Exception:
            driver.switch_to.parent_frame()
            continue

    return None


def login(driver):
    #
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '//*[@id="maindiv"]/table[2]/tbody/tr[1]/td[2]/form/table[1]/tbody/tr[2]/td[2]/input'))
    ).send_keys('iangary')

    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (By.XPATH, '//*[@id="maindiv"]/table[2]/tbody/tr[1]/td[2]/form/table[1]/tbody/tr[3]/td[2]/input'))
    ).send_keys('karim123')

    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (By.XPATH, '//*[@id="maindiv"]/table[2]/tbody/tr[1]/td[2]/form/table[1]/tbody/tr[5]/td[2]/input[1]'))
    ).click()



def _navigate_to_search(driver: Driver) -> None:
    """Click the 'Book & Page' tab to reveal the search form."""
    login(driver)
    find_element_in_iframes(driver,'//*[@id="accept"]')

    accept = find_element_in_iframes(driver,'//*[@id="accept"]')
    accept.click()
    search_type = find_element_in_iframes(driver,'/html/body/div[1]/div/div[3]/div[2]/div/div[1]/div/div/div/div/div[2]/div[2]/table/tbody/tr[3]')
    search_type.click()
    #criteriaframe


def _get_to_download_page(driver: Driver,i) -> None:
    """Click the first result row's view button."""
    down = WebDriverWait(driver, 5).until(#
        EC.element_to_be_clickable((By.XPATH, f'/html/body/form/div/div/div/div/div[2]/div[2]/table/tbody/tr/td[2]/div/span[1]/a'))
    )
    #
    down.click()
    time.sleep(1)
    find_element_in_iframes(driver,"/html/body/div/table/tbody/tr/td[2]/a/img").click()
    find_element_in_iframes(driver,"/html/body/form/div[2]/table/tbody/tr/td[2]/input").click()

def _return_to_table(driver):
    driver.click('//*[@id="img2"]')


def _trigger_download(driver: Driver,i) -> None:
    """Click the download button on the deed detail page."""

    find_element_in_iframes(driver,'//*[@id="btntable"]/tbody/tr/td[2]/a').click()
    find_element_in_iframes(driver,'/html/body/form/div[1]/table/tbody/tr[1]/td[1]/input').click()


    driver.click('//*[@id="okbar"]/table/tbody/tr/td[2]/input')


registry.register(
    CountyConfig(
        name="cumberland county",
        url="https://countyfusion1.kofiletech.us/countyweb/loginDisplay.action?town=&countyname=CumberlandNJ",
        navigate_to_search_func=_navigate_to_search,
        book_xpath='/html/body/form[1]/div[1]/div/table/tbody/tr[1]/td[2]/span/input[1]',
        page_xpath='/html/body/form[1]/div[1]/div/table/tbody/tr[2]/td[2]/span/input[1]',
        deed_type_xpath='',
        submit_button_xpath='//*[@id="imgSearch"]',
        file_trigger_download_func=_trigger_download,
        deeds_table_xpath='//*[@id="instList"]/div/div/div/div[2]/div[2]/table/tbody',
        row_tag_name="tr",
        return_to_table_func=_return_to_table,
        get_to_download_page_func=None,

        deed_type_values=["All Books"],
        download_timeout=90,
        extra_wait=1.5,
    )
)