"""SQLAlchemy ORM models."""

from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    department: Mapped[str] = mapped_column(String(255), default="Sales")
    azure_oid: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    campaigns: Mapped[list["Campaign"]] = relationship("Campaign", back_populates="owner_user")


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    campaign_name: Mapped[str] = mapped_column(String(255), nullable=False)
    campaign_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_audience: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="draft", index=True)
    emails_sent: Mapped[int] = mapped_column(Integer, default=0)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # ── Scheduling ─────────────────────────────────────────────────────────
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    use_recipient_timezone: Mapped[bool] = mapped_column(Boolean, default=False)

    owner_user: Mapped["User | None"] = relationship("User", back_populates="campaigns")
    templates: Mapped[list["Template"]] = relationship(
        "Template", back_populates="campaign", cascade="all, delete-orphan"
    )
    email_logs: Mapped[list["EmailLog"]] = relationship(
        "EmailLog", back_populates="campaign", cascade="all, delete-orphan"
    )
    campaign_recipients: Mapped[list["CampaignRecipient"]] = relationship(
        "CampaignRecipient", back_populates="campaign", cascade="all, delete-orphan"
    )
    sequence_stages: Mapped[list["CampaignSequenceStage"]] = relationship(
        "CampaignSequenceStage", back_populates="campaign", cascade="all, delete-orphan",
        order_by="CampaignSequenceStage.stage_order",
    )


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    campaign_id: Mapped[int] = mapped_column(Integer, ForeignKey("campaigns.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # manual, placeholder, ai
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    closing: Mapped[str | None] = mapped_column(Text, nullable=True)
    cta: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="templates")


class Mailer(Base):
    """A reusable, named email template — independent of any single campaign,
    unlike Template (which is deleted/recreated per campaign). Save once,
    search/reuse across future campaigns."""

    __tablename__ = "mailers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # manual, placeholder, ai
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    closing: Mapped[str | None] = mapped_column(Text, nullable=True)
    cta: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Recipient(Base):
    __tablename__ = "recipients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # ── Extended recipient sheet fields ──────────────────────────────────
    create_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    fresh_mail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    follow_up_1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    follow_up_2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    follow_up_3: Mapped[str | None] = mapped_column(String(255), nullable=True)
    grouping: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vertical: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sub_vertical: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revenue: Mapped[str | None] = mapped_column(String(100), nullable=True)
    revenue_range: Mapped[str | None] = mapped_column(String(100), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    designation_level: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    campaign_tag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linkedin_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_connection_request: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    response_2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Suppression / blacklist ───────────────────────────────────────────
    is_suppressed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    suppression_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    soft_bounce_count: Mapped[int] = mapped_column(Integer, default=0)

    # ── Manual response tagging ───────────────────────────────────────────
    response_tag: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)  # Cold, Negative, Warm, Hot

    # ── Advanced-search fields ────────────────────────────────────────────
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(100), nullable=True)
    years_of_experience: Mapped[str | None] = mapped_column(String(100), nullable=True)
    skills: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)  # IANA name, e.g. "Asia/Kolkata"

    email_logs: Mapped[list["EmailLog"]] = relationship("EmailLog", back_populates="recipient")
    group_memberships: Mapped[list["RecipientGroupMember"]] = relationship(
        "RecipientGroupMember", back_populates="recipient", cascade="all, delete-orphan"
    )
    campaign_links: Mapped[list["CampaignRecipient"]] = relationship(
        "CampaignRecipient", back_populates="recipient", cascade="all, delete-orphan"
    )
    tag_links: Mapped[list["RecipientTag"]] = relationship(
        "RecipientTag", back_populates="recipient", cascade="all, delete-orphan"
    )


class SuppressionEntry(Base):
    """Blacklist audit log. Rows are never edited or hard-deleted — an admin
    override sets `overridden_at` instead, so the historical record (why an
    address was suppressed, and that it was later manually cleared) survives.
    An entry is "currently active" iff `overridden_at is None`."""

    __tablename__ = "suppression_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)  # hard_bounce, soft_bounce_threshold_exceeded, domain_rejected, mail_server_blocked, complaint, manual
    bounce_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # Permanent, Transient
    smtp_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    campaign_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("campaigns.id"), nullable=True)
    recipient_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("recipients.id"), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    campaign: Mapped["Campaign | None"] = relationship("Campaign")
    recipient: Mapped["Recipient | None"] = relationship("Recipient")


