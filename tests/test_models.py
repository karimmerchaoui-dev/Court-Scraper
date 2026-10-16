"""
tests/test_models.py
====================
Unit tests for models.py — Case dataclass, _clean_str(), and all
county-specific computed properties (.id, .search_term, .get_file_dir).

No Selenium, no network, no file I/O.
"""
from __future__ import annotations

import os

import pytest

from models import Case, _clean_str


# ══════════════════════════════════════════════════════════════════════════════
# 1. _clean_str() — String Normaliser
# ══════════════════════════════════════════════════════════════════════════════

class TestCleanStr:
    """Tests for the private _clean_str() utility."""

    def test_returns_none_for_none(self):
        assert _clean_str(None) is None

    def test_strips_leading_and_trailing_whitespace(self):
        assert _clean_str("  hello  ") == "hello"

    def test_collapses_internal_whitespace(self):
        assert _clean_str("John   Doe") == "John Doe"

    def test_replaces_newlines_with_space(self):
        assert _clean_str("line1\nline2") == "line1 line2"

    def test_handles_carriage_return_newline(self):
        assert _clean_str("line1\r\nline2") == "line1 line2"

    def test_empty_string_stays_empty(self):
        assert _clean_str("") == ""

    def test_string_with_only_whitespace_becomes_empty(self):
        assert _clean_str("   \n\t  ") == ""


# ══════════════════════════════════════════════════════════════════════════════
# 2. Case — Instantiation & __post_init__ Cleaning
# ══════════════════════════════════════════════════════════════════════════════

class TestCaseInstantiation:
    """Tests that Case.__post_init__ cleans all string fields on construction."""

    def test_creates_with_clean_values(self):
        c = Case(year="2023", case_number="001234", county="broward")
        assert c.year == "2023"
        assert c.case_number == "001234"
        assert c.county == "broward"

    def test_cleans_whitespace_in_all_fields(self):
        c = Case(year="  2023  ", case_number="  001234  ", county="  broward  ")
        assert c.year == "2023"
        assert c.case_number == "001234"
        assert c.county == "broward"

    def test_default_case_type_is_ca(self):
        c = Case(year="2023", case_number="001234", county="orange")
        assert c.case_type == "CA"

    def test_custom_case_type_is_preserved(self):
        c = Case(year="2023", case_number="001234", county="orange", case_type="CH")
        assert c.case_type == "CH"

    def test_county_name_defaults_to_none(self):
        c = Case(year="2023", case_number="001234", county="orange")
        assert c.county_name is None

    def test_processor_name_aliases_county(self):
        c = Case(year="2023", case_number="001234", county="broward")
        assert c.processor_name == c.county


# ══════════════════════════════════════════════════════════════════════════════
# 3. Case.id — County-Specific ID Formatting
# ══════════════════════════════════════════════════════════════════════════════

class TestCaseId:
    """Tests for the Case.id computed property across all supported counties."""

    # ── Broward ───────────────────────────────────────────────────────────────

    def test_broward_id_format(self):
        """Broward: {case_type}-{year}-{case_number}"""
        c = Case(year="2023", case_number="001234", county="broward", case_type="CA")
        assert c.id == "CA-2023-001234"

    def test_broward_id_is_case_insensitive_on_county(self):
        """County matching is lowercased, so 'Broward' and 'BROWARD' both work."""
        assert Case(year="2023", case_number="001234", county="Broward").id == "CA-2023-001234"
        assert Case(year="2023", case_number="001234", county="BROWARD").id == "CA-2023-001234"

    # ── Orange ────────────────────────────────────────────────────────────────

    def test_orange_id_format(self):
        """Orange: {year}-{case_type}-{case_number}-O"""
        c = Case(year="2023", case_number="001234", county="orange", case_type="CA")
        assert c.id == "2023-CA-001234-O"

    def test_orange_id_without_case_type(self):
        """Orange with no case_type: {year}--{case_number}-O (empty type segment)"""
        c = Case(year="2023", case_number="001234", county="orange", case_type=None)
        assert c.id == "2023--001234-O"

    # ── Lee / Miami / Pasco ───────────────────────────────────────────────────

    def test_lee_id_format(self):
        """Lee: {year}-{case_type}-{case_number}"""
        c = Case(year="2023", case_number="001234", county="lee", case_type="CA")
        assert c.id == "2023-CA-001234"

    def test_miami_id_format(self):
        c = Case(year="2023", case_number="001234", county="miami", case_type="CA")
        assert c.id == "2023-CA-001234"

    def test_pasco_id_format(self):
        c = Case(year="2023", case_number="001234", county="pasco", case_type="CA")
        assert c.id == "2023-CA-001234"

    # ── New Jersey ────────────────────────────────────────────────────────────

    def test_nj_id_with_canonical_f_prefix(self):
        """NJ case numbers already prefixed with 'f-' are returned unchanged."""
        c = Case(year="2023", case_number="f-12345-23", county="jersey")
        assert c.id == "f-12345-23"

    def test_nj_id_with_canonical_ch_prefix(self):
        c = Case(year="2023", case_number="ch-99999-23", county="new jersey")
        assert c.id == "ch-99999-23"

    def test_nj_id_without_prefix_uses_f_prefix_format(self):
        """Bare NJ case numbers get f-{number}-{year} format."""
        c = Case(year="23", case_number="12345", county="nj")
        assert c.id == "f-12345-23"

    # ── Default fallback ──────────────────────────────────────────────────────

    def test_default_id_returns_stripped_case_number(self):
        """Unknown counties fall back to bare case_number (stripped)."""
        c = Case(year="2023", case_number="  999888  ", county="sarasota")
        assert c.id == "999888"


