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
