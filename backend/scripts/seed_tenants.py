"""Seed the two UAT/dev tenants + admin users.

Creates (idempotent — safe to re-run):
  Tenant One  → admin1@tenant.com / Admin@123
  Tenant Two  → admin2@tenant.com / Admin@123

Note: org_id values are opaque (org_<hex>), not literal TENANT-001/002.
Those legacy ids are only used to match older rows; new orgs get unique PKs.

Usage (from backend/ with DATABASE_URL pointing at the target env):

    python -m scripts.seed_tenants

Or:

    cd backend && python scripts/seed_tenants.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/seed_tenants.py` from backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.database.connection import SessionLocal  # noqa: E402
from app.models import Organization, User  # noqa: E402
from app.services.seed_service import provision_tenants  # noqa: E402
from app.services.tenant_constants import ADMIN_DEFS, TENANT_DEFS  # noqa: E402


def main() -> int:
    db = SessionLocal()
    try:
        print("Provisioning tenants + admin users…")
        provision_tenants(db)

        print("\nOrganizations:")
        for org in db.query(Organization).order_by(Organization.org_name).all():
            print(
                f"  - {org.org_id}  name={org.org_name!r}  "
                f"type={org.org_type}  status={org.status}"
            )

        print("\nAdmin users:")
        for admin in ADMIN_DEFS:
            user = db.query(User).filter(User.email == admin["email"]).first()
            if not user:
                print(f"  - MISSING {admin['email']}")
                continue
            print(
                f"  - {user.email}  org_id={user.org_id}  "
                f"role={user.role}  status={user.status}"
            )

        expected_names = {t["org_name"] for t in TENANT_DEFS}
        found_names = {
            o.org_name for o in db.query(Organization).all() if o.org_name in expected_names
        }
        if found_names != expected_names:
            missing = expected_names - found_names
            print(f"\nERROR: missing org(s): {sorted(missing)}")
            return 1

        print("\nDone. Log in with admin1@tenant.com or admin2@tenant.com / Admin@123")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
