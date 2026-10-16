import os.path
import re
import time
from datetime import datetime

import pandas as pd


def sanitize_filename(filename):
    """Remove all invalid characters and replace newlines with spaces"""
    # Replace newlines and multiple spaces with single space
    filename = filename.replace("\r\n", r"\n").replace("\n", r"\n")

    filename = re.sub(r'\s+', ' ', filename)
    # Remove invalid characters
    filename = re.sub(r'[\\/*?:"<>|]', "", filename).strip()
    # Truncate to reasonable length (200 chars)
    return filename[:100]


def format_seminole_case(docket):
    if '-' in docket:
        case_parts = docket.split('-')
        formatted_docket = f"{case_parts[1]}{case_parts[2]}{case_parts[3]}"
    else:
        formatted_docket = docket
    return formatted_docket

def format_case_number_oc(case):
    case = case.strip()

    # Find the year (4 digits starting with 2)
    year_match = re.search(r'(2\d{3})', case)
    year = year_match.group(1) if year_match else None

    # Find the court type (exactly 2 letters, any case)
    court_match = re.search(r'([A-Za-z]{2})', case)
    court_type = court_match.group(1).upper() if court_match else None

    # Find all digit sequences, remove the year, pick the first remaining as docket
    digits = re.findall(r'\d+', case)
    docket = next((d for d in digits if d != year), None)

    return year, docket, court_type

def format_case_number_bw(case_str):
    # Find continuous letters and digit sequences
    parts = re.findall(r'[A-Za-z]+|\d+', case_str)

    court_type = None
    year = None
    docket = None

    for p in parts:
        if p.isalpha() and len(p) >= 2:  # court type = letters
            court_type = p
        elif p.isdigit():
            if len(p) == 2:  # year
                year = p
            elif len(p) >= 4:  # docket
                docket = p

    return year, docket,court_type

def format_case_number_pasco(case_str):
    case_str = str(case_str).strip()
    if '-' in case_str:
        parts = case_str.split('-')
        if len(parts) >= 3:
            return parts[0].strip(), parts[1].strip(), parts[2].strip()
    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', case_str)
    year = year_match.group(1) if year_match else ""
    type_match = re.search(r'([A-Za-z]{2,3})', case_str)
    court_type = type_match.group(1).upper() if type_match else "CA"
    digits = re.findall(r'\d+', case_str)
    docket = None
    for d in digits:
        if d != year and (not year.endswith(d) or len(d) > 2):
            docket = d
            break
    if not docket and digits:
        docket = digits[-1]
    return year, court_type, docket or ""

def format_case_number_md(case_str):
    # Find all parts that match year (2 digits), case number (5+ digits), and case type (2 letters)
    year_match = re.match(r'^(\d{4}|\d{2})', case_str)
    case_number_match = re.search(r'\b(\d{5,})\b', case_str)
    case_type_match = re.search(r'\b([A-Za-z]{2})\b', case_str)

    if not (year_match and case_number_match and case_type_match):
        raise ValueError(f"Could not parse all parts from: {case_str}")

    year = year_match.group(1)
    case_number = case_number_match.group(1)
    case_type = case_type_match.group(1).upper()
    return [year,case_number,case_type]


def format_case_number_nj(case_data):
    """
    Deterministically validate/format an NJ case number.

    IMPORTANT:
    This function does NOT call the LLM.

    It returns:
        (year, docket)

    if the case is already recognizable.

    Otherwise:
        (None, None)

    The caller can then send all unrecognized cases to Mistral
    in one batch.
    """

    if pd.isna(case_data):
        return None, None

    case_data = str(case_data).strip().lower()

    # Remove obvious whitespace
    case_data = case_data.replace(" ", "")

    # Remove common suffixes
    case_data = re.sub(
        r"(alias|aka|jr|sr|llc)$",
        "",
        case_data,
        flags=re.IGNORECASE
    )

    # ---------------------------------------------------------
    # Already canonical:
    # f-6654-26
    # ch-1234-26
    # ---------------------------------------------------------

    match = re.fullmatch(
        r"(f|ch)-(\d+)-(\d{2})",
        case_data
    )

    if match:
        prefix = match.group(1)
        docket = match.group(2)
        year = match.group(3)

        return year, docket

    # ---------------------------------------------------------
    # Year-Docket format:
    #
    # 26-6654
    # ---------------------------------------------------------

    match = re.fullmatch(
        r"(\d{2})-(\d+)",
        case_data
    )

    if match:
        year = match.group(1)
        docket = match.group(2)

        return year, docket

    # ---------------------------------------------------------
    # Numeric format:
    #
    # 26000136
    #
    # First 2 digits = year
    # Remaining digits = docket
    # ---------------------------------------------------------

    if re.fullmatch(r"\d+", case_data) and len(case_data) > 2:

        year = case_data[:2]
        docket = case_data[2:]

        return year, docket

    # ---------------------------------------------------------
    # Prefix + docket + year:
    #
    # F00520925
    # F794216
    #
    # Only automatically accept F / CH here.
    # Other prefixes such as L will go to the LLM.
    # ---------------------------------------------------------

    match = re.fullmatch(
        r"(f|ch)(\d+)",
        case_data
    )

    if match:
        prefix = match.group(1)
        numbers = match.group(2)

        if len(numbers) >= 3:

            year = numbers[-2:]
            docket = numbers[:-2]

            if docket:
                return year, docket

    # ---------------------------------------------------------
    # Anything else requires LLM normalization
    # ---------------------------------------------------------

    return None, None

def format_case_number_lee(case_str):
    # Find continuous letters and digit sequences
    parts = re.findall(r'[A-Za-z]+|\d+', case_str)

    court_type = None
    year = None
    docket = None

    for p in parts:
        if p.isalpha() and len(p) >= 2:  # court type = letters
            court_type = p
        elif p.isdigit():
            if len(p) == 2:  # year
                year = p
            elif len(p) >= 4:  # docket
                docket = p

    return year, docket,court_type


def safe_int(value):
    if value is None:
        return None
    try:
        return int(str(value).replace(',', '').replace('$', '').split('.')[0])
    except (ValueError, AttributeError):
        return None

def convert_to_kb(size_str):
    units = {
        "B": 1 / 1024,
        "KB": 1,
        "MB": 1024,
        "GB": 1024 * 1024,
        "TB": 1024 * 1024 * 1024,
    }

    # Split into number and unit parts
    parts = size_str.strip().upper().split()
    if len(parts) != 2:
        raise ValueError("Input must be in format '<number> <unit>' e.g. '23.0 MB'")
    number, unit = parts

    number = float(number)
    if unit not in units:
        print(parts)
        raise ValueError(f"Unknown unit '{unit}'. Valid units are: {', '.join(units.keys())}")

    # Convert to KB
    kb_value = number * units[unit]
    return kb_value
def save_to_excel(report_cases, output_folder):
    # Find highest deed index across all cases
    max_deeds = 0
    for case in report_cases.values():
        for key in case:
            if key.startswith("book_"):
                max_deeds = max(max_deeds, int(key.split("_")[1]))

    # Fill missing deed columns with empty strings
    for case in report_cases.values():
        for i in range(1, max_deeds + 1):
            case.setdefault(f"book_{i}", "")
            case.setdefault(f"page_{i}", "")

    df = pd.DataFrame.from_dict(report_cases, orient="index")
    timestamp = time.strftime("%Y%m%d_%H_%M")
    filename = f"report_{timestamp}.xlsx"
    path = os.path.join(output_folder, filename)
    df.to_excel(path, index=False)
    return path


def parse_date_safe(date_str):
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%m_%d_%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return datetime.min