from __future__ import annotations

from datetime import datetime, timezone


def determine_finalize_mode(
    last_event_utc: datetime,
    now_utc: datetime | None = None,
    soft_seconds: int = 90,
    hard_seconds: int = 300,
) -> str:
    """Return the finalize mode based on silence duration.

    - ACTIVE: still receiving events (gap < soft_seconds)
    - COOLING: between soft and hard threshold
    - SOFT_FINALIZE: past soft but before hard
    - HARD_FINALIZE: past hard threshold
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    gap = (now_utc - last_event_utc).total_seconds()

    if gap < 30:
        return "ACTIVE"
    if gap < soft_seconds:
        return "COOLING"
    if gap < hard_seconds:
        return "SOFT_FINALIZE"
    return "HARD_FINALIZE"
