"""
Paste this block into main.py (near the top, after imports).
It replaces the Tkinter auto_driver_snoop with a web-compatible version
that streams pysnooper output to the browser's Driver Monitor panel.
"""

import functools
import threading

import pysnooper


class _WebDriverStream:
    """
    Pysnooper output stream that forwards lines to the web UI via
    web_gui.app.append_driver_log.  Thread-safe, non-blocking.
    """
    def __init__(self, driver_id: int):
        self.driver_id = driver_id
        self.case_id   = None
        self._buf      = []
        self._lock     = threading.Lock()

    def write(self, text: str):
        if not text.strip():
            return
        clean_text = text.rstrip('\r\n')
        try:
            from app import append_driver_log
            append_driver_log(self.driver_id, clean_text, self.case_id)
        except Exception:
            pass   # never crash the processing thread over a log failure

    def flush(self):
        pass


def attach_web_monitor(driver):
    """
    Call this once after creating each driver in DriverPool.
    Attaches a _monitor_log_func so auto_driver_snoop can find it,
    and stores the stream on the driver for reuse.
    """
    driver_id = id(driver)
    stream    = _WebDriverStream(driver_id)
    driver._web_stream      = stream
    driver._monitor_log_func = stream.write   # same attr the old decorator looked for


def auto_driver_snoop(*snoop_args, **snoop_kwargs):
    """
    Drop-in replacement for the Tkinter auto_driver_snoop decorator.
    Usage — same as before:

        @auto_driver_snoop
        def process_nj_case(driver, case, ...):
            ...

    You can also provide arguments like depth to trace inner functions:
        @auto_driver_snoop(depth=3)
        def process_nj_case(...):
            ...

    Works in both headless and non-headless mode.
    If no driver with _monitor_log_func is found in the args,
    the function runs unwrapped (no overhead).
    """
    def decorate(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            driver = None
            for arg in list(args) + list(kwargs.values()):
                if hasattr(arg, "_monitor_log_func"):
                    driver = arg
                    break

            if driver is None:
                return func(*args, **kwargs)

            driver_id = id(driver)
            
            # Extract case_id if possible
            case_id = None
            if "case" in kwargs:
                case_id = kwargs["case"]
            elif "case_id" in kwargs:
                case_id = kwargs["case_id"]
            else:
                for arg in args:
                    # Look for something that looks like a case ID (string, at least 5 chars, no spaces)
                    if isinstance(arg, str) and len(arg.strip()) >= 5 and " " not in arg.strip() and "http" not in arg:
                        case_id = arg
                        break
            
            # Temporary stream for this specific case execution
            stream = _WebDriverStream(driver_id)
            stream.case_id = case_id
            
            # Still attach to driver for legacy or fallback usage
            driver._web_stream = stream
            driver._monitor_log_func = stream.write

            default_kwargs = {
                "output": stream,
                "prefix": f"Driver-{driver_id}-",
                "thread_info": True,
                "depth": 3, # Automatically traces functions called within
            }
            default_kwargs.update(snoop_kwargs)

            snoop_wrapped = pysnooper.snoop(*snoop_args, **default_kwargs)(func)
            return snoop_wrapped(*args, **kwargs)
        return wrapper

    if len(snoop_args) == 1 and callable(snoop_args[0]) and not snoop_kwargs:
        func = snoop_args[0]
        snoop_args = ()
        return decorate(func)
    
    return decorate