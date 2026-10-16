"""
tests/test_report_generation.py
===============================
Unit tests for download/report_generation_helpers.py:
  - extract_date_from_filename
  - process_additional_sums
  - apply_first_file_rules
  - apply_unified_tracking_rules & apply_file_rules
  - initialize_empty_report

Validates document-keyword detection, date extraction, and RIP/Hold flags.
"""
from __future__ import annotations

import pytest

from download.report_generation_helpers import (
    apply_file_rules,
    apply_first_file_rules,
    apply_unified_tracking_rules,
    extract_date_from_filename,
    initialize_empty_report,
    process_additional_sums,
)


# ══════════════════════════════════════════════════════════════════════════════
# 1. extract_date_from_filename()
# ══════════════════════════════════════════════════════════════════════════════

class TestExtractDateFromFilename:
    """Tests for regex-based date extraction from standardized filenames."""

    def test_extracts_valid_date_with_underscores(self):
        filename = "final_judgment_05_14_2023_recorded.pdf"
        assert extract_date_from_filename(filename) == "05_14_2023"

    def test_returns_none_when_no_matching_date_pattern(self):
        assert extract_date_from_filename("complaint_no_date.pdf") is None
        assert extract_date_from_filename("2023-05-14_format.pdf") is None


# ══════════════════════════════════════════════════════════════════════════════
# 2. process_additional_sums()
# ══════════════════════════════════════════════════════════════════════════════

class TestProcessAdditionalSums:
    """Tests for counting and recording additional sums documents."""

    def test_counts_multiple_additional_sums_files(self):
        report = {"case-1": {}}
        files = [
            "order_for_additional_sums_01_01_2023.pdf",
            "motion_for_additional_sums.pdf",
            "complaint.pdf",
        ]
        process_additional_sums(files, "case-1", report)

        assert report["case-1"]["additional_sums_count"] == 2
        assert len(report["case-1"]["additional sums files"]) == 2

    def test_sets_zero_when_no_additional_sums_present(self):
        report = {"case-1": {}}
        files = ["complaint.pdf", "lis_pendens.pdf"]
        process_additional_sums(files, "case-1", report)

        assert report["case-1"]["additional_sums_count"] == "0"


# ══════════════════════════════════════════════════════════════════════════════
# 3. apply_first_file_rules()
# ══════════════════════════════════════════════════════════════════════════════

class TestApplyFirstFileRules:
    """Tests for case hold/disqualification rules triggered by the newest document."""

    def test_order_to_vacate_triggers_reason(self):
        report = {"case-1": {}}
        matched = apply_first_file_rules("order_to_vacate_01_02_2023.pdf", "case-1", report)
        assert matched is True
        assert report["case-1"].get("Reason") == "order_to_vacate"

    def test_dismissal_triggers_reason(self):
        report = {"case-1": {}}
        matched = apply_first_file_rules("notice_of_voluntary_dismissal.pdf", "case-1", report)
        assert matched is True
        assert report["case-1"].get("Reason") == "dismissal"

    def test_returns_false_for_ordinary_file(self):
        report = {"case-1": {}}
        matched = apply_first_file_rules("complaint_filing.pdf", "case-1", report)
        assert matched is False
        assert "Reason" not in report["case-1"]

    def test_returns_false_for_empty_string(self):
        report = {"case-1": {}}
        assert apply_first_file_rules("", "case-1", report) is False


# ══════════════════════════════════════════════════════════════════════════════
# 4. apply_file_rules() & initialize_empty_report()
# ══════════════════════════════════════════════════════════════════════════════

class TestApplyFileRules:
    """Tests for file-based flag setting across document rows."""

    def test_sets_bankruptcy_and_cancel_flags(self):
        report = {"case-1": {}}
        rows = [
            {"filename": "notice_of_bankruptcy_filing.pdf"},
            {"filename": "cancel_sale_order.pdf"},
        ]
        apply_file_rules(rows, "case-1", report)

        assert report["case-1"]["bankruptcy"] == "✅"
        assert report["case-1"]["cancel"] == "✅"
        assert report["case-1"]["vacate"] == "❌"
        assert report["case-1"]["Order To Stay/Motion To Stay"] == "✅"

    def test_initialize_empty_report_sets_default_emojis(self):
        report = {"case-1": {}}
        initialize_empty_report("case-1", report)

        assert report["case-1"]["Order To Stay/Motion To Stay"] == "❌"
        assert report["case-1"]["Bankruptcy"] == "❌"
        assert report["case-1"]["Vacate"] == "❌"
        assert report["case-1"]["Cancel"] == "❌"
        assert report["case-1"]["additional_sums_count"] == "0"
