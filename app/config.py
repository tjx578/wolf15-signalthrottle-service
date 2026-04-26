from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "production"
    service_name: str = "wolf15-signalthrottle-service"

    database_url: str = ""

    log_timezone: str = "UTC"
    owner_timezone: str = "Asia/Makassar"
    chart_time_offset_hours: int = 3

    finnhub_api_key: str | None = None
    ohlc_provider: str = "finnhub"

    webhook_secret: str | None = None

    min_radar_minutes: float = 5.0
    min_strong_minutes: float = 14.0
    max_event_gap_seconds: int = 300
    soft_finalize_seconds: int = 90
    hard_finalize_seconds: int = 300

    dashboard_basic_auth_user: str | None = None
    dashboard_basic_auth_password: str | None = None

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
