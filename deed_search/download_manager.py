import glob
import os
import shutil
import time
import traceback
from pathlib import Path


class DownloadManager:
    """Handles file download operations with retry logic and status tracking."""

    def __init__(self, driver, download_dir: Path):
        self.driver = driver
        self.download_dir = str(download_dir)

    # ------------------------------------------------------------------
    # File detection
    # ------------------------------------------------------------------

    def get_existing_files(self) -> set:
        """Get set of existing PDF and aspx files."""
        return (
            set(glob.glob(os.path.join(self.download_dir, "*.pdf")))
            | set(glob.glob(os.path.join(self.download_dir, "*.aspx")))
            | set(glob.glob(os.path.join(self.download_dir, "*.tiff")))
        )

    def get_newest_file(self, before_files: set):
        """Get the newest file that wasn't in before_files."""
        current_files = self.get_existing_files()
        before_files_set = set(before_files)
        new_files = current_files - before_files_set
        if new_files:
            return sorted(new_files, key=os.path.getctime)[0]
        return None

    # ------------------------------------------------------------------
    # Download waiting
    # ------------------------------------------------------------------

    def wait_for_download_start(self, before_files: set, timeout: int = 15):
        """Wait until a .crdownload file appears or a complete file lands."""
        print(f"⏳ Waiting for download to start (timeout: {timeout}s)...")
        new_complete_file = self.get_newest_file(before_files)
        if new_complete_file:
            print(f"✅ Download completed instantly: {os.path.basename(new_complete_file)}")
            return new_complete_file

        end_time = time.time() + timeout
        while time.time() < end_time:
            crdownload_files = set(glob.glob(os.path.join(self.download_dir, "*.crdownload")))
            if crdownload_files:
                newest = sorted(crdownload_files, key=os.path.getctime)[-1]
                print(f"✅ Download started: {os.path.basename(newest)}")
                return newest

            new_complete_file = self.get_newest_file(before_files)
            if new_complete_file:
                print(f"✅ Download completed instantly: {os.path.basename(new_complete_file)}")
                return new_complete_file

            time.sleep(0.2)
        print(f"before_files : {before_files}")
        print(f"self.get_newest_file(before_files) : {self.get_newest_file(before_files)}")
        print(f"Download did not start within {timeout} seconds")
        print(f"❌ Download did not start within {timeout} seconds")
        return None

    def wait_for_file_detection(self, before_files: set, timeout: int = 50):
        """Wait until a new complete file appears in the directory."""
        print(f"⏳ Waiting for file detection (timeout: {timeout}s)...")
        end_time = time.time() + timeout

        while time.time() < end_time:
            new_file = self.get_newest_file(before_files)
            if new_file:
                print(f"✅ File detected: {os.path.basename(new_file)}")
                return new_file
            time.sleep(0.5)

        print("❌ File was not detected within timeout")
        return None

    def wait_for_download_completion(self, file_path: str):
        """Wait until .crdownload is removed and file is complete."""
        crdownload_path = file_path + ".crdownload"
        print(f"⏳ Waiting for download completion: {os.path.basename(file_path)}")
        while os.path.exists(crdownload_path):
            time.sleep(0.5)
        print(f"✅ Download complete: {os.path.basename(file_path)}")

    # ------------------------------------------------------------------
    # Rename
    # ------------------------------------------------------------------

    def rename_file(self, new_name: str, new_file: str = None,
                    verify_retries: int = 5, verify_interval: float = 0.5) -> bool:
        """
        Safely rename a downloaded file with post-rename verification.
        Returns True on failure, False on success.
        """
        try:
            final_file = new_file or self.wait_for_file_detection(before_files=set())
            if not final_file:
                print("❌ No file to rename")
                return True

            if not os.path.exists(final_file):
                print(f"❌ Source file not found: {final_file}")
                return True

            final_file = os.path.normpath(final_file)
            original_basename = os.path.basename(final_file)

            # Sanitize and ensure .pdf extension
            # Before — always forces .pdf
            new_name = self._sanitize_filename(new_name)
            if new_name.lower().endswith(".pdf.pdf"):
                new_name = new_name[:-4]
            if not new_name.lower().endswith(".pdf"):
                new_name += ".pdf"

            # After — preserves the original file's extension
            original_ext = os.path.splitext(final_file)[1]  # e.g. ".pdf", ".tiff", ".aspx"
            new_name = self._sanitize_filename(new_name)

            # Strip any extension the caller may have accidentally included in new_name
            if "." in os.path.basename(new_name):
                new_name = os.path.splitext(new_name)[0]

            new_name = new_name + original_ext  # keep whatever extension the file actually has

            file_dir = os.path.dirname(final_file)
            new_path = os.path.join(file_dir, new_name)

            # Rename with verification retries
            for attempt in range(1, verify_retries + 1):
                if os.path.exists(new_path):
                    print(f"✅ Verified rename on attempt {attempt}: {new_name}")
                    break
                try:
                    shutil.move(final_file, new_path)
                    print(f"↪️  Rename attempt {attempt}: {original_basename} → {new_name}")
                except FileNotFoundError:
                    pass
                except Exception as e:
                    print(f"⚠️  Rename attempt {attempt} error: {e}")

                time.sleep(verify_interval)

                if os.path.exists(new_path):
                    print(f"✅ Rename verified on attempt {attempt}: {new_name}")
                    break
            else:
                print(f"❌ Could not confirm rename after {verify_retries} attempts.")
                return True

            # Cleanup leftover source files
            for leftover in glob.glob(os.path.join(file_dir, original_basename)):
                leftover = os.path.normpath(leftover)
                if leftover != new_path:
                    try:
                        os.remove(leftover)
                        print(f"🗑️  Deleted leftover: {original_basename}")
                    except Exception as e:
                        print(f"⚠️  Could not delete leftover: {e}")

            # Cleanup .crdownload remnants
            crdownload_path = final_file + ".crdownload"
            if os.path.exists(crdownload_path):
                try:
                    os.remove(crdownload_path)
                    print(f"🗑️  Deleted .crdownload: {os.path.basename(crdownload_path)}")
                except Exception as e:
                    print(f"⚠️  Could not delete .crdownload: {e}")

            print(f"✅ Renamed & verified: {new_name}")
            return False

        except Exception as e:
            print(f"❌ Rename error: {e}")
            traceback.print_exc()
            return True

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Remove characters that are invalid in file names."""
        invalid = r'\/:*?"<>|'
        for ch in invalid:
            name = name.replace(ch, "_")
        return name.strip()