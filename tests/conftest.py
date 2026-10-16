"""
tests/conftest.py
=================
Shared fixtures for the Court-Scraper test suite.

All fixtures here are available to every test module without import.
Heavy dependencies (Selenium, Supabase, live network) are deliberately
absent — fixtures only provide fast, in-process resources.
"""
from __future__ import annotations

import sys
import os

# ── Make the project root importable from within the tests/ directory ─────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from database.deed_queue_db import SqliteDeedQueue


# ── SQLite queue fixture ───────────────────────────────────────────────────────

@pytest.fixture()
def queue(tmp_path) -> SqliteDeedQueue:
    """
    Return a fresh SqliteDeedQueue backed by a temporary file.

    The file is automatically deleted by pytest after each test, so every
    test starts with a completely empty database — no shared state between
    tests.
    """
    db_file = str(tmp_path / "test_deed_queue.db")
    return SqliteDeedQueue(db_path=db_file)


# ── Canonical sample job tuple ─────────────────────────────────────────────────

SAMPLE_JOB: tuple = (
    "12345",       # book
    "678",         # page
    "/tmp/files",  # files_dir
    "A",           # block
    "John Doe",    # main_defendant
    "Palm Beach",  # county_name
    "sb-uuid-001", # supabase_case_id
    "case-001",    # case_id
)
