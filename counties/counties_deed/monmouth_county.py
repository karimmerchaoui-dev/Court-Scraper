import time

from browser_helpers import find_element_in_iframes
from county_config import CountyConfig, registry
from seleniumbase import Driver


def _navigate_to_search(driver: Driver) -> None:
    pass




def _get_to_download_page(driver: Driver,i) -> None:
    """Click the first result row's view button."""
    print(f"tr[3]/td/table/tbody/tr[{i+3}]/td[12]/input")
    #/html/body/form/div[3]/div[1]/div/div[4]/table[2]/tbody/tr[4]/td/div/table/tbody/tr[3]/td/table/tbody/tr[4]/td[11]/input
    down = find_element_in_iframes(driver,f'/html/body/form/div[3]/div[1]/div/div[4]/table[2]/tbody/tr[4]/td/div/table/tbody/tr[3]/td/table/tbody/tr[{i+3}]/td[11]/input')
    #
    down.click()

def _return_to_table(driver,i):
    driver.back()



def _trigger_download(driver: Driver,i) -> None:
    """Click the download button on the deed detail page."""
    time.sleep(2)
    find_element_in_iframes(driver,'//*[@id="btnImage"]').click()
    time.sleep(5)
    find_element_in_iframes(driver,'/html/body/form/table/tbody/tr[2]/td/table/tbody/tr[1]/td/table/tbody/tr/td/table[2]/tbody/tr[3]/td/table/tbody/tr/td[1]/table/tbody/tr/td[2]/table/tbody/tr/td[1]/img').click()

registry.register(
    CountyConfig(
        name="monmouth county",
        url="https://oprs.co.monmouth.nj.us/oprs/clerk/clerkhome.aspx?op=basic",
        book_xpath='/html/body/form/div[3]/div[1]/div/div[4]/table[2]/tbody/tr[3]/td/div/table/tbody/tr[2]/td/table/tbody/tr[2]/td/div/div[1]/table/tbody/tr[3]/td[3]/input',
        page_xpath='/html/body/form/div[3]/div[1]/div/div[4]/table[2]/tbody/tr[3]/td/div/table/tbody/tr[2]/td/table/tbody/tr[2]/td/div/div[1]/table/tbody/tr[3]/td[4]/input',
        deed_type_xpath='',
        submit_button_xpath='/html/body/form/div[3]/div[1]/div/div[4]/table[2]/tbody/tr[3]/td/div/table/tbody/tr[2]/td/table/tbody/tr[2]/td/div/div[1]/table/tbody/tr[5]/td/input[1]',
        deeds_table_xpath='/html/body/form/div[3]/div[1]/div/div[4]/table[2]/tbody/tr[4]/td/div/table/tbody/tr[3]/td/table/tbody',
        row_tag_name="tr",
        return_to_table_func=_return_to_table,
        get_to_download_page_func=_get_to_download_page,
        file_trigger_download_func=_trigger_download,
        navigate_to_search_func=None,

        deed_type_values=["All Books"],
        download_timeout=90,
        extra_wait=1.5,
    )
)