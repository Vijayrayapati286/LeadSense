"""Daily + month-wise dashboard totals must match running MTD / overall / ICP math."""

from datetime import datetime, timezone
from uuid import uuid4

from app.database.connection import SessionLocal
from app.icp.models import IcpRecordRow
from app.models import Campaign, EmailLog, Organization, Recipient, User
from app.services.dashboard_service import DashboardService
from app.services.functional_seed import dashboard_seed_totals


def test_seed_dashboard_targets_match_spreadsheet():
    totals = dashboard_seed_totals()
    assert totals["august_mails"] == 2491
    assert totals["september_mails"] == 2327
    assert totals["september_icp"] == 4618
    assert totals["october_mails"] == 4577
    assert totals["october_icp"] == 791
    assert totals["total_mails"] == 9395
    assert totals["total_icp"] == 5409


def _at(day: str) -> datetime:
    return datetime.fromisoformat(f"{day}T12:00:00").replace(tzinfo=timezone.utc)


def _add_sent(db, campaign_id, recipient_id, sender_id, day, count):
    for index in range(count):
        db.add(
            EmailLog(
                campaign_id=campaign_id,
                recipient_id=recipient_id,
                status="sent",
                sender_user_id=sender_id,
                sent_at=_at(day),
                subject=f"mail-{day}-{index}",
            )
        )


def _add_failed(db, campaign_id, recipient_id, sender_id, day):
    db.add(
        EmailLog(
            campaign_id=campaign_id,
            recipient_id=recipient_id,
            status="failed",
            sender_user_id=sender_id,
            sent_at=_at(day),
            subject=f"fail-{day}",
        )
    )


def _add_icp(db, org_id, user_id, day, count):
    suffix = uuid4().hex[:8]
    for index in range(count):
        db.add(
            IcpRecordRow(
                org_id=org_id,
                user_id=user_id,
                name=f"Contact {day} {index}",
                email=f"c-{suffix}-{day}-{index}@example.com",
                linkedin_url=f"https://linkedin.com/in/{suffix}-{day}-{index}",
                created_at=_at(day),
            )
        )


def test_daily_and_month_wise_running_totals(client):
    db = SessionLocal()
    stamp = uuid4().hex[:10]
    org = None
    try:
        org = Organization(
            org_id=f"ORG-DM-{stamp}",
            org_name="Dash Mail Org",
            org_type="TENANT",
            integration_token=f"dash-mail-{stamp}",
            status="ACTIVE",
        )
        db.add(org)
        db.flush()
        user = User(
            name="Dash Owner",
            email=f"dash.owner.{stamp}@example.com",
            org_id=org.org_id,
            role="ADMIN",
        )
        db.add(user)
        db.flush()
        campaign = Campaign(
            campaign_name="Dash Mail Campaign",
            campaign_id=f"CMP-DM-{stamp}",
            owner="Dash Owner",
            status="active",
            user_id=user.id,
            org_id=org.org_id,
        )
        db.add(campaign)
        db.flush()
        recipient = Recipient(
            name="Prospect",
            email=f"dash.prospect.{stamp}@example.com",
            org_id=org.org_id,
        )
        db.add(recipient)
        db.flush()

        _add_sent(db, campaign.id, recipient.id, user.id, "2026-08-10", 5)
        _add_sent(db, campaign.id, recipient.id, user.id, "2026-09-15", 7)
        _add_icp(db, org.org_id, user.id, "2026-09-20", 4)

        october = {
            "2026-10-05": (2, 0),
            "2026-10-06": (1, 0),
            "2026-10-08": (3, 2),
            "2026-10-14": (4, 1),
        }
        for day, (sent, icp) in october.items():
            _add_sent(db, campaign.id, recipient.id, user.id, day, sent)
            if icp:
                _add_icp(db, org.org_id, user.id, day, icp)
        _add_failed(db, campaign.id, recipient.id, user.id, "2026-10-14")
        db.commit()

        service = DashboardService()
        daily = service.get_emails_per_day(
            db,
            date_from=_at("2026-10-05"),
            date_to=_at("2026-10-14"),
            org_id=org.org_id,
        )
        by_day = {row["iso_date"]: row for row in daily}

        assert by_day["2026-10-07"]["sent"] == 0
        assert by_day["2026-10-07"]["cumulative_month"] == 3
        assert by_day["2026-10-05"]["sent"] == 2
        assert by_day["2026-10-05"]["cumulative_month"] == 2
        assert by_day["2026-10-05"]["cumulative_overall"] == 5 + 7 + 2
        assert by_day["2026-10-05"]["icp_db_day"] == 0
        assert by_day["2026-10-05"]["icp_db_cumulative"] == 4

        running_month = 0
        running_overall = 5 + 7
        running_icp = 4
        for day, (sent, icp) in october.items():
            running_month += sent
            running_overall += sent
            running_icp += icp
            assert by_day[day]["sent"] == sent
            assert by_day[day]["cumulative_month"] == running_month
            assert by_day[day]["cumulative_overall"] == running_overall
            assert by_day[day]["icp_db_day"] == icp
            assert by_day[day]["icp_db_cumulative"] == running_icp

        assert by_day["2026-10-14"]["cumulative_month"] == 10
        assert by_day["2026-10-14"]["cumulative_overall"] == 22
        assert by_day["2026-10-14"]["icp_db_cumulative"] == 7

        months = {
            row["month_key"]: row
            for row in service.get_month_wise(db, date_to=_at("2026-10-14"), org_id=org.org_id)
        }
        assert months["2026-08"]["mails_sent"] == 5
        assert months["2026-08"]["icp_database"] == 0
        assert months["2026-09"]["mails_sent"] == 7
        assert months["2026-09"]["icp_database"] == 4
        assert months["2026-10"]["mails_sent"] == 10
        assert months["2026-10"]["icp_database"] == 3
        assert sum(row["mails_sent"] for row in months.values()) == 22
        assert sum(row["icp_database"] for row in months.values()) == 7
    finally:
        if org is not None:
            campaign_ids = [row.id for row in db.query(Campaign.id).filter(Campaign.org_id == org.org_id).all()]
            if campaign_ids:
                db.query(EmailLog).filter(EmailLog.campaign_id.in_(campaign_ids)).delete(synchronize_session=False)
            db.query(IcpRecordRow).filter(IcpRecordRow.org_id == org.org_id).delete(synchronize_session=False)
            db.query(Campaign).filter(Campaign.org_id == org.org_id).delete(synchronize_session=False)
            db.query(Recipient).filter(Recipient.org_id == org.org_id).delete(synchronize_session=False)
            db.query(User).filter(User.org_id == org.org_id).delete(synchronize_session=False)
            db.query(Organization).filter(Organization.org_id == org.org_id).delete(synchronize_session=False)
            db.commit()
        db.close()
