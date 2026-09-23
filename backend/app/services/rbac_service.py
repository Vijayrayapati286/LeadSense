"""Seed and query org-scoped RBAC for LeadSense features (no tenants table)."""

from __future__ import annotations

import logging
import secrets

from sqlalchemy.orm import Session

from app.models import Organization, Role, Permission, RolePermission, User, UserRole
from app.services.tenant_constants import ORG_TYPE_PROVIDER, ROLE_ADMIN, ROLE_USER, STATUS_ACTIVE

logger = logging.getLogger(__name__)

ROLE_TYPE_ACCESS = "access"
ROLE_TYPE_FUNCTIONAL = "functional"
SCOPE_PROVIDER = "provider"
SCOPE_CLIENT = "client"
CONTEXT_ORG = "org"

LEGACY_ROLE_TO_NAME = {
    ROLE_ADMIN: "admin",
    ROLE_USER: "user",
}

SYSTEM_ROLES = (
    {
        "name": "owner",
        "role_type": ROLE_TYPE_ACCESS,
        "scope": SCOPE_CLIENT,
        "is_invitable": False,
        "description": "Tenant org admin (the client) — full LeadSense access in this organization only",
    },
    {
        "name": "admin",
        "role_type": ROLE_TYPE_ACCESS,
        "scope": SCOPE_CLIENT,
        "is_invitable": True,
        "description": "Tenant org admin — can invite members and manage this organization",
    },
    {
        "name": "user",
        "role_type": ROLE_TYPE_ACCESS,
        "scope": SCOPE_CLIENT,
        "is_invitable": True,
        "description": "Tenant org member — uses campaigns, ICP, LinkedIn extract, and offerings",
    },
    {
        "name": "manager",
        "role_type": ROLE_TYPE_FUNCTIONAL,
        "scope": SCOPE_CLIENT,
        "is_invitable": False,
        "description": "Legacy functional role — same product access as a tenant user",
    },
    {
        "name": "trainee",
        "role_type": ROLE_TYPE_FUNCTIONAL,
        "scope": SCOPE_CLIENT,
        "is_invitable": False,
        "description": "Legacy functional role — same product access as a tenant user",
    },
    {
        "name": "provider_admin",
        "role_type": ROLE_TYPE_ACCESS,
        "scope": SCOPE_PROVIDER,
        "is_invitable": True,
        "description": "Provider admin — onboard tenant orgs and manage the platform",
    },
)

# Permissions match LeadSense product surfaces, not a generic training/hierarchy catalog.
SYSTEM_PERMISSIONS = (
    ("dashboard:read", "dashboard", "View dashboard and analytics"),
    ("campaigns:read", "campaigns", "View campaigns"),
    ("campaigns:write", "campaigns", "Create and edit campaigns"),
    ("campaigns:send", "campaigns", "Send campaign emails"),
    ("recipients:read", "recipients", "View recipients"),
    ("recipients:write", "recipients", "Add and edit recipients"),
    ("logs:read", "email", "View email logs"),
    ("mailers:read", "email", "View mailer templates"),
    ("mailers:write", "email", "Create and edit mailer templates"),
    ("blacklist:read", "email", "View blacklist"),
    ("blacklist:write", "email", "Manage blacklist"),
    ("icp:read", "icp", "View ICP accounts and contacts"),
    ("icp:write", "icp", "Create and edit ICP records"),
    ("linkedin:read", "linkedin", "View LinkedIn extraction history and reviews"),
    ("linkedin:extract", "linkedin", "Run LinkedIn profile extraction"),
    ("offerings:read", "offerings", "View offerings"),
    ("offerings:write", "offerings", "Create and edit offerings"),
    ("settings:read", "settings", "View organization settings"),
    ("settings:write", "settings", "Update organization settings"),
    ("members:read", "members", "View members in this organization"),
    ("members:invite", "members", "Invite members to this organization"),
    ("members:manage", "members", "Update, deactivate, or remove members"),
    ("access:read", "access", "View roles and permissions"),
    ("access:manage", "access", "Assign roles in this organization"),
    ("orgs:read", "organizations", "View organizations"),
    ("orgs:onboard", "organizations", "Onboard a tenant organization"),
    ("integrations:read", "integrations", "View SmartOps / PAT integrations"),
    ("integrations:manage", "integrations", "Create and revoke PATs"),
)

