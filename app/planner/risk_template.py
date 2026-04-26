from __future__ import annotations


def apply_risk_template(
    symbol: str,
    execution_side: str,
    price: float | None,
    support: float | None = None,
    resistance: float | None = None,
) -> dict:
    """Generate entry_zone, invalidation, tp1/tp2/tp3 based on levels.

    This is a simple template — production should use more sophisticated
    level detection and multi-timeframe confirmation.
    """
    if price is None:
        return {}

    # Determine pip factor
    pip = 0.01 if "JPY" in symbol else 0.0001

    if execution_side in ("BUY_CONTINUATION", "BUY_ON_RETEST_OR_RECLAIM_HOLD"):
        entry = price
        sl = support if support else price - 30 * pip
        tp1_val = price + 20 * pip
        tp2_val = price + 40 * pip
        tp3_val = resistance if resistance else price + 60 * pip
    elif execution_side in (
        "SELL_ON_RALLY_OR_CONTINUATION",
        "PROTECT_LONG_OR_SELL_REJECTION",
    ):
        entry = price
        sl = resistance if resistance else price + 30 * pip
        tp1_val = price - 20 * pip
        tp2_val = price - 40 * pip
        tp3_val = support if support else price - 60 * pip
    else:
        return {}

    fmt = ".3f" if "JPY" in symbol else ".5f"

    return {
        "entry_zone": f"{entry:{fmt}}",
        "invalidation": f"{sl:{fmt}}",
        "tp1": f"{tp1_val:{fmt}}",
        "tp2": f"{tp2_val:{fmt}}",
        "tp3": f"{tp3_val:{fmt}}",
    }
