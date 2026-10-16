import os
import random
from http.client import RemoteDisconnected
from urllib.error import ContentTooShortError, URLError

from fake_useragent import UserAgent
from selenium.common.exceptions import SessionNotCreatedException
from seleniumbase import Driver
from seleniumbase.core import browser_launcher

from browser.driver_snoop_web import attach_web_monitor

audit_script = """
                return {
                // Core WebDriver flags
                webdriver: navigator.webdriver,
                
                // Chrome-specific
                chrome: {
                    present: !!window.chrome,
                    runtime: !!(window.chrome && window.chrome.runtime),
                    loadTimes: !!(window.chrome && window.chrome.loadTimes),
                    csi: !!(window.chrome && window.chrome.csi),
                },

                // Navigator properties
                navigator: {
                    platform: navigator.platform,
                    hardwareConcurrency: navigator.hardwareConcurrency,
                    deviceMemory: navigator.deviceMemory,
                    languages: navigator.languages,
                    plugins: navigator.plugins.length,
                    pluginNames: Array.from(navigator.plugins).map(p => p.name),
                    maxTouchPoints: navigator.maxTouchPoints,
                    cookieEnabled: navigator.cookieEnabled,
                    doNotTrack: navigator.doNotTrack,
                    connectionType: navigator.connection ? navigator.connection.effectiveType : 'N/A',
                    vendor: navigator.vendor,
                    userAgent: navigator.userAgent,
                    appVersion: navigator.appVersion,
                },

                // Screen & window
                screen: {
                    width: screen.width,
                    height: screen.height,
                    availWidth: screen.availWidth,
                    availHeight: screen.availHeight,
                    colorDepth: screen.colorDepth,
                    pixelDepth: screen.pixelDepth,
                    outerWidth: window.outerWidth,
                    outerHeight: window.outerHeight,
                    innerWidth: window.innerWidth,
                    innerHeight: window.innerHeight,
                    devicePixelRatio: window.devicePixelRatio,
                },

                // Document state
                document: {
                    hasFocus: document.hasFocus(),
                    hidden: document.hidden,
                    visibilityState: document.visibilityState,
                },

                // WebGL fingerprint
                webgl: (function() {
                    try {
                    const canvas = document.createElement('canvas');
                    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                    if (!gl) return { supported: false };
                    const ext = gl.getExtension('WEBGL_debug_renderer_info');
                    return {
                        supported: true,
                        vendor: ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : 'blocked',
                        renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'blocked',
                        glVendor: gl.getParameter(gl.VENDOR),
                        glRenderer: gl.getParameter(gl.RENDERER),
                        glVersion: gl.getParameter(gl.VERSION),
                        shadingLanguageVersion: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
                    };
                    } catch(e) { return { error: e.message }; }
                })(),

                // Canvas fingerprint (check if getContext works normally)
                canvas: (function() {
                    try {
                    const canvas = document.createElement('canvas');
                    const ctx = canvas.getContext('2d');
                    ctx.fillText('test', 10, 10);
                    return {
                        supported: true,
                        dataUrlLength: canvas.toDataURL().length,  // Consistent length = no noise injection
                    };
                    } catch(e) { return { error: e.message }; }
                })(),

                // AudioContext
                audio: (function() {
                    try {
                    const AudioCtx = window.AudioContext || window.webkitAudioContext;
                    if (!AudioCtx) return { supported: false };
                    const ctx = new AudioCtx();
                    return {
                        supported: true,
                        sampleRate: ctx.sampleRate,
                        state: ctx.state,
                        maxChannelCount: ctx.destination.maxChannelCount,
                    };
                    } catch(e) { return { error: e.message }; }
                })(),

                // Permissions API
                permissions: 'check separately (async)',

                // Timezone
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                timezoneOffset: new Date().getTimezoneOffset(),
                };
                """



import time
import traceback


def _resolve_headless_mode(val) -> bool:
    """Safely extracts a boolean from bool, Tkinter/Shim (with .get()), callable, or string."""
    try:
        if hasattr(val, "get") and callable(val.get):
            return bool(val.get())
        if callable(val):
            return bool(val())
        if isinstance(val, str):
            return val.strip().lower() in ("true", "1", "yes")
        return bool(val)
    except Exception:
        return True


def setup_driver(headless_mode):
    while True:
        try:
            browser_launcher.override_driver_dir(os.getcwd())
            dark = random.choice([True, False])
            incog = random.choice([True, False])
            is_headless = _resolve_headless_mode(headless_mode)
            if is_headless:
                ua = UserAgent()
                random_user_agent = ua.random
                
                print(f"headless {dark} {incog} {random_user_agent}")
                driver = Driver(uc_cdp=True, uc=True, external_pdf=True, headless=True, agent=random_user_agent, dark_mode=dark, incognito=incog)
                attach_web_monitor(driver)
                break
            else:
                ua = UserAgent()
                random_user_agent = ua.random
                
                print(f"headed {dark} {incog} {random_user_agent}")
                driver = Driver(uc_cdp=True, uc=True, external_pdf=True, agent=random_user_agent, dark_mode=dark, incognito=incog)
                attach_web_monitor(driver)
                break

        except (ContentTooShortError, URLError, ConnectionError, RemoteDisconnected, SessionNotCreatedException) as e:
            print(f"[WARN] Retrying driver creation after error: {e}")
            time.sleep(1)
        except Exception as e:
            print(f"[ERROR] Unexpected error in setup_driver: {e}")
            traceback.print_exc()
            time.sleep(2)
    return driver


import inspect

VPN_RESET_COUNTIES = {'osceola'}

def reset_and_retry(target_func, driver, driver_pool):
    try:
        driver_pool.release_driver(driver)
    except Exception:
        pass

    county_name = inspect.currentframe().f_back.f_locals.get('county_name', '')
    if county_name.lower() in VPN_RESET_COUNTIES:
        driver_pool.reset_vpn_pool(driver)

    # Don't recurse. Just put the case back in the queue.
    caller_locals = inspect.currentframe().f_back.f_locals
    case_id = caller_locals.get('case_id')
    config = caller_locals.get('config')
    files_dir = caller_locals.get('files_dir')
    cached_matching_rows = caller_locals.get('cached_matching_rows')

    if case_id and config:
        case_queue.put_resubmit(case_id, config, files_dir, cached_matching_rows)