"""
Excel export utilities.
"""

import json
from pathlib import Path

import pandas as pd


def save_to_excel(data: list[dict], output_path: str | Path) -> None:
    """
    Serialize a list of dicts to an Excel file.

    Nested lists/dicts are JSON-encoded so Excel can store them as strings.

    Parameters
    ----------
    data        : list of row dicts
    output_path : destination .xlsx path
    """
    rows = []
    for record in data:
        row = {
            k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
            for k, v in record.items()
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_excel(output_path, index=False)
    print(f"Saved {len(rows)} rows → {output_path}")
