"""Apify-only public LinkedIn profile extraction.

Delegates to app.linkedin.apify_extractor.extract_rich() so all profile
extraction uses supreme_coder/linkedin-profile-scraper with urls[] input.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ProfileApifyError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ProfileApifyService:
    """Call supreme_coder/linkedin-profile-scraper via shared extract_rich()."""

    def extract(self, profile_url: str) -> dict[str, str | None]:
        from app.linkedin.apify_extractor import LinkedInApifyProfileExtractor

        result = LinkedInApifyProfileExtractor().extract_rich(profile_url)
        if not result.get("success"):
            raise ProfileApifyError(result.get("message") or "No data found for this profile")

        data = result.get("data") or {}
        return {
            "full_name": data.get("name") or None,
            "company": data.get("company") or None,
            "designation": data.get("job_title") or data.get("headline") or None,
            "about": data.get("summary") or None,
        }
