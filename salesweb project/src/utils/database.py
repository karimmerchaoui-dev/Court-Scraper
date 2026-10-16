"""
database.py — SQLite storage layer for foreclosure-radar.

Every listing is stored once. Running the scraper again on the same county
updates existing rows rather than creating duplicates (upsert on property_id).

Usage:
    from src.utils.database import Database

    db = Database()                          # opens/creates foreclosures.db
    db.insert_listings(listings)             # save a batch from the scraper
    df = db.to_dataframe()                   # load everything as a DataFrame
    db.export_excel("output/leads.xlsx")     # export to Excel
    db.export_csv("output/leads.csv")        # export to CSV
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

import pandas as pd

# ---------------------------------------------------------------------------
# Schema
# Every column maps directly to a key produced by _process_single_listing()
# ---------------------------------------------------------------------------
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS listings (
    -- identity
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id         TEXT UNIQUE,          -- civilview PropertyId (dedup key)

    -- location
    address             TEXT,
    county_name         TEXT,

    -- auction info
    sales_date          TEXT,
    case_number         TEXT,
    found               TEXT,

    -- financial amounts
    upset_price         TEXT,
    upset_amount        TEXT,
    approx_judgment     TEXT,
    approx_upset        TEXT,
    debt_amount         TEXT,
    appraised_value     TEXT,

    -- zillow enrichment
    lowest_zestimate    REAL,
    zillow_status       TEXT,
    zillow_home_type    TEXT,
    zillow_prop_type    TEXT,
    zillow_is_agent     TEXT,

    -- housekeeping
    scraped_at          TEXT DEFAULT (datetime('now'))
);
"""

# Index speeds up county + date filters used by the dashboard
CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_county   ON listings(county_name);",
    "CREATE INDEX IF NOT EXISTS idx_date     ON listings(sales_date);",
    "CREATE INDEX IF NOT EXISTS idx_zest     ON listings(lowest_zestimate);",
]

# Map from scraper dict keys  →  DB column names
# Any key not listed here is silently ignored.
FIELD_MAP = {
    "property_id":       "property_id",
    "address":           "address",
    "county_name":       "county_name",
    "sales_date":        "sales_date",
    "case_number":       "case_number",
    "found":             "found",
    "Upset Price":       "upset_price",
    "Upset Amount":      "upset_amount",
    "Approx. Judgment":  "approx_judgment",
    "Approx. Upset":     "approx_upset",
    "Debt Amount":       "debt_amount",
    "Appraised Value":   "appraised_value",
    "lowest_zestimate":  "lowest_zestimate",
    "zillow_status":     "zillow_status",
    "zillow_home_type":  "zillow_home_type",
    "zillow_prop_type":  "zillow_prop_type",
    "zillow_is_agent":   "zillow_is_agent",
}


