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
    progress_percent: int = 0
    total_profiles: int
    processed_profiles: int
    successful_profiles: int
    failed_profiles: int
    total_batches: int
    completed_batches: int
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
    error: str | None = None
    uploaded: dict = Field(default_factory=dict)
    extracted: dict = Field(default_factory=dict)
    name_match: bool | None = None
    designation_match: bool | None = None
    company_match: bool | None = None
    location_match: bool | None = None
    verification_status: str | None = None
    verification_score: int = 0
    verification_reason: str | None = None


class BulkJobResultsResponse(BaseModel):
    job_id: str
    items: list[BulkJobResultItem]
