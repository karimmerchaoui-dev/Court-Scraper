"""
Central configuration — load secrets from environment variables.
Never commit real API keys to version control.
"""

import os

# ---------------------------------------------------------------------------
# Apify
# ---------------------------------------------------------------------------
# Set APIFY_API_KEY_1 … APIFY_API_KEY_N in your environment (or .env file).
# The list below collects however many keys are defined.
APIFY_API_KEYS: list[str] = [
    v for k, v in os.environ.items()
    if k.startswith("apify_api_") and v
]

if not APIFY_API_KEYS:
    # Fallback: single key via APIFY_API_KEY
    single = os.environ.get("apify_api_", "")
    if single:
        APIFY_API_KEYS = [single]

# ---------------------------------------------------------------------------
# Scraper defaults
# ---------------------------------------------------------------------------
DEFAULT_DELAY = int(os.environ.get("SCRAPER_DELAY", "2"))
DEFAULT_MAX_WORKERS = int(os.environ.get("SCRAPER_MAX_WORKERS", "5"))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