class RecipientGroup(Base):
    __tablename__ = "recipient_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    members: Mapped[list["RecipientGroupMember"]] = relationship(
        "RecipientGroupMember", back_populates="group", cascade="all, delete-orphan"
    )


class RecipientGroupMember(Base):
    __tablename__ = "recipient_group_members"

    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("recipient_groups.id"), primary_key=True)
    recipient_id: Mapped[int] = mapped_column(Integer, ForeignKey("recipients.id"), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    group: Mapped["RecipientGroup"] = relationship("RecipientGroup", back_populates="members")
    recipient: Mapped["Recipient"] = relationship("Recipient", back_populates="group_memberships")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    recipient_links: Mapped[list["RecipientTag"]] = relationship(
        "RecipientTag", back_populates="tag", cascade="all, delete-orphan"
    )


class RecipientTag(Base):
    __tablename__ = "recipient_tags"

    recipient_id: Mapped[int] = mapped_column(Integer, ForeignKey("recipients.id"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey("tags.id"), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    recipient: Mapped["Recipient"] = relationship("Recipient", back_populates="tag_links")
    tag: Mapped["Tag"] = relationship("Tag", back_populates="recipient_links")


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    filters: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-serialized filter dict
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CampaignRecipient(Base):
    """Per-campaign, per-recipient tracking row — the join that lets a recipient's
    status/sequence-progress be tracked distinctly within each campaign."""

    __tablename__ = "campaign_recipients"
    __table_args__ = (UniqueConstraint("campaign_id", "recipient_id", name="uq_campaign_recipient"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    campaign_id: Mapped[int] = mapped_column(Integer, ForeignKey("campaigns.id"), nullable=False)
    recipient_id: Mapped[int] = mapped_column(Integer, ForeignKey("recipients.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="not_contacted", index=True)
    current_stage: Mapped[int] = mapped_column(Integer, default=0)
    next_send_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bounced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="campaign_recipients")
    recipient: Mapped["Recipient"] = relationship("Recipient", back_populates="campaign_links")


class CampaignSequenceStage(Base):
    """A follow-up stage in a campaign's email sequence. Stage 0 is always the
    campaign's Template row; rows here represent stage_order >= 1 follow-ups."""

    __tablename__ = "campaign_sequence_stages"
    __table_args__ = (UniqueConstraint("campaign_id", "stage_order", name="uq_campaign_stage_order"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    campaign_id: Mapped[int] = mapped_column(Integer, ForeignKey("campaigns.id"), nullable=False)
    stage_order: Mapped[int] = mapped_column(Integer, nullable=False)
    delay_value: Mapped[int] = mapped_column(Integer, nullable=False)
    delay_unit: Mapped[str] = mapped_column(String(20), default="days")  # minutes, hours, days
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    closing: Mapped[str | None] = mapped_column(Text, nullable=True)
    cta: Mapped[str | None] = mapped_column(String(500), nullable=True)

    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="sequence_stages")


class AppSetting(Base):
    """Single-row table (id is always 1) holding runtime-configurable
    deliverability settings, so they can be changed from Settings without a
    server restart or env var edit."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    soft_bounce_threshold: Mapped[int] = mapped_column(Integer, default=3)
    send_interval_seconds: Mapped[int] = mapped_column(Integer, default=12)
    suppress_on_tags: Mapped[str] = mapped_column(Text, default="[]")  # JSON list, e.g. ["Negative", "Cold"]


class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    campaign_id: Mapped[int] = mapped_column(Integer, ForeignKey("campaigns.id"), nullable=False)
    recipient_id: Mapped[int] = mapped_column(Integer, ForeignKey("recipients.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # sent, failed, pending
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="email_logs")
    recipient: Mapped["Recipient"] = relationship("Recipient", back_populates="email_logs")
