"""
web_gui/app.py
Flask + Flask-SocketIO drop-in replacement for the Tkinter GUI layer.

Replace every Tkinter GUI call in your existing code with the equivalents
defined here.  Start the server with:
    python app.py
then open  http://localhost:5000  from any browser on the same network.
"""

import base64
import os
import queue
import tempfile
import threading
import time
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_file,
    send_from_directory,
)
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename

# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = "court-dl-secret"
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024   # 50 MB max upload
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# ── Shared state (mirrors your global tkinter vars) ───────────────────────────
case_status: dict   = {}          # case_id → dict of values
log_lines:   list   = []          # rolling log buffer
case_logs:   dict   = {}          # case_id → list of log lines
case_screenshots: dict = {}       # case_id → list of {image: b64, ts: float}
driver_case_map: dict  = {}       # driver_id → case_id  (updated from logs)
# ── Case queue & execution state ──────────────────────────────────────────────
# Synced directly with state.py so any module accessing app.case_queue or state.case_queue
# sees the exact same thread-safe queue.
from state import state

case_queue:  queue.Queue = state.case_queue
progress_value: float = 0.0
status_text_val: str  = "Idle"
running:     bool   = False
force_stop:  bool   = False

# settings
from config import settings

SETTINGS_FILE = Path(__file__).parent / "settings.json"

# In app.py, _settings is backed by and synchronized with typed Settings
_settings = settings.to_dict()

def _load_persisted_settings():
    settings.load_json(SETTINGS_FILE)
    _settings.clear()
    _settings.update(settings.to_dict())
    try:
        from state import state
        state.sync_settings(_settings)
    except Exception:
        pass

_load_persisted_settings()


# ══════════════════════════════════════════════════════════════════════════════
# TKINTER EQUIVALENTS  (call these from your processing code)
# ══════════════════════════════════════════════════════════════════════════════

STATUS_COLORS = {
    "pending":         "#6b7280",
    "starting":        "#3b82f6",
    "logging in":      "#f97316",
    "entering docket": "#38bdf8",
    "downloading":     "#22c55e",
    "completed":       "#16a34a",
    "error":           "#ef4444",
    "skipped":         "#f59e0b",
}

def _color_for(status: str) -> str:
    sl = status.lower()
    for key, color in STATUS_COLORS.items():
        if key in sl:
            return color
    return "#e2e8f0"


_case_status_callbacks = []

def add_case_status_callback(fn):
    """Register a callback fn(case, status) called whenever update_case_status runs."""
    if fn not in _case_status_callbacks:
        _case_status_callbacks.append(fn)

def update_case_status(driver, case, county, status, progress_down=None, details=None, address=None, case_county=None):
    global case_status
    prev = case_status.get(case, {})
    addr = address or prev.get("address", "")
    if not addr:
        try:
            import state
            addr = state.report_cases.get(case, {}).get("address") or state.report_cases.get(case, {}).get("court_address") or ""
        except Exception:
            pass

    resolved_county = case_county or prev.get("case_county", "")
    if not resolved_county or resolved_county.lower().strip() in ["new jersey", "nj"]:
        try:
            import state
            rc = state.report_cases.get(case, {})
            for key in ["county", "County", "county_name"]:
                val = str(rc.get(key) or "").strip()
                if val and val.lower() not in ["new jersey", "nj"]:
                    resolved_county = val
                    break
        except Exception:
            pass
    if not resolved_county:
        resolved_county = county or prev.get("county", "")

    case_status[case] = {
        "case":          case,
        "county":        county or prev.get("county", ""),
        "case_county":   resolved_county,
        "status":        status,
        "progress":      progress_down if progress_down is not None else "",
        "address":       addr,
        "details":       details or prev.get("details", ""),
        "color":         _color_for(status),
        # ← Preserve changes data across status updates
        "new_files":     prev.get("new_files", []),
        "removed_files": prev.get("removed_files", []),
        "total_changes": prev.get("total_changes", 0),
        "block_statuses": prev.get("block_statuses", {}),
    }
    if driver:
        try:
            driver.state = status
        except Exception:
            pass
    socketio.emit("case_update", case_status[case])

    for cb in _case_status_callbacks:
        try:
            cb(case, status)
        except Exception as e:
            print(f"Error in case_status callback: {e}")


def clear_case_status():
    """Equivalent of the Tkinter clear_case_status()."""
    global case_status
    case_status.clear()
    socketio.emit("clear_cases")


