"""
config_.py
==========
Legacy configuration shim for backward compatibility.
All configurations are now typed and centralized in `config.settings`.
"""

from config.settings import settings

# Export all legacy variables directly from typed settings
accounts = settings.accounts
SKIP_DEFENDANT_KEYWORDS = settings.skip_defendant_keywords
miami_accounts = settings.miami_accounts
DEFAULT_KEYWORDS = settings.default_keywords
DEFAULT_UNWANTED = settings.default_unwanted
nordvpn_path = settings.nordvpn_path
nordvpn_cli_dir = settings.nordvpn_cli_dir
NJ_LOGIN_PAGE = settings.nj_login_page
proxy_host = settings.proxy_host
proxy_port = settings.proxy_port
proxy_username = settings.proxy_username
proxy_password = settings.proxy_password


__all__ = [
    "accounts",
    "SKIP_DEFENDANT_KEYWORDS",
    "miami_accounts",
    "DEFAULT_KEYWORDS",
    "DEFAULT_UNWANTED",
    "nordvpn_path",
    "nordvpn_cli_dir",
    "NJ_LOGIN_PAGE",
    "proxy_host",
    "proxy_port",
    "proxy_username",
    "proxy_password",
    "settings",
]
