"""
tests/test_download_helpers.py
==============================
Unit tests for download file handling and data tracking helpers:
  - download/files_management.py: generate_safe_filename, cleanup_unwanted_files, get_existing_files
  - download/download_rename.py: _ensure_pdf_extension, _get_final_file_path, _detect_new_file, _rename_downloaded_file
  - download/download_helpers.py: get_timeout

Uses pytest's tmp_path fixture for isolated filesystem operations.
"""
from __future__ import annotations

import os
from pathlib import Path
import pytest

from download.files_management import (
    cleanup_unwanted_files,
    generate_safe_filename,
    get_existing_files,
)
from download.download_rename import (
    _detect_new_file,
    _ensure_pdf_extension,
    _get_final_file_path,
    _rename_downloaded_file,
)
from download.download_helpers import get_timeout


# ══════════════════════════════════════════════════════════════════════════════
# 1. generate_safe_filename()
# ══════════════════════════════════════════════════════════════════════════════

class TestGenerateSafeFilename:
    """Tests for download.files_management.generate_safe_filename."""

    def test_replaces_non_alphanumeric_with_underscore(self):
        result = generate_safe_filename("Complaint & Summons - 2023.pdf")
        assert "&" not in result
        assert "-" not in result
        assert "." not in result
        assert "Complaint_Summons_2023_pdf" == result

    def test_collapses_multiple_consecutive_underscores(self):
        result = generate_safe_filename("File   Name --- Test")
        assert "__" not in result
        assert result == "File_Name_Test"

    def test_strips_leading_and_trailing_underscores(self):
        result = generate_safe_filename("---Important Doc---")
        assert not result.startswith("_")
        assert not result.endswith("_")
        assert result == "Important_Doc"

    def test_truncates_to_max_length(self):
        long_name = "A" * 250
        result = generate_safe_filename(long_name, max_length=50)
        assert len(result) == 50

    def test_handles_empty_string(self):
        assert generate_safe_filename("") == ""


# ══════════════════════════════════════════════════════════════════════════════
# 2. cleanup_unwanted_files() & get_existing_files()
# ══════════════════════════════════════════════════════════════════════════════

class TestFilesManagementIO:
    """Tests for cleanup_unwanted_files and get_existing_files with isolated tmp_path."""

    def test_cleanup_unwanted_files_deletes_crdownload_and_aspx(self, tmp_path: Path):
        # Create a mix of valid and unwanted files
        valid_pdf = tmp_path / "valid.pdf"
        valid_pdf.write_text("dummy pdf content")

        in_progress_dl = tmp_path / "download.crdownload"
        in_progress_dl.write_text("partial download")

        aspx_error = tmp_path / "error_page.aspx"
        aspx_error.write_text("<html>server error</html>")

        # Run cleanup
        cleanup_unwanted_files(str(tmp_path))

        # Check results
        assert valid_pdf.exists(), "Valid PDF was incorrectly removed!"
        assert not in_progress_dl.exists(), "*.crdownload file was not cleaned up!"
        assert not aspx_error.exists(), "*.aspx file was not cleaned up!"

    def test_cleanup_handles_non_existent_or_empty_folder(self, tmp_path: Path):
        empty_folder = tmp_path / "empty_dir"
        empty_folder.mkdir()
        # Should not raise exception
        cleanup_unwanted_files(str(empty_folder))

    def test_get_existing_files_returns_filenames_set(self, tmp_path: Path):
        (tmp_path / "doc1.pdf").write_text("content")
        (tmp_path / "doc2.pdf").write_text("content")
        sub_dir = tmp_path / "sub"
        sub_dir.mkdir()  # directory should be ignored

        existing = get_existing_files(str(tmp_path))
        assert existing == {"doc1.pdf", "doc2.pdf"}


# ══════════════════════════════════════════════════════════════════════════════
# 3. download_rename.py helper functions
# ══════════════════════════════════════════════════════════════════════════════

class TestDownloadRenameHelpers:
    """Tests for rename, path resolution, and detection in download_rename.py."""

    def test_ensure_pdf_extension_adds_extension_if_missing(self):
        assert _ensure_pdf_extension("my_document") == "my_document.pdf"
        assert _ensure_pdf_extension("my_document.pdf") == "my_document.pdf"

    def test_get_final_file_path_strips_crdownload_suffix(self):
        assert _get_final_file_path("c:/downloads/report.pdf.crdownload") == "c:/downloads/report.pdf"
        assert _get_final_file_path("c:/downloads/report.pdf") == "c:/downloads/report.pdf"

    def test_detect_new_file_identifies_newly_arrived_file(self, tmp_path: Path):
        before_files = set()
        file_a = tmp_path / "doc_a.pdf"
        file_a.write_text("a")

        # Detect new file
        new_file = _detect_new_file(str(tmp_path), before_files)
        assert new_file == str(file_a)

    def test_detect_new_file_returns_none_if_no_difference(self, tmp_path: Path):
        file_a = str(tmp_path / "doc_a.pdf")
        Path(file_a).write_text("a")

        before_files = {file_a}
        assert _detect_new_file(str(tmp_path), before_files) is None

    def test_rename_downloaded_file_moves_and_ensures_pdf(self, tmp_path: Path):
        source = tmp_path / "temp_download_123.tmp"
        source.write_text("pdf bytes")

        target_dir = str(tmp_path / "dest")
        os.makedirs(target_dir, exist_ok=True)

        result_path = _rename_downloaded_file(
            source_path=str(source),
            download_dir=target_dir,
            new_filename="Final_Judgment",
        )

        assert result_path is not None
        assert os.path.exists(result_path)
        assert result_path.endswith("Final_Judgment.pdf")
        assert not source.exists()


# ══════════════════════════════════════════════════════════════════════════════
# 4. get_timeout()
# ══════════════════════════════════════════════════════════════════════════════

class TestDownloadTimeout:
    """Tests for download.download_helpers.get_timeout."""

    def test_get_timeout_calculates_based_on_total_size(self):
        # 400 KB / sec
        # status with 4000 KB = ~10 seconds (minimum is 20 if < 10)
        status = "100 KB of 8000 KB, 20 seconds left"
        timeout = get_timeout(status, init_timeout=60)
        # 8000 KB / 400 KB/s = 20
        assert timeout == 20

    def test_get_timeout_enforces_minimum_20_seconds(self):
        status = "100 KB of 1000 KB, 5 seconds left"
        # 1000 KB / 400 = 2.5s -> min capped at 20s
        timeout = get_timeout(status, init_timeout=60)
        assert timeout == 20

    def test_get_timeout_returns_none_or_init_if_not_in_status(self):
        assert get_timeout("Downloading...", init_timeout=60) is None
        assert get_timeout("", init_timeout=60) is None
