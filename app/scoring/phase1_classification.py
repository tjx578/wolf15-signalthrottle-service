from __future__ import annotations

JPY_SYMBOLS = {
    "AUDJPY",
    "CADJPY",
    "CHFJPY",
    "EURJPY",
    "GBPJPY",
    "NZDJPY",
    "USDJPY",
}


def pressure_temperature(density_per_minute: float | int | None) -> str:
    if density_per_minute is None:
        return "UNKNOWN"

    density = float(density_per_minute)
    if density < 1:
        return "LOW_SPARSE"
    if density < 2:
        return "LOW_SUSTAINED"
    if density < 4:
        return "LOW_MODERATE_SUSTAINED"
    if density < 7:
        return "ACTIVE_PRESSURE"
    return "HOT_PRESSURE"


def theme_cluster(symbol: str | None) -> str | None:
    if not symbol:
        return None

    normalized = symbol.upper()
    if normalized in JPY_SYMBOLS:
        return "JPY_BASKET_PRESSURE"
    if normalized == "XAUUSD":
        return "METALS_PRESSURE"
    if "EUR" in normalized:
        return "EUR_CROSS_PRESSURE"
    if "GBP" in normalized:
        return "GBP_CROSS_PRESSURE"
    if "AUD" in normalized:
        return "AUD_CROSS_PRESSURE"
    if "NZD" in normalized:
        return "NZD_CROSS_PRESSURE"
    if "CAD" in normalized:
        return "CAD_CROSS_PRESSURE"
    if "CHF" in normalized:
        return "CHF_CROSS_PRESSURE"
    return "FX_PRESSURE"


def phase1_signal_status(
    *,
    duration_minutes: float | int | None,
    event_count: int | None,
    density_per_minute: float | int | None,
) -> str:
    duration = float(duration_minutes or 0)
    events = int(event_count or 0)
    density = float(density_per_minute or 0)

    if duration >= 5 and events >= 20 and density >= 4:
        return "PRIORITY_SIGNAL"
    if duration >= 20 and events >= 20:
        return "PRIORITY_CONTEXTUAL"
    if duration >= 5 and events >= 5:
        return "SUSTAINED_RADAR"
    return "ARCHIVE"
