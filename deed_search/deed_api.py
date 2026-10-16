import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))






import os

from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://127.0.0.1:8002"
API_KEY = os.getenv("DEED_API_KEY", "")

headers = {"X-API-Key": API_KEY}

payload = {
    "county_name": "sussex county",
    "first_name": "Frank",
    "last_name": "Maenza",
    "download_file": False,
    "search_mode": "NAME",
    "block": "8",
}



import pysnooper


@pysnooper.snoop()
def run_deed_job(payload, poll_interval=2):

    """
    Submit a deed job, poll until completion, and return the final JSON
    exactly as the server provides it.
    """
    # 1. Kick off the job
    resp = requests.post(f"{BASE_URL}/api/deeds", json=payload, headers=headers)
    resp.raise_for_status()
    job_id = resp.json()["job_id"]

    # 2. Poll until done
    while True:
        status_resp = requests.get(f"{BASE_URL}/api/deeds/{job_id}", headers=headers)
        status_resp.raise_for_status()
        status = status_resp.json()

        if status["status"] in ("done", "error"):
            break


    # 3. If error, return the error payload directly
    if status["status"] == "error":
        return status

    # 4. Job succeeded — return the server's final result exactly
    return status["result"]



