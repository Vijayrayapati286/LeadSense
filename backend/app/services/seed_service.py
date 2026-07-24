"""Seed database with sample data for development."""

from datetime import datetime, timedelta
import random

from sqlalchemy.orm import Session

from app.models import Campaign, EmailLog, Recipient, Template, User
from app.services.auth_service import AuthService

# Named team members provisioned with a set password for email+password login
# (POST /auth/login) — distinct from the unauthenticated dev-login fallback.
# Passwords are fixed here (not randomly generated per boot) so they stay
# reproducible across DB resets; only the bcrypt hash is ever persisted.
CORE_USERS = [
    ("Veerendra Chowhan", "veerendra.chowhan@feuji.com", "Xh9bKDNz2w#"),
    ("Srikanth Reddy", "srikanth.k@feuji.com", "ussi0pKoDa%"),
    ("Preeti Gupta", "preeti.gupta@feuji.com", "vuU7RYNesA!"),
    ("Ramya Pinnika", "ramya.pinnika@feuji.com", "ePUh0uGsT2%"),
    ("Ramya Swathi", "ramya.pasupuleti@feuji.com", "Ofc4mHbQUu$"),
    ("Roshan Shenisetty", "roshan.shenishetty@feuji.com", "yZFQ0d7rUz%"),
    ("Srinivas Reddy", "sreenivas.jetningu@feuji.com", "99SvEkJTwp$"),
]


def provision_core_users(db: Session) -> None:
    """Get-or-create each named team member and (re)set their password hash —
    idempotent, safe to run on every startup, independent of the dummy demo
    data seed below."""
    for name, email, password in CORE_USERS:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(name=name, email=email, department="Sales")
            db.add(user)
        else:
            user.name = name
        user.password_hash = AuthService.hash_password(password)
    db.commit()


def seed_dummy_data(db: Session) -> None:
    """Populate database with realistic sample data."""

    # Users
    user = User(name="Demo User", email="demo@company.com", department="Sales")
    db.add(user)
    db.flush()

    # Recipients
    recipients_data = [
        ("John Smith", "john.smith@acme.com", "Acme Corp", "CEO", "Technology"),
        ("Jane Doe", "jane.doe@techcorp.io", "TechCorp", "CTO", "Software"),
        ("Robert Johnson", "robert.j@globalinc.com", "Global Inc", "VP Sales", "Finance"),
        ("Emily Chen", "emily.chen@startup.co", "StartupCo", "Founder", "SaaS"),
        ("Michael Brown", "michael.b@enterprise.com", "Enterprise Ltd", "Director", "Manufacturing"),
        ("Sarah Wilson", "sarah.w@innovate.io", "InnovateIO", "CMO", "Marketing"),
        ("David Lee", "david.lee@fintech.com", "FinTech Pro", "CFO", "Finance"),
        ("Lisa Anderson", "lisa.a@healthtech.com", "HealthTech", "COO", "Healthcare"),
        ("James Taylor", "james.t@retailmax.com", "RetailMax", "VP Marketing", "Retail"),
        ("Anna Martinez", "anna.m@cloudsys.com", "CloudSys", "Engineer", "Cloud"),
    ]

    recipients = []
    for name, email, company, designation, industry in recipients_data:
        r = Recipient(
            name=name,
            email=email,
            company=company,
            designation=designation,
            industry=industry,
            is_selected=random.choice([True, False]),
        )
        db.add(r)
        recipients.append(r)
    db.flush()

    # Campaigns
    campaigns_data = [
        ("Q1 Product Launch", "CMP-2024001", "Launch campaign for new product features", "active", 45),
        ("Enterprise Outreach", "CMP-2024002", "Target enterprise clients for upsell", "active", 120),
        ("Holiday Promotion", "CMP-2024003", "End of year promotional campaign", "completed", 200),
        ("Partner Recruitment", "CMP-2024004", "Recruit new channel partners", "draft", 0),
        ("Customer Re-engagement", "CMP-2024005", "Win back inactive customers", "paused", 30),
    ]

    campaigns = []
    for name, cid, desc, status, sent in campaigns_data:
        c = Campaign(
            campaign_name=name,
            campaign_id=cid,
            description=desc,
            owner="Demo User",
            department="Sales",
            target_audience="B2B Decision Makers",
            subject=f"Exclusive offer from {name}",
            status=status,
            emails_sent=sent,
            user_id=user.id,
        )
        db.add(c)
        campaigns.append(c)
    db.flush()

    # Templates
    for i, campaign in enumerate(campaigns[:3]):
        t = Template(
            campaign_id=campaign.id,
            name="Primary Template",
            type=["manual", "placeholder", "ai"][i],
            subject=f"Hello {{{{Name}}}} — Special offer for {{{{Company}}}}",
            body=(
                f"Dear {{{{Name}}}},\n\n"
                f"We noticed {{{{Company}}}} is making strides in the {{{{Industry}}}} sector. "
                f"As {{{{Designation}}}}, you might be interested in our latest solution.\n\n"
                f"Best regards,\nSales Team"
            ),
            closing="Best regards,\nSales Team",
            cta="Schedule a demo",
        )
        db.add(t)

    # Email Logs
    statuses = ["sent", "sent", "sent", "sent", "failed", "pending"]
    for i in range(30):
        campaign = random.choice(campaigns)
        recipient = random.choice(recipients)
        status = random.choice(statuses)
        log = EmailLog(
            campaign_id=campaign.id,
            recipient_id=recipient.id,
            status=status,
            error_message="SMTP connection timeout" if status == "failed" else None,
            sent_at=datetime.utcnow() - timedelta(days=random.randint(0, 14), hours=random.randint(0, 23)),
        )
        db.add(log)

    db.commit()
