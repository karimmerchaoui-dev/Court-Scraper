"""
tests/test_formatting.py
========================
Unit tests for utils/formatting.py — pure string/parsing functions.

All tests are pure Python: no Selenium, no file I/O (except where
explicitly needed for save_to_excel, which uses tmp_path).
"""
from __future__ import annotations

import math
import os

import pytest

from utils.formatting import (
    convert_to_kb,
    format_case_number_bw,
    format_case_number_lee,
    format_case_number_md,
    format_case_number_nj,
    format_case_number_oc,
    format_case_number_pasco,
    format_seminole_case,
    parse_date_safe,
    safe_int,
    sanitize_filename,
    save_to_excel,
)
from datetime import datetime


# ══════════════════════════════════════════════════════════════════════════════
# 1. sanitize_filename()
# ══════════════════════════════════════════════════════════════════════════════

class TestSanitizeFilename:
    """Tests for sanitize_filename()."""

    def test_removes_backslash(self):
        assert "\\" not in sanitize_filename("file\\name")

    def test_removes_forward_slash(self):
        assert "/" not in sanitize_filename("dir/file")

    def test_removes_asterisk(self):
        assert "*" not in sanitize_filename("file*name")

    def test_removes_question_mark(self):
        assert "?" not in sanitize_filename("file?name")

    def test_removes_colon(self):
        assert ":" not in sanitize_filename("C:file")

    def test_removes_double_quote(self):
        assert '"' not in sanitize_filename('say "hello"')

    def test_removes_angle_brackets(self):
        result = sanitize_filename("<tag>")
        assert "<" not in result and ">" not in result

    def test_removes_pipe(self):
        assert "|" not in sanitize_filename("a|b")

    def test_collapses_multiple_spaces(self):
        assert sanitize_filename("a   b") == "a b"

    def test_strips_leading_and_trailing_spaces(self):
        assert sanitize_filename("  hello  ") == "hello"

    def test_truncates_to_100_characters(self):
        long_name = "a" * 200
        assert len(sanitize_filename(long_name)) <= 100

    def test_normal_filename_is_returned_unchanged(self):
        assert sanitize_filename("John Doe 2023") == "John Doe 2023"

    def test_empty_string_returns_empty(self):
        assert sanitize_filename("") == ""

    def test_only_invalid_chars_returns_empty(self):
        assert sanitize_filename("/*?:\"<>|\\") == ""


# ══════════════════════════════════════════════════════════════════════════════
# 2. format_seminole_case()
# ══════════════════════════════════════════════════════════════════════════════

class TestFormatSeminoleCase:
    """Tests for format_seminole_case()."""

    def test_strips_dashes_from_dashed_docket(self):
        assert format_seminole_case("2023-CA-001234") == "2023CA001234"

    def test_returns_docket_unchanged_when_no_dashes(self):
        assert format_seminole_case("2023CA001234") == "2023CA001234"


# ══════════════════════════════════════════════════════════════════════════════
# 3. format_case_number_oc() — Orange County
# ══════════════════════════════════════════════════════════════════════════════

class TestFormatCaseNumberOC:
    """Tests for format_case_number_oc()."""

    def test_extracts_year_case_type_and_docket(self):
        year, docket, court_type = format_case_number_oc("2023-CA-001234")
        assert year == "2023"
        assert court_type == "CA"
        assert docket == "001234"

    def test_handles_compact_format_without_separators(self):
        year, docket, court_type = format_case_number_oc("2023CA001234")
        assert year == "2023"
        assert court_type == "CA"
        assert docket is not None

    def test_returns_uppercase_court_type(self):
        _, _, court_type = format_case_number_oc("2023-ca-001234")
        assert court_type == "CA"


# ══════════════════════════════════════════════════════════════════════════════
# 4. format_case_number_bw() — Broward
# ══════════════════════════════════════════════════════════════════════════════

class TestFormatCaseNumberBW:
    """Tests for format_case_number_bw()."""

    def test_parses_standard_broward_format(self):
        year, docket, court_type = format_case_number_bw("CA-23-001234")
        assert year == "23"
        assert docket == "001234"
        assert court_type == "CA"

    def test_returns_none_for_missing_parts(self):
        year, docket, court_type = format_case_number_bw("001234")
        # Only a docket number — year and court_type should be None
        assert year is None
        assert court_type is None


# ══════════════════════════════════════════════════════════════════════════════
# 5. format_case_number_nj() — New Jersey
# ══════════════════════════════════════════════════════════════════════════════

