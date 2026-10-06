"""Pydantic schemas for ICP Database API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IcpRecordCreate(BaseModel):
    name: str | None = None
    email: str | None = None
    company_name: str | None = None
    designation: str | None = None
    department: str | None = None
    about: str | None = None
    linkedin_url: str | None = None
    phone: str | None = None
    image: str | None = None
    industry: str | None = None
    company_size: str | None = None
    location: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    country_code: str | None = None
    company_website: str | None = None
    company_linkedin_url: str | None = None
    company_location: str | None = None
    company_city: str | None = None
    annual_revenue: str | None = None
    company_summary: str | None = None
    icp_status: str | None = "verified"
    icp_score: int | None = None
    tags: list[str] | None = None


class IcpRecordUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    company_name: str | None = None
    company: str | None = None
    designation: str | None = None
    department: str | None = None
    about: str | None = None
    linkedin_url: str | None = None
    phone: str | None = None
    image: str | None = None
    industry: str | None = None
    company_size: str | None = None
    location: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    country_code: str | None = None
    company_website: str | None = None
    company_linkedin_url: str | None = None
    company_location: str | None = None
    company_city: str | None = None
    annual_revenue: str | None = None
    company_summary: str | None = None
    icp_status: str | None = None
    icp_score: int | None = None
    tags: list[str] | None = None


class IcpRecordResponse(BaseModel):
    id: int
    user_id: int | None = None
    org_id: str | None = None
    name: str | None = None
    email: str | None = None
    company_name: str | None = None
    designation: str | None = None
    department: str | None = None
    about: str | None = None
    linkedin_url: str | None = None
    phone: str | None = None
    image: str | None = None
    industry: str | None = None
    company_size: str | None = None
    location: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    country_code: str | None = None
    contact_state: str | None = None
    contact_country: str | None = None
    company_website: str | None = None
    company_linkedin_url: str | None = None
    company_location: str | None = None
    company_city: str | None = None
    annual_revenue: str | None = None
    company_summary: str | None = None
    account_linkedin_url: str | None = None
    account_city: str | None = None
    account_summary: str | None = None
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
    company_location: str | None = None
    company_city: str | None = None
    account_city: str | None = None
    contact_count: int
    status: str = "active"


class IcpAccountListResponse(BaseModel):
    items: list[IcpAccountSummary]
    total: int
    page: int
    page_size: int
