
import os
import time

from bs4 import BeautifulSoup
from selenium.common.exceptions import (
    InvalidSessionIdException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from constants import NAME_SUFFIXES


def element_exists_xpath(driver, xpath):
    time.sleep(0.5)
    try:
        driver.find_element('xpath', xpath)
        return True
    except (NoSuchElementException,InvalidSessionIdException):
        return False


def find_element_in_iframes(driver, xpath: str):
    """
    Search for an element across the main document and all frames/iframes.
    Always tries main document first — so no iframe switching overhead
    when the element is in the top-level page.
    """
    # 1. Always try main document first
    driver.switch_to.default_content()
    try:
        return WebDriverWait(driver, 2).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
    except Exception:
        pass

    # 2. Only search frames/iframes if not found in main document
    return _search_iframes(driver, xpath)


def _search_iframes(driver, xpath: str, timeout=2):
    frames = (
        driver.find_elements(By.TAG_NAME, "iframe") +
        driver.find_elements(By.TAG_NAME, "frame")
    )

    for i, frame in enumerate(frames):
        try:
            # Enter frame
            driver.switch_to.frame(frame)

            # Try finding element in this frame
            try:
                return WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((By.XPATH, xpath))
                )
            except Exception:
                pass

            # Search nested frames
            nested = _search_iframes(driver, xpath, timeout)
            if nested:
                return nested

            # IMPORTANT: go back ONE level after recursion
            driver.switch_to.parent_frame()

        except Exception as e:
            try:
                driver.switch_to.parent_frame()
            except:
                pass

    return None

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


def set_download_dir(driver, down_path):
    os.makedirs(down_path, exist_ok=True)
    driver.command_executor._commands["send_command"] = ("POST", '/session/$sessionId/chromium/send_command')
    params = {
        'cmd': 'Page.setDownloadBehavior',
        'params': {
            'behavior': 'allow',
            'downloadPath': os.path.normpath(os.path.abspath(down_path))
        }
    }
    driver.execute("send_command", params)


    
def _fill_field(driver,xpath, value) -> None:
        element = find_element_in_iframes(driver,xpath)
        print(f"xpath : {xpath}")
        try:
            element.clear()
        except Exception:
            pass
        element.send_keys(value)



def _build_combined_name(first_name: str, last_name: str) -> str:
    """Combine first + last into one string for counties whose site uses a
    single search field. Any Jr/Sr/II/III/IV suffix in last_name is moved
    to the very end, regardless of where it appears."""
    first_name = (first_name or "").strip()
    last_parts = (last_name or "").strip().split()

    suffix = None
    if last_parts and last_parts[-1].lower().strip(".") in NAME_SUFFIXES:
        suffix = last_parts.pop()
    last_name = " ".join(last_parts)

    parts = [p for p in (last_name, first_name) if p]
    if suffix:
        parts.append(suffix)
    return " ".join(parts)

def is_restricted_document(driver):
    """Check if document has restricted images"""
    try:
        element = WebDriverWait(driver, 1).until(
            EC.presence_of_element_located(
                (By.XPATH, "/html/body/div[2]/div[4]/div/div[3]/section[3]/div/div/p")
            )
        )
        return "Images for this document have been restricted." in element.text
    except TimeoutException:
        return False