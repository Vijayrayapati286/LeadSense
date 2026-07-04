"""SQLAlchemy ORM models."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
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

    owner_user: Mapped["User | None"] = relationship("User", back_populates="campaigns")
    templates: Mapped[list["Template"]] = relationship(
        "Template", back_populates="campaign", cascade="all, delete-orphan"
    )
    email_logs: Mapped[list["EmailLog"]] = relationship(
        "EmailLog", back_populates="campaign", cascade="all, delete-orphan"
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

    email_logs: Mapped[list["EmailLog"]] = relationship("EmailLog", back_populates="recipient")


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
