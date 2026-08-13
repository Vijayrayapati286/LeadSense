"""Request / response schemas for Profile Extractor v1."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProfileExtractRequest(BaseModel):
    url: str = Field(..., min_length=12, description="Public LinkedIn /in/ profile URL")


class ProfileExtractQueuedResponse(BaseModel):
    job_id: str
    status: Literal["queued", "completed"] = "queued"


class ProfileData(BaseModel):
    full_name: str | None = None
    company: str | None = None
    designation: str | None = None
    about: str | None = None


class ProfileJobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "completed", "failed"]
    profile_url: str | None = None
    result: ProfileData | None = None
    download_url: str | None = None
    error: str | None = None
    cached: bool = False
