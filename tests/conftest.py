"""Shared pytest fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure app package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def configured_test_credentials(monkeypatch):
    """Tests opt in to explicit credentials; production defaults stay denied."""
    from app.config import settings

    monkeypatch.setattr(settings, "dashboard_basic_auth_user", "owner")
    monkeypatch.setattr(settings, "dashboard_basic_auth_password", "secret")
    monkeypatch.setattr(settings, "dashboard_basic_auth_role", "owner_admin")
    monkeypatch.setattr(settings, "webhook_secret", "webhook-secret")
