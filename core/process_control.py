"""
Process control — start_processing, stop_processing, and cleanup helpers.
"""

import ctypes
import os
import sys
import threading
import traceback
from queue import Queue

import psutil

from app import clear_case_status, log_message, set_status_text, update_progress
from utils.formatting import save_to_excel


def start_processing():
    """Called from web_gui/app.py's /api/start endpoint via threading.Thread."""
    import main

    main.force_stop = False
    temp_queue = Queue()
    base_path = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(main.__file__))
    os.environ["PATH"] = base_path + os.pathsep + os.environ["PATH"]
    while not main.case_queue.empty():
        item = main.case_queue.get()
        temp_queue.put(item)
    while not temp_queue.empty():
        main.case_queue.put(temp_queue.get())
    main.running = True
    try:
        main._socketio.emit("processing_state", {"running": True})
    except Exception:
        pass
    main.process_cases()


def kill_all_browser_processes():
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                name = proc.info['name'] or ""
                if any(b in name.lower() for b in ['chrome', 'chromedriver']):
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        print(f"Error killing processes: {e}")


def terminate_all_threads():
    current_thread = threading.current_thread()
    for thread in threading.enumerate():
        if thread is threading.main_thread() or thread is current_thread:
            continue
        try:
            if hasattr(thread, '_thread_id'):
                ctypes.pythonapi.PyThreadState_SetAsyncExc(
                    ctypes.c_long(thread._thread_id),
                    ctypes.py_object(SystemExit))
        except Exception:
            try:
                thread.join(0.1)
            except Exception:
                pass


def stop_processing(batch_folder=None):
    import main

    try:
        main.running = False
        main.force_stop = True
        set_status_text("Stopping immediately...")
        log_message("Force stopping process - terminating all threads and processes...")
        if batch_folder:
            save_to_excel(main.report_cases, batch_folder)
            log_message(f"📊 Partial Excel report saved to: {batch_folder}")
        if main.driver_pool:
            main.driver_pool.monitoring_active = False
        kill_all_browser_processes()
        terminate_all_threads()
        with main.case_queue.mutex:
            clear_case_status()
            main.case_queue.queue.clear()
        log_message("All processes terminated forcefully")
        update_progress(0)
        try:
            main._socketio.emit("processing_state", {"running": False})
        except Exception:
            pass
    except Exception:
        traceback.print_exc()


def kill_driver_processes():
    current_pid = os.getpid()
    parent = psutil.Process(current_pid)
    for child in parent.children(recursive=True):
        try:
            child.kill()
        except Exception as e:
            print(f"Failed to kill child process: {e}")
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            name = proc.info['name'] or ""
            cmdline = " ".join(proc.info.get('cmdline') or [])
            if any(b in name.lower() for b in ['chrome', 'firefox', 'edge', 'chromedriver', 'geckodriver']):
                proc.kill()
            if 'uc_driver' in name.lower() or 'uc_driver' in cmdline.lower():
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
