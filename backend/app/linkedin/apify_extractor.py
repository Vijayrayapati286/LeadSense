"""Apify-backed LinkedIn /in/ profile extraction (isolated from Sales Nav).

Uses APIFY_PROFILE_ACTOR_ID when set, otherwise APIFY_ACTOR_ID.
Cookies stay on the server. Maps output to full_name / company / job_title / about only.
Also supports a richer /linkedin/extract payload for the frontend.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import get_settings
from app.linkedin.extractor import ProfileResult

logger = logging.getLogger(__name__)


class LinkedInApifyProfileExtractor:
    """Run an Apify actor against one LinkedIn /in/ profile URL."""

    def extract_rich(self, profile_url: str) -> dict[str, Any]:
        """Run supreme_coder/linkedin-profile-scraper-style actor; input is urls[]."""
        settings = get_settings()
        token = (settings.apify_token or "").strip()
        actor_id = (
            (settings.apify_profile_actor_id or "").strip()
            or (settings.apify_actor_id or "").strip()
        )

        if not token:
            return {"success": False, "data": None, "message": "APIFY_TOKEN is not configured"}
        if not actor_id:
            return {
                "success": False,
                "data": None,
                "message": "APIFY_PROFILE_ACTOR_ID (or APIFY_ACTOR_ID) is not configured",
            }

        try:
            from apify_client import ApifyClient
        except ImportError as exc:
            return {
                "success": False,
                "data": None,
                "message": f"apify-client import failed: {exc}",
            }

        # Actor expects: { "urls": [{"url": "https://www.linkedin.com/in/.../"}] }
        run_input = {"urls": [{"url": profile_url}]}

        logger.info(
            "Starting Apify rich profile actor %s for url=%s",
            actor_id,
            self._safe_url(profile_url),
        )
        client = ApifyClient(token)
        try:
            run = client.actor(actor_id).call(run_input=run_input)
        except Exception as exc:
            logger.exception("Apify rich profile actor call failed")
            return {
                "success": False,
                "data": None,
                "message": f"Apify profile extraction failed: {exc}",
            }

        if not run:
            return {
                "success": False,
                "data": None,
                "message": "Apify returned an empty run response",
            }

        status = (run.get("status") or "").upper()
        if status and status not in {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS"}:
            return {
                "success": False,
                "data": None,
                "message": f"Apify run finished with status: {status or 'unknown'}",
            }

        dataset_id = run.get("defaultDatasetId")
        if not dataset_id:
            return {
                "success": False,
                "data": None,
                "message": "Apify run has no dataset id",
            }

        try:
            items = list(client.dataset(dataset_id).iterate_items())
        except Exception as exc:
            logger.exception("Apify dataset read failed")
            return {
                "success": False,
                "data": None,
                "message": f"Failed to read Apify dataset: {exc}",
            }

        logger.info("Apify rich profile actor returned %s raw items", len(items))
        if not items:
            return {
                "success": False,
                "data": None,
                "message": "No data found for this profile",
            }

        item = items[0] if isinstance(items[0], dict) else {}

        first_name = str(item.get("firstName") or "").strip()
        last_name = str(item.get("lastName") or "").strip()
        name = f"{first_name} {last_name}".strip()

        picture = item.get("pictureUrl")
        image = ""
        if isinstance(picture, dict):
            image = str(picture.get("400x400") or "").strip()

        def _as_int(value: Any, default: int = 0) -> int:
            try:
                if value is None or value == "":
                    return default
                return int(value)
            except (TypeError, ValueError):
                return default

        data = {
            "name": name,
            "headline": str(item.get("headline") or "").strip(),
            "company": str(item.get("companyName") or "").strip(),
            "job_title": str(item.get("jobTitle") or "").strip(),
            "location": str(item.get("geoLocationName") or "").strip(),
            "summary": str(item.get("summary") or "").strip(),
            "followers": _as_int(item.get("followerCount")),
            "connections": _as_int(item.get("connectionsCount")),
            "image": image,
            "profile_url": str(item.get("inputUrl") or "").strip(),
        }

        if not any(
            [
                data["name"],
                data["headline"],
                data["company"],
                data["job_title"],
                data["summary"],
            ]
        ):
            return {
                "success": False,
                "data": None,
                "message": "No data found for this profile",
            }

        return {"success": True, "data": data, "message": None}

    def extract(self, profile_url: str) -> ProfileResult:
        settings = get_settings()
        token = (settings.apify_token or "").strip()
        actor_id = (
            (settings.apify_profile_actor_id or "").strip()
            or (settings.apify_actor_id or "").strip()
        )
        li_at = (settings.linkedin_li_at or "").strip()

        if not token:
            return ProfileResult(ok=False, message="APIFY_TOKEN is not configured")
        if not actor_id:
            return ProfileResult(
                ok=False,
                message="APIFY_PROFILE_ACTOR_ID (or APIFY_ACTOR_ID) is not configured",
            )
        if not li_at:
            return ProfileResult(ok=False, message="LINKEDIN_LI_AT is not configured")

        try:
            from apify_client import ApifyClient
        except ImportError as exc:
            return ProfileResult(
                ok=False,
                message=f"apify-client import failed: {exc}",
            )

        cookies = self._build_cookies(li_at, settings.linkedin_cookies_json)
        run_input = self._build_run_input(profile_url, cookies)

        logger.info(
            "Starting Apify profile actor %s for url=%s",
            actor_id,
            self._safe_url(profile_url),
        )
        client = ApifyClient(token)
        try:
            run = client.actor(actor_id).call(run_input=run_input)
        except Exception as exc:
            logger.exception("Apify profile actor call failed")
            return ProfileResult(ok=False, message=f"Apify profile extraction failed: {exc}")

        if not run:
            return ProfileResult(ok=False, message="Apify returned an empty run response")

        status = (run.get("status") or "").upper()
        if status and status not in {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS"}:
            return ProfileResult(
                ok=False,
                message=f"Apify run finished with status: {status or 'unknown'}",
            )

        dataset_id = run.get("defaultDatasetId")
        if not dataset_id:
            return ProfileResult(ok=False, message="Apify run has no dataset id")

        items = list(client.dataset(dataset_id).iterate_items())
        logger.info("Apify profile actor returned %s raw items", len(items))
        if not items:
            return ProfileResult(ok=False, message="Apify returned no profile data")

        fields = self._normalize_item(items[0] if isinstance(items[0], dict) else {})
        if not any(fields.values()):
            return ProfileResult(
                ok=False,
                message="Apify returned a profile with no Name/Company/Title/About",
            )

        return ProfileResult(ok=True, message="ok", **fields)

    @staticmethod
    def _build_run_input(profile_url: str, cookies: list[dict[str, Any]]) -> dict[str, Any]:
        """Flexible input for common LinkedIn profile actors."""
        return {
            # Common profile-scraper shapes
            "urls": [profile_url],
            "url": profile_url,
            "profileUrls": [profile_url],
            "profileUrl": profile_url,
            "startUrls": [{"url": profile_url}],
            # Sales-nav style actors sometimes accept "search" as a URL
            "search": profile_url,
            "cookies": cookies,
            "cookie": cookies,
            "deep_profile": True,
            "max_results": 1,
        }

    @staticmethod
    def _build_rich_run_input(
        profile_url: str, cookies: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Flexible input for /linkedin/extract; cookies only when configured."""
        payload: dict[str, Any] = {
            "urls": [profile_url],
            "url": profile_url,
            "profileUrls": [profile_url],
            "profileUrl": profile_url,
            "startUrls": [{"url": profile_url}],
            "search": profile_url,
            "deep_profile": True,
            "max_results": 1,
        }
        if cookies:
            payload["cookies"] = cookies
            payload["cookie"] = cookies
        return payload

    @staticmethod
    def _optional_server_cookies(settings: Any) -> list[dict[str, Any]]:
        """Server-only cookies if present. Never required from the client."""
        li_at = (settings.linkedin_li_at or "").strip()
        raw = (settings.linkedin_cookies_json or "").strip()
        cookies: list[dict[str, Any]] = []
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    cookies = [c for c in parsed if isinstance(c, dict)]
            except json.JSONDecodeError:
                logger.warning("LINKEDIN_COOKIES_JSON invalid; ignoring for rich extract")
        if li_at:
            for cookie in cookies:
                if cookie.get("name") == "li_at":
                    cookie["value"] = li_at
                    break
            else:
                cookies.append(
                    {
                        "name": "li_at",
                        "value": li_at,
                        "domain": ".linkedin.com",
                        "path": "/",
                        "httpOnly": True,
                        "secure": True,
                    }
                )
        return cookies

    @staticmethod
    def _as_int(value: Any, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    def _map_rich_item(self, item: dict[str, Any], fallback_url: str = "") -> dict[str, Any]:
        first = self._first_str(item, ("firstName", "first_name")) or ""
        last = self._first_str(item, ("lastName", "last_name")) or ""
        name = f"{first} {last}".strip()
        if not name:
            name = self._first_str(item, ("fullName", "full_name", "name", "fullNameText")) or ""

        picture = item.get("pictureUrl")
        image = ""
        if isinstance(picture, dict):
            image = str(picture.get("400x400") or picture.get("800x800") or "").strip()
        elif isinstance(picture, str):
            image = picture.strip()
        if not image:
            image = self._first_str(item, ("profilePicture", "photoUrl", "avatar", "image")) or ""

        company = self._first_str(item, ("companyName", "company", "company_name", "current_company")) or ""
        job_title = self._first_str(item, ("jobTitle", "job_title", "title", "occupation")) or ""
        if not company or not job_title:
            default_position = item.get("defaultPosition") or item.get("current_position")
            if isinstance(default_position, dict):
                if not company:
                    company = (
                        self._first_str(
                            default_position,
                            ("companyName", "company_name", "company"),
                        )
                        or ""
                    )
                if not job_title:
                    job_title = (
                        self._first_str(
                            default_position,
                            ("title", "jobTitle", "job_title"),
                        )
                        or ""
                    )

        profile_url = (
            self._first_str(item, ("inputUrl", "profileUrl", "url", "linkedinUrl"))
            or fallback_url
            or ""
        )

        return {
            "name": name,
            "headline": self._first_str(item, ("headline",)) or "",
            "company": company,
            "job_title": job_title,
            "location": self._first_str(
                item, ("geoLocationName", "location", "geoLocation", "addressCountryOnly")
            )
            or "",
            "summary": self._first_str(item, ("summary", "about", "description", "bio")) or "",
            "followers": self._as_int(item.get("followerCount") or item.get("followers")),
            "connections": self._as_int(
                item.get("connectionsCount") or item.get("connections")
            ),
            "image": image,
            "profile_url": profile_url,
        }

    def _build_cookies(self, li_at: str, cookies_json: str) -> list[dict[str, Any]]:
        raw = (cookies_json or "").strip()
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list) and parsed:
                    # Prefer full dump but keep li_at authoritative.
                    cookies = [c for c in parsed if isinstance(c, dict)]
                    for cookie in cookies:
                        if cookie.get("name") == "li_at":
                            cookie["value"] = li_at
                            break
                    else:
                        cookies.append(
                            {
                                "name": "li_at",
                                "value": li_at,
                                "domain": ".linkedin.com",
                                "path": "/",
                                "httpOnly": True,
                                "secure": True,
                            }
                        )
                    return cookies
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

    def _normalize_item(self, item: dict[str, Any]) -> dict[str, str | None]:
        full_name = self._first_str(item, ("full_name", "fullName", "name", "fullNameText"))
        if not full_name:
            first = self._first_str(item, ("first_name", "firstName"))
            last = self._first_str(item, ("last_name", "lastName"))
            full_name = " ".join(p for p in (first, last) if p).strip() or None

        job_title = self._first_str(
            item,
            (
                "job_title",
                "jobTitle",
                "headline",
                "occupation",
                "title",
                "designation",
            ),
        )
        if not job_title:
            default_position = item.get("defaultPosition") or item.get("current_position")
            if isinstance(default_position, dict):
                job_title = self._first_str(
                    default_position,
                    ("title", "jobTitle", "jobtitle", "headline"),
                )

        company = self._first_str(
            item,
            ("company", "company_name", "companyName", "current_company"),
        )
        if not company:
            default_position = item.get("defaultPosition") or item.get("current_position")
            if isinstance(default_position, dict):
                company = self._first_str(
                    default_position,
                    ("companyName", "company_name", "company"),
                )
        if not company:
            positions = item.get("current_positions") or item.get("positions") or item.get("experience")
            if isinstance(positions, list) and positions:
                first_pos = positions[0]
                if isinstance(first_pos, dict):
                    company = self._first_str(
                        first_pos,
                        ("companyName", "company_name", "company", "subtitle"),
                    )
                    if not job_title:
                        job_title = self._first_str(first_pos, ("title", "jobTitle"))

        about = self._first_str(item, ("about", "summary", "description", "bio"))

        # Derive company from "Title @ Company | ..." headlines when missing.
        if job_title and not company:
            at_match = re.search(r"\s@\s([^|•\n]+)", job_title)
            if at_match:
                company = at_match.group(1).strip(" .") or None
            elif " at " in job_title:
                company = job_title.rsplit(" at ", 1)[-1].split("|")[0].strip(" .") or None

        return {
            "full_name": full_name,
            "company": company,
            "job_title": job_title,
            "about": about,
        }

    @staticmethod
    def _first_str(item: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = item.get(key)
            if value is None:
                continue
            text = str(value).strip()
            text = re.sub(r"\s+", " ", text)
            if text and text.lower() not in {"none", "null", "n/a"}:
                return text
        return None

    @staticmethod
    def _safe_url(url: str) -> str:
        try:
            from urllib.parse import urlparse

            p = urlparse(url)
            return f"{p.scheme}://{p.netloc}{p.path}"
        except Exception:
            return "[url]"
