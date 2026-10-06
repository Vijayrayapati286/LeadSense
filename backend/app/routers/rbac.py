"""Roles, permissions, and org-scoped user role assignments."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.tenant import require_org_id, require_permission
from app.models import Permission, Role, RolePermission, User, UserRole
from app.schemas.schemas import PermissionResponse, RoleResponse, UserRoleAssignRequest, UserRoleResponse
from app.services.rbac_service import CONTEXT_ORG, SCOPE_CLIENT, SCOPE_PROVIDER, new_id
from app.services.tenant_constants import ORG_TYPE_PROVIDER, ROLE_ADMIN, ROLE_USER

router = APIRouter(prefix="/rbac", tags=["RBAC"])


def _role_response(db: Session, role: Role) -> RoleResponse:
    names = [
        name
        for (name,) in (
            db.query(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id == role.id, RolePermission.context == CONTEXT_ORG)
            .order_by(Permission.name)
            .all()
        )
    ]
    return RoleResponse(
        id=role.id,
        name=role.name,
        role_type=role.role_type,
        scope=role.scope,
        is_system=role.is_system,
        is_invitable=role.is_invitable,
        description=role.description,
        permissions=names,
    )


def _assignment_response(db: Session, row: UserRole) -> UserRoleResponse:
    user = db.query(User).filter(User.id == row.user_id).first()
    return UserRoleResponse(
        id=row.id,
        user_id=row.user_id,
        user_name=user.name if user else None,
        user_email=user.email if user else None,
        role_id=row.role_id,
        role_name=row.role_name or (row.role.name if row.role else ""),
        role_type=row.role_type,
        organization_id=row.organization_id,
        created_at=row.created_at,
    )


@router.get("/roles", response_model=list[RoleResponse])
def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("access:read")),
):
    query = db.query(Role)
    org = getattr(current_user, "organization", None)
    if getattr(org, "org_type", None) != ORG_TYPE_PROVIDER:
        query = query.filter(Role.scope == SCOPE_CLIENT)
    roles = query.order_by(Role.scope, Role.role_type, Role.name).all()
    return [_role_response(db, role) for role in roles]


@router.get("/permissions", response_model=list[PermissionResponse])
def list_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("access:read")),
):
    rows = db.query(Permission).order_by(Permission.category, Permission.name).all()
    org = getattr(current_user, "organization", None)
    if getattr(org, "org_type", None) != ORG_TYPE_PROVIDER:
        rows = [row for row in rows if not row.name.startswith("orgs:")]
    return [
        PermissionResponse(id=row.id, name=row.name, category=row.category, description=row.description)
        for row in rows
    ]


@router.get("/assignments", response_model=list[UserRoleResponse])
def list_assignments(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("access:read")),
):
    org_id = require_org_id(current_user)
    rows = (
        db.query(UserRole)
        .filter(UserRole.organization_id == org_id)
        .order_by(UserRole.created_at.desc())
        .all()
    )
    return [_assignment_response(db, row) for row in rows]


@router.post("/assignments", response_model=UserRoleResponse, status_code=201)
def assign_role(
    data: UserRoleAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("access:manage")),
):
    org_id = require_org_id(current_user)
    user = db.query(User).filter(User.id == data.user_id, User.org_id == org_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    role = db.query(Role).filter(Role.id == data.role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    org = getattr(current_user, "organization", None)
    if role.scope == SCOPE_PROVIDER and getattr(org, "org_type", None) != ORG_TYPE_PROVIDER:
        raise HTTPException(status_code=403, detail="That role is not available in this organization")
    existing = (
        db.query(UserRole)
        .filter(
            UserRole.user_id == user.id,
            UserRole.role_id == role.id,
            UserRole.organization_id == org_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Role already assigned")
    row = UserRole(
        id=new_id("urole"),
        user_id=user.id,
        role_id=role.id,
        organization_id=org_id,
        role_type=role.role_type,
        role_name=role.name,
        assigned_by_user_id=current_user.id,
    )
    db.add(row)
    if role.name == "admin":
        user.role = ROLE_ADMIN
    elif role.name == "user":
        user.role = ROLE_USER
    db.commit()
    db.refresh(row)
    return _assignment_response(db, row)


@router.delete("/assignments/{assignment_id}", response_model=dict)
def remove_assignment(
    assignment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("access:manage")),
):
    org_id = require_org_id(current_user)
    row = (
        db.query(UserRole)
        .filter(UserRole.id == assignment_id, UserRole.organization_id == org_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if row.user_id == current_user.id and (row.role_name or "") == "admin":
        raise HTTPException(status_code=400, detail="You cannot remove your own admin assignment")
    db.delete(row)
    db.commit()
    return {"success": True}
