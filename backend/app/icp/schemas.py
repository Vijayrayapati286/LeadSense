"""Pydantic schemas for ICP Database API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class IcpRecordCreate(BaseModel):
    name: str | None = None
    email: str | None = None
    company_name: str | None = None
    designation: str | None = None
    about: str | None = None
    linkedin_url: str | None = None
    industry: str | None = None
    company_size: str | None = None
    location: str | None = None
    company_website: str | None = None
    icp_status: str | None = "verified"
    icp_score: int | None = None
    tags: list[str] | None = None


class IcpRecordUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    company_name: str | None = None
    company: str | None = None
    designation: str | None = None
    about: str | None = None
    linkedin_url: str | None = None
    industry: str | None = None
    company_size: str | None = None
    location: str | None = None
    company_website: str | None = None
    icp_status: str | None = None
    icp_score: int | None = None
    tags: list[str] | None = None


class IcpRecordResponse(BaseModel):
    id: int
    user_id: int | None = None
    name: str | None = None
    email: str | None = None
    company_name: str | None = None
    designation: str | None = None
    about: str | None = None
    linkedin_url: str | None = None
    industry: str | None = None
    company_size: str | None = None
    location: str | None = None
    company_website: str | None = None
    icp_status: str
    icp_score: int | None = None
    tags: list[Any] = Field(default_factory=list)
    verification_status: str
    verified_at: str | None = None
    source: str
    source_record_id: int | None = None
    source_job_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class IcpListResponse(BaseModel):
    items: list[IcpRecordResponse]
    total: int
    page: int
    page_size: int


class IcpAccountSummary(BaseModel):
    company_name: str
    industry: str | None = None
    company_size: str | None = None
    location: str | None = None
    company_website: str | None = None
    contact_count: int
    status: str = "active"


class IcpAccountListResponse(BaseModel):
    items: list[IcpAccountSummary]
    total: int
    page: int
    page_size: int
