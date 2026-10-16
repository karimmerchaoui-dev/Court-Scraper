"""
CivilView Foreclosure Scraper
Scrapes foreclosure listings from salesweb.civilview.com
"""

import re
import socket
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.utils.parsers import extract_amount
from src.utils.zillow import get_zillow_infos


class CivilViewForeclosureScraper:
    """
    Scrapes foreclosure listings from salesweb.civilview.com with two-level parallelism:
    - Level 1: Different months/statuses in parallel (10 threads)
    - Level 2: Individual listings within each month in parallel (4 threads)
    """

    BASE_URL = "https://salesweb.civilview.com"

    def __init__(self, base_url: str = BASE_URL, delay: int = 1,
                 max_workers: int = 5, files_dir: str = None):
        self.base_url = base_url
        self.delay = delay
        self.max_workers = max_workers
        self.files_dir = files_dir or "/tmp"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        })

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _get_page(self, url: str, timeout: int = 30):
        backoff = [2, 5, 10]
        for attempt, wait in enumerate(backoff):
            try:
                return self.session.get(url, timeout=timeout)
            except (requests.exceptions.ConnectionError, socket.gaierror):
                if attempt < len(backoff) - 1:
                    time.sleep(wait)
            except requests.exceptions.HTTPError as exc:
                if exc.response.status_code in (403, 429):
                    if attempt < len(backoff) - 1:
                        time.sleep(wait * 2)
                return None
            except requests.RequestException:
                if attempt < len(backoff) - 1:
                    time.sleep(wait)
        return None

    def _post_search(self, url: str, is_open: bool = True,
                     month_number: str = None, sales_date: str = None,
                     timeout: int = 30):
        backoff = [2, 5, 10]
        for attempt, wait in enumerate(backoff):
            try:
                resp = self.session.get(url, timeout=timeout)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.content, "html.parser")
                forms = soup.find_all("form")
                if not forms:
                    return resp

                form = forms[0]
                post_data = {
                    inp["name"]: inp.get("value", "")
                    for inp in form.find_all("input", type="hidden")
                    if inp.get("name")
                }
                post_data["IsOpen"] = "true" if is_open else "false"
                if month_number:
                    post_data["PropertyStatusDate"] = ""
                    post_data["MonthNumber"] = month_number
                elif sales_date:
                    post_data["PropertyStatusDate"] = sales_date
                    post_data["MonthNumber"] = "0"
                post_data["ctl00$MainContent$SearchButton"] = "Search"

                resp = self.session.post(urljoin(url, form.get("action", "")),
                                         data=post_data, timeout=timeout)
                resp.raise_for_status()
                return resp
            except requests.RequestException:
                if attempt < len(backoff) - 1:
                    time.sleep(wait)
        return None

    # ------------------------------------------------------------------
    # County helpers
    # ------------------------------------------------------------------

    def get_all_counties(self) -> dict:
        response = self._get_page(self.base_url)
        if not response:
            return {}
        soup = BeautifulSoup(response.content, "html.parser")
        counties = {}
        for link in soup.find_all("a", href=re.compile(r"/Sales/SalesSearch\?countyId=\d+")):
            href = link.get("href", "")
            name = link.text.strip()
            match = re.search(r"countyId=(\d+)", href)
            if match and name:
                counties[name] = {"county_id": match.group(1),
                                   "url": urljoin(self.base_url, href)}
        return counties

    def get_available_sales_dates_and_months(self, county_url: str) -> dict:
        response = self._get_page(county_url)
        if not response:
            return {"sales_dates": [], "sales_months": []}
        soup = BeautifulSoup(response.content, "html.parser")

        def parse_select(select_id, exclude_values=("", "0")):
            sel = soup.find("select", {"id": select_id})
            if not sel:
                return []
            return [{"value": o.get("value", "").strip(), "text": o.get_text(strip=True)}
                    for o in sel.find_all("option")
                    if o.get("value", "").strip() not in exclude_values]

        return {
            "sales_dates": parse_select("PropertyStatusDate", exclude_values=("",)),
            "sales_months": parse_select("MonthNumber"),
        }

    # ------------------------------------------------------------------
    # Table parsing
    # ------------------------------------------------------------------

    def _detect_table_structure(self, table) -> dict:
        header_row = table.find("tr")
        if not header_row:
            return {}
        headers = [h.get_text(strip=True).lower()
                   for h in header_row.find_all(["th", "td"])]
        checks = {
            "sheriff_number": lambda h: "sheriff" in h and "#" in h,
            "sales_date": lambda h: "sales date" in h or "sale date" in h,
            "court_case": lambda h: "court case" in h,
            "plaintiff": lambda h: "plaintiff" in h,
            "defendant": lambda h: "defendant" in h,
            "address": lambda h: h == "address",
            "attorney": lambda h: "attorney" in h,
            "parcel_number": lambda h: "parcel" in h,
            "case_title": lambda h: "case title" in h,
            "property_status": lambda h: "property status" in h or h == "status",
            "writ_amount": lambda h: "writ amount" in h or h == "amount",
        }
        mapping = {}
        for i, header in enumerate(headers):
            for field, check in checks.items():
                if field not in mapping and check(header):
                    mapping[field] = i
        return mapping

    def _extract_listing_basic_data(self, row, column_mapping: dict = None):
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            return None

        data = {}
        if column_mapping:
            for field, idx in column_mapping.items():
                if idx < len(cells):
                    data[field] = cells[idx].get_text(strip=True)
        else:
            for i, cell in enumerate(cells):
                text = cell.get_text(strip=True)
                data[f"column_{i}"] = text
                if re.match(r"\d{8}", text):
                    data["sheriff_number"] = text
                elif re.match(r"\d{1,2}/\d{1,2}/\d{4}", text):
                    data["sales_date"] = text
                elif "vs" in text.lower() or "v." in text:
                    data["case_title"] = text
                elif any(w in text.lower() for w in ["street", "road", "ave", "dr", "ct", "ln"]):
                    data["address"] = text

        case_title = data.get("case_title", "")
        for sep in [" vs ", " v.", " v ", " VS ", " V "]:
            if sep in case_title:
                parts = case_title.split(sep, 1)
                data["plaintiff"] = parts[0].strip()
                data["defendant"] = parts[1].strip()
                break

        for cell in cells:
            link = cell.find("a", href=re.compile(r"/Sales/SaleDetails\?PropertyId="))
            if link:
                href = link.get("href", "")
                data["detail_url"] = urljoin(self.base_url, href)
                m = re.search(r"PropertyId=(\d+)", href)
                if m:
                    data["property_id"] = m.group(1)
                break

        if any(data.get(f) for f in ["sheriff_number", "sales_date", "case_title", "plaintiff"]):
            return data
        return None

    def _get_listing_details(self, detail_url: str) -> dict:
        response = self._get_page(detail_url)
        if not response:
            return {}
        soup = BeautifulSoup(response.content, "html.parser")
        full_text = soup.get_text(separator="\n", strip=True)
        details = {"raw_text": full_text}
        for key, pattern in {
            "starting_bid": r"Starting Bid:\s*\$?([\d,]+\.?\d*)",
            "appraised_value": r"Appraised Value:\s*\$?([\d,]+\.?\d*)",
            "court_case": r"Court Case #:\s*([^\n]+)",
            "parcel_number": r"Parcel #:\s*([^\n]+)",
            "attorney": r"Attorney:\s*([^\n]+)",
        }.items():
            m = re.search(pattern, full_text)
            if m:
                details[key] = m.group(1).strip()
        return details

    # ------------------------------------------------------------------
    # Listing processor
    # ------------------------------------------------------------------

    def _process_single_listing(self, address: str, detail_url: str,
                                  thread_id: str, county_name: str):
        try:
            zest, status, home_type, city, prop_type, is_agent,auction = get_zillow_infos(
                address, self.files_dir
            )
            detailed_info = self._get_listing_details(detail_url)

            result = {
                "found": "✅", "address": address,
                "Upset Price": "", "Upset Amount": "",
                "Approx. Judgment": "", "Approx. Upset": "",
                "Debt Amount": "", "sales_date": "", "case_number": "",
                "lowest_zestimate": zest, "zillow_home_type": home_type,
                "zillow_prop_type": prop_type, "zillow_is_agent": is_agent,
                "zillow_status": status, "county_name": county_name, "is_auction": auction
            }

            raw = detailed_info.get("raw_text", "")
            cleaned = "\n".join(line for line in raw.splitlines() if line.strip())

            for marker, stopper in [("Sales Date:", "Plaintiff:"), ("Sale Date:", "Plaintiff:")]:
                if marker in raw:
                    result["sales_date"] = raw.split(marker)[1].split(stopper)[0].strip()
                    break

            if "DOCKET NO." in raw:
                case_num = raw.split("DOCKET NO.")[-1].split("SHERIFF")[0].strip()
                for s in ("ATTORNEY", "CTL"):
                    if s in case_num:
                        case_num = case_num.split(s)[0]
                result["case_number"] = case_num

            for label, value in extract_amount(cleaned):
                ll = label.lower()
                if "upset price" in ll:
                    result["Upset Price"] = value
                elif "upset amount" in ll:
                    result["Upset Amount"] = value
                elif "appraised value" in ll:
                    result["Appraised Value"] = value
                elif "approx. judgment" in ll:
                    result["Approx. Judgment"] = value
                elif "approx. upset" in ll:
                    result["Approx. Upset"] = value
                elif "debt amount" in ll:
                    result["Debt Amount"] = value

            return result
        except Exception:
            traceback.print_exc()
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scrape_county_listings(self, county_name: str, county_info: dict,
                                number_input: str, include_details: bool = True,
                                status: str = "open") -> list:
        """
        Scrape all listings for a county with two-level parallelism.

        Args:
            county_name:    Display name of the county.
            county_info:    Dict with 'url' key (from get_all_counties).
            number_input:   Address number prefix for filtering.
            include_details: Fetch individual detail pages.
            status:         'open', 'sold', or 'both'.

        Returns:
            List of listing dicts.
        """
        all_listings = []
        lock = threading.Lock()

        months = self.get_available_sales_dates_and_months(county_info["url"])["sales_months"]
        status_map = {
            "both": [("open", True), ("sold", False)],
            "open": [("open", True)],
            "sold": [("sold", False)],
        }
        statuses = status_map.get(status, [("open", True)])
        combinations = [
            {"status_name": s, "is_open": flag, "month_data": m, "county_url": county_info["url"]}
            for s, flag in statuses for m in months
        ]

        print(f"🚀 {len(combinations)} combinations — starting parallel scrape")

        def _process_month(combo: dict) -> list:
            resp = self._post_search(combo["county_url"], is_open=combo["is_open"],
                                     month_number=combo["month_data"]["value"])
            if not resp:
                return []

            soup = BeautifulSoup(resp.content, "html.parser")
            to_process = []

            for table in soup.find_all("table"):
                thead = table.find("thead")
                address_index = None
                if thead:
                    for i, th in enumerate(thead.find_all("th"), start=1):
                        if th.get_text(strip=True) == "Address":
                            address_index = i
                            break

                col_map = self._detect_table_structure(table)
                rows = table.find_all("tr")
                if len(rows) <= 1:
                    continue
                for row in rows[1:]:
                    listing = self._extract_listing_basic_data(row, col_map)
                    if not listing or "detail_url" not in listing:
                        continue
                    cells = row.find_all("td")
                    if address_index and address_index <= len(cells):
                        addr = cells[address_index - 1].get_text(strip=True)
                        to_process.append({"address": addr, "detail_url": listing["detail_url"]})

            results = []
            with ThreadPoolExecutor(max_workers=4) as ex:
                futures = {
                    ex.submit(self._process_single_listing,
                              item["address"], item["detail_url"],
                              threading.current_thread().name, county_name): item
                    for item in to_process
                }
                for future in as_completed(futures):
                    try:
                        r = future.result(timeout=60)
                        if r:
                            results.append(r)
                    except Exception:
                        traceback.print_exc()
            return results

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_map = {executor.submit(_process_month, c): c for c in combinations}
            done = 0
            for future in as_completed(future_map):
                try:
                    batch = future.result(timeout=120)
                    with lock:
                        all_listings.extend(batch)
                        done += 1
                        print(f"📊 {done}/{len(combinations)} done")
                except Exception:
                    traceback.print_exc()

        print(f"🎉 Total: {len(all_listings)} listings")
        return all_listings

    def scrape_single_county(self, county_name: str, number_input: str,
                              include_details: bool = True, status: str = "both"):
        counties = self.get_all_counties()
        if county_name not in counties:
            print(f"County '{county_name}' not found.")
            return None
        return self.scrape_county_listings(county_name, counties[county_name],
                                            number_input, include_details, status=status)
