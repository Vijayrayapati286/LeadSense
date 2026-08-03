"""Dashboard statistics aggregation service."""

import io
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from app.models import Campaign, EmailLog, Recipient, SuppressionEntry, Template

# Cap on how many days get_emails_per_day will break out individually — each
# day is its own COUNT query, so an unbounded custom date range (e.g. someone
# picks a 2-year window) would otherwise fan out into hundreds of queries.
MAX_EMAILS_PER_DAY_SPAN = 90


class DashboardService:
    """All aggregation methods take the same four optional filters —
    user_id (sender/owner), campaign_id, date_from, date_to (both
    timezone-aware datetimes bounding the relevant activity window) — so the
    Dashboard's filter bar can narrow every widget consistently. Each metric
    is filtered against whichever timestamp is actually meaningful for it
    (campaign counts by Campaign.created_at, email counts by
    EmailLog.sent_at, suppressions by SuppressionEntry.created_at)."""

    def _campaign_query(
        self, db: Session, user_id: int | None, campaign_id: int | None,
        date_from: datetime | None, date_to: datetime | None,
    ) -> Query:
        query = db.query(Campaign)
        if user_id:
            query = query.filter(Campaign.user_id == user_id)
        if campaign_id:
            query = query.filter(Campaign.id == campaign_id)
        if date_from:
            query = query.filter(Campaign.created_at >= date_from)
        if date_to:
            query = query.filter(Campaign.created_at <= date_to)
        return query

    def _log_query(
        self, db: Session, user_id: int | None, campaign_id: int | None,
        date_from: datetime | None, date_to: datetime | None,
    ) -> Query:
        query = db.query(EmailLog)
        if user_id:
            query = query.filter(EmailLog.sender_user_id == user_id)
        if campaign_id:
            query = query.filter(EmailLog.campaign_id == campaign_id)
        if date_from:
            query = query.filter(EmailLog.sent_at >= date_from)
        if date_to:
            query = query.filter(EmailLog.sent_at <= date_to)
        return query

    def _suppression_query(
        self, db: Session, user_id: int | None, campaign_id: int | None,
        date_from: datetime | None, date_to: datetime | None,
    ) -> Query:
        query = db.query(SuppressionEntry)
        if campaign_id:
            query = query.filter(SuppressionEntry.campaign_id == campaign_id)
        elif user_id:
            owned_ids = [c.id for c in db.query(Campaign.id).filter(Campaign.user_id == user_id).all()]
            query = query.filter(SuppressionEntry.campaign_id.in_(owned_ids))
        if date_from:
            query = query.filter(SuppressionEntry.created_at >= date_from)
        if date_to:
            query = query.filter(SuppressionEntry.created_at <= date_to)
        return query

    def get_stats(
        self, db: Session, user_id: int | None = None, campaign_id: int | None = None,
        date_from: datetime | None = None, date_to: datetime | None = None,
    ) -> dict:
        """Aggregate dashboard statistics from database."""
        campaign_q = self._campaign_query(db, user_id, campaign_id, date_from, date_to)
        total_campaigns = campaign_q.count()
        active_campaigns = campaign_q.filter(Campaign.status == "active").count()

        log_q = self._log_query(db, user_id, campaign_id, date_from, date_to)
        sent_count = log_q.filter(EmailLog.status == "sent").count()
        failed_count = log_q.filter(EmailLog.status == "failed").count()
        pending_count = log_q.filter(EmailLog.status == "pending").count()

        ai_templates_q = db.query(Template).filter(Template.type == "ai")
        if campaign_id:
            ai_templates_q = ai_templates_q.filter(Template.campaign_id == campaign_id)
        elif user_id:
            owned_ids = [c.id for c in db.query(Campaign.id).filter(Campaign.user_id == user_id).all()]
            ai_templates_q = ai_templates_q.filter(Template.campaign_id.in_(owned_ids))
        if date_from:
            ai_templates_q = ai_templates_q.filter(Template.created_at >= date_from)
        if date_to:
            ai_templates_q = ai_templates_q.filter(Template.created_at <= date_to)
        ai_templates = ai_templates_q.count()

        supp_q = self._suppression_query(db, user_id, campaign_id, date_from, date_to)
        hard_bounces = supp_q.filter(
            SuppressionEntry.reason == "hard_bounce", SuppressionEntry.overridden_at.is_(None)
        ).count()
        # Soft-bounce-pending is a standing recipient attribute, not tied to
        # any one campaign or sender, so it's left unfiltered — always the
        # system-wide count regardless of the active filters.
        soft_bounces_pending = (
            db.query(Recipient)
            .filter(Recipient.soft_bounce_count > 0, Recipient.is_suppressed == False)  # noqa: E712
            .count()
        )
        bounced_suppressions = supp_q.filter(
            SuppressionEntry.reason.in_(["hard_bounce", "soft_bounce_threshold_exceeded"]),
            SuppressionEntry.overridden_at.is_(None),
        ).count()
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

    def get_emails_per_day(
        self, db: Session, user_id: int | None = None, campaign_id: int | None = None,
        date_from: datetime | None = None, date_to: datetime | None = None,
    ) -> list[dict]:
        """Get email send counts per day. Defaults to the last 7 days when no
        date range is given; otherwise breaks out the given range day by day
        (capped at MAX_EMAILS_PER_DAY_SPAN days)."""
        if date_from and date_to:
            start_date = date_from.date()
            end_date = date_to.date()
            if (end_date - start_date).days >= MAX_EMAILS_PER_DAY_SPAN:
                start_date = end_date - timedelta(days=MAX_EMAILS_PER_DAY_SPAN - 1)
        else:
            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(days=6)

        results = []
        day = start_date
        while day <= end_date:
            count = (
                self._log_query(db, user_id, campaign_id, None, None)
                .filter(func.date(EmailLog.sent_at) == day, EmailLog.status == "sent")
                .count()
            )
            results.append({"date": day.strftime("%b %d"), "count": count})
            day += timedelta(days=1)

        return results

    def get_campaign_status_breakdown(
        self, db: Session, user_id: int | None = None, campaign_id: int | None = None,
        date_from: datetime | None = None, date_to: datetime | None = None,
    ) -> list[dict]:
        """Get campaign count grouped by status."""
        campaign_q = self._campaign_query(db, user_id, campaign_id, date_from, date_to)
        statuses = ["draft", "active", "completed", "paused"]
        results = []
        for status in statuses:
            count = campaign_q.filter(Campaign.status == status).count()
            results.append({"status": status.capitalize(), "count": count})
        return results

    def get_recent_activity(
        self, db: Session, limit: int = 5, user_id: int | None = None, campaign_id: int | None = None,
        date_from: datetime | None = None, date_to: datetime | None = None,
    ) -> list[dict]:
        """Build recent activity feed from email logs and campaigns."""
        activities = []

        recent_logs = (
            self._log_query(db, user_id, campaign_id, date_from, date_to)
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
                self._campaign_query(db, user_id, campaign_id, date_from, date_to)
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

    def get_recent_campaigns(
        self, db: Session, limit: int = 5, user_id: int | None = None, campaign_id: int | None = None,
        date_from: datetime | None = None, date_to: datetime | None = None,
    ) -> list[dict]:
        campaigns = (
            self._campaign_query(db, user_id, campaign_id, date_from, date_to)
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

    def get_full_dashboard(
        self, db: Session, user_id: int | None = None, campaign_id: int | None = None,
        date_from: datetime | None = None, date_to: datetime | None = None,
    ) -> dict:
        return {
            "stats": self.get_stats(db, user_id, campaign_id, date_from, date_to),
            "emails_per_day": self.get_emails_per_day(db, user_id, campaign_id, date_from, date_to),
            "campaign_status": self.get_campaign_status_breakdown(db, user_id, campaign_id, date_from, date_to),
            "recent_activity": self.get_recent_activity(db, 5, user_id, campaign_id, date_from, date_to),
            "recent_campaigns": self.get_recent_campaigns(db, 5, user_id, campaign_id, date_from, date_to),
        }

    def build_report_workbook(
        self, db: Session, user_id: int | None = None, campaign_id: int | None = None,
        date_from: datetime | None = None, date_to: datetime | None = None,
    ) -> bytes:
        """Multi-sheet Excel export for the Dashboard's "Export Report"
        button — one sheet each for summary stats, campaigns, prospects, and
        email send history, so a single download covers all the reportable
        data instead of requiring a separate export per page. Respects the
        same filters as the on-screen dashboard; the Prospects sheet is left
        unfiltered since a prospect isn't inherently scoped to one campaign
        or sender."""
        stats = self.get_stats(db, user_id, campaign_id, date_from, date_to)
        campaign_status = self.get_campaign_status_breakdown(db, user_id, campaign_id, date_from, date_to)
        summary_rows = [{"Metric": key.replace("_", " ").title(), "Value": value} for key, value in stats.items()]
        summary_rows += [{"Metric": f"{row['status']} Campaigns", "Value": row["count"]} for row in campaign_status]

        campaigns = (
            self._campaign_query(db, user_id, campaign_id, date_from, date_to)
            .order_by(Campaign.created_at.desc())
            .all()
        )
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

        logs_query = db.query(EmailLog, Campaign, Recipient).join(
            Campaign, Campaign.id == EmailLog.campaign_id
        ).join(Recipient, Recipient.id == EmailLog.recipient_id)
        if user_id:
            logs_query = logs_query.filter(EmailLog.sender_user_id == user_id)
        if campaign_id:
            logs_query = logs_query.filter(EmailLog.campaign_id == campaign_id)
        if date_from:
            logs_query = logs_query.filter(EmailLog.sent_at >= date_from)
        if date_to:
            logs_query = logs_query.filter(EmailLog.sent_at <= date_to)
        logs = logs_query.order_by(EmailLog.sent_at.desc()).all()
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