class Database:
    """Thin SQLite wrapper — open once, use everywhere."""

    def __init__(self, db_path: str = "foreclosures.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @contextmanager
    def _connect(self):
        """Context manager that always commits or rolls back cleanly."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row          # rows behave like dicts
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self):
        with self._connect() as conn:
            conn.execute(CREATE_TABLE)
            for idx in CREATE_INDEXES:
                conn.execute(idx)

    @staticmethod
    def _map_row(listing: dict) -> dict:
        """Convert a scraper result dict into a DB-column dict."""
        return {
            db_col: listing.get(scraper_key)
            for scraper_key, db_col in FIELD_MAP.items()
        }

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def insert_listings(self, listings: list[dict]) -> tuple[int, int]:
        """
        Upsert a batch of listings.

        If a row with the same property_id already exists it is updated,
        not duplicated. Rows without a property_id are always inserted.

        Returns:
            (inserted, updated) counts
        """
        if not listings:
            return 0, 0

        inserted = updated = 0

        with self._connect() as conn:
            for listing in listings:
                row = self._map_row(listing)

                if row.get("property_id"):
                    # Check whether this property already exists
                    exists = conn.execute(
                        "SELECT id FROM listings WHERE property_id = ?",
                        (row["property_id"],)
                    ).fetchone()

                    if exists:
                        # UPDATE — refresh all fields, bump scraped_at
                        cols = [c for c in row if c != "property_id"]
                        set_clause = ", ".join(f"{c} = ?" for c in cols)
                        values = [row[c] for c in cols] + [row["property_id"]]
                        conn.execute(
                            f"UPDATE listings SET {set_clause}, "
                            f"scraped_at = datetime('now') "
                            f"WHERE property_id = ?",
                            values
                        )
                        updated += 1
                        continue

                # INSERT (new row, or no property_id)
                cols = list(row.keys())
                placeholders = ", ".join("?" for _ in cols)
                col_clause = ", ".join(cols)
                conn.execute(
                    f"INSERT INTO listings ({col_clause}) VALUES ({placeholders})",
                    [row[c] for c in cols]
                )
                inserted += 1

        print(f"💾 DB: {inserted} inserted, {updated} updated")
        return inserted, updated

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def to_dataframe(
        self,
        county: str = None,
        status: str = None,
        min_zestimate: float = None,
        max_zestimate: float = None,
        since: str = None,
    ) -> pd.DataFrame:
        """
        Load listings into a DataFrame with optional filters.

        Args:
            county:         Filter to a specific county name (partial match).
            status:         Filter by zillow_status.
            min_zestimate:  Minimum lowest_zestimate value.
            max_zestimate:  Maximum lowest_zestimate value.
            since:          Only rows scraped on or after this date (YYYY-MM-DD).

        Returns:
            pandas DataFrame — empty DataFrame if no rows match.
        """
        query = "SELECT * FROM listings WHERE 1=1"
        params: list = []

        if county:
            query += " AND county_name LIKE ?"
            params.append(f"%{county}%")
        if status:
            query += " AND zillow_status = ?"
            params.append(status)
        if min_zestimate is not None:
            query += " AND lowest_zestimate >= ?"
            params.append(min_zestimate)
        if max_zestimate is not None:
            query += " AND lowest_zestimate <= ?"
            params.append(max_zestimate)
        if since:
            query += " AND scraped_at >= ?"
            params.append(since)

        query += " ORDER BY scraped_at DESC"

        with self._connect() as conn:
            return pd.read_sql_query(query, conn, params=params)

    def count(self) -> int:
        """Total number of listings stored."""
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]

    def counties(self) -> list[str]:
        """Distinct county names present in the DB."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT county_name FROM listings ORDER BY county_name"
            ).fetchall()
            return [r[0] for r in rows if r[0]]

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_excel(
        self,
        path: str = None,
        county: str = None,
        status: str = None,
        min_zestimate: float = None,
        max_zestimate: float = None,
    ) -> str:
        """
        Export matching listings to an Excel file.

        Args:
            path:           Output file path. Auto-generated if None.
            county/status/min_zestimate/max_zestimate: same as to_dataframe().

        Returns:
            Absolute path of the file written.
        """
        df = self.to_dataframe(county=county, status=status,
                               min_zestimate=min_zestimate,
                               max_zestimate=max_zestimate)

        path = path or _auto_path("xlsx", county)
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)

        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Listings")

            # Auto-size columns so the spreadsheet is readable immediately
            ws = writer.sheets["Listings"]
            for col_cells in ws.columns:
                max_len = max(
                    (len(str(c.value)) for c in col_cells if c.value is not None),
                    default=10,
                )
                ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 4, 60)

        print(f"✅ Excel exported → {os.path.abspath(path)}  ({len(df)} rows)")
        return os.path.abspath(path)

    def export_csv(
        self,
        path: str = None,
        county: str = None,
        status: str = None,
        min_zestimate: float = None,
        max_zestimate: float = None,
    ) -> str:
        """
        Export matching listings to a CSV file.

        Returns:
            Absolute path of the file written.
        """
        df = self.to_dataframe(county=county, status=status,
                               min_zestimate=min_zestimate,
                               max_zestimate=max_zestimate)

        path = path or _auto_path("csv", county)
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)

        df.to_csv(path, index=False)
        print(f"✅ CSV exported  → {os.path.abspath(path)}  ({len(df)} rows)")
        return os.path.abspath(path)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _auto_path(ext: str, county: str = None) -> str:
    """Generate a timestamped output path."""
    tag = county.replace(" ", "_").replace(",", "") if county else "all"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join("output", f"{tag}_{ts}.{ext}")