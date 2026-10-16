"""Unit tests for CivilViewForeclosureScraper (non-network logic)."""

import pytest
from src.scrapers.civilview import CivilViewForeclosureScraper


@pytest.fixture
def scraper():
    return CivilViewForeclosureScraper()


def test_detect_table_structure_address(scraper):
    from bs4 import BeautifulSoup
    html = "<table><tr><th>Address</th><th>Sales Date</th></tr></table>"
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    mapping = scraper._detect_table_structure(table)
    assert mapping.get("address") == 0
    assert mapping.get("sales_date") == 1


def test_extract_listing_basic_data_returns_none_for_short_rows(scraper):
    from bs4 import BeautifulSoup
    html = "<table><tr><td>A</td><td>B</td></tr></table>"
    soup = BeautifulSoup(html, "html.parser")
    row = soup.find("tr")
    result = scraper._extract_listing_basic_data(row)
    assert result is None
