"""
config package
==============
Centralized configuration, county dispatch mappings, and error telemetry.

Usage:
    from config import settings
    # or
    from config.settings import Settings, get_settings
"""

from config.settings import (
    COUNTY_DISPLAY_NAMES,
    AccountCredentials,
    LLMTaskConfig,
    Settings,
    get_settings,
    settings,
)

__all__ = [
    "Settings",
    "settings",
    "get_settings",
    "LLMTaskConfig",
    "AccountCredentials",
    "COUNTY_DISPLAY_NAMES",
]
