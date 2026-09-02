"""Pydantic schemas for Offerings API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OfferingVoucherMeta(BaseModel):
    file_id: int
    filename: str
    file_size: int = 0
    mime_type: str | None = None
    uploaded_at: str | None = None


class OfferingEmailTemplateMeta(BaseModel):
    name: str = "Introduction Outreach"
    subject: str
    body: str
    source_filename: str | None = None
    uploaded_at: str | None = None
    source: str | None = None  # ai_generated | upload


class OfferingCreate(BaseModel):
    name: str
    short_description: str | None = None
    description: str | None = None
    product_type: str | None = None
    website_url: str | None = None
    pricing_range: str | None = None
    hard_filter_rules: dict[str, Any] | None = None
    target_industries: list[str] | None = None
    company_size_min: int | None = None
    company_size_max: int | None = None
    company_size_label: str | None = None
    revenue_min: int | None = None
    revenue_max: int | None = None
    target_geographies: list[str] | None = None
    business_models: list[str] | None = None
    target_departments: list[str] | None = None
    target_job_titles: list[str] | None = None
    target_seniority: list[str] | None = None
    decision_maker_types: list[str] | None = None
    buying_roles: list[str] | None = None
    buyer_personas: list[Any] | None = None
    pain_points: list[str] | None = None
    business_problems: list[str] | None = None
    current_challenges: list[str] | None = None
    use_cases: list[str] | None = None
    desired_outcomes: list[str] | None = None
    benefits: list[str] | None = None
    must_have_rules: list[str] | None = None
    nice_to_have_rules: list[str] | None = None
    exclusion_rules: list[str] | None = None
    positive_keywords: list[str] | None = None
    negative_keywords: list[str] | None = None
    vouchers: list[OfferingVoucherMeta] | None = None
    email_template: OfferingEmailTemplateMeta | None = None
    status: str | None = "active"


class OfferingUpdate(OfferingCreate):
    name: str | None = None


class OfferingResponse(BaseModel):
    id: int
    user_id: int | None = None
    name: str
    short_description: str | None = None
    description: str | None = None
    product_type: str | None = None
    website_url: str | None = None
    pricing_range: str | None = None
    hard_filter_rules: dict[str, Any] = Field(default_factory=dict)
    profile_text: str | None = None
    target_industries: list[Any] = Field(default_factory=list)
    company_size_min: int | None = None
    company_size_max: int | None = None
    company_size_label: str | None = None
    revenue_min: int | None = None
    revenue_max: int | None = None
    target_geographies: list[Any] = Field(default_factory=list)
    business_models: list[Any] = Field(default_factory=list)
    target_departments: list[Any] = Field(default_factory=list)
    target_job_titles: list[Any] = Field(default_factory=list)
    target_seniority: list[Any] = Field(default_factory=list)
    decision_maker_types: list[Any] = Field(default_factory=list)
    buying_roles: list[Any] = Field(default_factory=list)
    buyer_personas: list[Any] = Field(default_factory=list)
    pain_points: list[Any] = Field(default_factory=list)
    business_problems: list[Any] = Field(default_factory=list)
    current_challenges: list[Any] = Field(default_factory=list)
    use_cases: list[Any] = Field(default_factory=list)
    desired_outcomes: list[Any] = Field(default_factory=list)
    benefits: list[Any] = Field(default_factory=list)
    must_have_rules: list[Any] = Field(default_factory=list)
    nice_to_have_rules: list[Any] = Field(default_factory=list)
    exclusion_rules: list[Any] = Field(default_factory=list)
    positive_keywords: list[Any] = Field(default_factory=list)
    negative_keywords: list[Any] = Field(default_factory=list)
    vouchers: list[OfferingVoucherMeta] = Field(default_factory=list)
    email_template: OfferingEmailTemplateMeta | None = None
    status: str
    definition_version: int
    definition_hash: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    # list summary stats (optional)
    total_matches: int | None = None
    strong_matches: int | None = None
    potential_matches: int | None = None
    approved_matches: int | None = None


class OfferingListResponse(BaseModel):
    items: list[OfferingResponse]
    total: int
    page: int
    page_size: int


class GenerateIcpRequest(BaseModel):
    description: str = Field(..., min_length=10)


class GenerateOfferingEmailRequest(BaseModel):
    """Offering context used to generate outreach email variants."""

    name: str = Field(..., min_length=1)
    short_description: str | None = None
    description: str | None = None
    product_type: str | None = None
    target_industries: list[str] = Field(default_factory=list)
    target_job_titles: list[str] = Field(default_factory=list)
    target_geographies: list[str] = Field(default_factory=list)
    company_size_label: str | None = None
    pain_points: list[str] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    desired_outcomes: list[str] = Field(default_factory=list)
    decision_maker_types: list[str] = Field(default_factory=list)
    buying_roles: list[str] = Field(default_factory=list)
    tone: str = "formal"
    additional_context: str | None = None
    count: int = Field(default=3, ge=2, le=3)


class OfferingEmailVersion(BaseModel):
    angle: str
    subject: str
    body: str
    closing: str = ""
    cta: str = ""


class GenerateOfferingEmailResponse(BaseModel):
    versions: list[OfferingEmailVersion]
    is_mock: bool = False


class CompanySizeHint(BaseModel):
    min: int | None = None
    max: int | None = None
    label: str | None = None


class GeneratedIcpPayload(BaseModel):
    industries: list[str] = Field(default_factory=list)
    company_size: CompanySizeHint = Field(default_factory=CompanySizeHint)
    departments: list[str] = Field(default_factory=list)
    job_titles: list[str] = Field(default_factory=list)
    seniority: list[str] = Field(default_factory=list)
    geographies: list[str] = Field(default_factory=list)
    business_models: list[str] = Field(default_factory=list)
    decision_maker_types: list[str] = Field(default_factory=list)
    buying_roles: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    business_problems: list[str] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    desired_outcomes: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    positive_keywords: list[str] = Field(default_factory=list)
    negative_keywords: list[str] = Field(default_factory=list)
    must_have_rules: list[str] = Field(default_factory=list)
    nice_to_have_rules: list[str] = Field(default_factory=list)
    exclusion_rules: list[str] = Field(default_factory=list)
    suggested_name: str | None = None
    short_description: str | None = None
    description: str | None = None
    product_type: str | None = None
    pricing_range: str | None = None
    is_mock: bool = False


class MatchReasonBreakdown(BaseModel):
    score: int = 0
    max: int = 0
    reason: str = ""
    matched: bool = False


class OfferingMatchResponse(BaseModel):
    id: int
    offering_id: int
    icp_record_id: int
    fit_score: int
    industry_score: int
    job_title_score: int
    department_score: int
    company_size_score: int
    pain_use_case_score: int
    seniority_score: int
    buying_signal_score: int
    icp_fit_score: int = 0
    problem_fit_score: int = 0
    role_fit_score: int = 0
    company_fit_score: int = 0
    historical_score: int = 70
    semantic_similarity: int = 0
    missing_information: list[Any] = Field(default_factory=list)
    explanation: str | None = None
    match_tier: str
    match_reasons: list[Any] = Field(default_factory=list)
    ai_analysis: dict[str, Any] | None = None
    status: str
    offering_definition_version: int
    reviewed_by: int | None = None
    reviewed_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    # joined ICP fields
    name: str | None = None
    company_name: str | None = None
    designation: str | None = None
    industry: str | None = None
    company_size: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    about: str | None = None
    icp_verification_status: str | None = None


class OfferingMatchListResponse(BaseModel):
    items: list[OfferingMatchResponse]
    total: int
    page: int
    page_size: int


class MatchStatusUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None


class PrepareCampaignRecipientsRequest(BaseModel):
    match_ids: list[int] = Field(default_factory=list)
    icp_record_ids: list[int] = Field(default_factory=list)
    campaign_id: int
    group_name: str | None = None


class PrepareCampaignRecipientsSkipped(BaseModel):
    name: str
    reason: str


class PrepareCampaignRecipientsResponse(BaseModel):
    recipient_ids: list[int] = Field(default_factory=list)
    tagged: int = 0
    skipped: list[PrepareCampaignRecipientsSkipped] = Field(default_factory=list)


class OfferingStatsResponse(BaseModel):
    total_candidates: int = 0
    strong_matches: int = 0
    potential_matches: int = 0
    poor_matches: int = 0
    approved: int = 0
    rejected: int = 0
    pending_review: int = 0
    needs_review: int = 0


class MatchingJobStatusResponse(BaseModel):
    job_id: str | None = None
    status: str
    total_count: int = 0
    processed_count: int = 0
    strong_count: int = 0
    potential_count: int = 0
    poor_count: int = 0
    error_count: int = 0
    percent: int = 0
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class SemanticMatchEvidence(BaseModel):
    pain_use_case_score: int = Field(ge=0, le=100, default=0)
    pain_use_case_reason: str = ""
    buying_signal_score: int = Field(ge=0, le=100, default=0)
    buying_signal_reason: str = ""
    job_title_boost: int = Field(ge=0, le=30, default=0)
    job_title_reason: str = ""


class RecommendationFeedbackCreate(BaseModel):
    action: str = Field(..., min_length=2, max_length=32)
    notes: str | None = None


class RecommendationFeedbackResponse(BaseModel):
    id: int
    recommendation_id: int
    offering_id: int
    icp_record_id: int
    action: str
    score_at_action: int | None = None
    created_at: str | None = None
