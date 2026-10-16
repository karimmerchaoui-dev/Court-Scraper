
import glob
import os
import re
from pathlib import Path


def get_existing_files(download_dir):
    return set(p.name for p in Path(download_dir).iterdir() if p.is_file())



def generate_safe_filename(raw_name, max_length=180):
    # Convert to lowercase for case-insensitive search
    lower_name = raw_name.lower()

    # Try to split before "submitted" or "granted"
    

    # Sanitize: keep only letters and numbers, replace all else with _
    sanitized = re.sub(r'[^a-zA-Z0-9]', '_', raw_name)
    sanitized = re.sub(r'_+', '_', sanitized).strip('_')  # Clean up multiple/edge underscores

    # Enforce max length
    sanitized = sanitized[:max_length]

    return sanitized



def cleanup_unwanted_files(folder):
    files_to_delete = set(glob.glob(os.path.join(folder, "*.crdownload"))) | set(glob.glob(os.path.join(folder, "*.aspx")))
    for file_path in files_to_delete:
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Failed to delete {file_path}: {e}")