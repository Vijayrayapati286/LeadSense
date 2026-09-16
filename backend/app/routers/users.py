"""User listing + tenant-admin user management routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.middleware.tenant import require_admin_user, require_org_id
from app.models import User
from app.routers.auth import _user_response
from app.schemas.schemas import (
    MessageResponse,
    UserAdminUpdateRequest,
    UserCreateRequest,
    UserResetPasswordRequest,
    UserResponse,
    UserStatusUpdateRequest,
)
from app.services.auth_service import AuthService
from app.services.tenant_constants import ROLE_ADMIN, STATUS_ACTIVE

router = APIRouter(prefix="/users", tags=["Users"])
auth_service = AuthService()


def _tenant_user_or_404(db: Session, user_id: int, org_id: str) -> User:
    user = db.query(User).filter(User.id == user_id, User.org_id == org_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List users in the caller's tenant only — never cross-tenant."""
    org_id = require_org_id(current_user)
    users = (
        db.query(User)
        .filter(User.org_id == org_id)
        .order_by(User.name)
        .all()
    )
    return [_user_response(u) for u in users]


@router.post("", response_model=UserResponse, status_code=201)
def create_user(
    data: UserCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    """Create a user in the admin's tenant only."""
    org_id = require_org_id(current_user)
    email = str(data.email).strip().lower()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="A user with that email already exists")

    user = User(
        name=data.name.strip(),
        email=email,
        department=data.department.strip() or "Sales",
        org_id=org_id,
        role=data.role,
        status=data.status,
        password_hash=AuthService.hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_response(user)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    data: UserAdminUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    """Edit name / department / role / status for a user in this tenant."""
    org_id = require_org_id(current_user)
    user = _tenant_user_or_404(db, user_id, org_id)

    payload = data.model_dump(exclude_unset=True)
    if "role" in payload and user.id == current_user.id and payload["role"] != ROLE_ADMIN:
        raise HTTPException(status_code=400, detail="You cannot demote your own admin role")
    if "status" in payload and user.id == current_user.id and payload["status"] != STATUS_ACTIVE:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    for field, value in payload.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return _user_response(user)


@router.patch("/{user_id}/status", response_model=UserResponse)
def update_user_status(
    user_id: int,
    data: UserStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    """Activate or deactivate a tenant user."""
    org_id = require_org_id(current_user)
    user = _tenant_user_or_404(db, user_id, org_id)
    if user.id == current_user.id and data.status != STATUS_ACTIVE:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    user.status = data.status
    db.commit()
    db.refresh(user)
    return _user_response(user)


@router.post("/{user_id}/reset-password", response_model=MessageResponse)
def reset_user_password(
    user_id: int,
    data: UserResetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    """Set a new password for a user in this tenant."""
    org_id = require_org_id(current_user)
    user = _tenant_user_or_404(db, user_id, org_id)
    user.password_hash = AuthService.hash_password(data.password)
    db.commit()
    return MessageResponse(message="Password updated successfully")


@router.delete("/{user_id}", response_model=MessageResponse)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    """Delete a user from this tenant. Admins cannot delete themselves."""
    org_id = require_org_id(current_user)
    user = _tenant_user_or_404(db, user_id, org_id)
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    db.delete(user)
    db.commit()
    return MessageResponse(message="User deleted successfully")
