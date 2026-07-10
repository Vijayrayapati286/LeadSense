"""Pydantic schemas for request/response validation."""

from datetime import date, datetime
from typing import Any, Literal

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


class DevLoginRequest(BaseModel):
    email: str | None = None
    name: str | None = None


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

    # ── Extended recipient sheet fields ──────────────────────────────────
    create_date: date | None = None
    fresh_mail: str | None = None
    follow_up_1: str | None = None
    follow_up_2: str | None = None
    follow_up_3: str | None = None
    grouping: str | None = None
    vertical: str | None = None
    sub_vertical: str | None = None
    revenue: str | None = None
    revenue_range: str | None = None
    website: str | None = None
    state: str | None = None
    region: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    designation_level: str | None = None
    contact_location: str | None = None
    campaign_tag: str | None = None
    linkedin_message: str | None = None
    linkedin_connection_request: str | None = None
    response_1: str | None = None
    response_2: str | None = None
    status: str | None = None
    comments: str | None = None

    # ── Suppression / advanced-search fields ──────────────────────────────
    is_suppressed: bool = False
    suppression_reason: str | None = None
    department: str | None = None
    company_size: str | None = None
    years_of_experience: str | None = None
    skills: str | None = None
    country: str | None = None
    city: str | None = None
    source: str | None = None


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
    group_name: str | None = None


# ── Suppression / Blacklist ───────────────────────────────────────────────────

SuppressionReason = Literal[
    "hard_bounce", "domain_rejected", "mail_server_blocked", "complaint", "manual"
]


class SuppressionEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    company: str | None
    reason: str
    campaign_id: int | None
    campaign_name: str | None = None
    recipient_id: int | None
    detail: str | None
    created_at: datetime


class SuppressionEntryListResponse(BaseModel):
    items: list[SuppressionEntryResponse]
    total: int
    page: int
    page_size: int


class SimulateEventRequest(BaseModel):
    email: str
    event_type: Literal["bounce", "complaint", "reply"]
    bounce_type: Literal["Permanent", "Transient"] = "Permanent"
    campaign_id: int | None = None


# ── Recipient Groups ───────────────────────────────────────────────────────────

class RecipientGroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class RecipientGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class RecipientGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime
    prospect_count: int = 0


class AddGroupMembersRequest(BaseModel):
    recipient_ids: list[int]


# ── Tags ───────────────────────────────────────────────────────────────────────

class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class TagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    recipient_count: int = 0


class AssignTagRequest(BaseModel):
    recipient_ids: list[int]


# ── Saved Searches ─────────────────────────────────────────────────────────────

class SavedSearchCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    filters: dict[str, Any]


class SavedSearchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    filters: dict[str, Any]
    created_at: datetime


# ── Campaign Recipient Tracking ───────────────────────────────────────────────

CampaignRecipientStatus = Literal[
    "not_contacted", "sent", "delivered", "opened", "clicked",
    "replied", "bounced", "invalid_email", "suppressed",
]


class CampaignRecipientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    recipient_id: int
    status: str
    current_stage: int
    next_send_at: datetime | None
    last_sent_at: datetime | None
    replied_at: datetime | None
    bounced_at: datetime | None
    recipient_name: str | None = None
    recipient_email: str | None = None
    recipient_company: str | None = None


class CampaignRecipientListResponse(BaseModel):
    items: list[CampaignRecipientResponse]
    total: int


# ── Campaign Sequence Stages ───────────────────────────────────────────────────

DelayUnit = Literal["minutes", "hours", "days"]


class CampaignSequenceStageCreate(BaseModel):
    stage_order: int = Field(..., ge=1)
    delay_value: int = Field(..., ge=1)
    delay_unit: DelayUnit = "days"
    subject: str
    body: str
    closing: str | None = None
    cta: str | None = None


class CampaignSequenceStageUpdate(BaseModel):
    delay_value: int | None = None
    delay_unit: DelayUnit | None = None
    subject: str | None = None
    body: str | None = None
    closing: str | None = None
    cta: str | None = None


class CampaignSequenceStageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    stage_order: int
    delay_value: int
    delay_unit: str
    subject: str
    body: str
    closing: str | None
    cta: str | None


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
    skipped_suppressed: int = 0


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
