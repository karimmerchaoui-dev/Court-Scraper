import os
import pickle
import random
import sys
import time
import traceback
import zipfile
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout

from requests.exceptions import ConnectionError, ConnectTimeout, ReadTimeout
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    InvalidSessionIdException,
    JavascriptException,
    MoveTargetOutOfBoundsException,
    NoAlertPresentException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from urllib3.exceptions import (
    IncompleteRead,
    MaxRetryError,
    NewConnectionError,
    ProtocolError,
    ReadTimeoutError,
)

from browser.HumanCursorSimulator import HumanCursorSimulator
from download.download_monitor import cancel_all_downloads, set_download_dir

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import re

from browser.OP import extract_info_from_salesweb
from config_ import NJ_LOGIN_PAGE
from utils.map_helpers import autocomplete_address
from utils.zillow_helpers import get_zillow_infos

PROXY_USER = os.getenv("PROXY_USER", "YEaEHtt7ZmhDX6GI")
PROXY_PASS = os.getenv("PROXY_PASS", "j0BhHjYjGeeHwiB9_country-ca,us")
PROXY_PORT = "12323"  # Your assigned port
PROXY_STRING = f"{PROXY_USER}:{PROXY_PASS}@geo.iproyal.com:{PROXY_PORT}"


class TypingFailedException(Exception):
    pass




print(f"browser in BASIC")

import threading


def take_screenshot(driver, label="manual", case_id=None):
    try:
        import base64
        import os
        import time as _time

        from app import case_screenshots, driver_case_map, socketio

        png = driver.get_screenshot_as_png()

        try:
            from io import BytesIO

            from PIL import Image
            img = Image.open(BytesIO(png))
            img.thumbnail((960, 540), Image.Resampling.BILINEAR)
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=60)
            jpg_bytes = buf.getvalue()
        except ImportError:
            jpg_bytes = png

        ts = _time.time()
        b64 = base64.b64encode(jpg_bytes).decode("utf-8")

        screenshots_base = os.path.join(os.path.dirname(__file__), "screenshots")
        safe_case = (case_id or "manual").replace("/", "_").replace("\\", "_").replace(":", "_")
        case_dir = os.path.join(screenshots_base, safe_case)
        os.makedirs(case_dir, exist_ok=True)
        filename = f"{label}_{ts:.3f}.jpg"
        with open(os.path.join(case_dir, filename), "wb") as f:
            f.write(jpg_bytes)

        rel_path = f"{safe_case}/{filename}"
        if case_id:
            case_screenshots.setdefault(case_id, []).append({"file": rel_path, "ts": ts})
            driver_case_map[id(driver)] = case_id
            socketio.emit("case_screenshot", {
                "case_id": case_id, "driver_id": id(driver),
                "image": b64, "file": rel_path, "ts": ts,
            })

        print(f"📸 Screenshot saved: {rel_path}")
        return rel_path

    except Exception as e:
        traceback.print_exc()
        print(f"⚠️ Screenshot failed: {e}")
        return None


def get_thread_number():
    """Get clean thread number from thread name"""
    thread_name = threading.current_thread().name
    match = re.search(r'ThreadPoolExecutor-\d+_(\d+)', thread_name)
    return int(match.group(1)) + 1 if match else 0


def wait_for_page_to_load(driver):
    WebDriverWait(driver, 15).until(lambda d: d.execute_script("return document.readyState") == "complete")


def create_new_tab(driver):
    driver.execute_script("window.open('', '_blank');")
    driver.switch_to.window(driver.window_handles[-1])


def wait_and_click(driver, by, value, timeout=10):
    """Wait for element and click it"""
    while True:
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((by, value))
            )
            driver.execute_script("arguments[0].click();", element)
            return element
        except ElementClickInterceptedException:
            element = driver.find_element(by, value)
            driver.execute_script("arguments[0].scrollIntoView();", element)




def maximize_driver(driver):
    try:
        driver.maximize_window()
    except WebDriverException:
        pass


def close_extra_tabs(driver, keep=2):
    """Close all tabs except the first `keep` tabs."""
    try:
        handles = driver.window_handles
        if len(handles) > keep:

            # Keep the first `keep` tabs, close the rest (from newest to oldest)
            for handle in handles[keep:][::-1]:
                driver.switch_to.window(handle)
                driver.close()

            # Switch back to the first tab (safe)
            driver.switch_to.window(handles[0])
        cancel_all_downloads(driver)

    except Exception as e:
        traceback.print_exc()



