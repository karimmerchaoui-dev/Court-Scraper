import os
import time
import traceback

from selenium.common.exceptions import (
    InvalidSessionIdException,
    NoSuchWindowException,
    TimeoutException,
)


def get_current_downloads_state(driver):
    """Print the current state of downloads once"""


    # Wait for page to load

    downloads = get_downloads_info(driver)
    if downloads:
        return downloads[0]['fileName'],downloads[0]['status'],downloads[0]['progress'],downloads[0]['url']
    else:
        return None,None,None,None
def get_downloads_info(driver):
    """Extract download information from Chrome's downloads page"""

    # JavaScript to access the downloads manager with debugging
    script = """
        const downloadsManager = document.querySelector('downloads-manager');
        if (!downloadsManager || !downloadsManager.shadowRoot) {
            return {error: 'downloads-manager not found'};
        }

        const downloadItems = downloadsManager.shadowRoot.querySelectorAll('downloads-item');
        const downloads = [];

        downloadItems.forEach((item, index) => {
            const shadow = item.shadowRoot;
            let fileName = 'Unknown';
            let url = 'Unknown';
            let status = 'Unknown';
            let progress = 0;

            // filename
            const fileLink = shadow.querySelector('#file-link, .file-link, a[href]');
            if (fileLink) {
                fileName = fileLink.textContent.trim();
                if (fileLink.href) url = fileLink.href;
            }

            // progress
            const prog = shadow.querySelector('progress');
            if (prog) progress = prog.value || 0;

            // state from element property
            let state = item.__data__?.state || item.state || null;
            if (state) {
                status = state; // e.g. COMPLETE, IN_PROGRESS, PAUSED, CANCELLED
            } else {
                // fallback to visible text
                const statusEl = shadow.querySelector('#status, .status, #description, .description');
                if (statusEl) status = statusEl.textContent.trim();
            }

            // resume button if paused
            let canResume = false;
            if (status.toUpperCase() === 'PAUSED' || status.toUpperCase() === 'INTERRUPTED') {
                const resumeBtn = shadow.querySelector('#resume, [id="resume"]');
                if (resumeBtn && !resumeBtn.disabled) {
                    canResume = true;
                }
            }

            downloads.push({
                fileName,
                url,
                status,
                progress,
                canResume
            });
        });

        return {items: downloads};
        """

    try:
        # Execute the JavaScript and return results
        while True:
            try:
                result = driver.execute_script(script)
                break
            except (NoSuchWindowException,InvalidSessionIdException):
                return []
            except Exception:
                traceback.print_exc()


        # Handle the new return format
        if isinstance(result, dict):
            if 'error' in result:
                return []
            elif 'items' in result:
                return result['items']
            else:
                print("Unexpected result format:", result)
                return []
        else:
            # Fallback for old format
            return result or []
    except Exception as e:
        traceback.print_exc()
        print(f"Error executing script: {e}")
        return []

def open_downloads_tab(driver):

    try:
        # If we're already in downloads tab, nothing to do
        try:
            if driver.current_url.startswith("chrome://downloads/"):
                return
        except Exception:
            pass  # current_url might fail if window closed

        # Check all open windows/tabs safely
        valid_handles = []
        for handle in driver.window_handles:
            try:
                driver.switch_to.window(handle)
                _ = driver.current_url  # test if still alive
                valid_handles.append(handle)
            except Exception:
                continue  # skip closed/dead handles

        # Look for an existing downloads tab among valid handles
        for handle in valid_handles:
            try:
                driver.switch_to.window(handle)
                if driver.current_url.startswith("chrome://downloads/"):
                    return  # Found it
            except Exception:
                traceback.print_exc()
                continue

        # If not found, open a new downloads tab
        while True:
            try:
                driver.execute_script("window.open('');")
                break
            except ConnectionResetError:
                driver.switch_to.window(driver.window_handles[0])
        driver.switch_to.window(driver.window_handles[-1])  # Switch to new tab
        driver.get("chrome://downloads/")
    except NoSuchWindowException:
        pass
    except Exception as e:
        traceback.print_exc()
        print(f"⚠️ Error opening downloads tab: {e}")


