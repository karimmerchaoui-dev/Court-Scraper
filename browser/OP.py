import json
import re
import socket
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from pipeline_tracker import update_pipeline_status

sys.path.append(r"C:\Users\pc\PycharmProjects\Court-Scraper")
from ai.llm_helper import extract_financial_obligations_haiku, match_address_with_haiku
from utils.zillow_helpers import get_zillow_infos


class CivilViewForeclosureScraper:
    def __init__(self, base_url="https://salesweb.civilview.com", delay=1, max_workers=5):
        self.base_url = base_url
        self.delay = delay
        self.max_workers = max_workers
        self.session = requests.Session()
        self.files_dir = r"C:\Users\pc\PycharmProjects\Court-Scraper\files"
        # Headers pour éviter le blocage
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

        # Setup logging

    def get_page(self, url, timeout=30):
        """Récupérer une page avec retry - méthode standard"""
        max_retries = 3
        backoff_delays = [2, 5, 10]  # Progressive backoff

        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=timeout)
                return response

            except (requests.exceptions.ConnectionError,
                    socket.gaierror) as e:
                if attempt < max_retries - 1:
                    delay = backoff_delays[attempt]
                    time.sleep(delay)
                else:
                    return None

            except requests.exceptions.HTTPError as e:
                if e.response.status_code in [403, 429]:  # Forbidden or Too Many Requests
                    if attempt < max_retries - 1:
                        delay = backoff_delays[attempt] * 2  # Longer wait for rate limiting
                        time.sleep(delay)
                    else:
                        return None
                else:
                    return None

            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    delay = backoff_delays[attempt]
                    time.sleep(delay)
                else:
                    return None

    def _process_single_listing(self, address, detail_url, thread_id):
        """
        Process a SINGLE listing - runs in its own thread for TRUE PARALLELISM
        This is the KEY function for parallel listing processing
        """
        try:
            print(f"🔹 Sub-thread {threading.current_thread().name} processing: {address}")

            # Get Zillow info (runs in parallel across threads)
            zest, status, home_type, city, prop_type, is_agent,is_auction = get_zillow_infos(
                address,
                self.files_dir
            )

            # Get listing details (runs in parallel across threads)
            detailed_info = self.get_listing_details(detail_url)

            result_row = {
                'found': '✅',
                'address': address,
                'Upset Price': '',
                'Upset Amount': '',
                'Approx. Judgment': '',
                'Approx. Upset': '',
                'Debt Amount': '',
                'sales_date': '',
                'case_number': '',
                'lowest_zestimate': zest,
                'zillow_home_type': home_type,
                'zillow_prop_type': prop_type,
                'zillow_is_agent': is_agent,
                'zillow_status': status,
            }

            raw_text = detailed_info.get('raw_text', '')
            cleaned_text = "\n".join(line for line in raw_text.splitlines() if line.strip())

            # Extract sales date
            if "Sales Date:" in raw_text:
                sales_date = raw_text.split('Sales Date:')[1].split('Plaintiff:')[0].strip()
                result_row['sales_date'] = sales_date
            elif "Sale Date" in raw_text:
                result_row['status_history'] = detailed_info.get('History', {})

            # Extract case number
            if "DOCKET NO." in raw_text:
                case_number = raw_text.split('DOCKET NO.')[-1].split('SHERIFF')[0].strip()
                result_row['case_number'] = case_number

            # Extract amounts
            amounts = extract_amount(cleaned_text)
            for label, value in amounts:
                label_lower = label.lower()
                if "upset price" in label_lower:
                    result_row['Upset Price'] = value
                elif "upset amount" in label_lower:
                    result_row['Upset Amount'] = value
                elif "appraised value" in label_lower:
                    result_row['Appraised Value'] = value
                elif "approx. judgment" in label_lower:
                    result_row['Approx. Judgment'] = value
                elif "approx. upset" in label_lower:
                    result_row['Approx. Upset'] = value
                elif "debt amount" in label_lower:
                    result_row['Debt Amount'] = value

            print(f"✅ Sub-thread completed: {address}")
            return result_row

        except Exception as e:
            print(f"❌ Error processing {address}: {e}")
            return None

    def get_available_sales_dates_and_months(self, county_url):
        """
        Extracts all available Sales Dates (PropertyStatusDate) and
        Sales Months (MonthNumber) from the search form.
        """
        response = self.get_page(county_url)
        if not response:
            return {'sales_dates': [], 'sales_months': []}

        soup = BeautifulSoup(response.content, 'html.parser')

        available_dates = []
        available_months = []

        # 1. Scrape Sales Date options from dropdown with id="PropertyStatusDate"
        sales_date_select = soup.find('select', {'id': 'PropertyStatusDate'})
        if sales_date_select:
            for option in sales_date_select.find_all('option'):
                date_value = option.get('value', '').strip()
                date_text = option.get_text(strip=True)
                if date_value:
                    available_dates.append({
                        'value': date_value,
                        'text': date_text
                    })

        # 2. Scrape Sales Month options from dropdown with id="MonthNumber"
        sales_month_select = soup.find('select', {'id': 'MonthNumber'})
        if sales_month_select:
            for option in sales_month_select.find_all('option'):
                month_value = option.get('value', '').strip()
                month_text = option.get_text(strip=True)
                # Skip the default/empty value, typically '0' or an empty string
                if month_value and month_value != '0':
                    available_months.append({
                        'value': month_value,
                        'text': month_text
                    })

        return {
            'sales_dates': available_dates,
            'sales_months': available_months
        }

    def get_page_with_status(self, url, is_open=True, timeout=30):
        """Récupérer une page avec un statut spécifique (Open ou Sold/Cancelled)"""
        max_retries = 3
        backoff_delays = [2, 5, 10]

        for attempt in range(max_retries):
            try:
                # Prepare POST data to simulate the radio button selection
                post_data = {
                    'IsOpen': 'true' if is_open else 'false'
                }

                # First, get the page normally to get any required form data
                response = self.session.get(url, timeout=timeout)
                response.raise_for_status()

                # Parse the page to get any hidden form fields
                soup = BeautifulSoup(response.content, 'html.parser')

                # Look for forms and hidden inputs
                forms = soup.find_all('form')
                for form in forms:
                    hidden_inputs = form.find_all('input', type='hidden')
                    for hidden_input in hidden_inputs:
                        name = hidden_input.get('name')
                        value = hidden_input.get('value', '')
                        if name:
                            post_data[name] = value

                # Make a POST request with the status selection
                if len(forms) > 0:  # If there's a form, submit it
                    form_action = forms[0].get('action', '')
                    if form_action:
                        post_url = urljoin(url, form_action)
                    else:
                        post_url = url

                    response = self.session.post(post_url, data=post_data, timeout=timeout)
                    response.raise_for_status()

                return response

            except (requests.exceptions.ConnectionError,
                    requests.exceptions.DNSLookupError,
                    socket.gaierror) as e:
                if attempt < max_retries - 1:
                    delay = backoff_delays[attempt]
                    time.sleep(delay)
                else:
                    return None

            except requests.exceptions.HTTPError as e:
                if e.response.status_code in [403, 429]:
                    if attempt < max_retries - 1:
                        delay = backoff_delays[attempt] * 2
                        time.sleep(delay)
                    else:
                        return None
                else:
                    return None

            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    delay = backoff_delays[attempt]
                    time.sleep(delay)
                else:
                    return None
        """Récupérer une page avec retry"""
        max_retries = 3
        backoff_delays = [2, 5, 10]  # Progressive backoff

        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=timeout)
                response.raise_for_status()
                return response

            except (requests.exceptions.ConnectionError,
                    requests.exceptions.DNSLookupError,
                    socket.gaierror) as e:
                if attempt < max_retries - 1:
                    delay = backoff_delays[attempt]
                    time.sleep(delay)
                else:
                    return None

            except requests.exceptions.HTTPError as e:
                if e.response.status_code in [403, 429]:  # Forbidden or Too Many Requests
                    if attempt < max_retries - 1:
                        delay = backoff_delays[attempt] * 2  # Longer wait for rate limiting
                        time.sleep(delay)
                    else:
                        return None
                else:
                    return None

            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    delay = backoff_delays[attempt]
                    time.sleep(delay)
                else:
                    return None

    def get_page_with_search_params(self, url, is_open=True, month_number=None, sales_date=None, timeout=30):
        """
        Retrieves a page after simulating a form submission with status, month, or date parameters.
        """
        # (Keep your existing retry logic here)
        max_retries = 3
        backoff_delays = [2, 5, 10]

        for attempt in range(max_retries):
            try:
                # 1. GET the page to get the initial form state (VIEWSTATE, etc.)
                response = self.session.get(url, timeout=timeout)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')

                post_data = {}

                # 2. Extract all hidden form fields (ASP.NET Web Forms)
                forms = soup.find_all('form')
                if not forms:
                    return response  # Return the initial GET page if no form

                # Extract hidden inputs from the first form
                form = forms[0]
                hidden_inputs = form.find_all('input', type='hidden')
                for hidden_input in hidden_inputs:
                    name = hidden_input.get('name')
                    value = hidden_input.get('value', '')
                    if name:
                        post_data[name] = value

                # 3. Apply search parameters: Status, Month, and Date

                # Status: Map the radio button state (assuming input name 'IsOpen')
                post_data['IsOpen'] = 'true' if is_open else 'false'

                # Month Number (if provided)
                if month_number:
                    # Clear date if month is selected
                    post_data['PropertyStatusDate'] = ''
                    post_data['MonthNumber'] = month_number

                # Sales Date (if provided)
                elif sales_date:
                    # Clear month if date is selected
                    post_data['PropertyStatusDate'] = sales_date
                    post_data['MonthNumber'] = '0'  # Default to '0' to clear month

                # IMPORTANT: Simulate clicking the Search button.
                # The Search button is often named 'Search' or has a specific control name.
                # Based on the screenshot, we'll try to simulate the main search action.
                # Note: The actual button action might be required if the page relies on JavaScript.
                post_data['ctl00$MainContent$SearchButton'] = 'Search'

                # 4. Perform the POST request
                form_action = form.get('action', '')
                post_url = urljoin(url, form_action)

                # The main 'Search' button value is often required for the POST to execute the search logic
                post_data['ctl00$MainContent$SearchButton'] = 'Search'

                # Perform POST (simulating the 'Search' button click)
                response = self.session.post(post_url, data=post_data, timeout=timeout)
                response.raise_for_status()

                return response

            except requests.RequestException as e:
                # (Keep your existing error/retry handling here)
                if attempt < max_retries - 1:
                    delay = backoff_delays[attempt]
                    time.sleep(delay)
                else:
                    return None
        return None

    def get_all_counties(self):
        """Lister tous les comtés disponibles"""
        response = self.get_page(self.base_url)
        if not response:
            return {}

        soup = BeautifulSoup(response.content, 'html.parser')
        counties = {}

        links = soup.find_all('a', href=re.compile(r'/Sales/SalesSearch\?countyId=\d+'))
        for link in links:
            href = link.get('href')
            county_name = link.text.strip()
            if href and county_name:
                match = re.search(r'countyId=(\d+)', href)
                if match:
                    county_id = match.group(1)
                    full_url = urljoin(self.base_url, href)
                    counties[county_name] = {
                        'county_id': county_id,
                        'url': full_url
                    }

        return counties

    def detect_table_structure(self, table):
        """Detect the structure of a table by analyzing headers"""
        header_row = table.find('tr')
        if not header_row:
            return None

        headers = header_row.find_all(['th', 'td'])
        header_texts = [h.get_text(strip=True).lower() for h in headers]

        # Create a mapping of known column types
        column_mapping = {}
        for i, header in enumerate(header_texts):
            if 'sheriff' in header and '#' in header:
                column_mapping['sheriff_number'] = i
            elif 'sales date' in header or 'sale date' in header:
                column_mapping['sales_date'] = i
            elif 'court case' in header:
                column_mapping['court_case'] = i
            elif 'plaintiff' in header:
                column_mapping['plaintiff'] = i
            elif 'defendant' in header:
                column_mapping['defendant'] = i
            elif 'address' in header:
                column_mapping['address'] = i
            elif 'attorney' in header:
                column_mapping['attorney'] = i
            elif 'parcel' in header:
                column_mapping['parcel_number'] = i
            elif 'case title' in header:
                column_mapping['case_title'] = i
            elif 'property status' in header or 'status' in header:
                column_mapping['property_status'] = i
            elif 'writ amount' in header or 'amount' in header:
                column_mapping['writ_amount'] = i
            elif 'terms' in header and 'conditions' in header:
                column_mapping['terms_conditions'] = i

        return column_mapping

    def extract_listing_basic_data(self, row, column_mapping=None):
        """Extraire les infos basiques d'une ligne - ADAPTIVE VERSION"""
        cells = row.find_all(['td', 'th'])

        # Log the number of cells found for debugging

        if len(cells) < 3:  # Need at least 3 columns for minimal data
            return None

        # Initialize data dictionary
        data = {}

        # If we have column mapping, use it
        if column_mapping:
            for field, col_index in column_mapping.items():
                if col_index < len(cells):
                    data[field] = cells[col_index].get_text(strip=True)
        else:
            # Fallback: try to guess based on common patterns
            # This is a generic approach when we don't have header mapping
            for i, cell in enumerate(cells):
                cell_text = cell.get_text(strip=True)
                data[f'column_{i}'] = cell_text

                # Try to identify specific fields by content pattern
                if re.match(r'\d{8}', cell_text):  # 8-digit number, likely sheriff number
                    data['sheriff_number'] = cell_text
                elif re.match(r'\d{1,2}/\d{1,2}/\d{4}', cell_text):  # Date pattern
                    data['sales_date'] = cell_text
                elif 'vs' in cell_text.lower() or 'v.' in cell_text:  # Case title with vs
                    data['case_title'] = cell_text
                elif any(word in cell_text.lower() for word in ['street', 'road', 'ave', 'dr', 'ct', 'ln']):
                    data['address'] = cell_text

        # Extract plaintiff and defendant from case_title if available
        case_title = data.get('case_title', '')
        if case_title and ('vs' in case_title.lower() or ' v ' in case_title):
            # Handle various formats: "vs", "v.", " v ", etc.
            separators = [' vs ', ' v.', ' v ', ' VS ', ' V ']
            for sep in separators:
                if sep in case_title:
                    parts = case_title.split(sep, 1)
                    data['plaintiff'] = parts[0].strip()
                    data['defendant'] = parts[1].strip()
                    break

        # If we have separate plaintiff/defendant columns, use those
        if not data.get('plaintiff') and column_mapping and 'plaintiff' in column_mapping:
            plaintiff_col = column_mapping['plaintiff']
            if plaintiff_col < len(cells):
                data['plaintiff'] = cells[plaintiff_col].get_text(strip=True)

        if not data.get('defendant') and column_mapping and 'defendant' in column_mapping:
            defendant_col = column_mapping['defendant']
            if defendant_col < len(cells):
                data['defendant'] = cells[defendant_col].get_text(strip=True)

        # Look for detail link in any cell
        detail_link = None
        for cell in cells:
            detail_link = cell.find('a', href=re.compile(r'/Sales/SaleDetails\?PropertyId='))
            if detail_link:
                break

        if detail_link:
            detail_href = detail_link.get('href')
            data['detail_url'] = urljoin(self.base_url, detail_href)
            match = re.search(r'PropertyId=(\d+)', detail_href)
            if match:
                data['property_id'] = match.group(1)

        # Debug log the extracted data

        # Only return data if we found some key fields
        key_fields = ['sheriff_number', 'sales_date', 'case_title', 'plaintiff']
        if any(field in data and data[field] for field in key_fields):
            return data
        else:
            return None

    def extract_case_number(self, text):
        """
        Extracts the case number from text following the line starting with 'Court Case'.
        """
        match = re.search(r'(?im)^Court Case[^\n]*\n([^\n]+)', text)
        if match:
            return match.group(1).strip()
        return None
    def match_address_with_mistral(self, target_address, candidates):
        """
        Uses Mistral to pick which candidate address (from scraped listings)
        best matches the target address.

        candidates: list of dicts like {"index": int, "address": str}
        Returns the matched index (int) or None if no confident match.
        """
        if not candidates:
            return None

        numbered_list = "\n".join(
            f"{c['index']}: {c['address']}" for c in candidates
        )

        prompt = f"""You are matching a target property address against addresses scraped from a county sheriff sale website. Scraped addresses may differ in formatting: abbreviations (St/Street, Ave/Avenue), extra unit/apt numbers, minor typos, or different word order.

Target address: "{target_address}"

Candidate addresses:
{numbered_list}

Decide which candidate (if any) refers to the same property as the target address.
Respond with ONLY a JSON object, no other text:
{{"best_match_index": <int index of the best match, or -1 if none plausibly match>, "confidence": "high" | "medium" | "low"}}
"""

        try:
            response = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {get_mistral_client()}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "mistral-large-latest",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0,
                },
                timeout=30,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            result = json.loads(content)

            idx = result.get("best_match_index", -1)
            confidence = result.get("confidence", "low")

            if idx is None or idx < 0:
                return None
            if confidence == "low":
                # be conservative — don't auto-accept low-confidence matches
                return None
            return idx

        except (requests.RequestException, json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"Mistral address match failed: {e}")
            return None
    def scrape_county_listings(self, county_name, county_info, target_address,
                               include_details=True, status='sold'):
        """
        Scrapes listings for a county, iterating through available statuses
        and sales months, then uses Mistral to identify which scraped
        listing matches target_address.
        """

        all_listings = []
        candidate_pool = []  # [{"index": int, "address": str, "listing_data": dict}, ...]

        date_info = self.get_available_sales_dates_and_months(county_info['url'])
        months_to_scrape = date_info['sales_months']

        statuses_to_scrape = []
        if status == 'both':
            statuses_to_scrape = [('open', True), ('sold', False)]
        elif status == 'open':
            statuses_to_scrape = [('open', True)]
        elif status == 'sold':
            statuses_to_scrape = [('sold', False)]
        else:
            statuses_to_scrape = [('open', True)]

        for status_name, is_open in statuses_to_scrape:
            for month_data in months_to_scrape:
                month_name = month_data['text']
                month_value = month_data['value']

                response = self.get_page_with_search_params(
                    county_info['url'],
                    is_open=is_open,
                    month_number=month_value
                )
                soup = BeautifulSoup(response.content, 'html.parser')
                listings = []

                tables = soup.find_all('table')
                for table_idx, table in enumerate(tables):
                    address_index = None
                    thead = table.find('thead')
                    if thead:
                        headers = thead.find_all('th')
                        for index, header in enumerate(headers, start=1):
                            if header.get_text(strip=True) == "Address":
                                address_index = index
                                break

                    rows = table.find_all('tr')
                    if len(rows) <= 1:
                        continue

                    column_mapping = self.detect_table_structure(table)

                    for row_idx, row in enumerate(rows[1:], 1):
                        listing_data = self.extract_listing_basic_data(row, column_mapping)
                        info = row.find_all('td')

                        if address_index and address_index <= len(info):
                            address_text = info[int(address_index) - 1].get_text(strip=True)
                            if address_text and listing_data:
                                listing_data['address'] = address_text
                                listing_data['county'] = county_name
                                listing_data['listing_status'] = status_name
                                listing_data['sales_month_filter'] = month_name

                                candidate_pool.append({
                                    "index": len(candidate_pool),
                                    "address": address_text,
                                    "listing_data": listing_data,
                                })
                                listings.append(listing_data)
                                continue

                        if listing_data:
                            listing_data['county'] = county_name
                            listing_data['listing_status'] = status_name
                            listing_data['sales_month_filter'] = month_name
                            listings.append(listing_data)

                all_listings.extend(listings)

        # --- Resolve match via Mistral once, across everything scraped ---
        if target_address and candidate_pool:

            match_result = match_address_with_haiku(
                target_address,
                [{"index": c["index"], "address": c["address"]} for c in candidate_pool]
            )
            print(f"match_result : {match_result}")
            idx = match_result.get("best_match_index")
            confidence = match_result.get("confidence")

            if idx is not None and confidence in ("high", "medium"):
                matched = candidate_pool[idx]["listing_data"]
                if matched.get('detail_url') and include_details:
                    detailed_info = self.get_listing_details(matched['detail_url'])
                    return detailed_info
                return matched
            else:
                print(
                    f"No confident address match for '{target_address}' "
                    f"(confidence={confidence}, reasoning={match_result.get('reasoning')})"
                )

        return all_listings

    def get_listing_details(self, detail_url):
        """Extraire tout le contenu détaillé d'une page de détails"""
        response = self.get_page(detail_url)
        if not response:
            return {}
        details = None
        soup = BeautifulSoup(response.content, 'html.parser')

        # Get the full text content
        full_text = soup.get_text(separator="\n", strip=True)
        try:
            history = []
            sales_history_text = full_text.split("[Collapse All]")[1].split("*")[0]

            lines = [line.strip() for line in sales_history_text.splitlines() if line.strip()]

            date_pattern = re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}")



            i = 0
            while i < len(lines) - 1:
                description = lines[i]
                next_line = lines[i + 1]

                if date_pattern.fullmatch(next_line):
                    history.append({
                        "description": description,
                        "date": next_line
                    })
                    i += 2
                else:
                    i += 1

            history_json = json.dumps(history, indent=4)
            details = {
                "raw_text": full_text,
                "sales_date": history_json
            }
        except Exception:
            print(f"error with : {detail_url}")
            traceback.print_exc()
            pass
        # Try to extract specific structured data from the page
        try:
            # Look for specific fields in the details page
            if "Starting Bid:" in full_text:
                bid_match = re.search(r'Starting Bid:\s*\$?([\d,]+\.?\d*)', full_text)
                if bid_match:
                    details['starting_bid'] = bid_match.group(1).strip()

            if "Appraised Value:" in full_text:
                value_match = re.search(r'Appraised Value:\s*\$?([\d,]+\.?\d*)', full_text)
                if value_match:
                    details['appraised_value'] = value_match.group(1).strip()

            if "Court Case #:" in full_text:
                case_match = re.search(r'Court Case #:\s*([^\n]+)', full_text)
                if case_match:
                    details['court_case'] = case_match.group(1).strip()

            if "Parcel #:" in full_text:
                parcel_match = re.search(r'Parcel #:\s*([^\n]+)', full_text)
                if parcel_match:
                    details['parcel_number'] = parcel_match.group(1).strip()

            if "Attorney:" in full_text:
                attorney_match = re.search(r'Attorney:\s*([^\n]+)', full_text)
                if attorney_match:
                    details['attorney'] = attorney_match.group(1).strip()
            if "Status History" in full_text:
                details['status_history'] = history_json
        except Exception as e:
            traceback.print_exc()
        return details

    def scrape_single_county(self, county_name, number_input, include_details=True, analyze_structure=False,
                             status='both'):
        """Scrape a single county by name with status option"""
        counties = self.get_all_counties()

        if county_name in counties:
            return self.scrape_county_listings(county_name, counties[county_name], number_input, include_details,
                                               status=status)

    def scrape_county_listings_(self, county_name, county_info, number_input, include_details=True, status='open'):
        """
        Scrapes listings with TWO-LEVEL PARALLELISM:
        - Level 1: Different months/statuses in parallel (10 threads)
        - Level 2: Individual listings within each month in parallel (10 threads each)
        """

        all_listings = []
        lock = threading.Lock()

        # Get available months
        date_info = self.get_available_sales_dates_and_months(county_info['url'])
        months_to_scrape = date_info['sales_months']

        # Determine statuses
        statuses_to_scrape = []
        if status == 'both':
            statuses_to_scrape = [('open', True), ('sold', False)]
        elif status == 'open':
            statuses_to_scrape = [('open', True)]
        elif status == 'sold':
            statuses_to_scrape = [('sold', False)]
        else:
            statuses_to_scrape = [('open', True)]

        # Build all combinations
        combinations = []
        for status_name, is_open in statuses_to_scrape:
            for month_data in months_to_scrape:
                combinations.append({
                    'status_name': status_name,
                    'is_open': is_open,
                    'month_data': month_data,
                    'county_url': county_info['url']
                })

        print(f"🚀 Starting TWO-LEVEL parallel processing with 10 month threads...")
        print(f"📊 Total month/status combinations: {len(combinations)}")

        def process_month_combination(combination):
            """
            Process ONE month/status combination.
            THIS RUNS IN ITS OWN THREAD (Level 1)
            """
            status_name = combination['status_name']
            is_open = combination['is_open']
            month_data = combination['month_data']
            county_url = combination['county_url']

            month_name = month_data['text']
            month_value = month_data['value']

            thread_name = threading.current_thread().name
            print(f"🧵 [Level 1] Thread {thread_name} started: {status_name} - {month_name}")

            # Get the page for this combination
            response = self.get_page_with_search_params(
                county_url,
                is_open=is_open,
                month_number=month_value
            )

            if not response:
                print(f"❌ No response for {status_name} - {month_name}")
                return []

            soup = BeautifulSoup(response.content, 'html.parser')

            # --- COLLECT ALL LISTINGS FIRST ---
            listings_to_process = []
            tables = soup.find_all('table')

            for table in tables:
                thead = table.find('thead')
                address_index = None
                if thead:
                    headers = thead.find_all('th')
                    for index, header in enumerate(headers, start=1):
                        if header.get_text(strip=True) == "Address":
                            address_index = index
                            break

                rows = table.find_all('tr')
                if len(rows) <= 1:
                    continue

                column_mapping = self.detect_table_structure(table)

                for row in rows[1:]:
                    listing_data = self.extract_listing_basic_data(row, column_mapping)
                    if not listing_data or 'detail_url' not in listing_data:
                        continue

                    info = row.find_all('td')
                    if address_index and address_index <= len(info):
                        address_cell = info[address_index - 1]
                        if address_cell:
                            if not isinstance(address_cell, str):
                                address = address_cell.get_text(strip=True)
                                listings_to_process.append({
                                    'address': address,
                                    'detail_url': listing_data['detail_url']
                                })

            print(f"📋 [Level 1] {thread_name} found {len(listings_to_process)} listings to process in parallel")

            # --- LEVEL 2: PROCESS EACH LISTING IN PARALLEL ---
            month_results = []
            if listings_to_process:
                # Create a pool of 10 sub-threads for this month
                with ThreadPoolExecutor(max_workers=10) as listing_executor:
                    # Submit ALL listings in this month to parallel threads
                    future_to_listing = {
                        listing_executor.submit(
                            self._process_single_listing,
                            listing['address'],
                            listing['detail_url'],
                            thread_name
                        ): listing
                        for listing in listings_to_process
                    }

                    # Collect results as they complete
                    for future in as_completed(future_to_listing):
                        try:
                            result = future.result(timeout=60)
                            if result:
                                month_results.append(result)
                        except Exception as e:
                            print(f"❌ Error in listing thread: {e}")

            print(
                f"✅ [Level 1] {thread_name} completed: {status_name} - {month_name} (processed {len(month_results)} listings)")
            return month_results

        # --- LEVEL 1: PROCESS MONTHS IN PARALLEL ---
        with ThreadPoolExecutor(max_workers=10) as month_executor:
            # Submit ALL month combinations to parallel threads
            future_to_combo = {
                month_executor.submit(process_month_combination, combo): combo
                for combo in combinations
            }

            completed = 0
            for future in as_completed(future_to_combo):
                combo = future_to_combo[future]
                try:
                    result_list = future.result(timeout=120)
                    with lock:
                        all_listings.extend(result_list)
                        completed += 1
                        print(f"📊 Overall Progress: {completed}/{len(combinations)} month threads completed")
                except Exception as e:
                    print(f"❌ Error in month thread for {combo['status_name']}: {e}")

        print(f"🎉 COMPLETE! Total listings found: {len(all_listings)}")
        return all_listings


