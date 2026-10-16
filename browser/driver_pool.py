# ══════════════════════════════════════════════════════════════════════════════
# DRIVER POOL
# ══════════════════════════════════════════════════════════════════════════════

import os
import threading
import time
import traceback
from contextlib import contextmanager
from http.client import RemoteDisconnected

import pysnooper
from selenium.common.exceptions import (
    InvalidSessionIdException,
    NoSuchWindowException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.by import By
from urllib3.exceptions import (
    MaxRetryError,
    NewConnectionError,
    ProtocolError,
    ReadTimeoutError,
)

LEASE_DURATION = 180          # max time a leader gets before considered "hung"
DEBOUNCE_SECONDS = 15


class DriverPool:
    """
    Manages a pool of Selenium WebDriver instances for concurrent scraping.

    All external helper functions and mutable globals are injected via the
    constructor so this module never imports from main.py (avoids circular
    imports).
    """

    def __init__(
            self,
            max_workers,
            *,
            # ── external functions ──────────────────────────────────────────
            setup_driver_func,
            attach_web_monitor_func,
            append_driver_log_func,
            reset_vpn_func,
            element_exists_id_func,
            element_exists_xpath_func,
            refresh_url_func,
            check_js_popup_func,
            request_url_func,
            delete_driver_func,
            # ── external state / values ─────────────────────────────────────
            case_queue,
            headless_mode,
            get_force_stop,
            get_max_workers,
            nj_login_page,
    ):
    
        # Store injected functions
        self._setup_driver = setup_driver_func
        self._attach_web_monitor = attach_web_monitor_func
        self._append_driver_log = append_driver_log_func
        self._reset_vpn = reset_vpn_func
        self._element_exists_id = element_exists_id_func
        self._element_exists_xpath = element_exists_xpath_func
        self._refresh_url = refresh_url_func
        self._check_js_popup = check_js_popup_func
        self._request_url = request_url_func
        self._delete_driver = delete_driver_func

        # Store injected state / getters
        self._case_queue = case_queue
        self._headless_mode = headless_mode
        self._get_force_stop = get_force_stop
        self._get_max_workers = get_max_workers
        self._nj_login_page = nj_login_page

        # Pool internals
        self.max_workers = max_workers
        self.available = []
        self.in_use = []
        self.lock = threading.RLock()
        self.monitoring_active = True
        self.error_callback = None
        self.last_vpn_reset_time = 0
        self.vpn_lock = threading.RLock()
        self.vpn_resetting = threading.Event()  # True while reset is happening
        self.vpn_reset_requested = threading.Event()  # Monitor signals workers
        self.stop_requested = threading.Event()
        self._vpn_cond = threading.Condition()
        self._vpn_resetting = False
        self._vpn_generation = 0          # bumped every time a reset attempt ENDS (success/fail/abort)
        self._vpn_lease_expiry = 0.0      # leader must be done before this or is presumed hung
        self._vpn_last_reset_time = 0.0
        self._vpn_last_result = None

        for _ in range(min(self.max_workers, self._case_queue.qsize())):
            try:
                driver = self._setup_driver(self._headless_mode)
                driver.state = "idle"
                self._attach_web_monitor(driver)
                self.available.append(driver)
            except Exception as e:
                traceback.print_exc()
                print(f"[ERROR] Failed to create initial driver: {e}")

        self.monitor_thread = threading.Thread(target=self._monitor_drivers, daemon=True)
        self.monitor_thread.start()

    # ── public helpers ──────────────────────────────────────────────────────

    def set_error_callback(self, callback_function):
        self.error_callback = callback_function

    def show_driver_log(self, driver, msg):
        try:
            self._append_driver_log(id(driver), msg)
        except Exception:
            pass  # never crash processing over a log failure

    def is_any_downloading_oc_retrying(self):
        with self.lock:
            for driver in self.in_use:
                if getattr(driver, "state", None) == "downloading oc retrying":
                    return True
            return False

    def close_and_refill(self, driver):
        if self._get_force_stop():
            return None

        try:
            with self.lock:
                if driver in self.in_use:
                    self.in_use.remove(driver)
                if driver in self.available:
                    self.available.remove(driver)

                try:
                    driver.quit()
                    print(f"[INFO] Driver closed")
                except Exception as e:
                    print(f"[WARN] Error closing driver: {e}")

                new_driver = self._setup_driver(self._headless_mode)
                new_driver.state = "idle"
                self._attach_web_monitor(new_driver)
                self.in_use.append(new_driver)

                print(f"[INFO] Replaced driver {id(driver)} with {id(new_driver)}")
                return new_driver

        except Exception as e:
            print(f"[ERROR] Error in close_and_refill: {e}")
            traceback.print_exc()
            return driver

    def request_stop(self):
        """
        Flag every driver in the pool as being intentionally stopped.
        """
        self.stop_requested.set()

        with self.lock:
            for driver in self.available + self.in_use:
                try:
                    driver.stop_requested = True
                    driver.state = "stopping"
                except Exception:
                    pass

    def clear_stop_request(self):
        """
        Called before starting a new batch.
        """
        self.stop_requested.clear()

        with self.lock:
            for driver in self.available + self.in_use:
                try:
                    driver.stop_requested = False
                    if driver.state == "stopping":
                        driver.state = "idle"
                except Exception:
                    pass

    def is_stop_requested(self, driver):
        return (
            self.stop_requested.is_set() or
            getattr(driver, "stop_requested", False)
        )
    def reset_vpn_pool(self, driver, download_wait_timeout=60, follower_wait_timeout=300):
        """
        Thread-safe VPN reset with leadership election and debouncing.
        Only ONE reset happens per cooldown period, regardless of how many drivers request it.
        """
        import inspect
        try:
            caller = inspect.stack()[1]
            print(f"🚨 reset_vpn_pool CALLED FROM: {caller.filename} line {caller.lineno} in {caller.function}")
        except Exception as e:
            print(f"🚨 reset_vpn_pool CALLED (could not determine caller: {e})")

        if not hasattr(self, "_reset_vpn_pool_counter"):
            self._reset_vpn_pool_counter = 0
        self._reset_vpn_pool_counter += 1
        
        log_dir = getattr(driver, "files_dir", "logs")
        os.makedirs(log_dir, exist_ok=True)
        _snoop_log = os.path.join(log_dir, f"snoop_reset_vpn_pool_{self._reset_vpn_pool_counter}.log")

        with pysnooper.snoop(_snoop_log):
            with self._vpn_cond:
                now = time.time()
                
                # ── DEBOUNCE: If a reset happened recently, skip ──
                if not self._vpn_resetting and (now - self._vpn_last_reset_time) < DEBOUNCE_SECONDS:
                    print(f"⏭️ [{threading.current_thread().name}] Skipping VPN reset — one completed {now - self._vpn_last_reset_time:.1f}s ago")
                    return self._vpn_last_result
                
                # ── If someone is already resetting, wait for them ──
                if self._vpn_resetting:
                    print(f"⏳ [{threading.current_thread().name}] VPN reset already in progress, waiting...")
                    
                    # Wait for the current reset to complete
                    start_wait = time.time()
                    while self._vpn_resetting:
                        if time.time() - start_wait > follower_wait_timeout:
                            print(f"❌ [{threading.current_thread().name}] Timeout waiting for VPN reset")
                            return "timeout"
                        self._vpn_cond.wait(timeout=5)
                    
                    # Reset completed, return the result
                    print(f"✅ [{threading.current_thread().name}] VPN reset completed by another thread")
                    return self._vpn_last_result
                
                # ── NO reset is happening → I become the leader ──
                print(f"👑 [{threading.current_thread().name}] Becoming VPN reset leader")
                self._vpn_resetting = True
                self._vpn_lease_expiry = now + LEASE_DURATION
                
            # ── Execute the reset (outside the lock) ──
            try:
                result = self._do_vpn_reset_work(driver, download_wait_timeout)
            except Exception as e:
                print(f"❌ [{threading.current_thread().name}] VPN reset failed: {e}")
                result = "failed"
            finally:
                # ── Update state and notify waiting threads ──
                with self._vpn_cond:
                    self._vpn_resetting = False
                    self._vpn_last_reset_time = time.time()
                    self._vpn_last_result = result
                    self._vpn_generation += 1
                    self._vpn_cond.notify_all()
                    
                print(f"✅ [{threading.current_thread().name}] VPN reset completed with result: {result}")
                return result

    def _do_vpn_reset_work(self, driver, download_wait_timeout):
        """Execute the actual VPN reset work."""
        start_time = time.time()
        
        # Wait for downloads to complete
        while self.is_any_downloading():
            elapsed = time.time() - start_time
            if elapsed > download_wait_timeout:
                print(f"❌ VPN reset ABORTED after {elapsed:.1f}s - downloads still in progress")
                return "aborted_downloading"
            print(f"⏳ Waiting for downloads to complete... ({elapsed:.1f}s elapsed)")
            time.sleep(2)
        
        # Execute the VPN reset
        try:
            print(f"🔄 [{threading.current_thread().name}] Resetting VPN...")
            self._reset_vpn(wait=True)
            print(f"✅ [{threading.current_thread().name}] VPN reset complete")
            return "success"
        except Exception as e:
            traceback.print_exc()
            print(f"❌ VPN reset raised: {e}")
            return "failed"

    def _retry_vpn_reset(self, driver):
        """Retry VPN reset after waiting."""
        print(f"🔄 Retrying VPN reset for driver {id(driver)}...")
        self.reset_vpn_pool(driver)

    def _check_error_conditions(self, driver):
        try:
            message_box = driver.find_element(By.ID, "message-box") if self._element_exists_id(driver, "message-box") else None
            connection_closed = driver.find_element(By.XPATH, '//*[@id="content"]/label') if self._element_exists_xpath(driver, '//*[@id="content"]/label') else None
            sub_frame_error = self._element_exists_id(driver, "sub-frame-error")
            body = driver.find_element(By.XPATH, '/html/body') if self._element_exists_xpath(driver, '/html/body') else None
            error_occured = driver.find_element(By.XPATH, '//*[@id="main-message"]/div[2]') if self._element_exists_xpath(driver, '//*[@id="main-message"]/div[2]') else None
            
            if body and "an error occurred while processing your request" in body.text.lower():
                self._refresh_url(driver)
                
            # ── CRITICAL SECURITY GUARD ───────────────────────────────────────
            # The background monitor should only release/recycle a driver if it is 
            # sitting unassigned in the `available` list. If a worker thread is 
            # currently using it (`in_use`), do NOT recycle it out from under them!
            # ──────────────────────────────────────────────────────────────────
            is_active_worker = False
            with self.lock:
                if driver in self.in_use:
                    is_active_worker = True

            if message_box and "too many requests" in message_box.text.lower():
                self.vpn_reset_requested.set()
                if not is_active_worker:
                    self.release_driver(driver)
            if connection_closed and "closed" in connection_closed.text.lower():
                self.vpn_reset_requested.set()
                if not is_active_worker:
                    self.release_driver(driver)
            if sub_frame_error:
                self.vpn_reset_requested.set()
                self._refresh_url(driver)
            if self._check_js_popup(driver):
                if not is_active_worker:
                    self.release_driver(driver)
            if error_occured and "occured" in error_occured.text:
                self._request_url(driver, self._nj_login_page)
            if self._element_exists_id(driver, 'botme'):
                self.vpn_reset_requested.set()
                self._refresh_url(driver)
        except (NoSuchWindowException, NewConnectionError, ReadTimeoutError,
                InvalidSessionIdException, ProtocolError,
                MaxRetryError, StaleElementReferenceException):
            pass
        except RemoteDisconnected:
            pass
        except Exception:
            pass
        return False

    def is_locked(self):
        locked = not self.lock.acquire(blocking=False)
        if not locked:
            self.lock.release()
        return locked

    def _monitor_drivers(self):
        while self.monitoring_active:
            try:
                for driver in list(self.available + self.in_use):
                    if not self.monitoring_active:
                        break
                    self._check_error_conditions(driver)
                time.sleep(1)
            except Exception as e:
                traceback.print_exc()
                print(f"❌ Error in monitoring thread: {e}")
                time.sleep(5)

    def get_driver(self):
        wait_cycles = 0
        while True:
            # Respect cancellation / stop requests
            if self.stop_requested.is_set() or (self._get_force_stop and self._get_force_stop()):
                print("[STOP] get_driver aborted: stop requested")
                return None

            with self.lock:
                snapshot = list(self.available)
            healthy = [d for d in snapshot if self._is_driver_healthy(d)]
            with self.lock:
                self.available = [d for d in self.available if d in healthy]
                if self.available:
                    driver = self.available.pop()
                    self.in_use.append(driver)
                    return driver

                # If no available driver, check if we can spin up a driver on-demand
                total_active = len(self.available) + len(self.in_use)
                # Acquire lock to ensure only one thread creates a driver when max_workers is limited
                with self.lock:
                    can_create = total_active < self.max_workers
                    if can_create:
                        try:
                            print(f"[POOL] Spawning on-demand driver ({total_active + 1}/{self.max_workers})...")
                            driver = self._setup_driver(self._headless_mode)
                            driver.state = "idle"
                            self._attach_web_monitor(driver)
                            self.in_use.append(driver)
                            return driver
                        except Exception as e:
                            traceback.print_exc()
                            print(f"[ERROR] Failed to create on-demand driver: {e}")

            wait_cycles += 1
            if wait_cycles % 10 == 0:
                print(f"[WAIT] Waiting for driver... (in_use: {len(self.in_use)}, available: {len(self.available)}, max: {self.max_workers})")
            time.sleep(1)

    @contextmanager
    def borrow_driver(self):
        """
        Context manager to safely borrow a driver from the pool and
        guarantee its release back to the pool, even on errors.
        """
        driver = self.get_driver()
        try:
            yield driver
        finally:
            self.release_driver(driver)

    def _is_driver_healthy(self, driver):
        try:
            driver.current_url
            return True
        except:
            return False

    def release_driver(self, driver):
        try:
            with self.lock:
                if driver not in self.in_use:
                    return  # already released, prevents double-release side effects
                self.in_use.remove(driver)
                if self._is_driver_healthy(driver):
                    try:
                        handles = driver.window_handles
                        if len(handles) > 1:
                            first_handle = handles[0]
                            for handle in handles[1:]:
                                driver.switch_to.window(handle)
                                driver.close()
                            driver.switch_to.window(first_handle)
                    except Exception:
                        pass
                    self.available.append(driver)
                else:
                    print("[WARN] Removing unhealthy driver")
                    try:
                        self._delete_driver(driver)
                        # Only create a replacement if pool is actually short
                        total = len(self.available) + len(self.in_use)
                        if total < self.max_workers:
                            new_driver = self._setup_driver(self._headless_mode)
                            new_driver.state = "idle"
                            self._attach_web_monitor(new_driver)
                            self.available.append(new_driver)
                        else:
                            print("[WARN] Pool already at capacity, skipping refill")
                    except Exception:
                        pass
        except Exception as e:
            print(f"[WARN] Error releasing driver: {e}")
            traceback.print_exc()
            try:
                self._delete_driver(driver)
            except:
                pass

    def is_any_downloading(self):
        """Check if ANY driver is currently downloading."""
        with self.lock:
            for driver in self.in_use:
                state = getattr(driver, "state", "")
                if state and "downloading" in state.lower():
                    # Double-check: look for .crdownload files too
                    files_dir = getattr(driver, "files_dir", None)
                    if files_dir and os.path.exists(files_dir):
                        crdownloads = [f for f in os.listdir(files_dir) if f.endswith('.crdownload')]
                        if crdownloads:
                            print(f"⚠️ Driver {id(driver)} has incomplete downloads: {crdownloads}")
                            return True
                    # Even without .crdownload files, state says downloading
                    return True
        return False