class TestFormatCaseNumberNJ:
    """Tests for format_case_number_nj()."""

    def test_canonical_f_prefix_format(self):
        year, docket = format_case_number_nj("f-6654-26")
        assert year == "26"
        assert docket == "6654"

    def test_canonical_ch_prefix_format(self):
        year, docket = format_case_number_nj("ch-1234-26")
        assert year == "26"
        assert docket == "1234"

    def test_year_docket_numeric_format(self):
        year, docket = format_case_number_nj("26-6654")
        assert year == "26"
        assert docket == "6654"

    def test_compact_numeric_format_first_two_digits_are_year(self):
        year, docket = format_case_number_nj("26000136")
        assert year == "26"
        assert docket == "000136"

    def test_f_prefix_compact_no_dash(self):
        year, docket = format_case_number_nj("F00520925")
        assert year == "25"
        assert docket == "005209"

    def test_nan_returns_none_none(self):
        import pandas as pd
        year, docket = format_case_number_nj(pd.NA)
        assert year is None
        assert docket is None

    def test_unrecognized_format_returns_none_none(self):
        year, docket = format_case_number_nj("L-999-AB")
        assert year is None
        assert docket is None

    def test_strips_known_suffixes(self):
        """Known suffixes like 'jr', 'llc', 'sr' must be stripped."""
        year, docket = format_case_number_nj("f-6654-26jr")
        # After stripping 'jr', becomes f-6654-26 which is canonical
        assert year == "26"
        assert docket == "6654"


# ══════════════════════════════════════════════════════════════════════════════
# 6. safe_int()
# ══════════════════════════════════════════════════════════════════════════════

class TestSafeInt:
    """Tests for safe_int()."""

    def test_converts_plain_integer_string(self):
        assert safe_int("42") == 42

    def test_strips_dollar_sign(self):
        assert safe_int("$1000") == 1000

    def test_strips_commas(self):
        assert safe_int("1,234,567") == 1234567

    def test_truncates_decimal(self):
        assert safe_int("99.99") == 99

    def test_strips_dollar_and_commas_combined(self):
        assert safe_int("$123,456.78") == 123456

    def test_returns_none_for_none(self):
        assert safe_int(None) is None

    def test_returns_none_for_non_numeric_string(self):
        assert safe_int("not-a-number") is None

    def test_converts_integer_directly(self):
        assert safe_int(99) == 99


# ══════════════════════════════════════════════════════════════════════════════
# 7. convert_to_kb()
# ══════════════════════════════════════════════════════════════════════════════

class TestConvertToKb:
    """Tests for convert_to_kb()."""

    def test_bytes_to_kb(self):
        result = convert_to_kb("1024 B")
        assert math.isclose(result, 1.0, rel_tol=1e-6)

    def test_kb_stays_kb(self):
        assert convert_to_kb("1 KB") == 1.0

    def test_mb_to_kb(self):
        assert convert_to_kb("1 MB") == 1024.0

    def test_gb_to_kb(self):
        assert convert_to_kb("1 GB") == 1024 * 1024

    def test_case_insensitive_unit(self):
        assert convert_to_kb("1 mb") == 1024.0

    def test_raises_on_unknown_unit(self):
        with pytest.raises(ValueError, match="Unknown unit"):
            convert_to_kb("1 XB")

    def test_raises_on_missing_unit(self):
        with pytest.raises(ValueError):
            convert_to_kb("1024")


# ══════════════════════════════════════════════════════════════════════════════
# 8. parse_date_safe()
# ══════════════════════════════════════════════════════════════════════════════

class TestParseDateSafe:
    """Tests for parse_date_safe() in formatting.py."""

    def test_parses_slash_format(self):
        result = parse_date_safe("01/15/2023")
        assert result == datetime(2023, 1, 15)

    def test_parses_dash_format(self):
        result = parse_date_safe("01-15-2023")
        assert result == datetime(2023, 1, 15)

    def test_parses_underscore_format(self):
        result = parse_date_safe("01_15_2023")
        assert result == datetime(2023, 1, 15)

    def test_returns_datetime_min_for_invalid_date(self):
        result = parse_date_safe("not-a-date")
        assert result == datetime.min

    def test_strips_surrounding_whitespace(self):
        result = parse_date_safe("  01/15/2023  ")
        assert result == datetime(2023, 1, 15)


# ══════════════════════════════════════════════════════════════════════════════
# 9. save_to_excel() — File output
# ══════════════════════════════════════════════════════════════════════════════

class TestSaveToExcel:
    """Tests for save_to_excel() using tmp_path for file I/O isolation."""

    def _sample_report(self):
        return {
            "case-001": {
                "case_id": "case-001",
                "book_1": "12345",
                "page_1": "678",
                "book_2": "99999",
                "page_2": "111",
            },
            "case-002": {
                "case_id": "case-002",
                "book_1": "11111",
                "page_1": "222",
            },
        }

    def test_creates_xlsx_file(self, tmp_path):
        path = save_to_excel(self._sample_report(), str(tmp_path))
        assert os.path.exists(path)
        assert path.endswith(".xlsx")

    def test_file_is_created_inside_output_folder(self, tmp_path):
        path = save_to_excel(self._sample_report(), str(tmp_path))
        assert os.path.dirname(path) == str(tmp_path)

    def test_fills_missing_deed_columns_with_empty_string(self, tmp_path):
        """case-002 only has book_1/page_1; save_to_excel must pad book_2/page_2."""
        import pandas as pd
        path = save_to_excel(self._sample_report(), str(tmp_path))
        df = pd.read_excel(path)
        assert "book_2" in df.columns
        assert "page_2" in df.columns

    def test_empty_report_creates_empty_xlsx(self, tmp_path):
        path = save_to_excel({}, str(tmp_path))
        assert os.path.exists(path)
