"""
counties/example_county_b.py
-----------------------------
Configuration for Example County B.

This county's portal:
  - Uses a div-based results list (not a <table>)
  - Opens the deed in a modal dialog (not a new page)
  - Requires accepting a disclaimer before downloading
"""

import time

from county_config import CountyConfig, registry
from seleniumbase import Driver

# ---------------------------------------------------------------------------
# Optional setup — dismiss cookie banner on first load
# ---------------------------------------------------------------------------

def _extra_setup(driver: Driver) -> None:
    try:
        driver.click('//button[@id="acceptCookies"]', timeout=5)
    except Exception:
        pass  # Banner may not appear every time


# ---------------------------------------------------------------------------
# Action functions
# ---------------------------------------------------------------------------

def _get_to_download_page(driver: Driver) -> None:
    """
    County B opens a modal when you click the deed reference number.
    We wait for the modal to become visible before returning.
    """
    driver.click('//div[@class="deed-row"]//a[@class="deed-ref"]')
    driver.wait_for_element_visible('//div[@id="deedModal"]', timeout=15)


def _trigger_download(driver: Driver) -> None:
    """
    There's a disclaimer checkbox that must be checked before the
    download button becomes enabled.
    """
    disclaimer_xpath = '//input[@id="disclaimerCheckbox"]'
    download_btn_xpath = '//button[@id="modalDownloadBtn"]'

    driver.click(disclaimer_xpath)
    time.sleep(0.5)   # brief pause for the button to enable

    driver.wait_for_element_clickable(download_btn_xpath, timeout=10)
    driver.click(download_btn_xpath)


# ---------------------------------------------------------------------------
# County registration
# ---------------------------------------------------------------------------

registry.register(
    CountyConfig(
        name="Example County B",

        url="https://press.essexregister.com/prodpress/clerk/ClerkHome.aspx?op=basic",

        book_xpath='//*[@id="ctl00_ContentPlaceHolder1_txtBookNumberTab3"]',
        page_xpath='//*[@id="ctl00_ContentPlaceHolder1_txtPageNumberTab3"]',
        deed_type_xpath="",   # custom checkbox group
        submit_button_xpath='//*[@id="ctl00_ContentPlaceHolder1_btnSearchTab3"]',

        deeds_table_xpath='//div[@id="searchResults"]',
        row_tag_name="div",    # rows are <div class="deed-row">

        get_to_download_page_func=_get_to_download_page,
        file_trigger_download_func=_trigger_download,

        deed_type_values=["Deed of Trust"],
        download_timeout=120,
        extra_wait=2.0,
        extra_setup=_extra_setup,
    )
)