def request_url(driver, url, download_dir=None):
    attempt = 0
    while attempt < 10:
        if download_dir:
            set_download_dir(driver, download_dir)
        try:
            driver.get(url)
            break
        except (
        ReadTimeoutError, ConnectTimeout, ProtocolError, ReadTimeout, ConnectionError, MaxRetryError, IncompleteRead,
        ):
            attempt =  attempt + 1
        except WebDriverException:
            attempt =  attempt + 5


def refresh_url(driver):
    while True:
        try:
            driver.refresh()

            break
        except (
        ReadTimeoutError, ConnectTimeout, ProtocolError, ReadTimeout, ConnectionError, MaxRetryError, IncompleteRead):
            pass


import pysnooper


def save_cookies(driver, cookie_file):
    """Save cookies to file"""
    with open(cookie_file, 'wb') as f:
        # Only save cookies for our domain
        cookies = [c for c in driver.get_cookies() if 'njcourts.gov' in c.get('domain', '')]
        pickle.dump(cookies, f)


def is_logged_in(driver, timeout=5):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.ID, 'searchByDocForm:idCivilDocketNum')))
        return True
    except:
        return False


def scroll_randomly(driver):
    """
    Enhanced random scrolling with human-like behavior
    """
    try:
        if not hasattr(driver, 'human_cursor'):
            driver.human_cursor = HumanCursorSimulator(driver)

        # Random scroll actions
        actions = ['scroll_down', 'scroll_up', 'small_scroll', 'reading_position']
        action = random.choice(actions)

        if action == 'scroll_down':
            driver.human_cursor.human_scroll(direction="down", amount=random.randint(2, 5), smooth=True)
        elif action == 'scroll_up':
            driver.human_cursor.human_scroll(direction="up", amount=random.randint(1, 3), smooth=True)
        elif action == 'small_scroll':
            driver.human_cursor.human_scroll(direction="down", amount=1, smooth=True)
        else:  # reading_position
            # Simulate adjusting page position for better reading
            driver.human_cursor.human_scroll(direction="down", amount=random.randint(1, 2), smooth=True)
            time.sleep(random.uniform(0.5, 1.0))

    except Exception as e:
        print(f"Human scrolling failed: {e}")
        # Fallback to JavaScript scrolling
        scroll_amount = random.randint(100, 500)
        driver.execute_script(f"window.scrollBy(0, {scroll_amount})")


def switch_to_window_by_url_prefix(driver, url_prefix, timeout=10):
    """
    Switches to the browser window/tab whose current_url starts with `url_prefix`.

    Args:
        driver: Selenium WebDriver
        url_prefix (str): URL start to match against current_url
        timeout (int): Seconds to wait for the window to appear

    Returns:
        bool: True if switched successfully, False otherwise
    """

    def _match_window(driver):
        for handle in driver.window_handles:
            driver.switch_to.window(handle)
            if driver.current_url.startswith(url_prefix):
                return True
        return False

    try:
        WebDriverWait(driver, timeout).until(_match_window)
        return True
    except Exception:
        return False


def close_download_frame(driver, main_frame):
    while len(driver.window_handles) > 1:
        try:
            switch_to_window_by_url_prefix(driver, "chrome://downloads/", timeout=10)
            driver.close()
            driver.switch_to.window(main_frame)
            break
        except (NewConnectionError, MaxRetryError):
            pass


def click_on_save(driver):
    time.sleep(1)

    print("clicking on save")
    while True:
        try:
            print("clicking on save")
            button = driver.find_element(By.ID, "savePrintButton")
            driver.execute_script("arguments[0].click();", button)
            break
        except TimeoutException:
            WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.ID, "documentDetails:j_id_1k6"))
            ).click()
            print("while loop : clicking")
        except StaleElementReferenceException:
            pass


_human_type_lock = threading.Lock()


