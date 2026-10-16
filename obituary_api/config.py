"""
obituary_api/config.py
======================
Central configuration for Obituary API.
Sourced from the project's structured configuration (config.settings).
"""

from config import settings as app_settings


class Settings:
    # Zyte API (used to fetch rendered HTML)
    ZYTE_API_KEY: str = app_settings.zyte_api_key or ""

    # Mistral AI
    MISTRAL_API_KEY: str = app_settings.mistral_api_key or ""
    MISTRAL_MODEL: str = app_settings.mistral_model

    # Server
    HOST: str = app_settings.obituary_api_host
    PORT: int = app_settings.obituary_api_port

    # Optional simple bearer token to protect the endpoint.
    API_SECRET_KEY: str | None = app_settings.obituary_api_secret_key


settings = Settings()
