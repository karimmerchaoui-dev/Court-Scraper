import re
import unittest
from datetime import datetime
from unittest.mock import MagicMock

BANNED_PARTY_KEYWORDS = [
    "llc", "unknown", "inc", "united", "county", "housing", "state", "florida", "city",
    "clerk", "court", "bank", "association", "national", "business", "admin", "corporation",
    "department", "serivce", "the ", "finance", "secretary"
]

MAX_DEFENDANTS = 10

def parse_date_safe(date_str):
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%m_%d_%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return datetime.min


def extract_defendants_into_report(driver, parties_table_xpath, case_id, report_cases, banned=None, max_defendants=MAX_DEFENDANTS):
    """
    Extracts defendants from the parties table and puts them into report_cases[case_id]
    just like in get_defendants:
    - name_1, description_1, name_2, description_2, ... up to max_defendants
    - main_defendant (newest defendant not containing banned keywords)
    - defendant
    """
    if not parties_table_xpath:
        return report_cases

    if banned is None:
        banned = BANNED_PARTY_KEYWORDS

    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        table = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, parties_table_xpath))
        )
    except Exception:
        return report_cases

    try:
        from selenium.webdriver.common.by import By
        rows = table.find_elements(By.XPATH, ".//tr")
        if not rows:
            rows = table.find_elements(By.XPATH, "./tr | .//div[contains(@class, 'row')]")
        if not rows:
            return report_cases

        name_col_idx = None
        type_col_idx = None
        date_col_idx = None
        header_row_idx = None

        # Inspect up to first 2 rows for header labels
        for r_idx in range(min(2, len(rows))):
            cells = rows[r_idx].find_elements(By.XPATH, "./th | ./td")
            texts = [c.text.strip().lower() for c in cells]
            for c_idx, txt in enumerate(texts):
                if "name" in txt and name_col_idx is None:
                    name_col_idx = c_idx
                    header_row_idx = r_idx
                if "type" in txt and type_col_idx is None:
                    type_col_idx = c_idx
                    header_row_idx = r_idx
                if any(d_kw in txt for d_kw in ("date", "filing", "added")) and date_col_idx is None:
                    date_col_idx = c_idx

        if name_col_idx is None:
            name_col_idx = 0
        if type_col_idx is None:
            type_col_idx = 1

        start_row = (header_row_idx + 1) if header_row_idx is not None else 0
        data_rows = rows[start_row:]

        date_pattern = re.compile(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b')
        defendant_count = 0
        valid_candidates = []
        print(f"len(data_rows) : {len(data_rows)}")
        for idx, row in enumerate(data_rows):
            cells = row.find_elements(By.XPATH, "./td | ./th")
            if len(cells) <= max(name_col_idx, type_col_idx):
                continue

            name = cells[name_col_idx].text.strip()
            party_type = cells[type_col_idx].text.strip()

            name_low = name.lower()
            party_low = party_type.lower()

            # Skip header-like text if present in data rows
            if (
                name_low in ("name", "party name", "name / dob / dl / id #")
                or ("name" in name_low and ("dob" in name_low or "dl" in name_low or "id #" in name_low))
                or party_low in ("type", "party type")
            ):
                continue

            # Must have type 'Defendant'
            if "defendant" not in party_low:
                continue

            clean_name = name.split('(')[0].replace("AKA", "").strip()

            # Populate name_i and description_i up to max_defendants
            defendant_count += 1
            if defendant_count <= max_defendants:
                report_cases[case_id][f"name_{defendant_count}"] = clean_name
                report_cases[case_id][f"description_{defendant_count}"] = party_type

            # Check if this defendant does not contain banned keywords
            if not any(b in name_low for b in banned):
                row_date = None
                if date_col_idx is not None and len(cells) > date_col_idx:
                    match = date_pattern.search(cells[date_col_idx].text.strip())
                    if match:
                        row_date = parse_date_safe(match.group(0))

                if row_date is None:
                    for c in cells:
                        match = date_pattern.search(c.text.strip())
                        if match:
                            parsed = parse_date_safe(match.group(0))
                            if parsed != datetime.min:
                                row_date = parsed
                                break

                valid_candidates.append({
                    "index": idx,
                    "name": clean_name,
                    "date": row_date
                })

        # Set main_defendant to newest valid candidate
        if valid_candidates:
            candidates_with_dates = [c for c in valid_candidates if c["date"] is not None and c["date"] != datetime.min]
            if candidates_with_dates:
                candidates_with_dates.sort(key=lambda c: c["date"], reverse=True)
                main_def = candidates_with_dates[0]["name"]
            else:
                main_def = valid_candidates[0]["name"]

            report_cases[case_id]["main_defendant"] = main_def
            report_cases[case_id]["defendant"] = main_def

        return report_cases
    except Exception as e:
        print(f"Error extracting defendants into report: {e}")
        return report_cases


def extract_newest_defendant(driver, parties_table_xpath, banned=None):
    dummy_report = {"temp_case": {}}
    extract_defendants_into_report(driver, parties_table_xpath, "temp_case", dummy_report, banned=banned)
    return dummy_report["temp_case"].get("main_defendant")


class TestPartiesExtraction(unittest.TestCase):
    def _create_mock_driver(self, table_data):
        driver = MagicMock()
        table = MagicMock()

        mock_rows = []
        for row_cells in table_data:
            mock_row = MagicMock()
            mock_cell_objs = []
            for cell_text in row_cells:
                cell_obj = MagicMock()
                cell_obj.text = cell_text
                mock_cell_objs.append(cell_obj)
            mock_row.find_elements.return_value = mock_cell_objs
            mock_rows.append(mock_row)

        table.find_elements.return_value = mock_rows
        return driver, table, mock_rows

    def test_extract_defendants_into_report(self):
        table_data = [
            ["Name / DOB / DL / ID #", "Type"],
            ["Bank of America, N.A.", "Defendant"],
            ["Unknown Spouse of John Doe", "Defendant"],
            ["John Doe", "Defendant"],
            ["Jane Doe (AKA Jane Smith)", "Defendant"],
        ]
        driver, table, mock_rows = self._create_mock_driver(table_data)

        report_cases = {"case_1": {}}
        with unittest.mock.patch("selenium.webdriver.support.ui.WebDriverWait.until", return_value=table):
            extract_defendants_into_report(driver, "//table", "case_1", report_cases)

            # Check that all defendants are populated into name_1, description_1, name_2, etc.
            self.assertEqual(report_cases["case_1"].get("name_1"), "Bank of America, N.A.")
            self.assertEqual(report_cases["case_1"].get("description_1"), "Defendant")
            self.assertEqual(report_cases["case_1"].get("name_2"), "Unknown Spouse of John Doe")
            self.assertEqual(report_cases["case_1"].get("name_3"), "John Doe")
            self.assertEqual(report_cases["case_1"].get("name_4"), "Jane Doe")
            # Check main_defendant filters out Bank of America and Unknown Spouse, picking John Doe
            self.assertEqual(report_cases["case_1"].get("main_defendant"), "John Doe")
            self.assertEqual(report_cases["case_1"].get("defendant"), "John Doe")

    def test_newest_by_date(self):
        table_data = [
            ["Name", "Type", "Date Added"],
            ["John Doe", "Defendant", "01/15/2023"],
            ["Jane Smith", "Defendant", "06/20/2024"],
            ["Old Defendant", "Defendant", "05/10/2021"],
        ]
        driver, table, mock_rows = self._create_mock_driver(table_data)

        report_cases = {"case_2": {}}
        with unittest.mock.patch("selenium.webdriver.support.ui.WebDriverWait.until", return_value=table):
            extract_defendants_into_report(driver, "//table", "case_2", report_cases)
            self.assertEqual(report_cases["case_2"].get("main_defendant"), "Jane Smith")


if __name__ == "__main__":
    unittest.main()