def human_type_helper(element, text, typing_speed_range=(0.04, 0.12), max_retries=6):
    while not _human_type_lock.acquire(blocking=False):
        time.sleep(1)
    try:
        # Your existing code
        punctuation_pause_chars = [".", ",", ":", ";", "!", "?"]
        for attempt in range(1, max_retries + 1):
            try:
                element.clear()
            except ElementNotInteractableException:
                return 1
            except StaleElementReferenceException:
                return 1
            typed = ""

            for char in text:
                if random.random() < 0.02 and typed:
                    element.send_keys("\b")
                    time.sleep(random.uniform(0.1, 0.5))
                    last_char = typed[-1]
                    element.send_keys(last_char)
                    time.sleep(random.uniform(*typing_speed_range))

                element.send_keys(char)
                typed += char

                if char in punctuation_pause_chars:
                    time.sleep(random.uniform(0.4, 0.6))
                elif char == " ":
                    time.sleep(random.uniform(0.3, 0.9))
                else:
                    time.sleep(random.uniform(*typing_speed_range))

            current_value = element.get_attribute("value")
            if current_value.strip() == text.strip():
                return
            else:
                print(f"🔁 Retry {attempt}: Typed '{current_value}', expected '{text}'")
                time.sleep(0.5)

        raise TypingFailedException(f"❌ Failed to reliably type text after {max_retries} attempts: '{text}'")

    finally:
        _human_type_lock.release()


def simulate_window_focus(driver):
    """Make it appear the window is focused using JavaScript"""
    try:
        driver.execute_script("""
        window.dispatchEvent(new Event('focus'));
        document.hasFocus = function() { return true; };
        document.activeElement.blur();
        document.activeElement.focus();
        """)
    except JavascriptException:
        pass
    time.sleep(random.uniform(0.1, 1))


def simulate_tab_switch(driver):
    try:
        driver.execute_script("""
        document.dispatchEvent(new Event('visibilitychange'));
        document.hidden = false;
        document.visibilityState = 'visible';
        window.dispatchEvent(new Event('focus'));
        """)
    except (NewConnectionError, MaxRetryError):
        pass
    # Add some random typing or clicking after "returning"
    time.sleep(random.uniform(0.3, 1.2))


def human_like_attention(driver):
    """Combined approach to simulate active user attention"""
    # Randomly choose which behaviors to perform
    behaviors = [
        simulate_window_focus,
        simulate_tab_switch,
    ]

    # Perform 1-3 random behaviors
    for _ in range(random.randint(1, 3)):
        random.choice(behaviors)(driver)
        time.sleep(random.uniform(0.2, 1.5))


def human_click(driver, element):
    """Perform a human-like click with safe wandering movements and random click style."""

    """Click with human-like mouse movement"""
    actions = ActionChains(driver)

    # Move to element with some randomness
    actions.move_to_element(element)

    # Add small random offset to make it more natural
    offset_x = random.randint(-5, 5)
    offset_y = random.randint(-5, 5)
    actions.move_by_offset(offset_x, offset_y)

    # Small pause before clicking
    time.sleep(random.uniform(0.05, 0.15))

    actions.click()
    try:
        actions.perform()
    except MoveTargetOutOfBoundsException:
        human_click(driver, element)
        print("MoveTargetOutOfBoundsException")

    # Simulate wandering movements inside the element

    # Final approach to a random point inside the element

    actions.pause(random.uniform(0.5, 6))

    # Randomized interaction type
    action_type = random.choices(
        ["click", "double_click", "click_and_hold"],
        weights=[0.7, 0.2, 0.1],
        k=1
    )[0]

    if action_type == "click":
        actions.click()
    elif action_type == "double_click":
        actions.double_click()
    elif action_type == "click_and_hold":
        actions.click_and_hold()
        actions.pause(random.uniform(0.3, 1.5))
        actions.release()

    actions.perform()

def delete_driver(driver):
    try:
        # driver_path = driver.service.path
        # parent_path = os.path.dirname(driver_path)
        driver.quit()
        time.sleep(0.5)
        # if os.path.exists(driver_path):
        #    os.remove(driver_path)
        print("✅ Driver removed successfully.")

    except Exception as e:
        print(f"⚠️ Failed to clean up driver: {e}")


def load_cookies(driver, cookie_file):
    with open(cookie_file, 'rb') as f:
        cookies = pickle.load(f)
        for cookie in cookies:
            driver.add_cookie(cookie)
    while True:
        try:
            driver.refresh()
            break
        except ReadTimeoutError:
            time.sleep(1)
            pass
    scroll_randomly(driver)