def set_download_dir(driver, download_path):
    """
    Ensures that every tab/window in this Chrome session uses the same download directory.
    """
    download_path = download_path.strip().replace("\n", "").replace("\r", "")
    os.makedirs(download_path, exist_ok=True)
    
    driver.command_executor._commands["send_command"] = ("POST", '/session/$sessionId/chromium/send_command')

    params = {
        "cmd": "Page.setDownloadBehavior",
        "params": {
            "behavior": "allow",
            "downloadPath": os.path.normpath(os.path.abspath(download_path)),
        },
    }

    # Apply to all currently open tabs
    for handle in driver.window_handles:
        try:
            driver.switch_to.window(handle)
            driver.execute("send_command", params)
        except TimeoutException:
            pass


def cancel_all_downloads(driver, timeout: int = 100) -> bool:
    """
    Cancels all active and queued downloads in Chrome/Edge browser.

    Args:
        driver: Selenium WebDriver instance
        timeout: Maximum seconds to wait for downloads page to load

    Returns:
        True if successfully cancelled all downloads, False otherwise
    """
    try:

        # Switch to downloads tab
        #open_downloads_tab(driver)


        # Wait for downloads page to load
        time.sleep(1)

        # Cancel all downloads
        cancelled_count = _cancel_downloads_in_shadow_dom(driver, timeout)



        print(f"✅ Cancelled {cancelled_count} download(s)")
        return True

    except Exception as e:
        print(f"❌ Error cancelling downloads: {e}")

        return False


def _cancel_downloads_in_shadow_dom(driver, timeout: int) -> int:
    """
    Navigates Chrome's Shadow DOM to find and cancel all downloads.

    Args:
        driver: Selenium WebDriver instance
        timeout: Maximum seconds to wait

    Returns:
        Number of downloads cancelled
    """
    cancelled_count = 0
    max_attempts = 10

    for attempt in range(max_attempts):
        try:
            # Access shadow DOM hierarchy
            downloads_manager = driver.execute_script(
                "return document.querySelector('downloads-manager')"
            )

            if not downloads_manager:
                break

            # Get shadow root of downloads manager
            shadow_root = driver.execute_script(
                "return arguments[0].shadowRoot", downloads_manager
            )

            # Find all download items
            download_items = driver.execute_script(
                "return arguments[0].querySelectorAll('downloads-item')",
                shadow_root
            )

            if not download_items:
                break

            # Cancel each download
            for item in download_items:
                if _cancel_single_download(driver, item):
                    cancelled_count += 1

            time.sleep(0.3)

        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1} failed: {e}")
            time.sleep(0.5)

    return cancelled_count


def _cancel_single_download(driver, download_item) -> bool:
    """
    Cancels a single download item.

    Args:
        driver: Selenium WebDriver instance
        download_item: Download item element from Shadow DOM

    Returns:
        True if successfully cancelled, False otherwise
    """
    try:
        # Get shadow root of the download item
        item_shadow = driver.execute_script(
            "return arguments[0].shadowRoot", download_item
        )

        # Try to find and click cancel button
        cancel_button = driver.execute_script("""
            const shadowRoot = arguments[0];

            // Try different selectors for cancel button
            let button = shadowRoot.querySelector('#cancel');
            if (!button) button = shadowRoot.querySelector('[id*="cancel"]');
            if (!button) button = shadowRoot.querySelector('cr-icon-button#cancel');
            if (!button) button = shadowRoot.querySelector('[aria-label*="Cancel"]');

            return button;
        """, item_shadow)

        if cancel_button:
            driver.execute_script("arguments[0].click()", cancel_button)
            return True

        # If no cancel button, try remove button (for completed downloads)
        remove_button = driver.execute_script("""
            const shadowRoot = arguments[0];

            let button = shadowRoot.querySelector('#remove');
            if (!button) button = shadowRoot.querySelector('[id*="remove"]');
            if (!button) button = shadowRoot.querySelector('cr-icon-button#remove');

            return button;
        """, item_shadow)

        if remove_button:
            driver.execute_script("arguments[0].click()", remove_button)
            return True

    except Exception as e:
        print(f"⚠️ Could not cancel download: {e}")

    return False