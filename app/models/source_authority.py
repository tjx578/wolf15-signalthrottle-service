from __future__ import annotations

from enum import StrEnum
from typing import Any


class SourceAuthority(StrEnum):
    LEGACY_OBSERVATIONAL = "LEGACY_OBSERVATIONAL"
    OBSERVER_DERIVED = "OBSERVER_DERIVED"
    CANONICAL_WOLF15 = "CANONICAL_WOLF15"
    UNKNOWN = "UNKNOWN"


_LEGACY_ALIASES = {
    "LEGACY_DERIVED_LOG": SourceAuthority.LEGACY_OBSERVATIONAL.value,
}
_CANONICAL_VALUES = frozenset(authority.value for authority in SourceAuthority)


def normalize_source_authority(
    value: Any,
    *,
    default: SourceAuthority = SourceAuthority.UNKNOWN,
) -> str:
    """Return only a source-authority value from the frozen observer contract."""
    if value is None or not str(value).strip():
        return default.value

    normalized = str(value).strip().upper()
    normalized = _LEGACY_ALIASES.get(normalized, normalized)
    if normalized in _CANONICAL_VALUES:
        return normalized
    return SourceAuthority.UNKNOWN.value
