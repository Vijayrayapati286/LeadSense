"""Tenant isolation helpers — org_id always comes from the authenticated user."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.services.rbac_service import has_permission
from app.services.tenant_constants import ORG_TYPE_PROVIDER, ROLE_ADMIN, STATUS_ACTIVE


def get_user_org_id(user: User) -> str | None:
    return getattr(user, "org_id", None)


def require_org_id(user: User) -> str:
    org_id = get_user_org_id(user)
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not assigned to a tenant organization",
        )
    return org_id


def assert_same_org(resource_org_id: str | None, user: User, *, not_found_detail: str = "Not found") -> None:
    """Hide cross-tenant resources as 404 so org_ids are not enumerable."""
    user_org = get_user_org_id(user)
    if user_org and resource_org_id and resource_org_id != user_org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_detail)
    if user_org and resource_org_id is None:
        # Legacy unscoped rows: deny once the caller is tenant-bound
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_detail)


async def require_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if getattr(current_user, "role", None) != ROLE_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    if getattr(current_user, "status", STATUS_ACTIVE) != STATUS_ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is not active")
    require_org_id(current_user)
    return current_user


def require_permission(permission: str):
    """Require a LeadSense application permission on the caller's organization."""

    async def _inner(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if getattr(current_user, "status", STATUS_ACTIVE) != STATUS_ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is not active",
            )
        require_org_id(current_user)
        if not has_permission(db, current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission}",
            )
        return current_user

    return _inner


def is_provider_admin(user: User) -> bool:
    org = getattr(user, "organization", None)
    return (
        getattr(user, "role", None) == ROLE_ADMIN
        and getattr(user, "status", STATUS_ACTIVE) == STATUS_ACTIVE
        and getattr(org, "org_type", None) == ORG_TYPE_PROVIDER
    )


async def require_provider_admin(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if getattr(current_user, "status", STATUS_ACTIVE) != STATUS_ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is not active")
    require_org_id(current_user)
    if has_permission(db, current_user, "orgs:onboard") or is_provider_admin(current_user):
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only a provider admin can onboard tenant organizations",
    )
