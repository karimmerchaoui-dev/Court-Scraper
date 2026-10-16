import sys

sys.path.append(r"c:\Users\pc\PycharmProjects\Court-Scraper")
import json

import pandas as pd
from OP import extract_info_from_salesweb


def save_dicts_to_excel(data, output_path):
    rows = []

    for d in data:
        row = {}
        for k, v in d.items():
            # Convert lists/dicts to JSON strings so Excel can store them
            if isinstance(v, (list, dict)):
                row[k] = json.dumps(v, ensure_ascii=False)
            else:
                row[k] = v
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_excel(output_path, index=False)

"""scraper = CivilViewForeclosureScraper(delay=2, max_workers=1)
counties = scraper.get_all_counties()
total_listings=[]
for i in counties:

    if "NJ" in i:
        print(i)
        listings=scraper.scrape_county_listings_(i,counties[i],"15",include_details=True,status="open")
        total_listings.extend(listings)
save_dicts_to_excel(total_listings, "NJ_output_listings.xlsx")"""

print(extract_info_from_salesweb("30 LINDALE Court Clifton NJ 07013", "Passaic", "NJ"))