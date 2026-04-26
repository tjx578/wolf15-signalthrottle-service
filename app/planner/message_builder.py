from __future__ import annotations


def build_trade_message(
    symbol: str,
    pressure_grade: str,
    chart_phase: str,
    action: str,
    entry_zone: str | None = None,
) -> str:
    parts = [
        f"{symbol} {pressure_grade} pressure.",
        f"Phase: {chart_phase}.",
        f"Action: {action}.",
    ]
    if entry_zone:
        parts.append(f"Zone: {entry_zone}.")
    return " ".join(parts)
