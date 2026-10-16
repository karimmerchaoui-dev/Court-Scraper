"""
Central configuration — loaded by all modules.

Copy `.env.example` to `.env` and fill in your credentials.
Settings here act as defaults / fallbacks.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Apify
# ---------------------------------------------------------------------------
# Comma-separated list of API keys for round-robin rotation
APIFY_API_KEYS: list[str] = [
    key.strip()
    for key in os.getenv("APIFY_API_KEYS").split(",")
    if key.strip()
]

# ---------------------------------------------------------------------------
# Scraper defaults
# ---------------------------------------------------------------------------
DEFAULT_DELAY: int = int(os.getenv("SCRAPER_DELAY", "2"))
DEFAULT_MAX_WORKERS: int = int(os.getenv("SCRAPER_MAX_WORKERS", "5"))
DEFAULT_TIMEOUT: int = int(os.getenv("SCRAPER_TIMEOUT", "30"))