def emit_report(report_cases: dict):
    """Called when processing finishes to push the full report to all clients."""
    socketio.emit("processing_state", {"running": False, "report": report_cases})


def append_driver_log(driver_id: int, text: str, case_id: str = None):
    """Called from driver_snoop_web to stream monitor logs."""
    if case_id:
        if case_id not in case_logs:
            case_logs[case_id] = []
        case_logs[case_id].append(text)
        # Track which case this driver is working on (for screenshot tagging)
        driver_case_map[driver_id] = case_id
    socketio.emit("driver_log", {"driver_id": driver_id, "case_id": case_id, "line": text})


def log_message(message: str):
    """Equivalent of the Tkinter log_message()."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    log_lines.append(line)
    if len(log_lines) > 2000:          # rolling buffer
        log_lines.pop(0)
    socketio.emit("log_line", {"line": line})


def update_progress(value: float):
    """Equivalent of the Tkinter update_progress()."""
    global progress_value
    progress_value = value
    socketio.emit("progress", {"value": value})


def set_status_text(text: str):
    """Equivalent of setting the Tkinter status_text StringVar."""
    global status_text_val
    status_text_val = text
    socketio.emit("status_text", {"text": text})


# ── Stubs so existing imports don't break ─────────────────────────────────────
def browse_input_file():  pass
def browse_output_folder(): pass
def clear_log(): log_lines.clear(); socketio.emit("clear_log")


# ══════════════════════════════════════════════════════════════════════════════
# HTTP ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/monitor")
def monitor_page():
    return render_template("index.html")


# ── Settings ──────────────────────────────────────────────────────────────────
@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(_settings)


@app.route("/api/settings", methods=["POST"])
def save_settings():
    data = request.json or {}
    for key in _settings:
        if key in data:
            if key == "llm_configs" and isinstance(data[key], dict):
                if not isinstance(_settings.get("llm_configs"), dict):
                    _settings["llm_configs"] = {}
                for subk, subv in data[key].items():
                    if isinstance(subv, dict):
                        if subk not in _settings["llm_configs"] or not isinstance(_settings["llm_configs"][subk], dict):
                            _settings["llm_configs"][subk] = {}
                        _settings["llm_configs"][subk].update(subv)
                    else:
                        _settings["llm_configs"][subk] = subv
            else:
                _settings[key] = data[key]

    if "headless_mode" in data:
        hm = bool(data["headless_mode"])
        _settings["headless_mode"] = hm
        try:
            from state import state
            state.headless_mode = hm
        except Exception:
            pass
        try:
            import main as _main
            if hasattr(_main, "headless_mode") and hasattr(_main.headless_mode, "set"):
                _main.headless_mode.set(hm)
        except Exception:
            pass

    try:
        settings.update_from_dict(_settings)
        settings.save_json(SETTINGS_FILE)
    except Exception as e:
        print(f"[Settings] Error saving {SETTINGS_FILE}: {e}")

    try:
        from state import state
        state.sync_settings(_settings)
    except Exception:
        pass

    socketio.emit("settings_updated", _settings)
    return jsonify({"ok": True, "settings": _settings})


@app.route("/api/llm-costs", methods=["GET"])
def api_get_llm_costs():
    try:
        from ai.llm_cost_tracker import get_cost_summary
        summary = get_cost_summary()
        return jsonify({"ok": True, "summary": summary, **summary})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/llm-costs/reset", methods=["POST"])
def api_reset_llm_costs():
    try:
        from ai.llm_cost_tracker import reset_llm_costs
        summary = reset_llm_costs()
        return jsonify({"ok": True, "costs": summary, "summary": summary})
    except Exception as e:
        return jsonify({"error": str(e)}), 500




@app.route("/api/reset-all", methods=["POST"])
def reset_all():
    """Remove all cases, clear queue, reset batch name, and clear input file."""
    global case_status, case_queue, running, force_stop, progress_value, status_text_val
    
    # Stop any running processing
    running = False
    force_stop = True
    
    # Clear case status
    case_status.clear()
    
    # Clear case queue
    with case_queue.mutex:
        case_queue.queue.clear()
        case_queue.all_tasks_done.notify_all()
        case_queue.unfinished_tasks = 0
    
    # Reset settings
    _settings["input_file"] = ""
    _settings["batch_name"] = ""
    settings.input_file = ""
    settings.batch_name = ""
    
    # Reset progress
    progress_value = 0.0
    status_text_val = "Idle"
    
    # Emit events to all clients
    socketio.emit("clear_cases")
    socketio.emit("progress", {"value": 0})
    socketio.emit("status_text", {"text": "Idle"})
    socketio.emit("processing_state", {"running": False})
    
    # Also emit settings update so UI updates
    socketio.emit("settings_updated", _settings)
    
    log_message("🧹 All cases removed and state reset")
    return jsonify({"ok": True, "message": "All cases removed and state reset"})


def restart_app_process():
    """Kill running drivers/threads and spawn a fresh process of main.py / entrypoint."""
    import os
    import subprocess
    import sys
    import time

    # 1. Gracefully stop scrapers and kill browsers
    try:
        from core.process_control import kill_all_browser_processes
        kill_all_browser_processes()
    except Exception as e:
        print(f"[Restart] Error terminating browsers: {e}")

    try:
        import main as _main
        if hasattr(_main, "driver_pool") and _main.driver_pool:
            all_drivers = list(getattr(_main.driver_pool, "in_use", [])) + list(getattr(_main.driver_pool, "available", []))
            for d in all_drivers:
                try:
                    d.quit()
                except Exception:
                    pass
    except Exception as e:
        print(f"[Restart] Error closing driver pool: {e}")

    # 2. Determine target script and interpreter
    python_exe = sys.executable
    project_root = os.path.dirname(os.path.abspath(__file__))

    # Detect the actual entrypoint that was started
    target_script = None
    if sys.argv and sys.argv[0]:
        candidate = os.path.abspath(sys.argv[0])
        if os.path.exists(candidate) and (candidate.endswith(".py") or os.path.isfile(candidate)):
            target_script = candidate

    if not target_script:
        # Check standard entrypoints
        candidate_main = os.path.join(project_root, "court_scraper_basic", "main.py")
        if os.path.exists(candidate_main):
            target_script = candidate_main
        elif os.path.exists(os.path.join(project_root, "main.py")):
            target_script = os.path.join(project_root, "main.py")
        else:
            target_script = os.path.join(project_root, "app.py")

    target_args = sys.argv[1:] if sys.argv and len(sys.argv) > 1 else []
    cwd = os.getcwd()
    env = os.environ.copy()
    env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")

    # Python detached launcher code: waits 1.5s so this process completely exits & releases sockets/ports, then launches new process
    launcher_code = (
        "import time, subprocess, sys, os; "
        "time.sleep(1.5); "
        "cmd = [sys.executable] + sys.argv[1:]; "
        "subprocess.Popen(cmd, cwd=os.getcwd(), close_fds=True)"
    )

    full_cmd = [python_exe, "-c", launcher_code, target_script] + target_args

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    print(f"[Restart] Spawning detached restarter: {full_cmd}")
    try:
        subprocess.Popen(
            full_cmd,
            cwd=cwd,
            env=env,
            creationflags=creationflags,
            close_fds=True,
        )
    except Exception as e:
        print(f"[Restart] Failed to spawn restart process: {e}")

    # Give the launcher process time to detach before terminating current process
    time.sleep(0.4)
    print(f"[Restart] Terminating current process (PID: {os.getpid()})...")
    os._exit(0)


@app.route("/api/restart", methods=["POST"])
def api_restart():
    """Shut down the entire application and restart it fresh from scratch."""
    global running, force_stop
    running = False
    force_stop = True
    log_message("⚡ App restart requested. Shutting down and relaunching application...")
    try:
        socketio.emit("app_restarting", {"message": "Application is restarting..."})
    except Exception:
        pass

    def _do_restart():
        time.sleep(0.4)
        restart_app_process()

    threading.Thread(target=_do_restart, daemon=True).start()
    return jsonify({"ok": True, "message": "Restart sequence initiated"})


# ── File upload (replaces browse_input_file) ──────────────────────────────────
@app.route("/api/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "No selected file"}), 400
    filename = secure_filename(f.filename)
    dest = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    f.save(dest)
    _settings["input_file"] = dest
    # Set batch name from filename (without extension)
    _settings["batch_name"] = os.path.splitext(filename)[0]
    settings.input_file = dest
    settings.batch_name = os.path.splitext(filename)[0]
    log_message(f"📂 Uploaded input file: {filename}")
    # kick off case loading in your existing code
    try:
        from core.excel_helpers import load_cases_from_excel
        load_cases_from_excel(dest)
    except Exception as e:
        log_message(f"⚠️  load_cases_from_excel error: {e}")
    return jsonify({"ok": True, "path": dest, "filename": filename})


# ── Output folder (user types a path since files live on server) ───────────────
@app.route("/api/output-folder", methods=["POST"])
def set_output_folder():
    data = request.json or {}
    folder = data.get("folder", "").strip()
    if not folder:
        return jsonify({"error": "Empty path"}), 400
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    _settings["output_folder"] = folder
    settings.output_folder = folder
    log_message(f"📁 Output folder set: {folder}")
    return jsonify({"ok": True})


# ── Driver Monitor ────────────────────────────────────────────────────────────
@app.route("/api/drivers/screenshots", methods=["GET"])
def get_driver_screenshots():
    try:
        from main import (
            driver_pool,  # state variable — main must be imported once running
        )
        drivers_data = []
        if driver_pool:
            all_drivers = driver_pool.in_use + driver_pool.available
            for index, driver in enumerate(all_drivers):
                d_id = id(driver)
                state = getattr(driver, "state", "unknown")
                in_use = driver in driver_pool.in_use
                url = None
                try:
                    url = driver.current_url
                except Exception:
                    pass

                screenshot_b64 = None
                try:
                    png_data = driver.get_screenshot_as_png()
                    import base64
                    from io import BytesIO

                    from PIL import Image
                    
                    img = Image.open(BytesIO(png_data))
                    thumbnail = img.copy()
                    thumbnail.thumbnail((1080, 1920), Image.Resampling.BILINEAR)
                    
                    buffered = BytesIO()
                    thumbnail.save(buffered, format="PNG")
                    screenshot_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                except Exception:
                    pass
                
                drivers_data.append({
                    "driver_id": d_id,
                    "index": index,
                    "state": state,
                    "in_use": in_use,
                    "url": url,
                    "screenshot": screenshot_b64
                })
        return jsonify(drivers_data)
    except ImportError:
        return jsonify([])
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── Cases ─────────────────────────────────────────────────────────────────────
@app.route("/api/cases", methods=["GET"])
def get_cases():
    return jsonify(list(case_status.values()))

@app.route("/api/cases/<case_id>/logs", methods=["GET"])
def get_case_logs(case_id):
    logs = case_logs.get(case_id, [])
    return jsonify(logs)

@app.route("/api/cases/<case_id>/blocks", methods=["GET"])
def get_case_blocks(case_id):
    """Return the recorded pipeline block statuses for a case."""
    c = case_status.get(case_id, {})
    return jsonify(c.get("block_statuses", {}))


@app.route("/api/cases/<case_id>/screenshots", methods=["GET"])
def get_case_screenshots(case_id):
    """Return the full timeline of screenshots stored for a case."""
    shots = case_screenshots.get(case_id, [])
    return jsonify(shots)  # list of {file, ts}

@app.route("/api/screenshot/<path:filepath>", methods=["GET"])
def serve_screenshot(filepath):
    """Serve a saved screenshot file from the screenshots directory."""
    screenshots_dir = os.path.join(os.path.dirname(__file__), "screenshots")
    return send_from_directory(screenshots_dir, filepath)


@app.route("/api/cases/add", methods=["POST"])
def add_case():
    data = request.json or {}
    case_raw = data.get("case_number", "").strip()
    county   = data.get("county", "").strip()
    if not case_raw or not county:
        return jsonify({"error": "Missing case_number or county"}), 400
    try:
        from models import Case
        from utils.formatting import (
            format_case_number_bw,
            format_case_number_lee,
            format_case_number_md,
            format_case_number_nj,
            format_case_number_oc,
        )
        county_l = county.lower()
        if "jersey" in county_l or "nj" in county_l:
            year, docket = format_case_number_nj(case_raw)
            court_type = "civil"
        elif "miami" in county_l:
            year, docket, court_type = format_case_number_md(case_raw)
        elif "orange" in county_l:
            year, docket, court_type = format_case_number_oc(case_raw)
        elif "broward" in county_l:
            year, docket, court_type = format_case_number_bw(case_raw)
        elif "lee" in county_l:
            year, docket, court_type = format_case_number_lee(case_raw)
        else:
            year, docket, court_type = "", case_raw, ""
        case_obj = Case(year=year, case_number=docket, county=county, case_type=court_type)
    except ImportError:
        # fallback when running standalone
        year, docket, court_type = "", case_raw, ""
        case_obj_id = case_raw
        case_queue.put((year, docket, court_type, county))
        update_case_status(None, case_obj_id, county, "Pending", details="Waiting to process")
        log_message(f"➕ Added case {case_obj_id} ({county})")
        return jsonify({"ok": True, "case_id": case_obj_id})
    except Exception as e:
        return jsonify({"error": f"Parse error: {e}"}), 400

    if case_obj.id in case_status:
        return jsonify({"error": "Case already in the list"}), 409
    case_queue.put((year, docket, court_type, county))
    update_case_status(None, case_obj.id, county, "Pending", details="Waiting to process")
    log_message(f"➕ Added case {case_obj.id} ({county})")
    return jsonify({"ok": True, "case_id": case_obj.id})


@app.route("/api/cases/remove", methods=["POST"])
def remove_cases():
    data = request.json or {}
    ids_to_remove = set(str(i).strip() for i in data.get("case_ids", []))
    if not ids_to_remove:
        return jsonify({"error": "No case IDs provided"}), 400

    # ── 1. Tell ALL clients to remove these rows immediately ──────────────────
    socketio.emit("remove_cases", {"case_ids": list(ids_to_remove)})

    # ── 2. Remove from server-side state ─────────────────────────────────────
    for cid in ids_to_remove:
        case_status.pop(cid, None)

    # ── 3. Drain & refill queue ───────────────────────────────────────────────
    try:
        from models import Case
        with case_queue.mutex:
            all_items = list(case_queue.queue)
            case_queue.queue.clear()
            case_queue.all_tasks_done.notify_all()
            case_queue.unfinished_tasks = 0
        kept = []
        for item in all_items:
            year, docket, court_type, county = item
            c = Case(year=year, case_number=docket, county=county, case_type=court_type)
            if c.id.strip() not in ids_to_remove:
                kept.append(item)
        for item in kept:
            case_queue.put(item)
        removed = len(all_items) - len(kept)
    except ImportError:
        removed = len(ids_to_remove)

    log_message(f"🗑️ Removed {removed} case(s): {', '.join(ids_to_remove)}")
    return jsonify({"ok": True, "removed": removed})





@app.route("/api/cases/load-range", methods=["POST"])
def load_case_range():
    data   = request.json or {}
    year   = str(data.get("year", "")).strip()
    from_n = data.get("from")
    to_n   = data.get("to")
    county = data.get("county", "").strip()

    if not year or from_n is None or to_n is None or not county:
        return jsonify({"error": "Missing year, from, to, or county"}), 400

    try:
        from_n = int(from_n)
        to_n   = int(to_n)
    except ValueError:
        return jsonify({"error": "from and to must be numbers"}), 400

    if from_n > to_n:
        return jsonify({"error": "'from' must be less than 'to'"}), 400
    if to_n - from_n > 10000:
        return jsonify({"error": "Range too large (max 10,000)"}), 400

    county_l = county.lower()
    loaded   = 0
    errors   = []

    for n in range(from_n, to_n + 1):
        try:
            # Build docket and case_id directly — no formatter needed
            docket    = str(n)
            court_type = "civil" if ("jersey" in county_l or "nj" in county_l) else ""
            case_id   = f"f-{docket}-{year}"

            if case_id not in case_status:
                case_queue.put((year, docket, court_type, county))
                update_case_status(None, case_id, county, "Pending", details="Waiting to process")
                loaded += 1

        except Exception as e:
            errors.append(f"{n}: {e}")
            continue

    if errors:
        log_message(f"⚠️ {len(errors)} errors during range load: {errors[:3]}")

    log_message(f"📋 Loaded {loaded} cases from range {year}/{from_n}–{to_n} ({county})")
    return jsonify({"ok": True, "count": loaded})



@app.route("/api/cases/clear", methods=["POST"])
def api_clear_cases():
    clear_case_status()
    with case_queue.mutex:
        case_queue.queue.clear()
    log_message("🧹 Case list cleared")
    return jsonify({"ok": True})


# ── Processing controls ───────────────────────────────────────────────────────

@app.route("/api/start", methods=["POST"])
def api_start():
    global running, force_stop

    try:
        import main as _main
        from state import state
        # ← Check both flags, not just running
        if state.running:
            return jsonify({"error": "Already running"}), 409
        if _main.case_queue.empty():
            return jsonify({"error": "No cases loaded — upload an Excel file first"}), 400
    except Exception:
        if running:
            return jsonify({"error": "Already running"}), 409

    data = request.json or {}
    if "headless_mode" in data:
        hm = bool(data["headless_mode"])
        _settings["headless_mode"] = hm
        try:
            settings.headless_mode = hm
        except Exception:
            pass
        try:
            from state import state
            state.headless_mode = hm
        except Exception:
            pass
        try:
            import main as _main
            if hasattr(_main, "headless_mode") and hasattr(_main.headless_mode, "set"):
                _main.headless_mode.set(hm)
        except Exception:
            pass
    else:
        hm = bool(_settings.get("headless_mode", False))
        try:
            from state import state
            state.headless_mode = hm
        except Exception:
            pass
        try:
            import main as _main
            if hasattr(_main, "headless_mode") and hasattr(_main.headless_mode, "set"):
                _main.headless_mode.set(hm)
        except Exception:
            pass

    try:
        from state import state
        state.sync_settings(_settings)
    except Exception:
        pass

    log_message("▶️  Processing started")
    socketio.emit("processing_state", {"running": True})

    # ── Check if Celery execution is enabled in settings ─────────────────────
    if _settings.get("use_celery", False):
        try:
            import main as _main
            from state import state
            from tasks.case_tasks import run_case_pipeline

            cases_dispatched = 0
            while not _main.case_queue.empty():
                item = _main.case_queue.get_nowait()
                if len(item) >= 6:
                    year, docket, court_type, processor_name, address, county = item[:6]
                else:
                    year, docket, court_type, processor_name = item[:4]
                    address = item[4] if len(item) > 4 else ""
                    county = ""
                case_payload = {
                    "year": year,
                    "docket": docket,
                    "court_type": court_type,
                    "county": processor_name or county,
                    "address": address,
                    "output_folder": getattr(state, "current_batch_folder", "") or "",
                }
                run_case_pipeline.delay(case_payload)
                cases_dispatched += 1

            log_message(f"🚀 Dispatched {cases_dispatched} cases to Celery worker queue ('cases')")
            return jsonify({"ok": True, "celery": True, "dispatched": cases_dispatched})
        except Exception as e:
            log_message(f"⚠️ Celery dispatch error, falling back to local thread: {e}")

    try:
        import importlib as _il
        import sys as _sys
        _main = _sys.modules.get('main')
        if _main is None or not hasattr(_main, 'process_cases'):
            _main = _il.import_module('main')
        threading.Thread(target=_main.process_cases, daemon=True).start()
    except Exception as e:
        log_message(f"⚠️  process_cases error: {e}")
        running = False
        try:
            state.running = False
        except Exception:
            pass

    return jsonify({"ok": True})


# ── Report ────────────────────────────────────────────────────────────────────
@app.route("/api/report", methods=["GET"])
def get_report():
    """Return report_cases from main for display."""
    try:
        import main
        report_cases = main.report_cases
    except Exception:
        report_cases = {}
    return jsonify(report_cases)


@app.route("/api/stop", methods=["POST"])
def api_stop():
    global running, force_stop
    running    = False
    force_stop = True
    log_message("⏹  Stop requested")
    try:
        import main
        report_cases = main.report_cases
    except Exception:
        report_cases = {}
    socketio.emit("processing_state", {"running": False, "report": report_cases})
    try:
        from core.process_control import stop_processing
        from state import state
        threading.Thread(target=stop_processing, args=(state.current_batch_folder,), daemon=True).start()
    except Exception as e:
        log_message(f"⚠️  stop error: {e}")
    return jsonify({"ok": True})


@app.route("/api/skip", methods=["POST"])
def api_skip():
    data    = request.json or {}
    case_id = data.get("case_id", "").strip()
    try:
        from main import skip_case_by_id, skip_current_case
        if case_id:
            skip_case_by_id(case_id)
            log_message(f"⏭  Skipping case {case_id}")
        else:
            skip_current_case()
            log_message("⏭  Skipping current case")
    except Exception as e:
        log_message(f"⚠️  skip error: {e}")
    return jsonify({"ok": True})


# ── Batch folder download ─────────────────────────────────────────────────────
@app.route("/api/download-batch-folder", methods=["GET"])
def download_batch_folder():
    """Zip the current batch folder (starts with 'Batch_') and stream it to the client."""
    try:
        import main as _main
        batch_folder = getattr(_main, "current_batch_folder", None)
    except Exception:
        batch_folder = None

    if not batch_folder or not os.path.isdir(batch_folder):
        return jsonify({"error": "No batch folder available"}), 404

    folder_name = os.path.basename(batch_folder)
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.close()
    try:
        with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(batch_folder):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    arcname = os.path.relpath(fpath, os.path.dirname(batch_folder))
                    zf.write(fpath, arcname)
        return send_file(
            tmp.name,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"{folder_name}.zip",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/api/log", methods=["GET"])
def get_log():
    return jsonify({"lines": log_lines})


@app.route("/api/log/clear", methods=["POST"])
def api_clear_log():
    log_lines.clear()
    socketio.emit("clear_log")
    return jsonify({"ok": True})


def _get_llm_costs_safe():
    try:
        from ai.llm_cost_tracker import get_cost_summary
        return get_cost_summary()
    except Exception:
        return {}

# ── Full state snapshot (on connect) ─────────────────────────────────────────
@app.route("/api/state", methods=["GET"])
def get_state():
    return jsonify({
        "cases":     list(case_status.values()),
        "log":       log_lines[-500:],
        "progress":  progress_value,
        "status":    status_text_val,
        "running":   running,
        "settings":  _settings,
        "llm_costs": _get_llm_costs_safe(),
    })


# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET EVENTS
# ══════════════════════════════════════════════════════════════════════════════

@socketio.on("connect")
def on_connect():
    """Send full state to newly connected client."""
    emit("init_state", {
        "cases":     list(case_status.values()),
        "log":       log_lines[-500:],
        "progress":  progress_value,
        "status":    status_text_val,
        "running":   running,
        "settings":  _settings,
        "llm_costs": _get_llm_costs_safe(),
    })


@socketio.on("disconnect")
def on_disconnect():
    pass


# ══════════════════════════════════════════════════════════════════════════════
# SCREENSHOT CAPTURE LOOP
# ══════════════════════════════════════════════════════════════════════════════

def _screenshot_loop():
    """Background thread: capture a screenshot from every in-use driver every 0.5s.
    Saves JPEG files to screenshots/<case_id>/ on disk."""
    screenshots_base = os.path.join(os.path.dirname(__file__), "screenshots")
    os.makedirs(screenshots_base, exist_ok=True)

    while True:
        try:
            if not running:
                time.sleep(1)
                continue

            import main as _m
            driver_pool = _m.driver_pool
            if not driver_pool:
                time.sleep(1)
                continue

            for driver in list(driver_pool.in_use):
                try:
                    driver_id = id(driver)
                    case_id = driver_case_map.get(driver_id)
                    if not case_id:
                        continue

                    png_data = driver.get_screenshot_as_png()
                    ts = time.time()

                    # Compress to JPEG quality 50
                    try:
                        from PIL import Image as PILImage
                        img = PILImage.open(BytesIO(png_data))
                        img.thumbnail((960, 540), PILImage.Resampling.BILINEAR)
                        buf = BytesIO()
                        img.save(buf, format="JPEG", quality=50)
                        jpg_bytes = buf.getvalue()
                    except ImportError:
                        jpg_bytes = png_data  # fallback

                    # Save to disk: screenshots/<case_id>/<timestamp>.jpg
                    safe_case = case_id.replace("/", "_").replace("\\", "_").replace(":", "_")
                    case_dir = os.path.join(screenshots_base, safe_case)
                    os.makedirs(case_dir, exist_ok=True)
                    filename = f"{ts:.3f}.jpg"
                    filepath = os.path.join(case_dir, filename)
                    with open(filepath, "wb") as f:
                        f.write(jpg_bytes)

                    # Store metadata in rolling buffer
                    rel_path = f"{safe_case}/{filename}"
                    entry = {"file": rel_path, "ts": ts}
                    if case_id not in case_screenshots:
                        case_screenshots[case_id] = []
                    case_screenshots[case_id].append(entry)

                    # Also broadcast base64 for live driver monitor
                    b64 = base64.b64encode(jpg_bytes).decode("utf-8")
                    socketio.emit("case_screenshot", {
                        "case_id": case_id,
                        "driver_id": driver_id,
                        "image": b64,
                        "file": rel_path,
                        "ts": ts,
                    })

                except Exception:
                    pass  # never crash the loop over a single driver failure

        except Exception:
            pass

        time.sleep(0.5)


def start_screenshot_loop():
    """Call once at startup to begin background screenshot capture."""
    t = threading.Thread(target=_screenshot_loop, daemon=True)
    t.start()



def update_case_changes(case_id: str, new_files: list, removed_files: list):
    """Store file changes in case_status and emit to clients."""
    print(f"[DEBUG] update_case_changes called with case_id={case_id}")
    print(f"[DEBUG] Current keys in case_status: {list(case_status.keys())}")
    if case_id in case_status:
        print("[DEBUG] case_id found in case_status! Updating...")
        case_status[case_id]["new_files"]     = new_files
        case_status[case_id]["removed_files"] = removed_files
        case_status[case_id]["total_changes"] = len(new_files) + len(removed_files)
        socketio.emit("case_update", case_status[case_id])
    else:
        print("[DEBUG] case_id NOT FOUND in case_status!")


# ══════════════════════════════════════════════════════════════════════════════
# QUEUE MANAGEMENT API  (Redis-backed dynamic add / remove / cancel / inspect)
# These routes are additive — they don't affect any scraping logic.
# If Redis is unavailable the RedisQueue falls back gracefully; the routes
# still work but return limited data in fallback mode.
# ══════════════════════════════════════════════════════════════════════════════

from flask import Blueprint
from flask import jsonify as _jsonify
from flask import request as _flask_request

_queue_bp = Blueprint("queue_api", __name__, url_prefix="/api/queue")


@_queue_bp.route("/status", methods=["GET"])
def queue_status():
    """Return the full live state of pending / processing / cancelled cases."""
    try:
        return _jsonify(case_queue.status_snapshot())
    except AttributeError:
        # Fallback mode: case_queue is a plain queue.Queue
        return _jsonify({"pending": [], "processing": [], "cancelled": [], "total_pending": case_queue.qsize()})


@_queue_bp.route("/add", methods=["POST"])
def queue_add():
    """
    Dynamically add a case to the queue while processing is running.
    Body (JSON):
        { "year": "...", "docket": "...", "court_type": "...",
          "processor_name": "...", "address": "...", "county": "...",
          "priority": false }   ← priority=true inserts at front (runs next)
    """
    data = _flask_request.get_json(force=True) or {}
    required = {"year", "docket", "court_type", "processor_name"}
    missing = required - data.keys()
    if missing:
        return _jsonify({"error": f"Missing fields: {missing}"}), 400

    item = (
        data["year"],
        data["docket"],
        data["court_type"],
        data["processor_name"],
        data.get("address", ""),
        data.get("county", ""),
    )
    if data.get("priority"):
        case_queue.put_priority(item)
    else:
        case_queue.put(item)

    return _jsonify({"status": "queued", "queue_length": case_queue.qsize()})


@_queue_bp.route("/remove", methods=["POST"])
def queue_remove():
    """
    Remove a PENDING case (not yet started) from the queue.
    Body: { "case_id": "f-DOCKET-YEAR" }
    If the case is already running, adds it to the cancelled set instead.
    """
    data = _flask_request.get_json(force=True) or {}
    case_id = data.get("case_id", "").strip()
    if not case_id:
        return _jsonify({"error": "case_id required"}), 400

    removed = case_queue.remove(case_id)
    if removed:
        return _jsonify({"status": "removed_from_queue", "case_id": case_id})

    # Not in the pending queue — request cancellation of the running case
    case_queue.cancel_running(case_id)
    return _jsonify({"status": "cancellation_requested", "case_id": case_id})


@_queue_bp.route("/cancel", methods=["POST"])
def queue_cancel():
    """
    Explicitly cancel a RUNNING case.  The pipeline checks this at each block
    boundary and stops cleanly, releasing the driver back to the pool.
    Body: { "case_id": "f-DOCKET-YEAR" }
    """
    data = _flask_request.get_json(force=True) or {}
    case_id = data.get("case_id", "").strip()
    if not case_id:
        return _jsonify({"error": "case_id required"}), 400
    case_queue.cancel_running(case_id)
    return _jsonify({"status": "cancellation_requested", "case_id": case_id})


app.register_blueprint(_queue_bp)

# ══════════════════════════════════════════════════════════════════════════════
# ENTRYPOINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  Court Downloader — Web Interface")
    print("  http://localhost:8080")
    print("=" * 60)
    #start_screenshot_loop()
    socketio.run(app, host="0.0.0.0", port=8080, debug=False, allow_unsafe_werkzeug=True)
