"""
cache/redis_client.py
=====================
Single shared Redis connection pool for the whole app.
Import `r` from here everywhere — never create your own redis.Redis() instance.
"""
import subprocess
import time

import redis

_pool = redis.ConnectionPool(
    host="localhost",
    port=6379,
    db=0,
    decode_responses=True,
    max_connections=50,
)

r: redis.Redis = redis.Redis(connection_pool=_pool)

# ── Queue key names ───────────────────────────────────────────────────────────
CASE_QUEUE_KEY   = "court:case_queue"       # Redis list  → pending cases (JSON)
PROCESSING_KEY   = "court:processing"       # Redis set   → case_ids currently running
CANCELLED_KEY    = "court:cancelled"        # Redis set   → case_ids cancelled mid-flight
DEED_QUEUE_KEY   = "court:deed_queue"       # Redis list  → pending deed jobs (JSON)
OBIT_QUEUE_KEY   = "court:obit_queue"       # Redis list  → pending obituary jobs (JSON)

# ── VPN coordination keys ─────────────────────────────────────────────────────
VPN_LOCK_KEY        = "court:vpn:lock"          # held by leader while resetting
VPN_LAST_RESET_KEY  = "court:vpn:last_reset"    # float timestamp of last successful reset
VPN_DEBOUNCE_SECS   = 15                         # mirrors DEBOUNCE_SECONDS in driver_pool.py

# ── State keys ────────────────────────────────────────────────────────────────
STATE_REPORT_CASES_KEY = "court:state:report_cases"   # Redis hash: case_id -> json
STATE_SKIP_CASES_KEY   = "court:state:skip_cases"     # Redis set: case_id
STATE_PREFIX           = "court:state:"               # Prefix for scalar properties


def is_redis_available() -> bool:
    """Quick health-check. Returns False if Redis is not running."""
    try:
        
        return bool(r.ping())
    except Exception:
        return False


def ensure_redis_running() -> bool:

    """
    Checks if Redis is running. If not, attempts to start it automatically via WSL.
    Returns True if Redis is reachable, False otherwise.
    """
    if is_redis_available():
        return True

    try:
        print("[Redis] Redis is not reachable. Attempting to start redis-server via WSL...")
        subprocess.run(
            ["wsl", "-d", "Ubuntu", "-u", "root", "--", "sh", "-c", "redis-server --daemonize yes </dev/null >/dev/null 2>&1"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
        # Give Redis a moment to bind and WSL2 to mirror port 6379 to localhost
        for _ in range(10):
            time.sleep(0.3)
            if is_redis_available():
                print("[Redis] Redis server started successfully via WSL.")
                return True

        print("[Redis] Redis is still unreachable after WSL start attempt.")
        return False
    except Exception as exc:
        print(f"[Redis] Could not auto-start Redis via WSL: {exc}")
        return False


def clear_court_queues() -> None:
    """
    Clears all pending case queues, processing sets, and cancelled flags
    to ensure a clean slate on startup.
    """
    if not is_redis_available():
        return
    try:
        keys_to_clear = [
            CASE_QUEUE_KEY,
            PROCESSING_KEY,
            CANCELLED_KEY,
            DEED_QUEUE_KEY,
            OBIT_QUEUE_KEY,
        ]
        r.delete(*keys_to_clear)
        print("[Redis] Court queues and processing keys cleared.")
    except Exception as exc:
        print(f"[Redis] Error clearing queues: {exc}")



