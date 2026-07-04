"""Dashboard statistics aggregation service."""

from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Campaign, EmailLog, Template


class DashboardService:
    def get_stats(self, db: Session) -> dict:
        """Aggregate dashboard statistics from database."""
        total_campaigns = db.query(Campaign).count()
        active_campaigns = db.query(Campaign).filter(Campaign.status == "active").count()

        sent_count = db.query(EmailLog).filter(EmailLog.status == "sent").count()
        failed_count = db.query(EmailLog).filter(EmailLog.status == "failed").count()
        pending_count = db.query(EmailLog).filter(EmailLog.status == "pending").count()

        ai_templates = db.query(Template).filter(Template.type == "ai").count()

        return {
            "total_campaigns": total_campaigns,
            "emails_sent": sent_count,
            "pending_emails": pending_count,
            "failed_emails": failed_count,
            "active_campaigns": active_campaigns,
            "ai_generated_emails": ai_templates,
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
