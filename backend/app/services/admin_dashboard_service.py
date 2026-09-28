"""Tenant-scoped admin dashboard aggregations."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.icp.models import IcpRecordRow
from app.linkedin.bulk_models import BulkExtractJobRow
from app.models import Campaign, CampaignRecipient, EmailLog, EmailVerification, Recipient, User


class AdminDashboardService:
    def get_admin_dashboard(self, db: Session, org_id: str) -> dict:
        users = db.query(User).filter(User.org_id == org_id).order_by(User.name).all()
        org_user_ids = [u.id for u in users]
        campaigns = (
            db.query(Campaign)
            .filter(Campaign.org_id == org_id)
            .order_by(Campaign.created_at.desc())
            .all()
        )
        campaign_ids = [c.id for c in campaigns]

        total_users = len(users)
        total_campaigns = len(campaigns)

        if campaign_ids:
            emails_sent = (
                db.query(EmailLog)
                .filter(EmailLog.campaign_id.in_(campaign_ids), EmailLog.status == "sent")
                .count()
            )
            bounced = (
                db.query(CampaignRecipient)
                .filter(
                    CampaignRecipient.campaign_id.in_(campaign_ids),
                    CampaignRecipient.bounced_at.isnot(None),
                )
                .count()
            )
            replies = (
                db.query(CampaignRecipient)
                .filter(
                    CampaignRecipient.campaign_id.in_(campaign_ids),
                    CampaignRecipient.replied_at.isnot(None),
                )
                .count()
            )
        else:
            emails_sent = bounced = replies = 0

        delivered = emails_sent

        user_activity = []
        for user in users:
            user_campaigns = sum(1 for c in campaigns if c.user_id == user.id)
            user_sent = (
                db.query(EmailLog)
                .filter(EmailLog.sender_user_id == user.id, EmailLog.status == "sent")
                .count()
            )
            user_activity.append({
                "user_id": user.id,
                "name": user.name,
                "email": user.email,
                "campaigns": user_campaigns,
                "emails_sent": user_sent,
                "status": getattr(user, "status", "ACTIVE") or "ACTIVE",
            })

        campaign_performance = []
        for camp in campaigns:
            sent = (
                db.query(EmailLog)
                .filter(EmailLog.campaign_id == camp.id, EmailLog.status == "sent")
                .count()
            )
            camp_bounced = (
                db.query(CampaignRecipient)
                .filter(
                    CampaignRecipient.campaign_id == camp.id,
                    CampaignRecipient.bounced_at.isnot(None),
                )
                .count()
            )
            camp_replied = (
                db.query(CampaignRecipient)
                .filter(
                    CampaignRecipient.campaign_id == camp.id,
                    CampaignRecipient.replied_at.isnot(None),
                )
                .count()
            )
            campaign_performance.append({
                "campaign_id": camp.id,
                "campaign_name": camp.campaign_name,
                "sent": sent,
                "delivered": sent,
                "bounced": camp_bounced,
                "replied": camp_replied,
            })

        if org_user_ids:
            icp_base = db.query(IcpRecordRow).filter(IcpRecordRow.user_id.in_(org_user_ids))
            icp_contacts = icp_base.count()
            icp_accounts = (
                db.query(func.count(func.distinct(IcpRecordRow.company_name)))
                .filter(
                    IcpRecordRow.user_id.in_(org_user_ids),
                    IcpRecordRow.company_name.isnot(None),
                    IcpRecordRow.company_name != "",
                )
                .scalar()
                or 0
            )
            added_to_icp = (
                db.query(IcpRecordRow)
                .filter(
                    IcpRecordRow.user_id.in_(org_user_ids),
                    IcpRecordRow.source == "linkedin_bulk",
                )
                .count()
            )
            li_totals = (
                db.query(
                    func.coalesce(func.sum(BulkExtractJobRow.total_urls), 0),
                    func.coalesce(func.sum(BulkExtractJobRow.success_count), 0),
                    func.coalesce(func.sum(BulkExtractJobRow.failed_count), 0),
                )
                .filter(BulkExtractJobRow.user_id.in_(org_user_ids))
                .one()
            )
            total_extracted, success_extracted, failed_extracted = (int(x or 0) for x in li_totals)
        else:
            icp_contacts = icp_accounts = added_to_icp = 0
            total_extracted = success_extracted = failed_extracted = 0

        org_emails = [
            (e or "").strip().lower()
            for (e,) in db.query(Recipient.email).filter(Recipient.org_id == org_id).all()
            if e
        ]
        if org_emails:
            verified_rows = (
                db.query(EmailVerification)
                .filter(func.lower(EmailVerification.email).in_(org_emails))
                .all()
            )
        else:
            verified_rows = []

        emails_verified = len(verified_rows)
        valid = sum(1 for r in verified_rows if (r.result or "").lower() in ("ok", "valid"))
        invalid = sum(1 for r in verified_rows if (r.result or "").lower() == "invalid")
        risky = sum(
            1
            for r in verified_rows
            if (r.result or "").lower() in ("risky", "catch_all", "unknown", "disposable")
        )

        return {
            "org_id": org_id,
            "summary": {
                "total_users": total_users,
                "campaigns": total_campaigns,
                "emails_sent": emails_sent,
                "delivered": delivered,
                "bounced": bounced,
                "replies": replies,
            },
            "user_activity": user_activity,
            "campaign_performance": campaign_performance,
            "icp": {
                "accounts": int(icp_accounts),
                "contacts": icp_contacts,
                "verified_emails": valid,
                "invalid_emails": invalid,
            },
            "linkedin": {
                "total_extracted": total_extracted,
                "successfully_extracted": success_extracted,
                "failed": failed_extracted,
                "added_to_icp": added_to_icp,
            },
            "email_verification": {
                "emails_verified": emails_verified,
                "valid": valid,
                "invalid": invalid,
                "risky": risky,
            },
        }
