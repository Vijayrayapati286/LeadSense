"""Dashboard statistics aggregation service."""

import io
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Campaign, EmailLog, Recipient, SuppressionEntry, Template


class DashboardService:
    def get_stats(self, db: Session) -> dict:
        """Aggregate dashboard statistics from database."""
        total_campaigns = db.query(Campaign).count()
        active_campaigns = db.query(Campaign).filter(Campaign.status == "active").count()

        sent_count = db.query(EmailLog).filter(EmailLog.status == "sent").count()
        failed_count = db.query(EmailLog).filter(EmailLog.status == "failed").count()
        pending_count = db.query(EmailLog).filter(EmailLog.status == "pending").count()

        ai_templates = db.query(Template).filter(Template.type == "ai").count()

        hard_bounces = (
            db.query(SuppressionEntry)
            .filter(SuppressionEntry.reason == "hard_bounce", SuppressionEntry.overridden_at.is_(None))
            .count()
        )
        soft_bounces_pending = (
            db.query(Recipient)
            .filter(Recipient.soft_bounce_count > 0, Recipient.is_suppressed == False)  # noqa: E712
            .count()
        )
        bounced_suppressions = (
            db.query(SuppressionEntry)
            .filter(
                SuppressionEntry.reason.in_(["hard_bounce", "soft_bounce_threshold_exceeded"]),
                SuppressionEntry.overridden_at.is_(None),
            )
            .count()
        )
        bounce_rate = round((bounced_suppressions / sent_count) * 100, 2) if sent_count else 0.0

        return {
            "total_campaigns": total_campaigns,
            "emails_sent": sent_count,
            "pending_emails": pending_count,
            "failed_emails": failed_count,
            "active_campaigns": active_campaigns,
            "ai_generated_emails": ai_templates,
            "hard_bounces": hard_bounces,
            "soft_bounces_pending": soft_bounces_pending,
            "bounce_rate": bounce_rate,
        }

    def get_emails_per_day(self, db: Session, days: int = 7) -> list[dict]:
        """Get email send counts per day for the last N days."""
        results = []
        today = datetime.utcnow().date()

        for i in range(days - 1, -1, -1):
            day = today - timedelta(days=i)
            count = (
                db.query(EmailLog)
                .filter(
                    func.date(EmailLog.sent_at) == day,
                    EmailLog.status == "sent",
                )
                .count()
            )
            results.append({"date": day.strftime("%b %d"), "count": count})

        return results

    def get_campaign_status_breakdown(self, db: Session) -> list[dict]:
        """Get campaign count grouped by status."""
        statuses = ["draft", "active", "completed", "paused"]
        results = []
        for status in statuses:
            count = db.query(Campaign).filter(Campaign.status == status).count()
            results.append({"status": status.capitalize(), "count": count})
        return results

    def get_recent_activity(self, db: Session, limit: int = 5) -> list[dict]:
        """Build recent activity feed from email logs and campaigns."""
        activities = []

        recent_logs = (
            db.query(EmailLog)
            .order_by(EmailLog.sent_at.desc())
            .limit(limit)
            .all()
        )
        for log in recent_logs:
            activities.append({
                "id": log.id,
                "action": f"Email {log.status}",
                "description": f"Email to recipient #{log.recipient_id} - {log.status}",
                "timestamp": log.sent_at.isoformat() if log.sent_at else "",
            })

        if len(activities) < limit:
            recent_campaigns = (
                db.query(Campaign)
                .order_by(Campaign.created_at.desc())
                .limit(limit - len(activities))
                .all()
            )
            for camp in recent_campaigns:
                activities.append({
                    "id": camp.id,
                    "action": "Campaign created",
                    "description": f"Campaign '{camp.campaign_name}' created",
                    "timestamp": camp.created_at.isoformat() if camp.created_at else "",
                })

        return activities[:limit]

    def get_recent_campaigns(self, db: Session, limit: int = 5) -> list[dict]:
        campaigns = (
            db.query(Campaign)
            .order_by(Campaign.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": c.id,
                "campaign_name": c.campaign_name,
                "campaign_id": c.campaign_id,
                "owner": c.owner,
                "status": c.status,
                "emails_sent": c.emails_sent,
                "created_at": c.created_at.isoformat() if c.created_at else "",
            }
            for c in campaigns
        ]

    def get_full_dashboard(self, db: Session) -> dict:
        return {
            "stats": self.get_stats(db),
            "emails_per_day": self.get_emails_per_day(db),
            "campaign_status": self.get_campaign_status_breakdown(db),
            "recent_activity": self.get_recent_activity(db),
            "recent_campaigns": self.get_recent_campaigns(db),
        }

    def build_report_workbook(self, db: Session) -> bytes:
        """Multi-sheet Excel export for the Dashboard's "Export Report"
        button — one sheet each for summary stats, campaigns, prospects, and
        email send history, so a single download covers all the reportable
        data instead of requiring a separate export per page."""
        stats = self.get_stats(db)
        campaign_status = self.get_campaign_status_breakdown(db)
        summary_rows = [{"Metric": key.replace("_", " ").title(), "Value": value} for key, value in stats.items()]
        summary_rows += [{"Metric": f"{row['status']} Campaigns", "Value": row["count"]} for row in campaign_status]

        campaigns = db.query(Campaign).order_by(Campaign.created_at.desc()).all()
        campaign_rows = [
            {
                "ID": c.id,
                "Campaign ID": c.campaign_id,
                "Name": c.campaign_name,
                "Owner": c.owner,
                "Department": c.department or "",
                "Status": c.status,
                "Target Audience": c.target_audience or "",
                "Emails Sent": c.emails_sent,
                "Scheduled At": c.scheduled_at.isoformat() if c.scheduled_at else "",
                "Created At": c.created_at.isoformat() if c.created_at else "",
            }
            for c in campaigns
        ]

        recipients = db.query(Recipient).order_by(Recipient.name).all()
        recipient_rows = [
            {
                "ID": r.id,
                "Name": r.name,
                "Email": r.email,
                "Company": r.company or "",
                "Designation": r.designation or "",
                "Industry": r.industry or "",
                "Department": r.department or "",
                "Country": r.country or "",
                "State": r.state or "",
                "City": r.city or "",
                "Status": r.status or "",
                "Source": r.source or "",
                "Suppressed": "Yes" if r.is_suppressed else "No",
                "Suppression Reason": r.suppression_reason or "",
            }
            for r in recipients
        ]

        logs = (
            db.query(EmailLog, Campaign, Recipient)
            .join(Campaign, Campaign.id == EmailLog.campaign_id)
            .join(Recipient, Recipient.id == EmailLog.recipient_id)
            .order_by(EmailLog.sent_at.desc())
            .all()
        )
        log_rows = [
            {
                "Campaign": camp.campaign_name,
                "Recipient Name": rec.name,
                "Recipient Email": rec.email,
                "Status": log.status,
                "Error": log.error_message or "",
                "Sent At": log.sent_at.isoformat() if log.sent_at else "",
            }
            for log, camp, rec in logs
        ]

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            pd.DataFrame(summary_rows).to_excel(writer, index=False, sheet_name="Summary")
            pd.DataFrame(campaign_rows).to_excel(writer, index=False, sheet_name="Campaigns")
            pd.DataFrame(recipient_rows).to_excel(writer, index=False, sheet_name="Prospects")
            pd.DataFrame(log_rows).to_excel(writer, index=False, sheet_name="Email Logs")
        buffer.seek(0)
        return buffer.getvalue()
