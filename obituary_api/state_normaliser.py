"""
State normalisation helpers.
Accepts abbreviations, short-hand names, and full state names and returns
the URL-encoded form expected by legacy.com's search endpoint.
"""

# Exhaustive US state map: both the abbreviation and common variants → legacy.com value
_STATE_MAP: dict[str, str] = {
    # Alabama
    "al": "Alabama", "alabama": "Alabama",
    # Alaska
    "ak": "Alaska", "alaska": "Alaska",
    # Arizona
    "az": "Arizona", "arizona": "Arizona",
    # Arkansas
    "ar": "Arkansas", "arkansas": "Arkansas",
    # California
    "ca": "California", "california": "California",
    # Colorado
    "co": "Colorado", "colorado": "Colorado",
    # Connecticut
    "ct": "Connecticut", "connecticut": "Connecticut",
    # Delaware
    "de": "Delaware", "delaware": "Delaware",
    # Florida
    "fl": "Florida", "florida": "Florida",
    # Georgia
    "ga": "Georgia", "georgia": "Georgia",
    # Hawaii
    "hi": "Hawaii", "hawaii": "Hawaii",
    # Idaho
    "id": "Idaho", "idaho": "Idaho",
    # Illinois
    "il": "Illinois", "illinois": "Illinois",
    # Indiana
    "in": "Indiana", "indiana": "Indiana",
    # Iowa
    "ia": "Iowa", "iowa": "Iowa",
    # Kansas
    "ks": "Kansas", "kansas": "Kansas",
    # Kentucky
    "ky": "Kentucky", "kentucky": "Kentucky",
    # Louisiana
    "la": "Louisiana", "louisiana": "Louisiana",
    # Maine
    "me": "Maine", "maine": "Maine",
    # Maryland
    "md": "Maryland", "maryland": "Maryland",
    # Massachusetts
    "ma": "Massachusetts", "massachusetts": "Massachusetts",
    # Michigan
    "mi": "Michigan", "michigan": "Michigan",
    # Minnesota
    "mn": "Minnesota", "minnesota": "Minnesota",
    # Mississippi
    "ms": "Mississippi", "mississippi": "Mississippi",
    # Missouri
    "mo": "Missouri", "missouri": "Missouri",
    # Montana
    "mt": "Montana", "montana": "Montana",
    # Nebraska
    "ne": "Nebraska", "nebraska": "Nebraska",
    # Nevada
    "nv": "Nevada", "nevada": "Nevada",
    # New Hampshire
    "nh": "New Hampshire", "new hampshire": "New Hampshire",
    # New Jersey
    "nj": "New Jersey", "new jersey": "New Jersey", "jersey": "New Jersey",
    # New Mexico
    "nm": "New Mexico", "new mexico": "New Mexico",
    # New York
    "ny": "New York", "new york": "New York",
    # North Carolina
    "nc": "North Carolina", "north carolina": "North Carolina",
    # North Dakota
    "nd": "North Dakota", "north dakota": "North Dakota",
    # Ohio
    "oh": "Ohio", "ohio": "Ohio",
    # Oklahoma
    "ok": "Oklahoma", "oklahoma": "Oklahoma",
    # Oregon
    "or": "Oregon", "oregon": "Oregon",
    # Pennsylvania
    "pa": "Pennsylvania", "pennsylvania": "Pennsylvania",
    # Rhode Island
    "ri": "Rhode Island", "rhode island": "Rhode Island",
    # South Carolina
    "sc": "South Carolina", "south carolina": "South Carolina",
    # South Dakota
    "sd": "South Dakota", "south dakota": "South Dakota",
    # Tennessee
    "tn": "Tennessee", "tennessee": "Tennessee",
    # Texas
    "tx": "Texas", "texas": "Texas",
    # Utah
    "ut": "Utah", "utah": "Utah",
    # Vermont
    "vt": "Vermont", "vermont": "Vermont",
    # Virginia
    "va": "Virginia", "virginia": "Virginia",
    # Washington
    "wa": "Washington", "washington": "Washington",
    # West Virginia
    "wv": "West Virginia", "west virginia": "West Virginia",
    # Wisconsin
    "wi": "Wisconsin", "wisconsin": "Wisconsin",
    # Wyoming
    "wy": "Wyoming", "wyoming": "Wyoming",
    # Washington D.C.
    "dc": "District of Columbia", "district of columbia": "District of Columbia",
}


def normalise_state(raw: str) -> str:
    """
    Convert any state input (abbreviation, alias, full name) into the
    canonical display name used by legacy.com.

    Raises:
        ValueError: if the input cannot be mapped to a known US state.
    """
    key = raw.strip().lower()
    if key not in _STATE_MAP:
        raise ValueError(
            f"Unknown state: '{raw}'. "
            "Pass a standard US state name or two-letter abbreviation."
        )
    return _STATE_MAP[key]
