"""Pydantic schemas for request/response validation."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    department: str


class AuthCallbackResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ── Dashboard ─────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_campaigns: int
    emails_sent: int
    pending_emails: int
    failed_emails: int
    active_campaigns: int
    ai_generated_emails: int


class DailyEmailStat(BaseModel):
    date: str
    count: int


class CampaignStatusStat(BaseModel):
    status: str
    count: int


class RecentActivity(BaseModel):
    id: int
    action: str
    description: str
    timestamp: str


class RecentCampaign(BaseModel):
    id: int
    campaign_name: str
    campaign_id: str
    owner: str
    status: str
    emails_sent: int
    created_at: str


class DashboardResponse(BaseModel):
    stats: DashboardStats
    emails_per_day: list[DailyEmailStat]
    campaign_status: list[CampaignStatusStat]
    recent_activity: list[RecentActivity]
    recent_campaigns: list[RecentCampaign]


# ── Campaign ──────────────────────────────────────────────────────────────────

class CampaignCreate(BaseModel):
    campaign_name: str = Field(..., min_length=1, max_length=255)
    campaign_id: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    owner: str = Field(..., min_length=1)
    department: str | None = None
    target_audience: str | None = None
    subject: str | None = None
    status: str = "draft"


class CampaignUpdate(BaseModel):
    campaign_name: str | None = None
    description: str | None = None
    owner: str | None = None
    department: str | None = None
    target_audience: str | None = None
    subject: str | None = None
    status: str | None = None


class CampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_name: str
    campaign_id: str
    description: str | None
    owner: str
    department: str | None
    target_audience: str | None
    subject: str | None
    status: str
    emails_sent: int
    created_at: datetime


# ── Template ──────────────────────────────────────────────────────────────────

class TemplateCreate(BaseModel):
    campaign_id: int
    type: str = Field(..., pattern="^(manual|placeholder|ai)$")
    subject: str
    body: str
    closing: str | None = None
    cta: str | None = None


class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    type: str
    subject: str
    body: str
    closing: str | None
    cta: str | None


class AITemplateRequest(BaseModel):
    campaign_name: str
    campaign_description: str | None = None
    target_audience: str | None = None
    tone: str = "formal"
    additional_context: str | None = None


class AITemplateResponse(BaseModel):
    subject: str
    body: str
    closing: str
    cta: str
    is_mock: bool = False


class PreviewTemplateRequest(BaseModel):
    subject: str
    body: str
    recipient_name: str = "John Doe"
    recipient_company: str = "Acme Corp"
    recipient_designation: str = "CEO"
    recipient_industry: str = "Technology"


class PreviewTemplateResponse(BaseModel):
    subject: str
    body: str
    rendered_html: str


# ── Recipient ─────────────────────────────────────────────────────────────────

class RecipientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    company: str | None
    designation: str | None
    industry: str | None
    is_selected: bool


class RecipientListResponse(BaseModel):
    items: list[RecipientResponse]
    total: int
    page: int
    page_size: int
    selected_count: int


class SelectRecipientsRequest(BaseModel):
    recipient_ids: list[int]
    select_all: bool = False
    deselect_all: bool = False


class UploadExcelResponse(BaseModel):
    imported: int
    message: str


# ── Email ─────────────────────────────────────────────────────────────────────

class SendEmailRequest(BaseModel):
    campaign_id: int
    subject: str
    body: str
    recipient_ids: list[int] | None = None


class SendEmailResponse(BaseModel):
    sent: int
    failed: int
    pending: int
    details: list[dict[str, Any]]


# ── Logs ──────────────────────────────────────────────────────────────────────

class EmailLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    recipient_id: int
    status: str
    error_message: str | None
    sent_at: datetime
    recipient_name: str | None = None
    recipient_email: str | None = None
    campaign_name: str | None = None


class EmailLogListResponse(BaseModel):
    items: list[EmailLogResponse]
    total: int
    page: int
    page_size: int


# ── Generic ───────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str
    success: bool = True
