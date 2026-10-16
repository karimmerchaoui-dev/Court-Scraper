"""
network/config.py
=================
Legacy network configuration shim for backward compatibility.
All configurations are now typed and centralized in `config.settings`.
"""

from config.settings import settings

accounts = settings.accounts
miami_accounts = settings.miami_accounts
DEFAULT_KEYWORDS = settings.default_keywords
DEFAULT_UNWANTED = settings.default_unwanted
nordvpn_path = settings.nordvpn_path
NJ_LOGIN_PAGE = settings.nj_login_page
proxy_host = settings.proxy_host
proxy_port = settings.proxy_port
proxy_username = settings.proxy_username
proxy_password = settings.proxy_password

COUNTY_DISPLAY_NAMES = settings.county_display_names