"""
Export helpers — write scraper output to Excel or CSV.
"""

import json

import pandas as pd


def save_to_excel(data: list[dict], output_path: str) -> None:
    """Serialize a list of dicts to an Excel file."""
    rows = []
    for d in data:
        row = {
            k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
            for k, v in d.items()
        }
        rows.append(row)
    pd.DataFrame(rows).to_excel(output_path, index=False)
    print(f"✅ Saved {len(rows)} rows → {output_path}")


def save_to_csv(data: list[dict], output_path: str) -> None:
    """Serialize a list of dicts to a CSV file."""
    rows = []
    for d in data:
        row = {
            k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
            for k, v in d.items()
        }
        rows.append(row)
    pd.DataFrame(rows).to_csv(output_path, index=False)
    print(f"✅ Saved {len(rows)} rows → {output_path}")
