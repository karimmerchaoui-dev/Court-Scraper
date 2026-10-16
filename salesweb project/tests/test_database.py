"""Tests for the Database class — uses a temp SQLite DB, no files on disk."""

import os
import sys
from pathlib import Path

import pytest

root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir))

from src.utils.database import Database


@pytest.fixture
def db(tmp_path):
    return Database(db_path=str(tmp_path / "test.db"))

SAMPLE = {
    "property_id": "12345", "address": "123 Main St, Newark, NJ",
    "county_name": "Essex County, NJ", "sales_date": "2024-03-15",
    "case_number": "F-12345-23", "found": "✅",
    "Upset Price": "$150,000.00", "Upset Amount": "",
    "Approx. Judgment": "$120,000.00", "Approx. Upset": "$145,000.00",
    "Debt Amount": "$118,000.00", "Appraised Value": "",
    "lowest_zestimate": 210000.0, "zillow_status": "FOR_SALE",
    "zillow_home_type": "SINGLE_FAMILY", "zillow_prop_type": "Single Family",
    "zillow_is_agent": None,
}

def test_insert_single(db):
    inserted, updated = db.insert_listings([SAMPLE])
    assert inserted == 1 and updated == 0 and db.count() == 1

def test_upsert_no_duplicate(db):
    db.insert_listings([SAMPLE])
    inserted, updated = db.insert_listings([{**SAMPLE, "zillow_status": "SOLD"}])
    assert inserted == 0 and updated == 1 and db.count() == 1

def test_upsert_updates_value(db):
    db.insert_listings([SAMPLE])
    db.insert_listings([{**SAMPLE, "lowest_zestimate": 999999.0}])
    assert db.to_dataframe().iloc[0]["lowest_zestimate"] == 999999.0

def test_no_property_id_always_inserts(db):
    row = {**SAMPLE, "property_id": None}
    db.insert_listings([row])
    db.insert_listings([row])
    assert db.count() == 2

def test_filter_county(db):
    db.insert_listings([SAMPLE])
    db.insert_listings([{**SAMPLE, "property_id": "99999", "county_name": "Bergen County, NJ"}])
    assert len(db.to_dataframe(county="Essex")) == 1

def test_filter_min_zestimate(db):
    db.insert_listings([SAMPLE])
    db.insert_listings([{**SAMPLE, "property_id": "99998", "lowest_zestimate": 50000.0}])
    df = db.to_dataframe(min_zestimate=100000)
    assert len(df) == 1 and df.iloc[0]["lowest_zestimate"] >= 100000

def test_export_excel(db, tmp_path):
    db.insert_listings([SAMPLE])
    path = db.export_excel(path=str(tmp_path / "out.xlsx"))
    assert os.path.exists(path) and path.endswith(".xlsx")

def test_export_csv(db, tmp_path):
    import pandas as pd
    db.insert_listings([SAMPLE])
    path = db.export_csv(path=str(tmp_path / "out.csv"))
    assert os.path.exists(path)
    df = pd.read_csv(path)
    assert df.iloc[0]["address"] == SAMPLE["address"]

def test_counties_list(db):
    db.insert_listings([SAMPLE])
    db.insert_listings([{**SAMPLE, "property_id": "99997", "county_name": "Bergen County, NJ"}])
    assert set(db.counties()) == {"Essex County, NJ", "Bergen County, NJ"}