def simulate_human_browsing2(driver):
    urls = [
        "https://www.njcourts.gov/public/find-a-case",
        "https://www.njcourts.gov/public",
        "https://www.njcourts.gov/jurors",
        "https://www.njcourts.gov/courts",
        "https://www.njcourts.gov/",
        "https://www.njcourts.gov/self-help",
        "https://www.njmcdirect.com/",
        "https://portal.njcourts.gov/webe41/MPAWeb/",
        "https://www.njcourts.gov/courts/vicinages/hudson",

    ]
    while True:
        try:
            request_url(driver, random.choice(urls))
            time.sleep(random.uniform(4, 7))
            r = random.randint(0, 4)
            if not (r):

                simulate_human_browsing(driver)
                driver.execute_script("window.history.go(-1)")
            else:
                scroll_randomly(driver)
            break
        except ReadTimeoutError:
            pass
    time.sleep(random.uniform(3, 8))


def element_exists_xpath(driver, xpath):
    time.sleep(0.5)
    try:
        driver.find_element('xpath', xpath)
        return True
    except (NoSuchElementException, InvalidSessionIdException):
        return False


def element_exists_id(driver, id):
    time.sleep(0.5)
    try:
        driver.find_element(By.ID, id)
        return True
    except (NoSuchElementException, WebDriverException):
        return False


def element_exists_css(driver, css):
    time.sleep(0.5)
    try:
        driver.find_element(By.CSS_SELECTOR, css)
        return True
    except (NoSuchElementException, InvalidSessionIdException, StaleElementReferenceException):
        return False


def check_for_files_page(driver, timeout=10):
    WebDriverWait(driver, 15).until(lambda d: d.execute_script("return document.readyState") == "complete")
    if element_exists_id(driver, "civilCaseSearchForm:searchCase"):
        return False
    try:
        table = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.ID, "caseSummaryDiv")))
    except TimeoutException:
        return False
    if table:
        return True
    else:
        return False


def check_error_message(driver, timeout=3):
    try:
        error_element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.ID, "errInfoMsg")))
    except TimeoutException:
        return False
    message = error_element.text
    if message == "System is available. Captcha verification has failed for this session. Please try again in a few minutes.":
        return True
    else:
        return False





def make_sure_tab1_is_selected(driver):
    try:
        elem = driver.find_element(By.XPATH, '//*[@id="tabs"]/ul/li[1]')
        elem_class = elem.get_attribute("class")
        if elem_class.strip() == "ui-state-default ui-corner-top":
            elem.click()
            return True  # clicked
        else:
            return False  # class didn't match
    except NoSuchElementException:
        return False  # element not found


def simulate_human_browsing(driver):
    """
    Enhanced human browsing simulation
    """
    try:
        if not hasattr(driver, 'human_cursor'):
            driver.human_cursor = HumanCursorSimulator(driver)

        # Simulate various human browsing behaviors
        behaviors = []

        # Add random behaviors
        if random.random() < 0.7:
            behaviors.append('read')
        if random.random() < 0.5:
            behaviors.append('scroll')
        if random.random() < 0.3:
            behaviors.append('hover_elements')
        if random.random() < 0.2:
            behaviors.append('check_corners')

        for behavior in behaviors:
            if behavior == 'read':
                driver.human_cursor.simulate_reading_behavior(duration=random.uniform(2.0, 5.0))

            elif behavior == 'scroll':
                scroll_randomly(driver)

            elif behavior == 'hover_elements':
                # Find some elements to hover over
                try:
                    elements = driver.find_elements(By.TAG_NAME, 'a')[:3]  # Get first 3 links
                    for element in elements:
                        if element.is_displayed():
                            driver.human_cursor.human_hover(element, hover_time=random.uniform(0.5, 1.5))
                            break
                except:
                    pass

            elif behavior == 'check_corners':
                # Move cursor to corners like humans sometimes do
                viewport_width, viewport_height = driver.human_cursor.viewport_size
                corners = [
                    (50, 50),  # top-left
                    (viewport_width - 50, 50),  # top-right
                    (viewport_width - 50, viewport_height - 50),  # bottom-right
                ]
                corner = random.choice(corners)

                current_x, current_y = driver.human_cursor.current_position
                offset_x = corner[0] - current_x
                offset_y = corner[1] - current_y

                driver.human_cursor.actions.move_by_offset(offset_x, offset_y)
                driver.human_cursor.actions.perform()
                driver.human_cursor.actions = ActionChains(driver)
                driver.human_cursor.current_position = corner

                time.sleep(random.uniform(0.3, 0.8))

            # Small pause between behaviors
            time.sleep(random.uniform(0.5, 1.5))
    except MoveTargetOutOfBoundsException:
        pass
    except Exception as e:
        traceback.print_exc()
        time.sleep(random.uniform(2, 5))


