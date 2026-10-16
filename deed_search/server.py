"""
Flask API server that exposes `download_deed` (from your existing `main.py`)
as a remote HTTP service.

Why "job-based" instead of a plain synchronous endpoint?
----------------------------------------------------------
`download_deed` almost certainly drives a browser (Selenium/Playwright) against
a county recorder site. Those calls can take anywhere from a few seconds to
several minutes, and a plain synchronous request would:
  - tie up a Flask worker thread for the whole scrape
  - risk client/proxy timeouts (nginx, load balancers, browsers all have
    default timeouts well under a minute)
  - make it impossible to check progress on a long-running batch

So this API accepts a job, runs it in a background thread pool, and gives you
a job_id you can poll. If you truly want fire-and-forget synchronous calls for
quick lookups, see the `/api/deeds/sync` endpoint at the bottom (use with
caution -- it will block until the scrape finishes).

Run locally:
    pip install -r requirements.txt
    export DEED_API_KEY="some-long-random-secret"
    python app.py

Run in production:
    gunicorn -w 1 --threads 8 -b 0.0.0.0:8000 app:app
    (Use 1 worker process with multiple threads -- or a shared job store like
     Redis -- since jobs live in this process's memory. See notes at bottom.)
"""

import logging
import os
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import wraps

from county_config import SearchMode
from flask import Flask, abort, jsonify, request, send_from_directory

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import settings
# --- Your existing scraping code -------------------------------------------
from main import download_deed

API_KEY = settings.deed_api_key
OUTPUT_BASE_DIR = os.path.abspath(settings.deed_output_dir)
MAX_WORKERS = settings.deed_max_workers
DEFAULT_HEADLESS = settings.deed_default_headless

os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)

"""logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)"""
logger = logging.getLogger("deed_api")

app = Flask(__name__)

executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# In-memory job store. Fine for a single-process deployment; swap for Redis
# (or a DB table) if you scale to multiple processes/machines -- see notes
# at the bottom of this file.
_jobs = {}
_jobs_lock = threading.Lock()

JOB_PENDING = "pending"
JOB_RUNNING = "running"
JOB_DONE = "done"
JOB_ERROR = "error"


# -----------------------------------------------------------------------------
# Auth
# -----------------------------------------------------------------------------

