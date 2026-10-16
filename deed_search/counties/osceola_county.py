import time

import pysnooper
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumbase import Driver

from deed_search.county_config import CountyConfig, registry


def _navigate_to_search(driver: Driver) -> None:
    """Click the 'Book & Page' tab to reveal the search form."""
    nav = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '/html/body/div[2]/div[3]/div/div[1]/div/div/ul/li[5]'))
    )
    nav.click()


from bs4 import BeautifulSoup


def html_table_to_dict(html: str) -> dict:
    """
    Convert an HTML table like the county deed details page
    into a clean Python dictionary.
    """

    soup = BeautifulSoup(html, "html.parser")

    data = {}

    rows = soup.find_all("tr")

    for row in rows:
        cells = row.find_all("td")

        if len(cells) < 2:
            continue

        # -----------------------------
        # Extract key
        # -----------------------------
        key = cells[0].get_text(" ", strip=True)
        key = key.replace(":", "").strip()

        # normalize key
        normalized_key = (
            key.lower()
            .replace(" ", "_")
            .replace("/", "_")
            .replace(".", "")
        )

        value_cell = cells[1]

        # -----------------------------
        # Handle multiple div values
        # (grantors, grantees, towns...)
        # -----------------------------
        divs = value_cell.find_all("div")

        if divs:
            values = []

            for div in divs:
                text = div.get_text(" ", strip=True)

                if text:
                    values.append(text)

            # single item -> string
            # multiple items -> list
            if len(values) == 1:
                value = values[0]
            else:
                value = values

        else:
            value = value_cell.get_text(" ", strip=True)

        # -----------------------------
        # Split book/page automatically
        # -----------------------------
        if normalized_key in ["book_page", "book_pv_page"]:
            if "/" in value:
                book, page = value.split("/", 1)

                data["book"] = book.strip()
                data["page"] = page.strip()

        data[normalized_key] = value

    return data

@pysnooper.snoop()
def _get_to_download_page(driver: Driver,i) -> None:
    """Click the first result row's view button."""
    down = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.XPATH, f'//*[@id="center"]/div/div[4]/div[2]/div/div/div[{i+1}]/div[1]/button'))
    )
    #//*[@id="center"]/div/div[4]/div[2]/div/div/div[1]/div[1]/button
    down.click()
    document_table = WebDriverWait(driver, 3).until(
        EC.element_to_be_clickable((By.XPATH, '//*[@id="documentDetail"]/div[2]/table/tbody')))
    data = html_table_to_dict(document_table.get_attribute("outerHTML"))
    return data


def _return_to_table(driver,i):
    driver.click('/html/body/div[2]/div[3]/ul/li[2]/a')


def _trigger_download(driver: Driver,i) -> None:
    """Click the download button on the deed detail page."""
    driver.click('//*[@id="documentImage"]/div/div[2]/button[7]')
    time.sleep(5)  # reduced from 100 — just enough to let the download start

    driver.click('//*[@id="pdfLink"]/a')

def _navigate_to_name_search(driver):
    driver.click('/html/body/div[2]/div[3]/div/div[1]/div/div/ul/li[1]/a')

registry.register(
    CountyConfig(
        name="osceola county",
        url="https://officialrecords.osceolaclerk.org/browserview/",
        navigate_to_name_search_func=_navigate_to_name_search,
        name_url="https://officialrecords.osceolaclerk.org/browserview/",
        first_name_xpath="/html/body/div[2]/div[3]/div/div[1]/div/div/div/div[1]/form/div[1]/div[2]/div/input",
        last_name_xpath="/html/body/div[2]/div[3]/div/div[1]/div/div/div/div[1]/form/div[1]/div[2]/div/input",
        name_submit_button_xpath="/html/body/div[2]/div[3]/div/div[1]/div/div/div/div[1]/form/div[1]/div[3]/button[2]",
        
        


        book_xpath='/html/body/div[2]/div[3]/div/div[1]/div/div/div/div[5]/form/div[2]/div[2]/div[1]/span[1]/input',
        page_xpath='/html/body/div[2]/div[3]/div/div[1]/div/div/div/div[5]/form/div[2]/div[2]/div[1]/span[3]/input',
        deed_type_xpath='/html/body/div[2]/div[3]/div/div[1]/div/div/div/div[5]/form/div[1]/div[2]/span/select',
        submit_button_xpath='/html/body/div[2]/div[3]/div/div[1]/div/div/div/div[5]/form/div[2]/div[3]/button[2]',
        deeds_table_xpath='//*[@id="center"]/div/div[4]/div[2]/div/div',
        row_tag_name="div",
        return_to_table_func=_return_to_table,
        get_to_download_page_func=_get_to_download_page,
        file_trigger_download_func=_trigger_download,
        navigate_to_search_func=_navigate_to_search,

        deed_type_values=["All Books"],
        download_timeout=90,
        extra_wait=1.5,
    )
)