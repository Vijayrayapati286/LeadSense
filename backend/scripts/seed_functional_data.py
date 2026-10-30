"""Seed demo rows for every tenant screen (dashboard, campaigns, ICP, LinkedIn, offerings).

    python -m scripts.seed_functional_data
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.database.connection import SessionLocal, _ensure_linkedin_bulk_schema  # noqa: E402
from app.services.functional_seed import dashboard_seed_totals, ensure_functional_demo_data  # noqa: E402


def main() -> int:
    totals = dashboard_seed_totals()
    _ensure_linkedin_bulk_schema()
    db = SessionLocal()
    try:
        ensure_functional_demo_data(db)
    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}")
        return 1
    finally:
        db.close()

    print("Functional seed complete for Tenant One (admin1@tenant.com / Admin@123).")
    print("Filter dashboard User = Admin 1, Campaign = October Outreach Tracker.")
    print(
        "Expected month-wise through 14 Oct 2026: "
        f"Aug {totals['august_mails']}/0, "
        f"Sep {totals['september_mails']}/{totals['september_icp']}, "
        f"Oct {totals['october_mails']}/{totals['october_icp']}, "
        f"Total {totals['total_mails']}/{totals['total_icp']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
