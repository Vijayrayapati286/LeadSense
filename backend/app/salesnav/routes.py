"""Sales Navigator contact extraction routes."""

from __future__ import annotations

import io
import logging
import re
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.middleware.auth import get_current_user
from app.models import User
from app.salesnav.apify_service import ApifyService, ApifyServiceError
from app.salesnav.excel_service import SalesNavExcelService
from app.salesnav.playwright_service import PlaywrightService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/salesnav", tags=["Sales Navigator"])

playwright_service = PlaywrightService()
apify_service = ApifyService()
excel_service = SalesNavExcelService()

_SALES_NAV_HOSTS = {"www.linkedin.com", "linkedin.com"}


class SalesNavExtractRequest(BaseModel):
    search_url: str = Field(..., min_length=20, description="LinkedIn Sales Navigator search URL")


class ProfileExtractRequest(BaseModel):
    profile_url: str = Field(
        ...,
        min_length=8,
        description="Any http(s) page URL to screenshot and OCR",
    )


def _validate_search_url(url: str) -> str:
    cleaned = (url or "").strip()
    try:
        parsed = urlparse(cleaned)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid search URL",
        ) from exc

    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    if parsed.scheme not in {"http", "https"} or host not in _SALES_NAV_HOSTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL must be a LinkedIn Sales Navigator link",
        )
    if not re.search(r"/sales/(search|lead|accounts|lists)", path, re.I):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL must be a Sales Navigator search/people URL",
        )
    return cleaned


def _validate_page_url(url: str) -> str:
    """Accept any http(s) URL for screenshot + OCR."""
    cleaned = (url or "").strip()
    try:
        parsed = urlparse(cleaned)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid URL",
        ) from exc

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL must be a valid http:// or https:// link",
        )
    return cleaned


# Back-compat name used elsewhere
_validate_profile_url = _validate_page_url


@router.post("/extract")
def extract_contacts(
    body: SalesNavExtractRequest,
    current_user: User = Depends(get_current_user),
):
    """Validate LinkedIn session, extract via Apify, return Excel download."""
    search_url = _validate_search_url(body.search_url)
    logger.info(
        "Sales Navigator extract requested by user_id=%s",
        getattr(current_user, "id", None),
    )

    validation = playwright_service.validate_sales_nav_access(search_url)
    if not validation.ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=validation.message,
        )

    try:
        contacts = apify_service.extract_contacts(search_url)
    except ApifyServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    if not contacts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No contacts were extracted from this search URL",
        )

    content, filename = excel_service.build_workbook(contacts)
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/extract-profile")
def extract_profile(
    body: ProfileExtractRequest,
    current_user: User = Depends(get_current_user),
):
    """Any site URL → anonymous screenshot → backend OCR → Excel.

    Never uses LinkedIn cookies (avoids session logout). Public page text only.
    """
    profile_url = _validate_page_url(body.profile_url)
    logger.info(
        "Cookie-free page SS→OCR extract user_id=%s",
        getattr(current_user, "id", None),
    )

    result = playwright_service.extract_profile(profile_url)
    if not result.ok or not result.contact:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message,
        )

    logger.info(
        "Page OCR extract ok screenshots=%s",
        len(result.screenshot_paths or []),
    )

    content, filename = excel_service.build_workbook([result.contact])
    test_name = filename.replace("salesnav_contacts_", "salesnav_profile_", 1)
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{test_name}"'},
    )
