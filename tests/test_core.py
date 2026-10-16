"""
tests/test_core.py
==================
Unit tests for:
  - core/CaseStatus.py  — CaseStatus constants class
  - core/SearchResult.py — SearchResult enum

These are data-contract tests: they validate that all expected values exist
with their correct string representations, and that they behave correctly
in comparisons and membership checks.
"""
from __future__ import annotations

import pytest

from core.CaseStatus import CaseStatus
from core.SearchResult import SearchResult


# ══════════════════════════════════════════════════════════════════════════════
# 1. CaseStatus — Constants Class
# ══════════════════════════════════════════════════════════════════════════════

class TestCaseStatus:
    """Tests for the CaseStatus constants class."""

    # ── Existence of all expected statuses ────────────────────────────────────

    def test_new_status_exists(self):
        assert hasattr(CaseStatus, "NEW")

    def test_uploading_status_exists(self):
        assert hasattr(CaseStatus, "UPLOADING")

    def test_processing_status_exists(self):
        assert hasattr(CaseStatus, "PROCESSING")

    def test_completed_status_exists(self):
        assert hasattr(CaseStatus, "COMPLETED")

    def test_failed_status_exists(self):
        assert hasattr(CaseStatus, "FAILED")

    def test_updated_status_exists(self):
        assert hasattr(CaseStatus, "UPDATED")

    def test_ineligible_status_exists(self):
        assert hasattr(CaseStatus, "INELIGIBLE")

    # ── String value correctness ───────────────────────────────────────────────

    def test_new_value_is_string_new(self):
        assert CaseStatus.NEW == "new"

    def test_uploading_value_is_string_uploading(self):
        assert CaseStatus.UPLOADING == "uploading"

    def test_processing_value_is_string_processing(self):
        assert CaseStatus.PROCESSING == "processing"

    def test_completed_value_is_string_completed(self):
        assert CaseStatus.COMPLETED == "completed"

    def test_failed_value_is_string_failed(self):
        assert CaseStatus.FAILED == "failed"

    def test_updated_value_is_string_updated(self):
        assert CaseStatus.UPDATED == "updated"

    def test_ineligible_value_is_string_ineligible(self):
        assert CaseStatus.INELIGIBLE == "ineligible"

    # ── Status values are plain strings (not enums) ───────────────────────────

    def test_all_status_values_are_strings(self):
        """CaseStatus uses plain class attributes, not enum members."""
        statuses = [
            CaseStatus.NEW, CaseStatus.UPLOADING, CaseStatus.PROCESSING,
            CaseStatus.COMPLETED, CaseStatus.FAILED, CaseStatus.UPDATED,
            CaseStatus.INELIGIBLE,
        ]
        for status in statuses:
            assert isinstance(status, str), f"Expected str, got {type(status)} for {status!r}"

    # ── All values are unique ──────────────────────────────────────────────────

    def test_all_status_values_are_unique(self):
        statuses = [
            CaseStatus.NEW, CaseStatus.UPLOADING, CaseStatus.PROCESSING,
            CaseStatus.COMPLETED, CaseStatus.FAILED, CaseStatus.UPDATED,
            CaseStatus.INELIGIBLE,
        ]
        assert len(statuses) == len(set(statuses)), "Duplicate status values detected"

    # ── Usability in comparisons (typical usage pattern in the codebase) ──────

    def test_status_can_be_compared_with_string_literal(self):
        assert CaseStatus.COMPLETED == "completed"
        assert CaseStatus.FAILED != "completed"

    def test_status_works_as_dict_key(self):
        transitions = {CaseStatus.NEW: CaseStatus.PROCESSING}
        assert transitions["new"] == "processing"

    def test_status_works_in_membership_check(self):
        terminal_statuses = {CaseStatus.COMPLETED, CaseStatus.FAILED, CaseStatus.INELIGIBLE}
        assert "completed" in terminal_statuses
        assert "new" not in terminal_statuses


# ══════════════════════════════════════════════════════════════════════════════
# 2. SearchResult — Enum
# ══════════════════════════════════════════════════════════════════════════════

class TestSearchResult:
    """Tests for the SearchResult enum."""

    # ── Member existence ──────────────────────────────────────────────────────

    def test_success_member_exists(self):
        assert hasattr(SearchResult, "SUCCESS")

    def test_retry_needed_member_exists(self):
        assert hasattr(SearchResult, "RETRY_NEEDED")

    def test_not_found_member_exists(self):
        assert hasattr(SearchResult, "NOT_FOUND")

    def test_error_member_exists(self):
        assert hasattr(SearchResult, "ERROR")

    # ── Enum integrity ────────────────────────────────────────────────────────

    def test_all_members_are_searchresult_instances(self):
        for member in SearchResult:
            assert isinstance(member, SearchResult)

    def test_enum_has_exactly_four_members(self):
        assert len(SearchResult) == 4

    def test_all_member_values_are_unique(self):
        values = [m.value for m in SearchResult]
        assert len(values) == len(set(values)), "Duplicate enum values detected"

    # ── Identity comparisons (how the code uses it) ───────────────────────────

    def test_success_is_identity_comparable(self):
        assert SearchResult.SUCCESS is SearchResult.SUCCESS

    def test_different_members_are_not_equal(self):
        assert SearchResult.SUCCESS != SearchResult.ERROR
        assert SearchResult.RETRY_NEEDED != SearchResult.NOT_FOUND

    def test_usable_in_if_statement(self):
        result = SearchResult.SUCCESS
        if result == SearchResult.SUCCESS:
            passed = True
        else:
            passed = False
        assert passed

    def test_usable_in_match_style_dict(self):
        """Typical usage pattern in county scrapers."""
        handlers = {
            SearchResult.SUCCESS: "process",
            SearchResult.RETRY_NEEDED: "retry",
            SearchResult.NOT_FOUND: "skip",
            SearchResult.ERROR: "abort",
        }
        assert handlers[SearchResult.ERROR] == "abort"

    def test_members_not_equal_to_raw_string(self):
        """SearchResult is a proper enum — members are not plain strings."""
        assert SearchResult.SUCCESS != "SUCCESS"
        assert SearchResult.SUCCESS != "success"
