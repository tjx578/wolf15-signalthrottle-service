from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from ..config import settings

_dashboard_security = HTTPBasic(auto_error=False)


@dataclass(frozen=True)
class OwnerPrincipal:
    username: str
    role: str


def dashboard_auth_enabled() -> bool:
    return settings.owner_auth_configured()


def require_dashboard_auth(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(_dashboard_security)] = None,
) -> OwnerPrincipal:
    if not dashboard_auth_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Owner authentication is not configured",
        )
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
        return OwnerPrincipal(
            username=credentials.username,
            role=settings.dashboard_basic_auth_role.strip().upper(),
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Basic"},
    )


def require_owner_operator(
    principal: Annotated[OwnerPrincipal, Depends(require_dashboard_auth)],
) -> str:
    if principal.role not in {"OWNER_OPERATOR", "OWNER_ADMIN"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner operator role required",
        )
    return principal.username
