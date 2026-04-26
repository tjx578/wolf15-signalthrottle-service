from __future__ import annotations

import re

_FX_PAIR_RE = re.compile(r"^[A-Z]{6}$")


def normalize_symbol(raw: str) -> str:
    s = raw.strip().upper().replace("/", "").replace("_", "").replace("-", "")
    if _FX_PAIR_RE.match(s):
        return s
    return raw.strip().upper()


def to_finnhub_symbol(symbol: str) -> str:
    if ":" in symbol:
        return symbol
    norm = normalize_symbol(symbol)
    if len(norm) == 6 and norm.isalpha():
        return f"OANDA:{norm[:3]}_{norm[3:]}"
    return symbol
