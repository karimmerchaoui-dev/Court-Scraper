"""
config/settings.py
==================
Structured Configuration with Typed Validation for Court-Scraper.

Features:
- Validated Pydantic BaseSettings loading from `.env` and `settings.json`.
- Fail-fast validation with explicit errors on missing or invalid configuration.
- Full type hinting across all scraper, database, network, and LLM configuration keys.
- Dict-like compatibility (supports `settings['key']`, `settings.get('key')`, `in`).
- Case-insensitive attribute access (supports both `settings.supabase_url` and `settings.SUPABASE_URL`).
- Zero circular imports: cleanly importable anywhere in the application via:
      from config import settings
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("config")

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"
SETTINGS_JSON_PATH = PROJECT_ROOT / "settings.json"

from dotenv import load_dotenv

if ENV_FILE_PATH.exists():
    load_dotenv(ENV_FILE_PATH)
else:
    load_dotenv()


# ══════════════════════════════════════════════════════════════════════════════
# SUBMODELS
# ══════════════════════════════════════════════════════════════════════════════

class LLMTaskConfig(BaseModel):
    """Configuration for a specific LLM analysis task (complaint, judgment, deed, etc.)."""
    service: str = Field(default="groq", description="LLM provider: groq, anthropic, openrouter, gemini")
    api_key: str = Field(default="", description="API key override for this task")
    model: str = Field(default="", description="Model name override for this task")


class AccountCredentials(BaseModel):
    """User login credentials for NJ court portal or county portals."""
    index: int
    user_id: str
    password: str
    type: str = "backup"


# ══════════════════════════════════════════════════════════════════════════════
# DEFAULTS & CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

def _get_default_nj_accounts():
    accounts = []
    for i in range(5):
        user = os.getenv(f"NJ_USER_{i}", "")
        pwd = os.getenv(f"NJ_PASS_{i}", "")
        if user or pwd:
            accounts.append({
                "index": i,
                "user_id": user,
                "password": pwd,
                "type": "main" if i == 1 else "backup"
            })
    return accounts

DEFAULT_NJ_ACCOUNTS = _get_default_nj_accounts()

DEFAULT_MIAMI_ACCOUNTS = [
    {"index": 0, "user_id": os.getenv("MIAMI_CLERK_USER", ""), "password": os.getenv("MIAMI_CLERK_PASS", "")},
]

DEFAULT_SKIP_DEFENDANT_KEYWORDS = [
    "llc", "business", "corporation", "assoc", "trust", "america", "new jersey"
]

DEFAULT_KEYWORDS_LIST = [
    "SETTLEMENT", "cancel", "DISMISSAL", "final judgment", "partial stipulation",
    "Motion to stay", "bankruptcy", "Certification of Mailing", "vacate",
    "Complaint", "Additional Sums"
]

DEFAULT_UNWANTED_LIST = ["proof", "mailing"]

DEFAULT_KEYWORDS_STR = (
    "SETTLEMENT, DISMISSAL,MOTION CORRECTING DEFENDANT NAME,final judgment,judgment,"
    "pluries writ,partial stipulation ,Motion to stay,bankruptcy, Certification of Mailing,"
    "vacate, Complaint, Additional Sums,Summons Issued,notice of sale,notice of dropping party,"
    "emergency motion,MOTION TO SUBSTITUTE PARTY DEFENDANT,Affidavit"
)

DEFAULT_UNWANTED_STR = (
    "Proof of mailing,Return of Sums, Request Of Additional Sums,military,"
    "answer to complaint,foreclosure judgment notice"
)

DEFAULT_LLM_CONFIGS: Dict[str, Dict[str, str]] = {
    "complaint": {"service": "anthropic", "api_key": "", "model": "claude-3-5-haiku-20241022"},
    "judgment": {"service": "groq", "api_key": "", "model": "openai/gpt-oss-120b"},
    "bankruptcy": {"service": "groq", "api_key": "", "model": "openai/gpt-oss-120b"},
    "deed": {"service": "groq", "api_key": "", "model": "llama-3.3-70b-versatile"},
    "obituary": {"service": "groq", "api_key": "", "model": "llama-3.3-70b-versatile"},
    "salesweb": {"service": "anthropic", "api_key": "", "model": "claude-haiku-4-5-20251001"},
}

COUNTY_DISPLAY_NAMES = {
    "jersey": "New Jersey", "nj": "New Jersey",
    "miami": "Miami Dade", "orange": "Orange County",
    "broward": "Broward", "lee": "Lee",
    "palm": "Palm Beach", "duval": "Duval",
    "pinn": "Pinellas", "volusia": "Volusia",
    "brevard": "Brevard", "polk": "Polk",
    "seminole": "Seminole", "pasco": "Pasco",
}


# ══════════════════════════════════════════════════════════════════════════════
# MAIN SETTINGS CLASS
# ══════════════════════════════════════════════════════════════════════════════

class Settings(BaseSettings):
    """
    Centralized, typed, validated application settings.
    Loads secrets and server configs from `.env`, and scraper batch settings from `settings.json`.
    """
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH) if ENV_FILE_PATH.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Database & Backend ────────────────────────────────────────────────────
    supabase_url: str = Field(default="", description="Supabase project URL")
    supabase_key: str = Field(default="", description="Supabase service role or anon key")
    supabase_email: Optional[str] = Field(default="", description="Supabase user email")
    supabase_password: Optional[str] = Field(default="", description="Supabase user password")

    # ── Data Scraping & Enrichment APIs ───────────────────────────────────────
    apify_api_key: str = Field(default="", description="Apify API key for property & people search")
    zyte_api_key: Optional[str] = Field(default="", description="Zyte API key for rendered scraping")

    # ── AI / LLM Configuration ────────────────────────────────────────────────
    openrouter_api_key: Optional[str] = Field(default="", description="OpenRouter API key")
    anthropic_api_key: Optional[str] = Field(default="", description="Anthropic Claude API key")
    groq_api_key: Optional[str] = Field(
        default="",
        description="Groq API key"
    )
    gemini_api_key: Optional[str] = Field(default="", description="Google Gemini API key")
    mistral_api_key: Optional[str] = Field(default="", description="Mistral AI API key")
    mistral_model: str = Field(default="mistral-small-latest", description="Default Mistral model")

    llm_service: str = Field(default="groq", description="Active general LLM service")
    llm_api_key: str = Field(default="", description="Global LLM API key override")
    llm_model: str = Field(default="", description="Global LLM model override")
    llm_configs: Dict[str, LLMTaskConfig] = Field(
        default_factory=lambda: {
            k: LLMTaskConfig(**v) for k, v in DEFAULT_LLM_CONFIGS.items()
        },
        description="Per-task LLM configurations"
    )

    # ── CAPTCHA Solving ───────────────────────────────────────────────────────
    apikey_2captcha: str = Field(
        default="aae95ba642c1c690c18843df6af05b48",
        description="2Captcha API service key"
    )

    # ── Sentry Error Monitoring ───────────────────────────────────────────────
    sentry_dsn: Optional[str] = Field(default=None, description="Sentry DSN endpoint")
    sentry_environment: str = Field(default="production", description="Sentry execution environment")

    # ── Obituary Microservice ─────────────────────────────────────────────────
    obituary_api_host: str = Field(default="0.0.0.0", description="Obituary API host")
    obituary_api_port: int = Field(default=8100, description="Obituary API port")
    obituary_api_secret_key: Optional[str] = Field(default=None, description="Obituary API auth token")

    # ── Deed Search Service ───────────────────────────────────────────────────
    deed_api_key: Optional[str] = Field(default=None, description="Deed API security key")
    deed_output_dir: str = Field(default="deed_output", description="Deed output directory")
    deed_max_workers: int = Field(default=2, description="Deed search concurrency")
    deed_default_headless: bool = Field(default=True, description="Deed search headless browser")

    # ── Celery & Redis Queuing ────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis server URL")
    celery_broker_url: str = Field(default="redis://localhost:6379/0", description="Celery broker URL")
    celery_result_backend: str = Field(default="redis://localhost:6379/1", description="Celery result backend URL")
    use_celery: bool = Field(default=False, description="Whether to route case execution through Celery")

    # ── Runtime Batch & Scraper Controls ──────────────────────────────────────
    input_file: str = Field(default="", description="Path to input Excel sheet")
    output_folder: str = Field(default="", description="Batch output destination folder")
    batch_name: str = Field(default="", description="Current batch label")
    keywords: str = Field(default=DEFAULT_KEYWORDS_STR, description="Target document keyword filters")
    unwanted_keywords: str = Field(default=DEFAULT_UNWANTED_STR, description="Unwanted document keywords")
    headless_mode: bool = Field(default=False, description="Run Selenium headlessly")
    max_workers: int = Field(default=1, description="Number of worker browser threads")
    skip_closed_cases: bool = Field(default=False, description="Skip court cases marked closed")
    skip_business: bool = Field(default=True, description="Skip corporate/LLC defendants")

    # ── Accounts & County Credentials ─────────────────────────────────────────
    accounts: List[Dict[str, Any]] = Field(default_factory=lambda: [dict(a) for a in DEFAULT_NJ_ACCOUNTS])
    miami_accounts: List[Dict[str, Any]] = Field(default_factory=lambda: [dict(a) for a in DEFAULT_MIAMI_ACCOUNTS])
    skip_defendant_keywords: List[str] = Field(default_factory=lambda: list(DEFAULT_SKIP_DEFENDANT_KEYWORDS))
    default_keywords: List[str] = Field(default_factory=lambda: list(DEFAULT_KEYWORDS_LIST))
    default_unwanted: List[str] = Field(default_factory=lambda: list(DEFAULT_UNWANTED_LIST))
    nj_login_page: str = Field(
        default="https://portal.njcourts.gov/webcivilcj/CIVILCaseJacketWeb/pages/civilCaseSearch.faces"
    )

    # ── VPN & Proxy Networking ────────────────────────────────────────────────
    nordvpn_path: str = Field(default=r"C:\Program Files\NordVPN\NordVPN.exe")
    nordvpn_cli_dir: str = Field(default=r"C:\Program Files\NordVPN")
    proxy_host: str = Field(default="ipv4.webshare.io")
    proxy_port: str = Field(default="8001")
    proxy_username: str = Field(default="")
    proxy_password: str = Field(default="")



    # ── Timeouts & Scraping Constants ─────────────────────────────────────────
    deed_download_max_retries: int = 3
    download_timeout: int = 10
    file_detection_timeout: int = 7
    download_start_timeout: int = 10
    row_wait_timeout: int = 15
    name_suffixes: Set[str] = Field(default_factory=lambda: {"jr", "sr", "ii", "iii", "iv"})
    download_extension: str = ".crdownload"
    county_display_names: Dict[str, str] = Field(default_factory=lambda: dict(COUNTY_DISPLAY_NAMES))

    # ── Field Validators ──────────────────────────────────────────────────────

    @field_validator("max_workers", mode="before")
    @classmethod
    def parse_max_workers(cls, v: Any) -> int:
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                return 1
        return int(v) if v is not None else 1

    @field_validator("headless_mode", mode="before")
    @classmethod
    def parse_headless_mode(cls, v: Any) -> bool:
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)

    @field_validator("supabase_url")
    @classmethod
    def validate_supabase_url(cls, v: str) -> str:
        stripped = (v or "").strip()
        if stripped and not (stripped.startswith("http://") or stripped.startswith("https://")):
            raise ValueError(f"Invalid SUPABASE_URL: must start with http:// or https:// (got {v!r})")
        return stripped

    @field_validator("llm_configs", mode="before")
    @classmethod
    def parse_llm_configs(cls, v: Any) -> Dict[str, LLMTaskConfig]:
        if not isinstance(v, dict):
            return {k: LLMTaskConfig(**val) for k, val in DEFAULT_LLM_CONFIGS.items()}
        result: Dict[str, LLMTaskConfig] = {}
        for task, default_val in DEFAULT_LLM_CONFIGS.items():
            if task in v and isinstance(v[task], dict):
                merged = {**default_val, **v[task]}
                result[task] = LLMTaskConfig(**merged)
            elif task in v and isinstance(v[task], LLMTaskConfig):
                result[task] = v[task]
            else:
                result[task] = LLMTaskConfig(**default_val)
        for task, val in v.items():
            if task not in result:
                if isinstance(val, dict):
                    result[task] = LLMTaskConfig(**val)
                elif isinstance(val, LLMTaskConfig):
                    result[task] = val
        return result

    # ── Helper Properties ─────────────────────────────────────────────────────

    @property
    def keywords_list(self) -> List[str]:
        """Parsed list of document keywords."""
        if isinstance(self.keywords, list):
            return self.keywords
        return [k.strip() for k in str(self.keywords).split(",") if k.strip()]

    @property
    def unwanted_keywords_list(self) -> List[str]:
        """Parsed list of unwanted document keywords."""
        if isinstance(self.unwanted_keywords, list):
            return self.unwanted_keywords
        return [k.strip() for k in str(self.unwanted_keywords).split(",") if k.strip()]

    def get_llm_config(self, task_key: str) -> LLMTaskConfig:
        """
        Retrieves the LLM configuration for a specific task.
        Falls back to global llm_service / llm_api_key / llm_model if task settings are empty.
        """
        cfg = self.llm_configs.get(task_key)
        service = (cfg.service if cfg and cfg.service else self.llm_service) or "groq"
        api_key = (cfg.api_key if cfg and cfg.api_key else self.llm_api_key) or ""
        model = (cfg.model if cfg and cfg.model else self.llm_model) or ""
        return LLMTaskConfig(service=service, api_key=api_key, model=model)

    def validate_critical_settings(self, raise_error: bool = False) -> List[str]:
        """
        Validates required secrets and configuration keys.
        Fails fast if raise_error is True.
        """
        issues: List[str] = []
        if not self.supabase_url:
            issues.append("Missing SUPABASE_URL: Database operations will fail.")
        if not self.supabase_key:
            issues.append("Missing SUPABASE_KEY: Supabase client cannot authenticate.")
        if not self.apify_api_key:
            issues.append("Missing APIFY_API_KEY: Zillow & Skip trace scrapers will fail.")

        if issues and raise_error:
            msg = "\n".join(f"- {i}" for i in issues)
            raise ValueError(f"CRITICAL CONFIGURATION ERROR:\n{msg}")
        return issues

    # ── Dict-like Interoperability ────────────────────────────────────────────

    def __getitem__(self, item: str) -> Any:
        lower = item.lower()
        if hasattr(self, lower):
            val = getattr(self, lower)
            if isinstance(val, LLMTaskConfig):
                return val.model_dump()
            return val
        raise KeyError(item)

    def __setitem__(self, key: str, value: Any) -> None:
        lower = key.lower()
        if hasattr(self, lower):
            setattr(self, lower, value)
        else:
            setattr(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except (KeyError, AttributeError):
            return default

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key.lower())

    def __getattr__(self, name: str) -> Any:
        # Support case-insensitive access like settings.SUPABASE_URL
        lower = name.lower()
        if lower in self.__class__.model_fields:
            return getattr(self, lower)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    # ── Serialization & Synchronization ───────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """
        Converts configuration to a plain dictionary formatted for settings.json and web UI.
        """
        return {
            "input_file": self.input_file,
            "output_folder": self.output_folder,
            "batch_name": self.batch_name,
            "keywords": self.keywords,
            "unwanted_keywords": self.unwanted_keywords,
            "headless_mode": self.headless_mode,
            "max_workers": str(self.max_workers),
            "skip_closed_cases": self.skip_closed_cases,
            "skip_business": self.skip_business,
            "use_celery": self.use_celery,
            "llm_service": self.llm_service,
            "llm_api_key": self.llm_api_key,
            "llm_model": self.llm_model,
            "llm_configs": {
                k: (v.model_dump() if hasattr(v, "model_dump") else v)
                for k, v in self.llm_configs.items()
            },
        }

    def update_from_dict(self, data: Dict[str, Any]) -> None:
        """
        Updates settings fields in place from a dictionary (e.g. from Web UI or JSON).
        """
        for k, v in data.items():
            lower_k = k.lower()
            if hasattr(self, lower_k):
                if lower_k == "llm_configs" and isinstance(v, dict):
                    for subk, subv in v.items():
                        if subk in self.llm_configs and isinstance(subv, dict):
                            curr = self.llm_configs[subk].model_dump()
                            curr.update(subv)
                            self.llm_configs[subk] = LLMTaskConfig(**curr)
                        elif isinstance(subv, (dict, LLMTaskConfig)):
                            self.llm_configs[subk] = (
                                subv if isinstance(subv, LLMTaskConfig) else LLMTaskConfig(**subv)
                            )
                elif lower_k == "max_workers":
                    try:
                        self.max_workers = int(v)
                    except (ValueError, TypeError):
                        pass
                elif lower_k == "headless_mode":
                    self.headless_mode = bool(v) if not isinstance(v, str) else v.lower() in ("true", "1")
                else:
                    setattr(self, lower_k, v)

    def load_json(self, path: Optional[Union[str, Path]] = None) -> None:
        """Loads and merges saved values from settings.json."""
        target_path = Path(path) if path else SETTINGS_JSON_PATH
        if target_path.exists():
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if isinstance(saved, dict):
                        self.update_from_dict(saved)
            except Exception as e:
                logger.warning(f"Error loading {target_path}: {e}")

    def save_json(self, path: Optional[Union[str, Path]] = None) -> None:
        """Saves current web/batch settings back to settings.json."""
        target_path = Path(path) if path else SETTINGS_JSON_PATH
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Error saving {target_path}: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# SINGLETON INSTANCE
# ══════════════════════════════════════════════════════════════════════════════

_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """Returns the shared Settings singleton, loading .env and settings.json on first access."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
        # Merge settings.json if present
        _settings_instance.load_json()
    return _settings_instance


# Shared global instance for instant import: `from config import settings`
settings: Settings = get_settings()