PRODUCT_PERMS = [
    "dashboard:read",
    "campaigns:read",
    "campaigns:write",
    "campaigns:send",
    "recipients:read",
    "recipients:write",
    "logs:read",
    "mailers:read",
    "mailers:write",
    "blacklist:read",
    "blacklist:write",
    "icp:read",
    "icp:write",
    "linkedin:read",
    "linkedin:extract",
    "offerings:read",
    "offerings:write",
    "settings:read",
]

TENANT_ADMIN_PERMS = [
    *PRODUCT_PERMS,
    "settings:write",
    "members:read",
    "members:invite",
    "members:manage",
    "access:read",
    "access:manage",
    "integrations:read",
    "integrations:manage",
]

OWNER_PERMS = list(TENANT_ADMIN_PERMS)
ADMIN_PERMS = list(TENANT_ADMIN_PERMS)
USER_PERMS = list(PRODUCT_PERMS)
MANAGER_PERMS = list(PRODUCT_PERMS)
TRAINEE_PERMS = list(PRODUCT_PERMS)
PROVIDER_PERMS = [name for name, _, _ in SYSTEM_PERMISSIONS]

ROLE_PERMISSION_MAP = {
    "owner": OWNER_PERMS,
    "admin": ADMIN_PERMS,
    "user": USER_PERMS,
    "manager": MANAGER_PERMS,
    "trainee": TRAINEE_PERMS,
    "provider_admin": PROVIDER_PERMS,
}

_ADMIN_ONLY_PERMS = {
    "settings:write",
    "members:read",
    "members:invite",
    "members:manage",
    "access:read",
    "access:manage",
    "orgs:read",
    "orgs:onboard",
    "integrations:read",
    "integrations:manage",
}


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def _get_or_create_role(db: Session, spec: dict) -> Role:
    row = db.query(Role).filter(Role.name == spec["name"], Role.scope == spec["scope"]).first()
    if row:
        row.role_type = spec["role_type"]
        row.is_invitable = spec["is_invitable"]
        row.description = spec["description"]
        return row
    row = Role(
        id=new_id("role"),
        name=spec["name"],
        role_type=spec["role_type"],
        scope=spec["scope"],
        is_system=True,
        is_invitable=spec["is_invitable"],
        description=spec["description"],
    )
    db.add(row)
    db.flush()
    return row


def _get_or_create_permission(db: Session, name: str, category: str, description: str) -> Permission:
    row = db.query(Permission).filter(Permission.name == name).first()
    if row:
        row.category = category
        row.description = description
        return row
    row = Permission(id=new_id("perm"), name=name, category=category, description=description)
    db.add(row)
    db.flush()
    return row


def _retire_stale_permissions(db: Session) -> None:
    wanted = {name for name, _, _ in SYSTEM_PERMISSIONS}
    stale = db.query(Permission).filter(Permission.name.notin_(wanted)).all()
    for row in stale:
        db.query(RolePermission).filter(RolePermission.permission_id == row.id).delete(
            synchronize_session=False
        )
        db.delete(row)
    if stale:
        logger.info("Retired %s unused permissions from the LeadSense catalog", len(stale))


def _sync_role_permission_grants(db: Session, roles: dict[str, Role], perms: dict[str, Permission]) -> None:
    for role_name, perm_names in ROLE_PERMISSION_MAP.items():
        role = roles[role_name]
        wanted_ids = {perms[name].id for name in perm_names}
        existing = (
            db.query(RolePermission)
            .filter(RolePermission.role_id == role.id, RolePermission.context == CONTEXT_ORG)
            .all()
        )
        have = set()
        for grant in existing:
            if grant.permission_id not in wanted_ids:
                db.delete(grant)
            else:
                have.add(grant.permission_id)
        for perm_name in perm_names:
            permission = perms[perm_name]
            if permission.id in have:
                continue
            db.add(
                RolePermission(
                    role_id=role.id,
                    permission_id=permission.id,
                    context=CONTEXT_ORG,
                )
            )


