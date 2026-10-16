import glob
import os
import re
import shutil
import threading
import time

from selenium.common.exceptions import NoSuchWindowException

from browser.browser_helpers import *
from browser.driver_snoop_web import auto_driver_snoop
from download.download_monitor import get_current_downloads_state, open_downloads_tab
from download.files_management import cleanup_unwanted_files
from utils.formatting import convert_to_kb, sanitize_filename


def wait_until_unlocked(filepath, timeout=30):
    start = time.time()

    while time.time() - start < timeout:
        try:
            with open(filepath, "rb"):
                return True
        except PermissionError:
            time.sleep(0.5)

    return False


def get_thread_number():
    """Get clean thread number from thread name"""
    thread_name = threading.current_thread().name
    match = re.search(r'ThreadPoolExecutor-\d+_(\d+)', thread_name)
    return int(match.group(1)) + 1 if match else 0


class DownloadManager:
    """Handles file download operations with retry logic and status tracking."""

    def __init__(self, driver, driver_pool, download_dir, case_id, county="",status_callback=None):
        self.driver = driver
        self.driver_pool = driver_pool
        self.download_dir = download_dir
        self.case_id = case_id
        self.county = county
        self.max_retry_seconds = 30
        self.default_timeout = 100
        self.status_callback = status_callback

    def get_existing_files(self):
        """Get set of existing PDF and crdownload files."""
        return set(glob.glob(os.path.join(self.download_dir, "*.pdf"))) | set(glob.glob(os.path.join(self.download_dir, "*.aspx")))

    def get_newest_file(self, before_files):
        """Get the newest file that wasn't in before_files."""
        current_files = self.get_existing_files()

        # Convert before_files to set if it isn't already
        before_files_set = set(before_files) if not isinstance(before_files, set) else before_files

        new_files = current_files - before_files_set
        if new_files:
            return sorted(new_files, key=os.path.getctime)[0]
        return None

    def update_status(self, status, details="", progress_down=None):
        """Update case download status."""
        thread_num = get_thread_number()
        status_text = f"{status} (Thread {thread_num})"
        self.status_callback(self.driver, self.case_id, self.county, status_text,details=details, progress_down=progress_down)

    @auto_driver_snoop(depth=1)
    def wait_for_download_start(self, before_files, timeout=10):
        print(f"⏳ Waiting for download to start (timeout: {timeout}s)...")

        # Check immediately — fast downloads may already be done before we even enter
        new_complete_file = self.get_newest_file(before_files)
        if new_complete_file:
            print(f"✅ Download completed instantly: {os.path.basename(new_complete_file)}")
            return new_complete_file

        end_time = time.time() + timeout

        while time.time() < end_time:
            crdownload_files = set(glob.glob(os.path.join(self.download_dir, "*.crdownload")))

            if crdownload_files:
                newest_crdownload = sorted(crdownload_files, key=os.path.getctime)[-1]
                print(f"✅ Download started: {os.path.basename(newest_crdownload)}")
                return newest_crdownload

            # Re-check on every iteration too
            new_complete_file = self.get_newest_file(before_files)
            if new_complete_file:
                print(f"✅ Download completed instantly: {os.path.basename(new_complete_file)}")
                return new_complete_file

            time.sleep(0.2)
    
        print(f"before_files : {before_files}")
        print(f"self.get_newest_file(before_files) : {self.get_newest_file(before_files)}")
        print(f"Download did not start within {timeout} seconds")
        return None

    @auto_driver_snoop(depth=1)
    def wait_for_file_detection(self, before_files,driver=None, timeout=50):
        """
        Wait until a new file appears in the directory.
        Dynamically adjusts timeout based on detected file size.
        """
        print(f"timeout : {timeout}")
        end_time = time.time() + timeout
        detected_size = None

        while time.time() < end_time:
            # Check for new file
            open_downloads_tab(self.driver)
            new_file = self.get_newest_file(before_files)
            if new_file:
                return new_file

            # Get download status to adjust timeout dynamically
            try:
                file, status, progress, url = get_current_downloads_state(self.driver)

                # Handle stalled download
                if not status and not self.get_newest_file(before_files):
                    print("⚠️ Download stalled during detection, reopening tab...")
                    print(f"newest file after download stalled : {self.get_newest_file(before_files)}")
                    return self.get_newest_file(before_files)

                # Adjust timeout based on file size
                if status and "of" in status:
                    timeout, new_size = self.adjust_timeout_by_size(status, timeout)
                    if new_size and new_size != detected_size:
                        detected_size = new_size
                        end_time = time.time() + timeout

            except (NoSuchWindowException, Exception) as e:
                # Continue waiting even if we can't get status
                pass

            time.sleep(0.5)

        return None

    def wait_for_download_completion(self, file_path):
        """Wait until .crdownload is removed and file is complete."""
        crdownload_path = file_path + ".crdownload"

        while os.path.exists(crdownload_path):
            try:
                file, status, progress, url = get_current_downloads_state(self.driver)
                self.update_status("Downloading", progress_down=status)

                if not status and url:
                    # Download stalled, retry
                    request_url(self.driver, url)
                    open_downloads_tab(self.driver)
                    time.sleep(2)

            except Exception:
                traceback.print_exc()

            time.sleep(0.5)

    def adjust_timeout_by_size(self, status, current_timeout):
        """Dynamically adjust timeout based on file size."""
        if status and "of" in status:
            total_size_str = status.split("of")[1].split(',')[0].strip()
            try:
                size_kb = convert_to_kb(total_size_str)
                new_timeout = max(int(size_kb / 200), 5)
                return new_timeout, size_kb
            except ValueError:
                pass
        return current_timeout, None

    def retry_download_from_url(self, url, files_dir):
        """Retry download by requesting URL again."""
        print("⚠️ No status reported, retrying download from URL...")
        set_download_dir(self.driver,files_dir)
        # Wait for other threads to finish retrying
        while self.driver_pool.is_any_downloading_oc_retrying():
            time.sleep(1)

        cleanup_unwanted_files(self.download_dir)
        set_download_dir(self.driver, files_dir)
        request_url(self.driver, url)
        open_downloads_tab(self.driver)
        time.sleep(2)

        return self.get_existing_files()
    @auto_driver_snoop(depth=1)

    def rename_file(self, new_name, case_id, report_cases, new_file=None, verify_retries=5, verify_interval=0.5):
        """Safely rename a downloaded file, with post-rename verification and cleanup of any leftover source files."""
        try:
            # Find the file to rename
            if new_file:
                final_file = new_file
            else:
                final_file = self.wait_for_file_detection(before_files=[])

            if not final_file:
                print("❌ No file to rename")
                return False, None

            if not os.path.exists(final_file):
                print(f"❌ Source file not found: {final_file}")
                return False,None

            final_file = os.path.normpath(final_file)
            original_basename = os.path.basename(final_file)
            new_name = sanitize_filename(new_name)

            if new_name.lower().endswith(".pdf.pdf"):
                new_name = new_name[:-4]
            if not new_name.lower().endswith(".pdf"):
                new_name += ".pdf"

            file_dir = os.path.dirname(final_file)
            new_path = os.path.join(file_dir, new_name)

            # --- Perform the rename with post-verification loop ---
            for attempt in range(1, verify_retries + 1):
                # If the target already exists from a prior attempt, we're done
                if os.path.exists(new_path):
                    print(f"✅ Verified rename on attempt {attempt}: {new_name} exists")
                    break

                try:
                    if not wait_until_unlocked(final_file):
                        print(f"❌ File remained locked: {final_file}")
                        return True,new_path

                    shutil.move(final_file, new_path)
                    print(f"↪️  Rename attempt {attempt}: {original_basename} → {new_name}")
                except FileNotFoundError:
                    # Source may have disappeared — check if target appeared anyway
                    pass
                except Exception as e:
                    print(f"⚠️  Rename attempt {attempt} error: {e}")

                # Give the filesystem a moment, then verify
                time.sleep(verify_interval)

                if os.path.exists(new_path):
                    print(f"✅ Rename verified on attempt {attempt}: {new_name}")
                    break
            else:
                # Exhausted all retries without confirming the file exists
                print(f"❌ Could not confirm rename after {verify_retries} attempts. Target: {new_path}")
                print(f"   Files in dir: {os.listdir(file_dir)[:10]}")
                return True,new_path  # Signal failure to caller

            # --- Cleanup: delete any leftover files matching the original source name ---
            # This catches cases where the OS or another thread left a duplicate behind
            for leftover in glob.glob(os.path.join(file_dir, original_basename)):
                leftover = os.path.normpath(leftover)
                if leftover != new_path:  # Never delete the freshly renamed target
                    try:
                        os.remove(leftover)
                        print(f"🗑️  Deleted leftover source file: {original_basename}")
                    except Exception as e:
                        print(f"⚠️  Could not delete leftover file {leftover}: {e}")

            # Also clean up any .crdownload remnants tied to the original name
            crdownload_path = final_file + ".crdownload"
            if os.path.exists(crdownload_path):
                try:
                    os.remove(crdownload_path)
                    print(f"🗑️  Deleted leftover .crdownload: {os.path.basename(crdownload_path)}")
                except Exception as e:
                    print(f"⚠️  Could not delete .crdownload: {e}")

            # Only register the file after we've confirmed it exists
            report_cases[case_id]['files'].append(new_name)
            print(f"✅ Renamed & verified: {new_name}")
            return False,new_path

        except FileNotFoundError as e:
            traceback.print_exc()
            print(f"❌ File not found error: {e}")
            return True,None
        except Exception as e:
            print(f"❌ Rename error: {e}")
            traceback.print_exc()
            return True