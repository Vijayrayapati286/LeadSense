"""PAT (integration) authentication dependencies."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models import Organization, OrganizationToken
from app.services import organization_token_service as pat_service

security = HTTPBearer(auto_error=False)


@dataclass
class PatPrincipal:
    """Authenticated integration principal (SmartOps / machine client)."""

    token: OrganizationToken
    organization: Organization

    @property
    def organization_id(self) -> str:
        return self.organization.org_id


async def get_pat_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> PatPrincipal:
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    resolved = pat_service.resolve_active_pat(db, credentials.credentials)
    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token, org = resolved
    return PatPrincipal(token=token, organization=org)
