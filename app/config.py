from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "production"
    service_name: str = "wolf15-signalthrottle-service"

    database_url: str = ""
    db_schema: str = "signalthrottle"
    database_pool_min_size: int = 1
    database_pool_max_size: int = 5
    database_pool_timeout_seconds: float = 30.0
    database_pool_reconnect_timeout_seconds: float = 30.0

    log_timezone: str = "UTC"
    owner_timezone: str = "Asia/Makassar"
    chart_time_offset_hours: int = 3

    deployment_environment: str = "production"
    observer_mode: str = "observe_only"
    observer_authority: str = "observational_only"
    phase1_observe_only: bool = True
    signalthrottle_mode: str = "phase1"
    enable_trade_plans: bool = False
    enable_market_context: bool = False
    enable_outcome_worker: bool = False
    enable_legacy_replay: bool = False
    execution_allowed: bool = False

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
    dashboard_basic_auth_role: str = "owner_admin"

    model_config = {"env_file": ".env", "extra": "ignore"}

    @model_validator(mode="after")
    def validate_observer_boundary(self) -> "Settings":
        self.assert_observe_only_runtime()
        return self

    def assert_observe_only_runtime(self) -> None:
        """Reject every configuration that could reactivate Phase 2.

        This service has one production identity: an observational pressure
        service.  Keeping the legacy settings explicit lets startup fail with a
        useful error when an old Railway variable is accidentally left enabled.
        """
        violations: list[str] = []
        if self.database_pool_min_size < 1:
            violations.append("DATABASE_POOL_MIN_SIZE must be at least 1")
        if self.database_pool_max_size < self.database_pool_min_size:
            violations.append(
                "DATABASE_POOL_MAX_SIZE must be greater than or equal to min size"
            )
        if self.database_pool_timeout_seconds <= 0:
            violations.append("DATABASE_POOL_TIMEOUT_SECONDS must be positive")
        if self.database_pool_reconnect_timeout_seconds <= 0:
            violations.append(
                "DATABASE_POOL_RECONNECT_TIMEOUT_SECONDS must be positive"
            )
        if not self.phase1_observe_only:
            violations.append("PHASE1_OBSERVE_ONLY must be true")
        if self.observer_mode.strip().lower() != "observe_only":
            violations.append("OBSERVER_MODE must be observe_only")
        if self.observer_authority.strip().lower() != "observational_only":
            violations.append("OBSERVER_AUTHORITY must be observational_only")
        if self.signalthrottle_mode.strip().lower() != "phase1":
            violations.append("SIGNALTHROTTLE_MODE must be phase1")
        if self.enable_market_context:
            violations.append("ENABLE_MARKET_CONTEXT must be false")
        if self.enable_trade_plans:
            violations.append("ENABLE_TRADE_PLANS must be false")
        if self.enable_outcome_worker:
            violations.append("ENABLE_OUTCOME_WORKER must be false")
        if (
            self.deployment_environment.strip().lower() == "production"
            and self.enable_legacy_replay
        ):
            violations.append("ENABLE_LEGACY_REPLAY must be false in production")
        if self.execution_allowed:
            violations.append("EXECUTION_ALLOWED must be false")
        if self.finnhub_api_key:
            violations.append("FINNHUB_API_KEY must not be configured")

        if violations:
            raise ValueError(
                "Observer containment violation: " + "; ".join(violations)
            )

    def owner_auth_configured(self) -> bool:
        return bool(
            self.dashboard_basic_auth_user
            and self.dashboard_basic_auth_password
            and self.dashboard_basic_auth_role.strip().upper()
            in {"OWNER_VIEWER", "OWNER_OPERATOR", "OWNER_ADMIN"}
        )

    def webhook_auth_configured(self) -> bool:
        return bool(self.webhook_secret)


settings = Settings()
