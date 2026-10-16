import os
from datetime import datetime

from app import append_driver_log, log_message


def _save_matching_files_log(case_id, files_dir, matching_rows, file_name="_matched_files.txt"):
    """
    Write a plain-text log of every file that scan_table_multithreaded selected
    for download. Saved as  <files_dir>/_matched_files.txt  so you can compare
    it against the files that actually landed on disk.
    """
    try:
        log_path = os.path.join(files_dir, file_name)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"Case: {case_id}\n")
            f.write(f"Total matched: {len(matching_rows)}\n")
            f.write("-" * 60 + "\n")
            for i, row in enumerate(matching_rows, start=1):
                name = row.get('filename') or row.get('name', 'N/A')
                date = row.get('date', 'N/A')
                idx = row.get('row_index', 'N/A')
                href = row.get('href', '')
                desc = row.get('description', '')
                f.write(f"[{i}]  row={idx}  date={date}\n")
                f.write(f"      name : {name}\n")
                if desc:
                    f.write(f"      desc : {desc}\n")
                if href:
                    f.write(f"      href : {href}\n")
                f.write("\n")
    except Exception as e:
        print(f"⚠️  Could not write matched-files log for {case_id}: {e}")




def _log_file_status(case_id, files_dir, filename, index, date, status, reason=""):
    log_path = os.path.join(files_dir, f"{case_id}_download_log.txt")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{status}] File {index}: {filename} ({date})"
    if reason:
        line += f" | Reason: {reason}"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def display_matching_rows(case_id, driver, matching_rows):
    for file in matching_rows:
        index = file['row_index']
        filename = file['filename']
        append_driver_log(id(driver), f"file {index} {filename} \n", case_id)


def _cleanup_prefixed_files(files_dir, prefix):
    """Delete any file in files_dir whose name starts with prefix."""
    if not prefix or not os.path.isdir(files_dir):
        return
    for fname in os.listdir(files_dir):
        if fname.startswith(prefix):
            fpath = os.path.join(files_dir, fname)
            try:
                os.remove(fpath)
                log_message(f"🗑️ Deleted prefixed leftover: {fname}")
            except Exception as e:
                log_message(f"⚠️ Could not delete {fname}: {e}")

def _verify_downloaded_files(files_dir, files_to_download, failed_files):
    """Verify files actually exist on disk"""
    try:
        existing_files = os.listdir(files_dir) if os.path.exists(files_dir) else []
        for file_info in files_to_download:
            if file_info not in failed_files:
                if not any(file_info['filename'] in f for f in existing_files):
                    failed_files.append(file_info)
    except Exception as e:
        log_message(f"⚠️ File verification error: {e}")

    return failed_files
