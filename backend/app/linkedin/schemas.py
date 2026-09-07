"""Request / response models for LinkedIn Profile Extractor."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProfileExtractRequest(BaseModel):
    url: str = Field(..., min_length=12, description="LinkedIn /in/ profile URL")


class ProfileExtractResponse(BaseModel):
    full_name: str | None = None
    company: str | None = None
    job_title: str | None = None
    about: str | None = None
    excel_file: str
    source: Literal["playwright", "apify"] | None = None


class LinkedInExtractRequest(BaseModel):
    url: str = Field(..., min_length=12, description="LinkedIn /in/ profile URL")


class LinkedInExtractData(BaseModel):
    name: str = ""
    headline: str = ""
    company: str = ""
    job_title: str = ""
    location: str = ""
    summary: str = ""
    followers: int = 0
    connections: int = 0
    image: str = ""
    profile_url: str = ""


class LinkedInExtractResponse(BaseModel):
    success: bool
    data: LinkedInExtractData | None = None
    message: str | None = None


class JobCreateResponse(BaseModel):
    job_id: str
    status: Literal["pending", "running", "done", "failed"] = "pending"


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["pending", "running", "done", "failed"]
    result: ProfileExtractResponse | None = None
    error: str | None = None


class BulkJobCreateResponse(BaseModel):
    job_id: str
    status: Literal["pending"] = "pending"
    total: int


class BulkJobStatusResponse(BaseModel):
    job_id: str
    status: Literal["pending", "running", "done", "failed"]
    phase: str = "uploading"
    total: int
    completed: int
    failed: int
    retrying: int = 0
    processed: int = 0
    success: int = 0
    verified: int = 0
    mismatched: int = 0
    review: int = 0
    needs_review: int = 0
    resolved: int = 0
    backup_status: str = "none"
    original_file_name: str | None = None
    progress_percent: int = 0
    total_profiles: int
    processed_profiles: int
    successful_profiles: int
    failed_profiles: int
    total_batches: int
    completed_batches: int
    created_at: str | None = None
    updated_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    excel_file: str | None = None
    download_ready: bool = False
    error: str | None = None


class BulkJobResultItem(BaseModel):
    item_id: int
    source_row_number: int
    url: str | None = None
    extraction_status: str
    attempt_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    uploaded_raw: dict = Field(default_factory=dict)
    uploaded: dict = Field(default_factory=dict)
    extracted: dict = Field(default_factory=dict)
    name_match: bool | None = None
    designation_match: bool | None = None
    company_match: bool | None = None
    location_match: bool | None = None
    company_location_match: bool | None = None
    verification_status: str | None = None
    verification_score: int = 0
    verification_reason: str | None = None
    resolved: dict = Field(default_factory=dict)
    resolution_summary: str | None = None
    needs_review: bool = False


class BulkJobResultsResponse(BaseModel):
    job_id: str
    items: list[BulkJobResultItem]


class BulkJobListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[BulkJobStatusResponse]


class BulkJobItemsPageResponse(BaseModel):
    job_id: str
    total: int
    page: int
    page_size: int
    items: list[BulkJobResultItem]


class ConflictFieldDecision(BaseModel):
    field: str
    resolution: Literal[
        "KEEP_UPLOADED",
        "KEEP_EXISTING",
        "KEEP_EXTRACTED",
        "MANUAL_EDIT",
        "MARK_REVIEW",
    ]
    edited_value: str | None = None


class ConflictResolveRequest(BaseModel):
    decisions: list[ConflictFieldDecision]


class ConflictBulkResolveRequest(BaseModel):
    item_ids: list[int]
    decisions: list[ConflictFieldDecision]
    confirm: bool = False


class BackupCreateResponse(BaseModel):
    backup_id: int
    job_id: str
    status: str
    file_path: str | None = None


class BackupListItem(BaseModel):
    id: int
    job_id: str
    backup_version: int
    status: str
    file_path: str
    created_at: str | None = None
    original_file_name: str | None = None


class BackupListResponse(BaseModel):
    total: int
    items: list[BackupListItem]


class BackupRestoreResponse(BaseModel):
    job_id: str
    status: str
    total: int
    message: str = "Backup restored as a new job"
