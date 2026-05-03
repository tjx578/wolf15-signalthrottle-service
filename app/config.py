from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "production"
    service_name: str = "wolf15-signalthrottle-service"

    database_url: str = ""
    db_schema: str = "signalthrottle"

    log_timezone: str = "UTC"
    owner_timezone: str = "Asia/Makassar"
    chart_time_offset_hours: int = 3

    signalthrottle_mode: str = "phase1"
    enable_trade_plans: bool = False
    enable_market_context: bool = False

    ohlc_provider: str = "finnhub"
    finnhub_api_key: str | None = None

    webhook_secret: str | None = None

    engine_log_sync_enabled: bool = False
    engine_log_source_url: str | None = None
    engine_log_source_token: str | None = None
    engine_log_source_service: str = "wolf15-engine"
    engine_log_fetch_filter: str | None = None
    engine_log_sync_overlap_seconds: int = 300
    engine_log_sync_interval_seconds: int = 300
    engine_log_sync_timeout_seconds: int = 30
    daily_report_window: str = "utc_day"

    min_radar_minutes: float = 5.0
    min_strong_minutes: float = 14.0
    max_event_gap_seconds: int = 300
    max_continuity_gap_seconds: int = 90
    soft_finalize_seconds: int = 90
    hard_finalize_seconds: int = 300

    dashboard_basic_auth_user: str | None = None
    dashboard_basic_auth_password: str | None = None

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