def provision_rbac(db: Session) -> None:
    """Idempotent: seed LeadSense catalog + backfill user_roles from users.role / org_id."""
    roles = {_spec["name"]: _get_or_create_role(db, _spec) for _spec in SYSTEM_ROLES}
    perms = {
        name: _get_or_create_permission(db, name, category, description)
        for name, category, description in SYSTEM_PERMISSIONS
    }
    db.flush()
    _retire_stale_permissions(db)
    db.flush()
    _sync_role_permission_grants(db, roles, perms)
    db.flush()

    assigned = 0
    for user in db.query(User).filter(User.org_id.isnot(None)).all():
        org = db.query(Organization).filter(Organization.org_id == user.org_id).first()
        if org and org.owner_user_id == user.id and getattr(org, "org_type", None) != ORG_TYPE_PROVIDER:
            mapped = "owner"
        elif org and getattr(org, "org_type", None) == ORG_TYPE_PROVIDER and (user.role or "").upper() == ROLE_ADMIN:
            mapped = "provider_admin"
        else:
            mapped = LEGACY_ROLE_TO_NAME.get((user.role or ROLE_USER).upper(), "user")
        role = roles.get(mapped)
        if not role:
            continue
        exists = (
            db.query(UserRole)
            .filter(
                UserRole.user_id == user.id,
                UserRole.role_id == role.id,
                UserRole.organization_id == user.org_id,
            )
            .first()
        )
        if exists:
            continue
        db.add(
            UserRole(
                id=new_id("urole"),
                user_id=user.id,
                role_id=role.id,
                organization_id=user.org_id,
                role_type=role.role_type,
                role_name=role.name,
            )
        )
        assigned += 1

    db.commit()
    if assigned:
        logger.info("Backfilled %s user_roles from existing users", assigned)


def assign_system_role(db: Session, user: User, role_name: str) -> UserRole | None:
    """Attach a catalog role to a user in their organization (idempotent)."""
    if not getattr(user, "org_id", None):
        return None
    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        return None
    exists = (
        db.query(UserRole)
        .filter(
            UserRole.user_id == user.id,
            UserRole.role_id == role.id,
            UserRole.organization_id == user.org_id,
        )
        .first()
    )
    if exists:
        return exists
    row = UserRole(
        id=new_id("urole"),
        user_id=user.id,
        role_id=role.id,
        organization_id=user.org_id,
        role_type=role.role_type,
        role_name=role.name,
    )
    db.add(row)
    db.flush()
    return row


def user_permissions(db: Session, user: User) -> set[str]:
    if not getattr(user, "org_id", None):
        return set()
    rows = (
        db.query(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .filter(
            UserRole.user_id == user.id,
            UserRole.organization_id == user.org_id,
            RolePermission.context == CONTEXT_ORG,
        )
        .all()
    )
    return {name for (name,) in rows}


def _legacy_fallback_permissions(user: User) -> set[str]:
    org = getattr(user, "organization", None)
    is_admin = (getattr(user, "role", None) or "").upper() == ROLE_ADMIN
    is_provider = is_admin and getattr(org, "org_type", None) == ORG_TYPE_PROVIDER
    if is_provider:
        return set(PROVIDER_PERMS)
    if is_admin:
        return set(TENANT_ADMIN_PERMS)
    return set(USER_PERMS)


def has_permission(db: Session, user: User, permission: str) -> bool:
    if getattr(user, "status", STATUS_ACTIVE) != STATUS_ACTIVE:
        return False
    granted = user_permissions(db, user)
    if not granted:
        granted = _legacy_fallback_permissions(user)
    return permission in granted