def extract_amount(text):
    """
    Extracts labeled dollar amounts from text based on foreclosure keywords.
    Returns a list of tuples like: [("Approx. Judgment", "$55,758.18"), ...]
    """
    pattern = r'(?im)\b(Upset Price|Upset Amount|Appraised Value|Approx\. Judgment\*?|Approx\. Upset\*?)\b[^$:\n]*[:\s-]*?(\$[\d,]+(?:\.\d{1,2})?)'
    matches = re.findall(pattern, text)
    # Clean and normalize labels (remove trailing * if present)
    return [(label.replace('*', '').strip(), amount.strip()) for label, amount in matches]



def extract_info_from_salesweb(address, county, state):
    try:
        scraper = CivilViewForeclosureScraper(delay=2, max_workers=1)

        test_data = scraper.scrape_single_county(f"{county.strip().capitalize()} County, {state.strip()}", address,
                                                include_details=True, analyze_structure=True)
        # Prepare empty columns for each possible amount type
        result_row = {
            'found': '',
            'address': address,
            'Upset Price': '',
            'Upset Amount': '',
            'Approx. Judgment': '',
            'Approx. Upset': '',
        }
        if test_data:
            for label in ["Description:", "Priors:","Property Note:"]:
                if label in test_data['raw_text']:
                    note = test_data['raw_text'].split(label, 1)[1].split("Status History", 1)[0].strip()
                    break
            financial_obligations = extract_financial_obligations_haiku(note)
            print(f"financial_obligations : {financial_obligations}")
            result_row['found'] = '✅'
            raw_text = test_data.get('raw_text', '')
            cleaned_text = "\n".join(line for line in raw_text.splitlines() if line.strip())
            if "Sales Date:" in raw_text:
                sales_date = raw_text.split('Sales Date:')[1].split('Plaintiff:')[0].strip()
                result_row['sales_date'] = sales_date
            elif "Sale Date" in raw_text:
                print("raaaaw 2 : ", raw_text)
                sales_date = raw_text.split('Sale Date:')[1].split('Plaintiff:')[0].strip()
                print("saaaale : ", sales_date)
                result_row['sales_date'] = sales_date
            if "status_history" in test_data:
                result_row['status_history'] = test_data['status_history']
            if financial_obligations:
                if financial_obligations:
                    financial_obligations = financial_obligations["financial_obligations"]
                result_row['financial_obligations'] = financial_obligations
            amounts = extract_amount(cleaned_text)
            match = re.search(r'Address:\s*\n(.*\n.*)', raw_text)
            if match:
                address = match.group().strip()
                result_row['address'] = address.replace('\n', ' ').replace('Address:', '').strip()
            # Fill correct columns based on label
            for label, value in amounts:
                label_lower = label.lower()
                if "upset price" in label_lower:
                    result_row['Upset Price'] = value
                elif "upset amount" in label_lower:
                    result_row['Upset Amount'] = value
                elif "appraised value" in label_lower:
                    result_row['Appraised Value'] = value
                elif "approx. judgment" in label_lower:
                    result_row['Approx. Judgment'] = value
                elif "approx. upset" in label_lower:
                    result_row['Approx. Upset'] = value
        else:
            result_row['found'] = '❌'
        update_pipeline_status("salesweb", "SUCCESS")
        return result_row
    except Exception:
        update_pipeline_status("salesweb", "FAILED", tb_message=traceback.format_exc())