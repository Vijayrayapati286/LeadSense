"""Apify client for LinkedIn Sales Navigator contact extraction.

Uses actor data_link_miner/linkedin-sales-navigator (or APIFY_ACTOR_ID).
Keeps only Name, About, and Company (null when missing).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


class ApifyServiceError(Exception):
    """Raised when Apify configuration or extraction fails."""


class ApifyService:
    """Run the Sales Navigator Apify actor and normalize contact rows."""

    def extract_contacts(self, search_url: str) -> list[dict[str, str | None]]:
        settings = get_settings()
        token = (settings.apify_token or "").strip()
        actor_id = (settings.apify_actor_id or "").strip()
        li_at = (settings.linkedin_li_at or "").strip()

        if not token:
            raise ApifyServiceError("APIFY_TOKEN is not configured")
        if not actor_id:
            raise ApifyServiceError("APIFY_ACTOR_ID is not configured")
        if not li_at:
            raise ApifyServiceError("LINKEDIN_LI_AT is not configured")

        try:
            from apify_client import ApifyClient
        except ImportError as exc:
            raise ApifyServiceError(f"apify-client import failed: {exc}") from exc

        cookies = self._build_cookies(li_at, settings.linkedin_cookies_json)
        run_input: dict[str, Any] = {
            "search": search_url,
            "cookies": cookies,
            "deep_profile": False,
            "max_results": 0,
        }

        logger.info("Starting Apify actor %s for Sales Navigator extraction", actor_id)
        client = ApifyClient(token)
        try:
            run = client.actor(actor_id).call(run_input=run_input)
        except Exception as exc:
            logger.exception("Apify actor call failed")
            raise ApifyServiceError(f"Apify extraction failed: {exc}") from exc

        if not run:
            raise ApifyServiceError("Apify returned an empty run response")

        status = (run.get("status") or "").upper()
        if status and status not in {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS"}:
            raise ApifyServiceError(f"Apify run finished with status: {status or 'unknown'}")

        dataset_id = run.get("defaultDatasetId")
        if not dataset_id:
            raise ApifyServiceError("Apify run has no dataset id")

        items = list(client.dataset(dataset_id).iterate_items())
        logger.info("Apify returned %s raw items", len(items))
        contacts = [row for item in items if (row := self._normalize_item(item))]
        logger.info("Normalized %s contacts (name/about/company only)", len(contacts))
        return contacts

    def _build_cookies(self, li_at: str, cookies_json: str) -> list[dict[str, Any]]:
        """Prefer full cookie dump when provided; otherwise build li_at cookie."""
        raw = (cookies_json or "").strip()
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list) and parsed:
                    return parsed
            except json.JSONDecodeError:
                logger.warning("LINKEDIN_COOKIES_JSON is invalid JSON; falling back to li_at")

        return [
            {
                "name": "li_at",
                "value": li_at,
                "domain": ".linkedin.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
            }
        ]

    def _normalize_item(self, item: dict[str, Any]) -> dict[str, str | None] | None:
        if not isinstance(item, dict):
            return None

        name = self._first_str(item, ("full_name", "fullName", "name"))
        if not name:
            first = self._first_str(item, ("first_name", "firstName"))
            last = self._first_str(item, ("last_name", "lastName"))
            combined = " ".join(p for p in (first, last) if p).strip()
            name = combined or None

        about = self._first_str(
            item,
            ("about", "summary", "headline", "jobtitle", "job_title", "jobTitle"),
        )
        if not about:
            default_position = item.get("defaultPosition")
            if isinstance(default_position, dict):
                about = self._first_str(
                    default_position,
                    ("description", "title", "jobtitle"),
                )

        company = self._first_str(
            item,
            ("company_name", "companyName", "company"),
        )
        if not company:
            default_position = item.get("defaultPosition")
            if isinstance(default_position, dict):
                company = self._first_str(
                    default_position,
                    ("companyName", "company_name", "company"),
                )
        if not company:
            positions = item.get("current_positions") or item.get("positions")
            if isinstance(positions, list) and positions:
                first_pos = positions[0]
                if isinstance(first_pos, dict):
                    company = self._first_str(
                        first_pos,
                        ("companyName", "company_name", "company"),
                    )

        # Skip empty shells with no usable identity fields at all.
        if not name and not about and not company:
            return None

        return {
            "name": name or None,
            "about": about or None,
            "company": company or None,
        }

    @staticmethod
    def _first_str(item: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = item.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text and text.lower() not in {"none", "null", "n/a"}:
                return text
        return None
