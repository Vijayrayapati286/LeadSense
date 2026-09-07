"""Hybrid LinkedIn profile extractor: Playwright primary, Apify fallback.

Keeps a single public interface so routes/UI stay engine-agnostic.
"""

from __future__ import annotations

import logging
from typing import Literal

from app.linkedin.apify_extractor import LinkedInApifyProfileExtractor
from app.linkedin.extractor import LinkedInProfileExtractor, ProfileResult

logger = logging.getLogger(__name__)

Engine = Literal["auto", "playwright", "apify"]


class HybridLinkedInProfileExtractor:
    """Try Playwright first; fall back to Apify when auto mode needs it."""

    def __init__(self) -> None:
        self._playwright = LinkedInProfileExtractor()
        self._apify = LinkedInApifyProfileExtractor()

    def extract(self, profile_url: str, *, engine: Engine = "auto") -> ProfileResult:
        engine = (engine or "auto").lower()  # type: ignore[assignment]
        if engine not in {"auto", "playwright", "apify"}:
            return ProfileResult(
                ok=False,
                message="engine must be one of: auto, playwright, apify",
            )

        playwright_result: ProfileResult | None = None
        if engine in {"auto", "playwright"}:
            playwright_result = self._playwright.extract(profile_url)
            if self._is_useful(playwright_result):
                logger.info("LinkedIn profile extract succeeded via playwright")
                return ProfileResult(
                    ok=True,
                    message="ok",
                    full_name=playwright_result.full_name,
                    company=playwright_result.company,
                    job_title=playwright_result.job_title,
                    about=playwright_result.about,
                    source="playwright",
                )
            if engine == "playwright":
                return playwright_result or ProfileResult(ok=False, message="Playwright extraction failed")
            logger.info(
                "Playwright profile extract incomplete (%s); trying Apify",
                (playwright_result.message if playwright_result else "no result"),
            )

        if engine in {"auto", "apify"}:
            apify_result = self._apify.extract(profile_url)
            if self._is_useful(apify_result):
                logger.info("LinkedIn profile extract succeeded via apify")
                return ProfileResult(
                    ok=True,
                    message="ok",
                    full_name=apify_result.full_name,
                    company=apify_result.company,
                    job_title=apify_result.job_title,
                    about=apify_result.about,
                    source="apify",
                )
            if engine == "apify":
                return apify_result

            # auto: both failed — surface the most actionable message
            parts = []
            if playwright_result and playwright_result.message:
                parts.append(f"Playwright: {playwright_result.message}")
            if apify_result.message:
                parts.append(f"Apify: {apify_result.message}")
            return ProfileResult(
                ok=False,
                message=" | ".join(parts) or "Both Playwright and Apify extraction failed",
            )

        return ProfileResult(ok=False, message="Extraction failed")

    @staticmethod
    def _is_useful(result: ProfileResult | None) -> bool:
        if not result or not result.ok:
            return False
        # Need a real name plus at least one other profile field.
        if not (result.full_name or "").strip():
            return False
        extras = [
            (result.company or "").strip(),
            (result.job_title or "").strip(),
            (result.about or "").strip(),
        ]
        extras = [e for e in extras if e]
        if not extras:
            return False
        # Reject known junk designations from bad DOM scrapes.
        junk = {"skip to main content", "skip to content", "linkedin"}
        if (result.job_title or "").strip().lower() in junk and not (
            (result.company or "").strip() or (result.about or "").strip()
        ):
            return False
        return True
