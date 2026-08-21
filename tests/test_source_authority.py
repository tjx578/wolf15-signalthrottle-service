from __future__ import annotations

import asyncio

import pytest

from app.dashboard.view_models import build_pressure_observation_view
from app.models.source_authority import SourceAuthority, normalize_source_authority
from app.storage.repositories import SignalRepository


def test_frozen_source_authority_values_are_canonical() -> None:
    assert {authority.value for authority in SourceAuthority} == {
        "LEGACY_OBSERVATIONAL",
        "OBSERVER_DERIVED",
        "CANONICAL_WOLF15",
        "UNKNOWN",
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("LEGACY_DERIVED_LOG", "LEGACY_OBSERVATIONAL"),
        ("legacy_observational", "LEGACY_OBSERVATIONAL"),
        ("OBSERVER_DERIVED", "OBSERVER_DERIVED"),
        ("CANONICAL_WOLF15", "CANONICAL_WOLF15"),
        ("untrusted-client-value", "UNKNOWN"),
        (None, "UNKNOWN"),
    ],
)
def test_source_authority_normalization_is_fail_closed(raw, expected: str) -> None:
    assert normalize_source_authority(raw) == expected


def test_dashboard_serializer_normalizes_legacy_alias() -> None:
    view = build_pressure_observation_view(
        {
            "symbol": "USDJPY",
            "source_authority": "LEGACY_DERIVED_LOG",
        }
    )

    assert view is not None
    assert view["source_authority"] == "LEGACY_OBSERVATIONAL"


def test_repository_projection_emits_only_canonical_legacy_authority(monkeypatch) -> None:
    async def fake_get_block_history(self, symbol=None, limit=50):
        return [
            {
                "id": 1,
                "symbol": "USDJPY",
                "pressure_grade": "B+",
                "source_authority": "LEGACY_DERIVED_LOG",
                "is_active": False,
            }
        ]

    monkeypatch.setattr(SignalRepository, "get_block_history", fake_get_block_history)
    observations = asyncio.run(SignalRepository().get_latest_pressure_observations())

    assert observations[0]["source_authority"] == "LEGACY_OBSERVATIONAL"
    assert "LEGACY_DERIVED_LOG" not in observations[0].values()