def force_send_keys(driver, element, text):
    try:
        # First, try normal send_keys
        element.send_keys(text)
        return
    except ElementNotInteractableException:
        pass

    # Try focusing via JS
    driver.execute_script("arguments[0].scrollIntoView(true); arguments[0].focus();", element)
    try:
        element.send_keys(text)
        return
    except ElementNotInteractableException:
        pass

    # Try ActionChains
    try:
        ActionChains(driver).move_to_element(element).click().send_keys(text).perform()
        return
    except Exception:
        pass

    # Final fallback: set value + fire events via JS
    driver.execute_script("""
        let el = arguments[0];
        let txt = arguments[1];
        el.value = txt;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
    """, element, text)


def check_js_popup(driver):
    try:
        alert = driver.switch_to.alert  # Switch to alert if present
        msg = alert.text
        # Dismiss the popup (click OK)
        alert.accept()
        print(f"POP UP: {msg}")
        # If it matches the error you're expecting, restart
        return True
    except NoAlertPresentException:
        # No popup visible
        return False
    except AttributeError:
        pass






def apply_stealth(driver, tz_id="America/New_York", locale="en-US"):
    """
    Minimal, modern stealth patches for Selenium + Chrome.
    Focused on what real Chrome 2024+ actually looks like.
    """

    # ── 1. CDP-level overrides (most reliable, runs before any JS) ──────────
    driver.execute_cdp_cmd("Emulation.setTimezoneOverride", {"timezoneId": tz_id})
    driver.execute_cdp_cmd("Emulation.setLocaleOverride",   {"locale": locale})

    # Realistic screen sizes only — avoid obvious headless defaults
    screen = random.choice([
        {"width": 1920, "height": 1080},
        {"width": 1440, "height": 900},
        {"width": 2560, "height": 1440},
    ])
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
        "width":             screen["width"],
        "height":            screen["height"],
        "deviceScaleFactor": random.choice([1.0, 1.25, 2.0]),
        "mobile":            False,
        "hasTouch":          False,   # Desktop — keep it consistent
    })

    # ── 2. JS patches injected before every page loads ──────────────────────
    stealth_js = f"""
    (() => {{

      // navigator.webdriver → undefined (not false, not missing — undefined)
      Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});

      // navigator.language / languages — match CDP locale
      Object.defineProperty(navigator, 'language',  {{ get: () => '{locale}' }});
      Object.defineProperty(navigator, 'languages', {{ get: () => ['{locale}', 'en'] }});

      // navigator.platform — should match the User-Agent you set
      Object.defineProperty(navigator, 'platform', {{ get: () => 'Win32' }});

      // navigator.hardwareConcurrency — realistic value
      Object.defineProperty(navigator, 'hardwareConcurrency', {{
        get: () => {random.choice([4, 8, 12, 16])}
      }});

      // navigator.deviceMemory — realistic value
      Object.defineProperty(navigator, 'deviceMemory', {{
        get: () => {random.choice([4, 8, 16])}
      }});

      // navigator.maxTouchPoints — 0 for desktop
      Object.defineProperty(navigator, 'maxTouchPoints', {{ get: () => 0 }});

      // Modern Chrome plugins: only PDF viewer + Widevine (accurate for 2024+)
      // DO NOT fake Flash/Java/Silverlight — they don't exist in any real Chrome
      const pdfPlugin = {{ 
        name: 'PDF Viewer', 
        filename: 'internal-pdf-viewer', 
        description: 'Portable Document Format',
        length: 1,
        item: (i) => i === 0 ? mimeEntry : null,
        namedItem: (n) => n === 'application/pdf' ? mimeEntry : null,
      }};
      const mimeEntry = {{
        type: 'application/pdf',
        suffixes: 'pdf',
        description: 'Portable Document Format',
        enabledPlugin: pdfPlugin,
      }};
      const pluginArray = Object.assign([pdfPlugin], {{
        item:      (i) => i === 0 ? pdfPlugin : null,
        namedItem: (n) => n === 'PDF Viewer' ? pdfPlugin : null,
        refresh:   () => {{}},
      }});
      Object.defineProperty(navigator, 'plugins',   {{ get: () => pluginArray }});
      Object.defineProperty(navigator, 'mimeTypes', {{
        get: () => Object.assign([mimeEntry], {{
          item: (i) => i === 0 ? mimeEntry : null,
          namedItem: (n) => n === 'application/pdf' ? mimeEntry : null,
        }})
      }});

      // window.chrome — needs enough properties to pass basic checks
      window.chrome = {{
        app: {{
          isInstalled: false,
          InstallState: {{ DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' }},
          RunningState: {{ CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }},
          getDetails:    () => {{}},
          getIsInstalled: () => false,
          runningState:  () => 'cannot_run',
        }},
        runtime: {{
          OnInstalledReason: {{ CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' }},
          OnRestartRequiredReason: {{ APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' }},
          PlatformArch: {{ ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' }},
          PlatformNaclArch: {{ ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' }},
          PlatformOs: {{ ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' }},
          RequestUpdateCheckStatus: {{ NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' }},
          connect:           () => {{}},
          sendMessage:       () => {{}},
          id:                undefined,
        }},
        csi:       () => ({{ startE: Date.now(), onloadT: Date.now(), pageT: 0, tran: 15 }}),
        loadTimes: () => ({{
          commitLoadTime:   performance.timeOrigin / 1000,
          connectionInfo:   'h2',
          finishDocumentLoadTime: 0,
          finishLoadTime:   0,
          firstPaintAfterLoadTime: 0,
          firstPaintTime:   0,
          navigationType:   'Other',
          npnNegotiatedProtocol: 'h2',
          requestTime:      performance.timeOrigin / 1000,
          startLoadTime:    performance.timeOrigin / 1000,
          wasAlternateProtocolAvailable: false,
          wasFetchedViaSpdy: true,
          wasNpnNegotiated:  true,
        }}),
      }};

      // WebGL — spoof a realistic GPU string
      const _getParameter = WebGLRenderingContext.prototype.getParameter;
      WebGLRenderingContext.prototype.getParameter = function(param) {{
        if (param === 37445) return 'Intel Inc.';                        // UNMASKED_VENDOR_WEBGL
        if (param === 37446) return 'Intel(R) Iris(R) Plus Graphics 640'; // UNMASKED_RENDERER_WEBGL
        return _getParameter.call(this, param);
      }};

      // Permissions API — match real Chrome behaviour
      const _query = navigator.permissions.query.bind(navigator.permissions);
      navigator.permissions.query = (desc) => {{
        if (desc.name === 'notifications') return Promise.resolve({{ state: 'denied',  onchange: null }});
        if (desc.name === 'clipboard-read')  return Promise.resolve({{ state: 'prompt', onchange: null }});
        return _query(desc);
      }};

      // document.hasFocus — should be true when the user "has the tab open"
      const _hasFocus = document.hasFocus.bind(document);
      document.hasFocus = () => true;

      // outerWidth / outerHeight must not be 0 (headless tell)
      if (window.outerWidth  === 0) Object.defineProperty(window, 'outerWidth',  {{ get: () => window.innerWidth  }});
      if (window.outerHeight === 0) Object.defineProperty(window, 'outerHeight', {{ get: () => window.innerHeight + 74 }});

    }})();
    """

    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": stealth_js})




