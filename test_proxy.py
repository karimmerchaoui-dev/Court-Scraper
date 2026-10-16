import os

from dotenv import load_dotenv
from seleniumbase import Driver

load_dotenv()

# Webshare / proxy configuration
proxy_host = os.getenv("PROXY_HOST", "ipv4.webshare.io")
proxy_port = int(os.getenv("PROXY_PORT", 8001))
proxy_username = os.getenv("PROXY_USER", "")
proxy_password = os.getenv("PROXY_PASS", "")
import time

LOCAL_PORT = 8899

"""fwd = subprocess.Popen([sys.executable, "-m", "pproxy",
    "-l", f"http://127.0.0.1:{LOCAL_PORT}",
    "-r", f"http://{proxy_host}:{proxy_port}#{proxy_username}:{proxy_password}"])

"""
driver = Driver(uc=True, incognito=False, proxy=f"127.0.0.1:{LOCAL_PORT}",chromium_arg="--proxy-server=http://host:8001")

driver.get(
    "https://iplocation.io/"
)
time.sleep(100)
print(driver.title, driver.current_url)