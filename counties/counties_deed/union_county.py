import time

from browser_helpers import find_element_in_iframes
from county_config import CountyConfig, registry
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumbase import Driver


def _navigate_to_search(driver: Driver) -> None:
    WebDriverWait(driver, 5).until(  #
        EC.element_to_be_clickable((By.XPATH,
                                    f'/html/body/form/table/tbody/tr[2]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr[3]/td/table/tbody/tr/td/table[2]/tbody/tr[3]/td/div/table/tbody/tr[2]/td/table/tbody/tr[2]/td/div/div[1]/table'))
    )
    pass




def _get_to_download_page(driver: Driver,i) -> None:
    pass

def _return_to_table(driver,i):
    time.sleep(5)
    driver.back()



def _trigger_download(driver: Driver,i) -> None:
    """Click the download button on the deed detail page."""
    #/html/body/div[1]/table[2]/tbody/tr/td/table/tbody/tr[1]/td[4]/a[2]
    find_element_in_iframes(driver,f'/html/body/div[1]/table[2]/tbody/tr/td/table/tbody/tr[1]/td[4]/a[2]').click()
    time.sleep(2)
    frame = driver.find_element(By.XPATH,'/html/body/div[1]/div[2]/iframe')
    driver.get(frame.get_attribute('src'))



registry.register(
    CountyConfig(
        name="union county",
        url="https://clerk.ucnj.org/UCPA/DocIndex?s=book",
        book_xpath='/html/body/div[1]/form/table[1]/tbody/tr/td[3]/input',
        page_xpath='/html/body/div[1]/form/table[1]/tbody/tr/td[5]/input',
        deed_type_xpath='/html/body/div[1]/form/table[1]/tbody/tr/td[1]/select',
        submit_button_xpath='/html/body/div[1]/form/table[2]/tbody/tr/td[1]/input[1]',
        deeds_table_xpath='//*[@id="main"]/table[2]/tbody',
        row_tag_name="tr",
        return_to_table_func=_return_to_table,
        get_to_download_page_func=_get_to_download_page,
        file_trigger_download_func=_trigger_download,
        navigate_to_search_func=None,
        deed_type_values=["Assignment","Mortgage"],
        download_timeout=90,
        extra_wait=1.5,
    )
)