from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from ..config import settings

_dashboard_security = HTTPBasic(auto_error=False)


def dashboard_auth_enabled() -> bool:
    return bool(settings.dashboard_basic_auth_user and settings.dashboard_basic_auth_password)


def require_dashboard_auth(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(_dashboard_security)] = None,
) -> None:
    if not dashboard_auth_enabled():
        return
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    valid_user = secrets.compare_digest(
        credentials.username,
        settings.dashboard_basic_auth_user or "",
    )
    valid_password = secrets.compare_digest(
        credentials.password,
        settings.dashboard_basic_auth_password or "",
    )
    if valid_user and valid_password:
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Basic"},
    )