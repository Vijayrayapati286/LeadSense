"""Idempotent demo data for every tenant screen, including dashboard totals.

Safe to re-run. Skips SQLite test databases. Marker campaign:
CMP-FUNC-SEED-2026.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.icp.models import ICP_STATUS_VERIFIED, SOURCE_LINKEDIN_BULK, SOURCE_MANUAL, IcpRecordRow
from app.linkedin.bulk_models import (
    ITEM_FINAL_FAILED,
    ITEM_SUCCESS,
    JOB_DONE,
    PHASE_REVIEW,
    BulkExtractJobRow,
    BulkJobItemRow,
)
from app.models import (
    Campaign,
    CampaignRecipient,
    CampaignSequenceStage,
    EmailLog,
    EmailVerification,
    Invite,
    Mailer,
    Recipient,
    RecipientGroup,
    RecipientGroupMember,
    RecipientTag,
    SuppressionEntry,
    Tag,
    Template,
    User,
    UserNotification,
)
from app.offerings.sync_service import upsert_from_smartops
from app.profile_extractor.models import ProfileExtractJob, ProfileExtractResult
from app.services.seed_service import get_default_tenant_org_id, resolve_org_id_by_tenant_key
from app.utils.helpers import utc_now

logger = logging.getLogger(__name__)

FUNC_CAMPAIGN_ID = "CMP-FUNC-SEED-2026"
FUNC_CAMPAIGN_T2_ID = "CMP-FUNC-SEED-T2"
FUNC_LINKEDIN_JOB_ID = "seed-linkedin-job-t1-01"
FUNC_PROFILE_JOB_ID = "seed-profile-job-t1-01"
LEGACY_DUMMY_CAMPAIGN_IDS = (
    "CMP-2024001",
    "CMP-2024002",
    "CMP-2024003",
    "CMP-2024004",
    "CMP-2024005",
)

# Spreadsheet totals (14 Oct 2026 snapshot).
AUG_MAILS = 2491
SEP_MAILS = 2327
SEP_ICP = 4618
OCTOBER_DAYS = {
    "2026-10-05": (214, 0),
    "2026-10-06": (142, 0),
    "2026-10-07": (326, 0),
    "2026-10-08": (347, 0),
    "2026-10-09": (1055, 0),
    "2026-10-12": (742, 50),
    "2026-10-13": (829, 360),
    "2026-10-14": (922, 381),
}

COMPANIES = (
    ("Acme Corp", "Technology"),
    ("TechCorp", "Software"),
    ("Global Inc", "Finance"),
    ("StartupCo", "SaaS"),
    ("Enterprise Ltd", "Manufacturing"),
    ("InnovateIO", "Marketing"),
    ("FinTech Pro", "Finance"),
    ("HealthTech", "Healthcare"),
)


def dashboard_seed_totals() -> dict[str, int]:
    oct_mails = sum(sent for sent, _icp in OCTOBER_DAYS.values())
    oct_icp = sum(icp for _sent, icp in OCTOBER_DAYS.values())
    return {
        "august_mails": AUG_MAILS,
        "september_mails": SEP_MAILS,
        "september_icp": SEP_ICP,
        "october_mails": oct_mails,
        "october_icp": oct_icp,
        "total_mails": AUG_MAILS + SEP_MAILS + oct_mails,
        "total_icp": SEP_ICP + oct_icp,
    }


def _at(day: str, hour: int = 12) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour:02d}:00:00").replace(tzinfo=timezone.utc)


def _is_sqlite(db: Session) -> bool:
    return db.get_bind().dialect.name == "sqlite"


def _chunked_insert(db: Session, model, rows: list[dict], size: int = 1000) -> None:
    for start in range(0, len(rows), size):
        db.bulk_insert_mappings(model, rows[start:start + size])


def _redate_legacy_dummy_logs(db: Session, org_id: str) -> None:
    """Keep original demo sends out of the Oct 2026 dashboard window."""
    campaign_ids = [
        row.id
        for row in db.query(Campaign.id).filter(
            Campaign.org_id == org_id,
            Campaign.campaign_id.in_(LEGACY_DUMMY_CAMPAIGN_IDS),
        ).all()
    ]
    if not campaign_ids:
        return
    moved = (
        db.query(EmailLog)
        .filter(EmailLog.campaign_id.in_(campaign_ids), EmailLog.sent_at >= _at("2026-09-01"))
        .update({EmailLog.sent_at: _at("2025-07-15")}, synchronize_session=False)
    )
    if moved:
        logger.info("Moved %s legacy dummy sends to July 2025", moved)


def _ensure_mailers(db: Session, org_id: str) -> None:
    if db.query(Mailer).filter(Mailer.org_id == org_id).first():
        return
    db.add_all([
        Mailer(
            name="Introduction Outreach",
            type="placeholder",
            subject="Quick introduction — {{Company}}",
            body="Hello {{Name}},\n\nI wanted to share how we help teams like {{Company}}.\n",
            closing="Best regards,\nAdmin 1",
            cta="Book a 15-minute chat",
            org_id=org_id,
        ),
        Mailer(
            name="Follow-up after no reply",
            type="manual",
            subject="Following up — {{Company}}",
            body="Hi {{Name}},\n\nJust bumping this in case it was buried.\n",
            closing="Thanks,\nAdmin 1",
            cta="Reply with a time that works",
            org_id=org_id,
        ),
    ])


def _ensure_invite(db: Session, org_id: str, admin_id: int) -> None:
    email = "seed.invitee@example.com"
    if db.query(Invite).filter(Invite.org_id == org_id, Invite.email == email).first():
        return
    db.add(Invite(
        org_id=org_id,
        email=email,
        role="USER",
        status="PENDING",
        invite_token=secrets.token_urlsafe(24),
        invited_by_user_id=admin_id,
        expires_at=utc_now() + timedelta(days=14),
    ))


def _ensure_recipients_and_lists(db: Session, org_id: str) -> list[Recipient]:
    existing = (
        db.query(Recipient)
        .filter(Recipient.org_id == org_id, Recipient.email.like("seed.prospect.%@example.com"))
        .order_by(Recipient.id)
        .all()
    )
    if existing:
        return existing

    recipients: list[Recipient] = []
    for index in range(40):
        company, industry = COMPANIES[index % len(COMPANIES)]
        first = f"Prospect{index + 1:02d}"
        recipient = Recipient(
            name=f"{first} Seed",
            email=f"seed.prospect.{index + 1:02d}@example.com",
            company=company,
            designation="Director" if index % 2 == 0 else "VP Sales",
            industry=industry,
            org_id=org_id,
            first_name=first,
            last_name="Seed",
            country="India" if index % 3 else "United States",
            city="Hyderabad" if index % 3 else "Austin",
            source="seed",
            is_selected=index < 12,
        )
        db.add(recipient)
        recipients.append(recipient)
    db.flush()

    group = (
        db.query(RecipientGroup)
        .filter(RecipientGroup.org_id == org_id, RecipientGroup.name == "Seed Enterprise List")
        .first()
    )
    if not group:
        group = RecipientGroup(name="Seed Enterprise List", description="Demo list for campaign send", org_id=org_id)
        db.add(group)
        db.flush()
    for recipient in recipients[:12]:
        db.add(RecipientGroupMember(group_id=group.id, recipient_id=recipient.id))

    def _tag(name: str) -> Tag:
        row = db.query(Tag).filter(Tag.org_id == org_id, Tag.name == name).first()
        if row:
            return row
        row = Tag(name=name, org_id=org_id)
        db.add(row)
        db.flush()
        return row

    warm = _tag("Warm")
    enterprise = _tag("Enterprise")
    for recipient in recipients[:8]:
        db.add(RecipientTag(recipient_id=recipient.id, tag_id=warm.id))
    for recipient in recipients[8:16]:
        db.add(RecipientTag(recipient_id=recipient.id, tag_id=enterprise.id))
    return recipients


def _ensure_dashboard_history(db: Session, org_id: str, admin: User, recipients: list[Recipient]) -> Campaign | None:
    campaign = db.query(Campaign).filter(Campaign.campaign_id == FUNC_CAMPAIGN_ID).first()
    if campaign:
        return campaign

    totals = dashboard_seed_totals()
    campaign = Campaign(
        campaign_name="October Outreach Tracker",
        campaign_id=FUNC_CAMPAIGN_ID,
        description="Seeded mail + ICP history that matches the dashboard tables.",
        owner=admin.name,
        department="Sales",
        target_audience="B2B decision makers",
        subject="Partnership opportunity for {{Company}}",
        status="active",
        emails_sent=totals["total_mails"],
        user_id=admin.id,
        org_id=org_id,
    )
    db.add(campaign)
    db.flush()

    template = Template(
        campaign_id=campaign.id,
        name="Primary Template",
        type="placeholder",
        subject="Hello {{Name}} — {{Company}}",
        body="Dear {{Name}},\n\nWe help teams like {{Company}} run outreach with accurate tracking.\n",
        closing="Best regards,\nAdmin 1",
        cta="Schedule a call",
    )
    db.add(template)
    db.flush()
    db.add(CampaignSequenceStage(
        campaign_id=campaign.id,
        stage_order=1,
        delay_value=3,
        delay_unit="days",
        subject="Following up with {{Company}}",
        body="Hi {{Name}},\n\nJust checking whether the earlier note was useful.\n",
        closing="Thanks,\nAdmin 1",
        cta="Reply with a time",
    ))

    for index, recipient in enumerate(recipients):
        status = "replied" if index < 3 else "bounced" if index == 3 else "sent" if index < 20 else "not_contacted"
        db.add(CampaignRecipient(
            campaign_id=campaign.id,
            recipient_id=recipient.id,
            template_id=template.id,
            status=status,
            current_stage=1 if status == "sent" else 0,
            sender_user_id=admin.id,
            last_sent_at=_at("2026-10-14") if status != "not_contacted" else None,
        ))

    mail_rows: list[dict] = []
    recipient_ids = [row.id for row in recipients]

    def add_mails(day: str, count: int) -> None:
        when = _at(day)
        for index in range(count):
            mail_rows.append({
                "campaign_id": campaign.id,
                "recipient_id": recipient_ids[index % len(recipient_ids)],
                "status": "sent",
                "sender_user_id": admin.id,
                "sent_at": when,
                "subject": f"Seed mail {day}",
                "source": "ses",
            })

    add_mails("2026-08-10", AUG_MAILS)
    add_mails("2026-09-15", SEP_MAILS)
    for day, (sent, _icp) in OCTOBER_DAYS.items():
        add_mails(day, sent)
    # Failed row must not affect sent totals.
    mail_rows.append({
        "campaign_id": campaign.id,
        "recipient_id": recipient_ids[0],
        "status": "failed",
        "sender_user_id": admin.id,
        "sent_at": _at("2026-10-14", 18),
        "subject": "Seed mail failed",
        "error_message": "SMTP connection timeout",
        "source": "ses",
    })
    _chunked_insert(db, EmailLog, mail_rows)

    icp_rows: list[dict] = []

    def add_icp(day: str, count: int, source: str) -> None:
        when = _at(day, 9)
        for index in range(count):
            company, industry = COMPANIES[index % len(COMPANIES)]
            suffix = f"{day}-{index}"
            icp_rows.append({
                "org_id": org_id,
                "user_id": admin.id,
                "name": f"ICP {suffix}",
                "email": f"icp-{suffix}@example.com",
                "company_name": company,
                "designation": "VP Sales",
                "industry": industry,
                "linkedin_url": f"https://www.linkedin.com/in/seed-{suffix}",
                "icp_status": ICP_STATUS_VERIFIED,
                "verification_status": "VERIFIED",
                "source": source,
                "created_at": when,
                "updated_at": when,
            })

    add_icp("2026-09-20", SEP_ICP, SOURCE_MANUAL)
    for day, (_sent, icp) in OCTOBER_DAYS.items():
        if icp:
            add_icp(day, icp, SOURCE_LINKEDIN_BULK)
    _chunked_insert(db, IcpRecordRow, icp_rows)
    logger.info(
        "Seeded dashboard history: %s mails, %s ICP",
        totals["total_mails"],
        totals["total_icp"],
    )
    return campaign


def _ensure_linkedin(db: Session, admin: User) -> None:
    now = utc_now()
    if not db.query(BulkExtractJobRow).filter(BulkExtractJobRow.id == FUNC_LINKEDIN_JOB_ID).first():
        job = BulkExtractJobRow(
            id=FUNC_LINKEDIN_JOB_ID,
            user_id=admin.id,
            original_file_name="seed_linkedin_urls.xlsx",
            input_columns=["linkedin_url", "name", "company"],
            total_urls=8,
            processed_count=8,
            success_count=6,
            failed_count=2,
            verified_count=5,
            mismatch_count=1,
            review_count=1,
            needs_review_count=1,
            resolved_count=0,
            phase=PHASE_REVIEW,
            excel_finalized=True,
            status=JOB_DONE,
            created_at=now - timedelta(days=2),
            started_at=now - timedelta(days=2),
            completed_at=now - timedelta(days=1),
            icp_added_count=0,
        )
        db.add(job)
        db.flush()
        profiles = [
            ("https://www.linkedin.com/in/seed-ok-1", "Priya Shah", "Acme Corp", "VP Sales", ITEM_SUCCESS, "VERIFIED", True),
            ("https://www.linkedin.com/in/seed-ok-2", "Rahul Mehta", "TechCorp", "CTO", ITEM_SUCCESS, "VERIFIED", True),
            ("https://www.linkedin.com/in/seed-ok-3", "Anita Rao", "HealthTech", "COO", ITEM_SUCCESS, "VERIFIED", True),
            ("https://www.linkedin.com/in/seed-ok-4", "James Cole", "FinTech Pro", "CFO", ITEM_SUCCESS, "VERIFIED", True),
            ("https://www.linkedin.com/in/seed-ok-5", "Sara Kim", "CloudSys", "Director", ITEM_SUCCESS, "VERIFIED", True),
            ("https://www.linkedin.com/in/seed-review-1", "Alex Uploaded", "Global Inc", "VP Marketing", ITEM_SUCCESS, "MISMATCH", False),
            ("https://www.linkedin.com/in/seed-fail-1", None, None, None, ITEM_FINAL_FAILED, "NOT_VERIFIED", None),
            ("https://www.linkedin.com/in/seed-fail-2", None, None, None, ITEM_FINAL_FAILED, "NOT_VERIFIED", None),
        ]
        for index, (url, name, company, designation, status, verify, match) in enumerate(profiles, start=1):
            extracted_name = "Alex Extracted" if not match else name
            db.add(BulkJobItemRow(
                job_id=job.id,
                source_row_number=index,
                profile_url=url,
                normalized_url=url,
                status=status,
                attempt_count=1 if status == ITEM_SUCCESS else 3,
                name=extracted_name,
                company=company if match is not False else "Different Co",
                designation=designation,
                location="Hyderabad, India",
                source_row_json={"name": name, "company": company, "designation": designation},
                verification_status=verify,
                verification_score=90 if match else 40,
                name_match=match,
                company_match=match,
                designation_match=True if match is not None else None,
                last_error=None if status == ITEM_SUCCESS else "Profile is private",
                completed_at=now - timedelta(days=1),
            ))

    if db.query(ProfileExtractJob).filter(ProfileExtractJob.id == FUNC_PROFILE_JOB_ID).first():
        return
    extract = ProfileExtractJob(
        id=FUNC_PROFILE_JOB_ID,
        user_id=admin.id,
        profile_url="https://www.linkedin.com/in/seed-single-profile",
        status="completed",
        created_at=now - timedelta(days=1),
        completed_at=now - timedelta(hours=20),
    )
    db.add(extract)
    db.flush()
    db.add(ProfileExtractResult(
        job_id=extract.id,
        full_name="Neha Kapoor",
        company="InnovateIO",
        designation="CMO",
        about="Demand-gen leader for B2B SaaS.",
    ))


def _ensure_offerings(db: Session, org_id: str, admin_id: int) -> None:
    from scripts.seed_smartops_offerings import SEED_OFFERINGS, _intro_email_template, _payload

    for spec in SEED_OFFERINGS:
        payload = _payload(org_id, spec)
        row, _created = upsert_from_smartops(
            db,
            organization_id=org_id,
            data=payload,
            owner_user_id=admin_id,
        )
        if not row.email_template:
            row.email_template = _intro_email_template(row.name, row.content or "")
        if not row.user_id:
            row.user_id = admin_id


def _ensure_blacklist_and_verification(db: Session, org_id: str, campaign: Campaign | None) -> None:
    bounce_email = "seed.hardbounce@example.com"
    if not db.query(SuppressionEntry).filter(SuppressionEntry.email == bounce_email).first():
        recipient = db.query(Recipient).filter(Recipient.email == bounce_email, Recipient.org_id == org_id).first()
        if not recipient:
            recipient = Recipient(
                name="Hard Bounce Seed",
                email=bounce_email,
                company="Closed Co",
                org_id=org_id,
                is_suppressed=True,
                suppression_reason="hard_bounce",
            )
            db.add(recipient)
            db.flush()
        db.add(SuppressionEntry(
            email=bounce_email,
            company="Closed Co",
            reason="hard_bounce",
            bounce_type="Permanent",
            campaign_id=campaign.id if campaign else None,
            recipient_id=recipient.id,
            detail="550 mailbox does not exist",
        ))
        db.add(SuppressionEntry(
            email="seed.cleared@example.com",
            company="Cleared Co",
            reason="manual",
            campaign_id=campaign.id if campaign else None,
            detail="Added by seed, then cleared",
            overridden_at=utc_now(),
        ))

    now = utc_now()
    samples = (
        ("seed.good@example.com", "ok", 1, "good"),
        ("seed.risky@example.com", "catch_all", 4, "risky"),
        ("seed.bad@example.com", "invalid", 2, "bad"),
    )
    for email, result, code, quality in samples:
        if db.query(EmailVerification).filter(EmailVerification.email == email).first():
            continue
        db.add(EmailVerification(
            email=email,
            result=result,
            resultcode=code,
            quality=quality,
            source="millionverifier",
            verified_at=now,
            expires_at=now + timedelta(days=30),
        ))


def _ensure_notification(db: Session, admin_id: int, campaign: Campaign | None) -> None:
    key = "seed-bounce-hardbounce"
    exists = db.query(UserNotification).filter(
        UserNotification.user_id == admin_id,
        UserNotification.dedupe_key == key,
    ).first()
    if exists:
        return
    db.add(UserNotification(
        user_id=admin_id,
        kind="bounce",
        title="Hard bounce on seed send",
        body="seed.hardbounce@example.com bounced from October Outreach Tracker.",
        dedupe_key=key,
        campaign_id=campaign.id if campaign else None,
        recipient_email="seed.hardbounce@example.com",
        bounce_type="Permanent",
    ))


def _ensure_tenant_two(db: Session) -> None:
    org_id = resolve_org_id_by_tenant_key(db, "tenant_two")
    admin = db.query(User).filter(User.email == "admin2@tenant.com").first()
    if not org_id or not admin:
        return
    if db.query(Campaign).filter(Campaign.campaign_id == FUNC_CAMPAIGN_T2_ID).first():
        return
    recipient = Recipient(
        name="Tenant Two Prospect",
        email="seed.t2.prospect@example.com",
        company="T2 Corp",
        org_id=org_id,
    )
    db.add(recipient)
    db.flush()
    campaign = Campaign(
        campaign_name="Tenant Two Pilot",
        campaign_id=FUNC_CAMPAIGN_T2_ID,
        description="Isolation check for tenant two.",
        owner=admin.name,
        status="active",
        emails_sent=8,
        user_id=admin.id,
        org_id=org_id,
    )
    db.add(campaign)
    db.flush()
    for index in range(8):
        db.add(EmailLog(
            campaign_id=campaign.id,
            recipient_id=recipient.id,
            status="sent",
            sender_user_id=admin.id,
            sent_at=_at("2026-10-10", 10 + index),
            subject="T2 seed mail",
        ))
    for index in range(12):
        db.add(IcpRecordRow(
            org_id=org_id,
            user_id=admin.id,
            name=f"T2 Contact {index + 1}",
            email=f"t2-icp-{index + 1}@example.com",
            company_name="T2 Corp",
            linkedin_url=f"https://www.linkedin.com/in/t2-seed-{index + 1}",
            icp_status=ICP_STATUS_VERIFIED,
            verification_status="VERIFIED",
            source=SOURCE_MANUAL,
            created_at=_at("2026-10-08"),
        ))


def ensure_functional_demo_data(db: Session) -> dict[str, int]:
    """Fill Tenant One (and a light Tenant Two set) so every screen has rows."""
    totals = dashboard_seed_totals()
    if _is_sqlite(db):
        logger.info("Skipping functional seed on SQLite")
        return totals

    org_id = get_default_tenant_org_id(db)
    admin = db.query(User).filter(User.email == "admin1@tenant.com").first()
    if not org_id or not admin:
        logger.warning("Tenant One / Admin 1 missing — functional seed skipped")
        return totals

    _redate_legacy_dummy_logs(db, org_id)
    _ensure_mailers(db, org_id)
    _ensure_invite(db, org_id, admin.id)
    recipients = _ensure_recipients_and_lists(db, org_id)
    campaign = _ensure_dashboard_history(db, org_id, admin, recipients)
    db.commit()

    for step, action in (
        ("linkedin", lambda: _ensure_linkedin(db, admin)),
        ("offerings", lambda: _ensure_offerings(db, org_id, admin.id)),
        ("blacklist", lambda: _ensure_blacklist_and_verification(db, org_id, campaign)),
        ("notification", lambda: _ensure_notification(db, admin.id, campaign)),
        ("tenant_two", lambda: _ensure_tenant_two(db)),
    ):
        try:
            action()
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Functional seed step %s failed", step)

    logger.info("Functional demo data ready for org %s", org_id)
    return totals
