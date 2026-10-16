from concurrent.futures import ThreadPoolExecutor

import pysnooper
from twocaptcha import TwoCaptcha
from urllib3.exceptions import MaxRetryError

from config import settings


def _solve_captcha_task(api_key, sitekey, url):
    solver = TwoCaptcha(api_key)
    result = solver.recaptcha(
        sitekey=sitekey,
        url=url
    )
    return result
def _solve_turnstile_task(api_key, sitekey, url):
    solver = TwoCaptcha(api_key)
    return solver.turnstile(sitekey=sitekey, url=url)

def _solve_hcaptcha_task(api_key, sitekey, url):
    solver = TwoCaptcha(api_key)
    return solver.hcaptcha(sitekey=sitekey, url=url)

@pysnooper.snoop()
def captcha_solver(driver,sitekey, url, timeout=10):
    """
    Solve captcha with retries, timeout enforced even if solver hangs.
    """
    api_key = settings.apikey_2captcha
    result=None
    attempt=0
    with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_solve_captcha_task, api_key, sitekey, url)
            while not result and attempt < 3:
                attempt=+1
                try:
                    result = future.result(timeout=timeout)
                    print(f"result: {result}")
                except MaxRetryError:
                    continue
                except Exception:
                    return
            # allow some grace beyond retry_interval
            if result:
                return result.get('code') if isinstance(result, dict) else result
            return result
#
#
def turnstile_solver(driver,sitekey, url, timeout=10):
    """
    Solve captcha with retries, timeout enforced even if solver hangs.
    """
    api_key = settings.apikey_2captcha
    result=None
    attempt=0
    with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_solve_turnstile_task, api_key, sitekey, url)
            while not result and attempt < 3:
                attempt=+1
                try:
                    result = future.result(timeout=timeout)
                    print(f"result: {result}")
                except MaxRetryError:
                    continue
                except Exception:
                    return
            # allow some grace beyond retry_interval
            if result:
                return result.get('code') if isinstance(result, dict) else result
            return result

@pysnooper.snoop()
def hcaptcha_solver(driver, sitekey, url, timeout=180):
    """
    Solve hCaptcha via 2captcha.
    timeout=180 because 2captcha's internal polling is up to 120s —
    we need to wait longer than that for the future to complete.
    """
    api_key = settings.apikey_2captcha
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_solve_hcaptcha_task, api_key, sitekey, url)
        try:
            # Wait the full budget — 2captcha needs up to 120s internally
            result = future.result(timeout=timeout)
            print(f"hcaptcha result: {result}")
            if result:
                return result.get('code') if isinstance(result, dict) else result
        except MaxRetryError as e:
            print(f"hcaptcha MaxRetryError: {e}")
        except Exception as e:
            print(f"hcaptcha error ({type(e).__name__}): {e}")
    return None
#
#