# ══════════════════════════════════════════════════════════════════════════════
# 4. Case.search_term — Website Search Bar Values
# ══════════════════════════════════════════════════════════════════════════════

class TestSearchTerm:
    """Tests for the Case.search_term property."""

    def test_seminole_search_term_is_compact_no_dashes(self):
        """Seminole wants: {year}{case_type}{case_number}"""
        c = Case(year="2023", case_number="001234", county="seminole", case_type="CA")
        assert c.search_term == "2023CA001234"

    def test_polk_search_term_format(self):
        """Polk wants: {year}-{case_number}"""
        c = Case(year="2023", case_number="001234", county="polk")
        assert c.search_term == "2023-001234"

    def test_nj_search_term_extracts_bare_docket(self):
        """NJ docket input takes only the number part of f-{docket}-{year}."""
        c = Case(year="23", case_number="f-12345-23", county="jersey")
        assert c.search_term == "12345"

    def test_default_search_term_delegates_to_id(self):
        """Non-special counties return the same value as .id."""
        c = Case(year="2023", case_number="001234", county="orange", case_type="CA")
        assert c.search_term == c.id


# ══════════════════════════════════════════════════════════════════════════════
# 5. Case.get_file_dir — Directory Path Generation
# ══════════════════════════════════════════════════════════════════════════════

class TestGetFileDir:
    """Tests for Case.get_file_dir()."""

    BASE = "/output"

    def test_nj_directory_format(self):
        """NJ: f-{case_number}-{year}"""
        c = Case(year="23", case_number="12345", county="jersey")
        result = c.get_file_dir(self.BASE)
        assert result == os.path.join(self.BASE, "f-12345-23")

    def test_orange_directory_format(self):
        """Orange: f-{case_number}-{year}"""
        c = Case(year="2023", case_number="001234", county="orange")
        result = c.get_file_dir(self.BASE)
        assert result == os.path.join(self.BASE, "f-001234-2023")

    def test_lee_directory_format(self):
        """Lee: f-{case_number}-{year}"""
        c = Case(year="2023", case_number="001234", county="lee")
        result = c.get_file_dir(self.BASE)
        assert result == os.path.join(self.BASE, "f-001234-2023")

    def test_broward_directory_format(self):
        """Broward: {case_type}-{year}-{case_number}-{county}"""
        c = Case(year="2023", case_number="001234", county="broward", case_type="CA")
        result = c.get_file_dir(self.BASE)
        assert result == os.path.join(self.BASE, "CA-2023-001234-broward")

    def test_default_directory_format(self):
        """Default: {case_number}-{county}"""
        c = Case(year="2023", case_number="001234", county="sarasota")
        result = c.get_file_dir(self.BASE)
        assert result == os.path.join(self.BASE, "001234-sarasota")

    def test_returns_absolute_path_under_base_folder(self):
        """The returned path must be a child of the given output folder."""
        c = Case(year="2023", case_number="001234", county="sarasota")
        result = c.get_file_dir(self.BASE)
        assert result.startswith(self.BASE)