def create_proxy_auth_extension(proxy_host, proxy_port, proxy_username, proxy_password, scheme='http'):
    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        },
        "minimum_chrome_version":"22.0.0"
    }
    """

    background_js = """
    var config = {
            mode: "fixed_servers",
            rules: {
              singleProxy: {
                scheme: "%s",
                host: "%s",
                port: parseInt(%s)
              },
              bypassList: ["localhost"]
            }
          };

    chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});

    function callbackFn(details) {
        return {
            authCredentials: {
                username: "%s",
                password: "%s"
            }
        };
    }

    chrome.webRequest.onAuthRequired.addListener(
                callbackFn,
                {urls: ["<all_urls>"]},
                ['blocking']
    );
    """ % (scheme, proxy_host, proxy_port, proxy_username, proxy_password)

    # Create extension directory
    plugin_path = 'proxy_auth_extension.zip'

    with zipfile.ZipFile(plugin_path, 'w') as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)

    return plugin_path


def navigate_to_url_nj(driver):
    """Fast and reliable navigation without repeatedly checking driver.current_url"""
    if driver.current_url != NJ_LOGIN_PAGE:
        if element_exists_id(driver, 'caseActionTbId2'):
            refresh_url(driver)
        request_url(driver,
                    NJ_LOGIN_PAGE)


def safe_int(value):
    if value is None:
        return None
    try:
        return int(str(value).replace(',', '').replace('$', '').split('.')[0])
    except (ValueError, AttributeError):
        return None


def extract_property_infos(driver, report_cases, case_id):
    # ---- Extract the property Address ----
    with pysnooper.snoop(output=os.path.join(driver.files_dir, "extract_property_infos.log")):
        li_xpath = '//*[@id="tabs"]/ul/li[contains(normalize-space(.), "Properties")]'
        property_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, li_xpath))
        )
        element_id = property_tab.get_attribute('aria-labelledby')
        property_tab.click()
        # Assuming 'elem' is the variable containing the value for 'aria-labelledby'
        property_details = driver.find_element(By.XPATH,
                                            f"//div[@id='tabs']//*[@id[starts-with(., 'tabs-')]][@aria-labelledby='{element_id}']")
        property_details.click()
        a = property_details.find_element(By.ID, 'propertiesAccordion')
        property_info = a.text
        pattern = r"Municipality:(.*?)\n"
        county = property_info.split("County:")[1].split("Municipality")[0].strip()
        address = property_info.split("Address:")[1].split("County")[0].strip()
        match = re.search(pattern, property_info)
        if match:
            city_adress_nj = match.group(1).strip()
            if '-' in city_adress_nj:
                city_adress_nj = city_adress_nj.split('-')[1]
                nj_address = autocomplete_address(f"{address},{city_adress_nj},NJ")
            report_cases[case_id]['Address from NJ Courts'] = nj_address
        if county and address:
            salesweb_data = extract_info_from_salesweb(address, county, 'NJ')
            try:
                if salesweb_data:
                    report_cases[case_id]['found'] = salesweb_data['found']
                    report_cases[case_id]['sales_web_address'] = salesweb_data['Address']
                    report_cases[case_id]['Upset Price'] = salesweb_data['Upset Price']
                    report_cases[case_id]['Upset Amount'] = salesweb_data['Upset Amount']
                    report_cases[case_id]['Approx. Judgment'] = salesweb_data['Approx. Judgment']
                    report_cases[case_id]['Approx. Upset'] = salesweb_data['Approx. Upset']
                    report_cases[case_id]['sales_date'] = salesweb_data['sales_date']
                    price = safe_int(salesweb_data.get('Upset Price'))
                    amount = safe_int(salesweb_data.get('Upset Amount'))
                    judgment = safe_int(salesweb_data.get('Approx. Judgment'))
                    upset = safe_int(salesweb_data.get('Approx. Upset'))
                    candidates = [x for x in [price, amount, judgment, upset] if x is not None]
                    unpaid_balance = max(candidates) if candidates else None
                    if nj_address:
                        zestimate, zillow_status, homeType, city, propertyTypeDimension, is_current_signed_in_agent_responsible,is_auction = get_zillow_infos(nj_address)
                    else:
                        zestimate, zillow_status, homeType, city, propertyTypeDimension, is_current_signed_in_agent_responsible,is_auction = get_zillow_infos(salesweb_data['Address'])
                    if unpaid_balance and zestimate:
                        report_cases[case_id]['Equity'] = zestimate - unpaid_balance
                    if zillow_status:
                        report_cases[case_id]['zillow_status'] = zillow_status
                    if homeType:
                        report_cases[case_id]['home_type'] = zillow_status
                else:
                    print("Property Not Found in SalesWeb")
            except Exception:
                pass



def random_scroll(driver):
    # Small random scroll up/down (pixels)
    pixels = random.randint(-200, 200)
    driver.execute_script(f"window.scrollBy(0, {pixels});")
    time.sleep(random.uniform(0.3, 0.8))


def request_url_with_timeout(driver, url, timeout=30):
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(request_url, driver, url)
        try:
            future.result(timeout=timeout)
        except FuturesTimeout:
            return 1


def _cleanup_windows(driver, main_window):
    """Close all extra windows and return to main window"""
    try:
        # Close all windows except main
        for handle in driver.window_handles:
            if handle != main_window:
                try:
                    driver.switch_to.window(handle)
                    driver.close()
                except Exception:
                    pass

        # Switch back to main window
        driver.switch_to.window(main_window)

    except Exception as e:
        # Try to at least get back to main window
        try:
            driver.switch_to.window(main_window)
        except:
            pass


def close_new_windows(driver, windows_before, main_window):
    """
    Close any new windows/tabs that appeared after an action

    Args:
        driver: Selenium WebDriver instance
        windows_before: List of window handles before the action
        main_window: The main window handle to return to
    """
    try:
        # Get current windows
        windows_after = driver.window_handles

        # Find new windows
        new_windows = [w for w in windows_after if w not in windows_before]

        # Close each new window
        for window in new_windows:
            try:
                driver.switch_to.window(window)
                driver.close()
                print(f"✅ Closed new window: {window}")
            except Exception as e:
                print(f"⚠️ Could not close window {window}: {e}")

        # Switch back to main window
        if main_window in driver.window_handles:
            driver.switch_to.window(main_window)
        else:
            # If main window was closed, switch to first available
            if driver.window_handles:
                driver.switch_to.window(driver.window_handles[0])

    except Exception as e:
        print(f"❌ Error closing new windows: {e}")


def human_type(element, text):
    driver = element._parent
    if not hasattr(driver, 'human_cursor'):
        driver.human_cursor = HumanCursorSimulator(driver)
    field_id = element.get_attribute('id') or ''
    if 'password' in field_id.lower():
        typing_speed = "slow"
    else:
        typing_speed = random.choice(["normal", "fast"])
    driver.human_cursor.human_type(element, text, typing_speed=typing_speed)


def find_by_text(sb, text, parent_xpath=None, tag="*", timeout=10):
    t = text.strip()
    base = (
        f'.//{tag}['
        f'contains(normalize-space(.), "{t}") or '
        f'contains(@value, "{t}") or '
        f'contains(@placeholder, "{t}") or '
        f'contains(@aria-label, "{t}") or '
        f'contains(@title, "{t}") or '
        f'contains(@alt, "{t}")'
        f']'
    )

    full_xpath = f'({parent_xpath})[1]{base}' if parent_xpath else f'/{base}'

    try:
        sb.wait_for_element_visible(By.XPATH, full_xpath, timeout=timeout)
        return sb.find_element(By.XPATH, full_xpath)
    except (TimeoutException, NoSuchElementException):
        scope = f"under '{parent_xpath}'" if parent_xpath else "in page"
        raise NoSuchElementException(
            f"No <{tag}> containing '{text}' found {scope}\nXPath: {full_xpath}"
        )


def find_element_by_text(
        driver,
        text,
        parent_xpath=None,
        tag="*",
        class_name=None,
        first_only=True,
        get_sibling_value=False
):
    lowered = text.lower()

    base = f"{parent_xpath}//{tag}" if parent_xpath else f"//{tag}"

    upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    lower = "abcdefghijklmnopqrstuvwxyz"

    class_filter = f"and contains(@class, '{class_name}')" if class_name else ""
    sibling = "/following-sibling::span[contains(@class,'LabelField')][1]" if get_sibling_value else ""

    xpaths = [
        f"{base}[contains(translate(normalize-space(.), '{upper}', '{lower}'), '{lowered}') {class_filter}]{sibling}",
        f"{base}[contains(translate(normalize-space(text()), '{upper}', '{lower}'), '{lowered}') {class_filter}]{sibling}",
        f"{base}[contains(translate(@value, '{upper}', '{lower}'), '{lowered}') {class_filter}]{sibling}",
        f"{base}[contains(translate(@aria-label, '{upper}', '{lower}'), '{lowered}') {class_filter}]{sibling}",
        f"{base}[contains(translate(@title, '{upper}', '{lower}'), '{lowered}') {class_filter}]{sibling}",
        f"{base}[contains(translate(@placeholder, '{upper}', '{lower}'), '{lowered}') {class_filter}]{sibling}",
    ]

    results = []

    for xpath in xpaths:
        found = driver.find_elements(By.XPATH, xpath)
        if found:
            results.extend(found)
            if first_only:
                return found[0]

    return results if results else None