"""Seed LeadSense offerings with the exact SmartOps → LeadSense sync payload shape.

Mirrors what pitch-perfect-connector-gateway push_offering / LeadSense
upsert_from_smartops stores:

  organization_id, smartops_offering_id, name, description, content,
  doc_count, docs[{doc_id, file_name, file_format, s3_key, content, created_at}],
  created_at

Also attaches email_template (Introduction Outreach) derived from offering
content so Campaign → Offering Email can load it for testing.

Usage (from backend/, DATABASE_URL pointing at target env):

    python -m scripts.seed_smartops_offerings
    python -m scripts.seed_smartops_offerings --org-id org_xxx --user-email you@feuji.com

Idempotent on smartops_offering_id + organization_id.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.database.connection import SessionLocal, init_db  # noqa: E402
from app.models import Organization, User  # noqa: E402
from app.offerings.sync_service import upsert_from_smartops  # noqa: E402


# Exact sync-shaped payloads (same keys SmartOps POSTs to /api/offerings).
SEED_OFFERINGS: list[dict] = [
    {
        "smartops_offering_id": "off_SEED_SMARTOPS_WEALTH_HNI_001",
        "name": "SmartOps Wealth Advisory Pack",
        "description": (
            "Private-wealth outreach pack for HNI / UHNI prospects — "
            "fiduciary positioning, second-opinion reviews, and portfolio discovery."
        ),
        "created_at": "2026-10-06T06:00:00Z",
        "docs": [
            {
                "doc_id": "odoc_SEED_WEALTH_PITCH_001",
                "file_name": "wealth_advisory_pitch.pdf",
                "file_format": "pdf",
                "s3_key": "offerings/seed/wealth_advisory_pitch.pdf",
                "content": (
                    "SmartOps Wealth Advisory helps private wealth advisors run discovery, "
                    "practice competitor-comparison calls, and coach live conversations. "
                    "Key modules: Ask (tenant KB), Practice (AI buyers), Live Call Copilot, "
                    "and Call Memory for repeat-client context."
                ),
                "created_at": "2026-10-06T06:05:00Z",
            },
            {
                "doc_id": "odoc_SEED_WEALTH_COMPETITIVE_001",
                "file_name": "WM13_Competitive_Wirehouse_vs_RIA.pdf",
                "file_format": "pdf",
                "s3_key": "offerings/seed/WM13_Competitive_Wirehouse_vs_RIA.pdf",
                "content": (
                    "Competitive positioning: never attack the incumbent advisor. "
                    "Ask about fiduciary status, total fees, and proactivity. "
                    "Frame a second opinion as validation, not competition."
                ),
                "created_at": "2026-10-06T06:06:00Z",
            },
        ],
    },
    {
        "smartops_offering_id": "off_SEED_SMARTOPS_CLARITY_RCM_002",
        "name": "AetherCare Clarity RCM Suite",
        "description": (
            "Healthcare RCM offering — prior auth, denials IQ, and A/R command "
            "for hospital systems and ambulatory groups."
        ),
        "created_at": "2026-10-06T07:00:00Z",
        "docs": [
            {
                "doc_id": "odoc_SEED_CLARITY_OVERVIEW_001",
                "file_name": "clarity_rcm_overview.docx",
                "file_format": "docx",
                "s3_key": "offerings/seed/clarity_rcm_overview.docx",
                "content": (
                    "AetherCare Clarity reduces prior-auth backlog and denial rates. "
                    "Modules: Clarity PriorAuth, Denials IQ, A/R Command, PayerConnect. "
                    "Typical buyers: VP Revenue Cycle, CFO, CMIO."
                ),
                "created_at": "2026-10-06T07:05:00Z",
            },
            {
                "doc_id": "odoc_SEED_CLARITY_ROI_001",
                "file_name": "clarity_roi_one_pager.txt",
                "file_format": "txt",
                "s3_key": "offerings/seed/clarity_roi_one_pager.txt",
                "content": (
                    "ROI proof points: 12% YoY denial reduction target, "
                    "4–6 day prior-auth cycle compression, overtime reduction in RCM teams."
                ),
                "created_at": "2026-10-06T07:06:00Z",
            },
        ],
    },
]


def _combined_content(description: str, docs: list[dict]) -> str:
    """Same combine rule as SmartOps connector push_offering."""
    parts: list[str] = []
    desc = (description or "").strip()
    if desc:
        parts.append(desc)
    for item in docs or []:
        body = str(item.get("content") or "").strip()
        if not body:
            continue
        name = str(item.get("file_name") or "document").strip() or "document"
        parts.append(f"## {name}\n{body}")
    text = "\n\n".join(parts)
    return text[:200_000] if len(text) > 200_000 else text


def _intro_email_template(name: str, content: str) -> dict:
    """Optional email_template (not sent by SmartOps today) for campaign Offering Email tests."""
    blurb = " ".join((content or name).split())
    if len(blurb) > 320:
        blurb = blurb[:319].rsplit(" ", 1)[0] + "…"
    return {
        "name": "Introduction Outreach",
        "subject": f"Quick introduction — {{{{Company}}}} & {name}",
        "body": (
            f"Hello {{{{Name}}}},\n\n"
            f"I came across {{{{Company}}}} and thought you might be interested in {name}.\n\n"
            f"{blurb}\n\n"
            f"As {{{{Designation}}}}, would you be open to a brief chat?"
        ),
        "source": "smartops_seed",
        "source_filename": None,
        "uploaded_at": "2026-10-06T08:00:00Z",
    }


def _resolve_org(db, org_id: str | None) -> Organization:
    if org_id:
        org = db.query(Organization).filter(Organization.org_id == org_id).first()
        if not org:
            raise SystemExit(f"Organization not found: {org_id}")
        return org
    org = db.query(Organization).order_by(Organization.created_at.asc()).first()
    if not org:
        raise SystemExit(
            "No organizations found. Run: python -m scripts.seed_tenants"
        )
    return org


def _resolve_user(db, org: Organization, email: str | None) -> User | None:
    if email:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise SystemExit(f"User not found: {email}")
        return user
    if getattr(org, "owner_user_id", None):
        return db.query(User).filter(User.id == org.owner_user_id).first()
    return (
        db.query(User)
        .filter(User.org_id == org.org_id)
        .order_by(User.id.asc())
        .first()
    )


def _payload(org_id: str, spec: dict) -> dict:
    docs = list(spec["docs"])
    description = spec["description"]
    combined = _combined_content(description, docs)
    return {
        "organization_id": org_id,
        "smartops_offering_id": spec["smartops_offering_id"],
        "name": spec["name"],
        "description": description,
        "content": combined,
        "doc_count": len(docs),
        "docs": docs,
        "created_at": spec["created_at"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed SmartOps-shaped offering rows")
    parser.add_argument("--org-id", default=None, help="LeadSense organization_id (org_…)")
    parser.add_argument(
        "--user-email",
        default=None,
        help="Owner user email (defaults to org owner / first org user)",
    )
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="Call init_db() before seeding (local empty Postgres)",
    )
    args = parser.parse_args()

    if args.init_db:
        print("Initializing database schema…")
        init_db()

    db = SessionLocal()
    try:
        org = _resolve_org(db, args.org_id)
        user = _resolve_user(db, org, args.user_email)
        owner_id = getattr(user, "id", None) if user else None

        print(f"Org:  {org.org_id}  name={org.org_name!r}")
        print(f"User: {getattr(user, 'email', None)!r}  id={owner_id}")
        print()

        for spec in SEED_OFFERINGS:
            payload = _payload(org.org_id, spec)
            row, created = upsert_from_smartops(
                db,
                organization_id=org.org_id,
                data=payload,
                owner_user_id=owner_id,
            )
            # Campaign Offering Email path reads email_template; SmartOps sync
            # does not send it today — attach a seed template from content.
            if not row.email_template:
                row.email_template = _intro_email_template(row.name, row.content or "")
            if owner_id and not row.user_id:
                row.user_id = owner_id
            db.commit()
            db.refresh(row)
            action = "CREATED" if created else "UPDATED"
            print(
                f"  [{action}] id={row.id} offering_id={row.offering_id} "
                f"smartops={row.smartops_offering_id} docs={row.doc_count} "
                f"content_len={len(row.content or '')}"
            )

        print("\nDone. In Campaign create:")
        print("  1) Campaign source = offering")
        print("  2) Pick 'SmartOps Wealth Advisory Pack' or 'AetherCare Clarity RCM Suite'")
        print("  3) Template → Offering Email → Introduction / Product Demo / Follow-up")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
