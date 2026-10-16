
import re

import requests
from arcgis.geocoding import geocode, reverse_geocode
from arcgis.gis import GIS
from requests.exceptions import ConnectionError

while True:
    try:
        gis = GIS()  # anonymous ArcGIS Online connection
        break
    except ConnectionError:
        pass

def autocomplete_address(address):
    results = geocode(address)

    if results:
        location = results[0]['location']
        lat=location['y']
        lon=location['x']
        result = reverse_geocode(location={"x": lon, "y": lat})
        return result["address"]["Address"],result["address"]["City"],result["address"]["RegionAbbr"],result["address"]["Postal"],result["address"]["Subregion"]


# Bidirectional state lookup — handles abbreviation → full name and vice versa
STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

# Reverse map: full name → abbreviation
STATES_REVERSE = {v.lower(): k for k, v in STATES.items()}


def normalize_state(state: str) -> tuple[str, str]:
    """
    Given either a 2-letter abbreviation or full state name (any casing),
    returns (full_name, abbreviation).
    Raises ValueError if unrecognized.
    """
    state = state.strip()

    if len(state) == 2:
        abbr = state.upper()
        if abbr not in STATES:
            raise ValueError(f"Unknown state abbreviation: '{abbr}'")
        return STATES[abbr], abbr
    else:
        key = state.lower()
        if key not in STATES_REVERSE:
            raise ValueError(f"Unknown state name: '{state}'")
        abbr = STATES_REVERSE[key]
        return STATES[abbr], abbr


def get_city_population_wikipedia(city: str, state: str) -> int | None:
    """
    Returns the population of a US city from Wikipedia.
    `state` accepts either a 2-letter abbreviation (TX) or full name (Texas),
    in any casing.
    """
    full_state, abbr = normalize_state(state)

    # Wikipedia titles to try, in order of likelihood
    candidates = [
        f"{city}, {full_state}",       # Austin, Texas
        f"{city}, {abbr}",             # Austin, TX  (less common but exists)
        f"{city}",                     # Austin (last resort, ambiguous)
    ]

    headers = {"User-Agent": "CityPopBot/1.0"}

    for title in candidates:
        page_title = title.replace(" ", "_")
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{page_title}"
        resp = requests.get(url, headers=headers)

        if resp.status_code != 200:
            continue

        data = resp.json()

        # Skip disambiguation pages — they have no useful population data
        if data.get("type") == "disambiguation":
            continue

        # Sanity check: make sure the page is actually about our state
        extract = data.get("extract", "")
        if full_state.lower() not in extract.lower() and abbr.lower() not in extract.lower():
            continue
        match = re.search(r'population[^\d]*?([\d,]+)', extract, re.IGNORECASE)
        if match:
            return int(match.group(1).replace(",", ""))

    return None
