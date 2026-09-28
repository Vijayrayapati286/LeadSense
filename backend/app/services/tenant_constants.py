"""Fixed multi-tenant constants — exactly two seeded tenants in this deployment.

org_id values are NOT hardcoded here. They are generated as unique opaque
ids like ``org_<hex>`` at provision time (see seed_service).
"""

from __future__ import annotations

ROLE_ADMIN = "ADMIN"
ROLE_USER = "USER"

STATUS_ACTIVE = "ACTIVE"
STATUS_INACTIVE = "INACTIVE"

ORG_TYPE_TENANT = "TENANT"
ORG_TYPE_PROVIDER = "PROVIDER"

PROVIDER_DEF = {
    "org_name": "Feuji",
    "client_name": "Feuji",
    "org_type": ORG_TYPE_PROVIDER,
    "status": STATUS_ACTIVE,
}

PROVIDER_USERS = (
    {
        "email": "provider.admin@feuji.com",
        "name": "Provider Admin",
        "password": "Provider@123",
        "role": ROLE_ADMIN,
        "status": STATUS_ACTIVE,
    },
    {
        "email": "provider.user@feuji.com",
        "name": "Provider User",
        "password": "ProviderUser@123",
        "role": ROLE_USER,
        "status": STATUS_ACTIVE,
    },
)

# Stable logical keys — match orgs by org_name / tenant_key, never by TENANT-00x.
TENANT_DEFS = (
    {
        "tenant_key": "tenant_one",
        "org_name": "Tenant One",
        "org_type": ORG_TYPE_TENANT,
        "status": STATUS_ACTIVE,
        # Legacy predictable ids that should be rotated to org_<random>
        "legacy_org_ids": ("TENANT-001",),
    },
    {
        "tenant_key": "tenant_two",
        "org_name": "Tenant Two",
        "org_type": ORG_TYPE_TENANT,
        "status": STATUS_ACTIVE,
        "legacy_org_ids": ("TENANT-002",),
    },
)

ADMIN_DEFS = (
    {
        "email": "admin1@tenant.com",
        "name": "Admin 1",
        "password": "Admin@123",
        "tenant_key": "tenant_one",
        "role": ROLE_ADMIN,
        "status": STATUS_ACTIVE,
    },
    {
        "email": "admin2@tenant.com",
        "name": "Admin 2",
        "password": "Admin@123",
        "tenant_key": "tenant_two",
        "role": ROLE_ADMIN,
        "status": STATUS_ACTIVE,
    },
)

DEFAULT_TENANT_KEY = "tenant_one"