def require_api_key(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if API_KEY:  # only enforce if an API key was configured
            provided = request.headers.get("X-API-Key")
            if not provided or provided != API_KEY:
                return jsonify(error="Unauthorized: missing or invalid X-API-Key header"), 401
        return fn(*args, **kwargs)
    return wrapper


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _safe_job_output_dir(job_id: str) -> str:
    """Every job gets its own isolated subdirectory under OUTPUT_BASE_DIR so
    concurrent jobs can never collide or read each other's files, and so we
    can safely serve files back without a path-traversal risk."""
    path = os.path.join(OUTPUT_BASE_DIR, job_id)
    os.makedirs(path, exist_ok=True)
    return path


def _parse_search_mode(value):
    """Accept the search mode as a string (e.g. "NAME", "name", "BLOCK_LOT")
    and convert it to the SearchMode enum member. Raises ValueError if the
    name doesn't exist on the enum."""
    if value is None:
        return None
    if isinstance(value, SearchMode):
        return value
    key = str(value).strip().upper()
    try:
        return SearchMode[key]
    except KeyError:
        valid = ", ".join(m.name for m in SearchMode)
        raise ValueError(f"Invalid search_mode '{value}'. Valid options: {valid}")


def _build_kwargs(payload: dict, job_id: str) -> dict:
    """Translate the incoming JSON body into kwargs for download_deed().

    We pass most fields straight through (your `download_deed` signature is
    the source of truth), but we:
      - force `output_dir` to a per-job sandboxed directory (ignoring
        whatever the client sent, for safety)
      - convert `search_mode` from a string to the SearchMode enum
      - default `headless` to True on the server (there's normally no
        display attached to a server process)
    """
    kwargs = dict(payload)  # shallow copy

    if "county_name" not in kwargs or not kwargs["county_name"]:
        raise ValueError("'county_name' is required")

    kwargs["output_dir"] = _safe_job_output_dir(job_id)

    if "search_mode" in kwargs:
        kwargs["search_mode"] = _parse_search_mode(kwargs["search_mode"])

    kwargs.setdefault("headless", DEFAULT_HEADLESS)

    return kwargs


def _run_job(job_id: str, kwargs: dict):
    with _jobs_lock:
        _jobs[job_id]["status"] = JOB_RUNNING
        _jobs[job_id]["started_at"] = datetime.now(timezone.utc).isoformat()

    try:
        logger.info("Job %s starting with params=%s", job_id, {k: v for k, v in kwargs.items()})
        result = download_deed(**kwargs)
        with _jobs_lock:
            _jobs[job_id]["status"] = JOB_DONE
            _jobs[job_id]["result"] = _jsonify_result(result)
            _jobs[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()
        logger.info("Job %s finished successfully", job_id)
    except Exception as exc:  # noqa: BLE001 - we want to capture and report everything
        logger.exception("Job %s failed", job_id)
        with _jobs_lock:
            _jobs[job_id]["status"] = JOB_ERROR
            _jobs[job_id]["error"] = str(exc)
            _jobs[job_id]["traceback"] = traceback.format_exc()
            _jobs[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()


def _jsonify_result(result):
    """download_deed's return value might not be JSON-serializable as-is
    (e.g. a dataclass, Path object, tuple, etc). Do a best-effort conversion
    so the API always returns clean JSON. Adjust this to match whatever
    `download_deed` actually returns."""
    if result is None:
        return None
    if isinstance(result, (str, int, float, bool, dict, list)):
        return result
    if hasattr(result, "_asdict"):  # namedtuple
        return result._asdict()
    if hasattr(result, "__dict__"):  # dataclass / plain object
        return {k: str(v) for k, v in vars(result).items()}
    return str(result)


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    return jsonify(status="ok", time=datetime.now(timezone.utc).isoformat())


@app.route("/api/deeds", methods=["POST"])
@require_api_key
def create_deed_job():
    """Kick off a deed lookup/download as a background job.

    Example body:
    {
        "county_name": "gloucester county",
        "first_name": "Robert",
        "last_name": "Anderson",
        "case_number": "19-000",
        "download_file": false,
        "search_mode": "NAME",
        "block": "181.02"
    }

    Returns 202 with a job_id you can poll at GET /api/deeds/<job_id>.
    """
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify(error="Request body must be valid JSON"), 400

    job_id = str(uuid.uuid4())

    try:
        kwargs = _build_kwargs(payload, job_id)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": JOB_PENDING,
            "params": {k: (v.name if isinstance(v, SearchMode) else v) for k, v in kwargs.items()},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "result": None,
            "error": None,
        }

    executor.submit(_run_job, job_id, kwargs)

    return jsonify(job_id=job_id, status=JOB_PENDING), 202


@app.route("/api/deeds/<job_id>", methods=["GET"])
@require_api_key
def get_deed_job(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return jsonify(error="Unknown job_id"), 404
    return jsonify(job)


@app.route("/api/deeds", methods=["GET"])
@require_api_key
def list_deed_jobs():
    with _jobs_lock:
        jobs = list(_jobs.values())
    return jsonify(jobs=jobs, count=len(jobs))


@app.route("/api/deeds/<job_id>/files", methods=["GET"])
@require_api_key
def list_deed_job_files(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return jsonify(error="Unknown job_id"), 404

    job_dir = os.path.join(OUTPUT_BASE_DIR, job_id)
    if not os.path.isdir(job_dir):
        return jsonify(files=[])

    files = []
    for root, _dirs, filenames in os.walk(job_dir):
        for name in filenames:
            rel = os.path.relpath(os.path.join(root, name), job_dir)
            files.append(rel)
    return jsonify(files=files)


@app.route("/api/deeds/<job_id>/files/<path:filename>", methods=["GET"])
@require_api_key
def download_deed_job_file(job_id, filename):
    job_dir = os.path.join(OUTPUT_BASE_DIR, job_id)
    # send_from_directory safely resolves `filename` against job_dir and
    # 404s on any attempt to traverse outside of it.
    if not os.path.isdir(job_dir):
        abort(404)
    return send_from_directory(job_dir, filename, as_attachment=True)


@app.route("/api/deeds/sync", methods=["POST"])
@require_api_key
def create_deed_job_sync():
    """Synchronous variant: blocks the request until the scrape finishes and
    returns the result directly. Only use this for quick lookups behind a
    client/proxy with a generous timeout -- for anything that might take a
    while, use POST /api/deeds instead and poll for the result."""
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify(error="Request body must be valid JSON"), 400

    job_id = str(uuid.uuid4())
    try:
        kwargs = _build_kwargs(payload, job_id)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    try:
        result = download_deed(**kwargs)
        return jsonify(job_id=job_id, status=JOB_DONE, result=_jsonify_result(result))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Synchronous job %s failed", job_id)
        return jsonify(job_id=job_id, status=JOB_ERROR, error=str(exc)), 500


@app.errorhandler(404)
def not_found(_e):
    return jsonify(error="Not found"), 404


@app.errorhandler(500)
def server_error(_e):
    return jsonify(error="Internal server error"), 500


if __name__ == "__main__":
    if not API_KEY:
        logger.warning(
            "DEED_API_KEY is not set -- the API is running WITHOUT authentication. "
            "Set the DEED_API_KEY environment variable before exposing this publicly."
        )
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8002)), debug=False)