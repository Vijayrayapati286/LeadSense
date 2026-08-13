"""Playwright helpers for LinkedIn session validation and screenshot capture.

Profile field extraction (name / company / about) is done in the backend via
OCR on viewport screenshots — not from DOM parsing.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from app.config import get_settings

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = Path(__file__).resolve().parent / "screenshots"
MAX_PROFILE_SCREENSHOTS = 2


@dataclass(frozen=True)
class SessionValidationResult:
    ok: bool
    message: str


@dataclass(frozen=True)
class ProfileScreenshotResult:
    ok: bool
    message: str
    screenshot_paths: list[str] = field(default_factory=list)
    page_title: str | None = None
    current_url: str | None = None


@dataclass(frozen=True)
class ProfileExtractResult:
    ok: bool
    message: str
    contact: dict[str, str | None] | None = None
    screenshot_paths: list[str] = field(default_factory=list)


class PlaywrightService:
    """LinkedIn session checks + viewport screenshot capture for profiles."""

    def validate_sales_nav_access(self, search_url: str) -> SessionValidationResult:
        settings = get_settings()
        li_at = (settings.linkedin_li_at or "").strip()
        if not li_at:
            return SessionValidationResult(
                ok=False,
                message="LINKEDIN_LI_AT is not configured on the server",
            )

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("playwright is not installed")
            return SessionValidationResult(
                ok=False,
                message="Playwright is not installed on the server",
            )

        logger.info("Validating LinkedIn Sales Navigator session for URL")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = self._new_context(browser, li_at, settings.linkedin_cookies_json)
                page = context.new_page()
                self._warm_linkedin_session(page)
                page.goto(search_url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(2_500)

                final_url = (page.url or "").lower()
                title = (page.title() or "").lower()
                body_text = self._safe_body_text(page)
                browser.close()
        except Exception as exc:
            logger.exception("Playwright Sales Navigator validation failed")
            return SessionValidationResult(
                ok=False,
                message=f"Failed to open Sales Navigator page: {exc}",
            )

        if self._looks_like_login(final_url, title, body_text):
            return SessionValidationResult(
                ok=False,
                message="LinkedIn session is invalid or expired. Update LINKEDIN_LI_AT.",
            )

        if "linkedin.com/sales" not in final_url:
            return SessionValidationResult(
                ok=False,
                message="Sales Navigator page was not accessible with the current session.",
            )

        logger.info("Sales Navigator session validation succeeded")
        return SessionValidationResult(ok=True, message="Session valid")

    def capture_profile_screenshots(
        self,
        profile_url: str,
        *,
        max_pages: int = MAX_PROFILE_SCREENSHOTS,
    ) -> ProfileScreenshotResult:
        """Open any http(s) link anonymously and take viewport screenshots (max 2).

        Never uses LinkedIn cookies / LINKEDIN_LI_AT — URL only, then OCR in backend.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return ProfileScreenshotResult(
                ok=False,
                message="Playwright is not installed on the server",
            )

        target_url = self._normalize_page_url(profile_url)
        job_id = uuid.uuid4().hex[:12]
        out_dir = SCREENSHOTS_DIR / job_id
        max_pages = max(1, min(int(max_pages or 1), MAX_PROFILE_SCREENSHOTS))

        logger.info("Capturing page screenshots (cookie-free, max_pages=%s)", max_pages)
        paths: list[str] = []
        page_title: str | None = None
        current_url: str | None = None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                # Always anonymous — do not attach li_at / cookie jar (avoids LinkedIn logout).
                context = self._new_context(browser, li_at="", cookies_json="")
                page = context.new_page()
                page.goto(target_url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(3_500)

                out_dir.mkdir(parents=True, exist_ok=True)
                page_title = (page.title() or "").strip() or None
                current_url = page.url or target_url

                path1 = out_dir / "page_1.png"
                page.screenshot(path=str(path1), full_page=False)
                paths.append(str(path1))

                if max_pages >= 2:
                    moved = self._prepare_second_viewport(page)
                    if moved:
                        page.wait_for_timeout(1_200)
                        path2 = out_dir / "page_2.png"
                        page.screenshot(path=str(path2), full_page=False)
                        paths.append(str(path2))

                browser.close()
        except Exception as exc:
            logger.exception("Playwright page screenshot capture failed")
            return ProfileScreenshotResult(
                ok=False,
                message=self._friendly_goto_error(exc),
            )

        if not paths:
            return ProfileScreenshotResult(
                ok=False,
                message="No screenshots were captured from this URL",
            )

        return ProfileScreenshotResult(
            ok=True,
            message="Screenshots captured",
            screenshot_paths=paths,
            page_title=page_title,
            current_url=current_url,
        )

    def extract_profile(self, profile_url: str) -> ProfileExtractResult:
        """URL only (no cookies) → screenshot(s) → backend OCR Name / About / Company."""
        from app.salesnav.ocr_service import OcrProfileService, OcrServiceError

        shot = self.capture_profile_screenshots(profile_url, max_pages=MAX_PROFILE_SCREENSHOTS)
        if not shot.ok:
            return ProfileExtractResult(ok=False, message=shot.message)

        try:
            contact = OcrProfileService().extract_contact(shot.screenshot_paths)
        except OcrServiceError as exc:
            return ProfileExtractResult(
                ok=False,
                message=str(exc),
                screenshot_paths=list(shot.screenshot_paths),
            )

        if not contact.get("name") and not contact.get("about") and not contact.get("company"):
            return ProfileExtractResult(
                ok=False,
                message=(
                    "Could not read Name/About/Company from the page screenshot. "
                    "The page may be a login wall or have little public text visible."
                ),
                screenshot_paths=list(shot.screenshot_paths),
            )

        return ProfileExtractResult(
            ok=True,
            message="Extracted from screenshots",
            contact=contact,
            screenshot_paths=list(shot.screenshot_paths),
        )

    @staticmethod
    def _prepare_second_viewport(page: Any) -> bool:
        """Try See more / scroll once for a second viewport. Returns True if view changed."""
        see_more_selectors = [
            "button:has-text('See more')",
            "button:has-text('Show more')",
            "button:has-text('…see more')",
            "a:has-text('See more')",
            "[aria-label*='see more' i]",
        ]
        for sel in see_more_selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=3_000)
                    return True
            except Exception:
                continue

        try:
            before = page.evaluate("() => window.scrollY")
            page.mouse.wheel(0, 900)
            page.wait_for_timeout(400)
            after = page.evaluate("() => window.scrollY")
            return float(after or 0) > float(before or 0)
        except Exception:
            return False

    def _new_context(self, browser: Any, li_at: str, cookies_json: str = "") -> Any:
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        cookies = self._build_playwright_cookies(li_at, cookies_json)
        if cookies:
            context.add_cookies(cookies)
        return context

    @staticmethod
    def _normalize_page_url(url: str) -> str:
        """Normalize URL; for LinkedIn /in/ strip query noise that can cause redirects."""
        raw = (url or "").strip()
        try:
            parsed = urlparse(raw)
        except Exception:
            return raw
        if not parsed.scheme or not parsed.netloc:
            return raw
        path = parsed.path or ""
        host = (parsed.hostname or "").lower()
        if host in {"www.linkedin.com", "linkedin.com"} and re.search(
            r"/in/[^/]+", path, re.I
        ):
            clean_path = path.rstrip("/") + "/"
            return urlunparse((parsed.scheme, parsed.netloc, clean_path, "", "", ""))
        return raw

    # Back-compat alias
    _normalize_profile_url = _normalize_page_url

    @staticmethod
    def _is_linkedin_host(url: str) -> bool:
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        return host in {"www.linkedin.com", "linkedin.com"} or host.endswith(
            ".linkedin.com"
        )

    @staticmethod
    def _warm_linkedin_session(page: Any) -> None:
        """Hit LinkedIn once so auth cookies settle before opening a profile."""
        try:
            page.goto(
                "https://www.linkedin.com/feed/",
                wait_until="domcontentloaded",
                timeout=45_000,
            )
            page.wait_for_timeout(1_500)
        except Exception:
            logger.warning("LinkedIn session warm-up navigation failed; continuing")

    @staticmethod
    def _friendly_goto_error(exc: Exception) -> str:
        text = str(exc)
        if "ERR_TOO_MANY_REDIRECTS" in text:
            return (
                "The page redirected in a loop. Try a public profile URL "
                "(/in/...) or another link that opens without login."
            )
        return f"Failed to open page: {exc}"

    def _build_playwright_cookies(self, li_at: str, cookies_json: str) -> list[dict[str, Any]]:
        """Prefer full cookie dump; always ensure li_at is present for Playwright."""
        cookies: list[dict[str, Any]] = []
        raw = (cookies_json or "").strip()
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    for item in parsed:
                        converted = self._to_playwright_cookie(item)
                        if converted:
                            cookies.append(converted)
            except json.JSONDecodeError:
                logger.warning("LINKEDIN_COOKIES_JSON is invalid JSON; falling back to li_at")

        if li_at and not any(c.get("name") == "li_at" for c in cookies):
            cookies.append(
                {
                    "name": "li_at",
                    "value": li_at,
                    "domain": ".linkedin.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "None",
                }
            )
        elif li_at:
            # Keep .env li_at authoritative when both are set.
            for cookie in cookies:
                if cookie.get("name") == "li_at":
                    cookie["value"] = li_at
                    break
        return cookies

    @staticmethod
    def _to_playwright_cookie(item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        value = item.get("value")
        if not name or value is None:
            return None

        domain = (item.get("domain") or ".linkedin.com").strip()
        if domain.startswith("www."):
            domain = "." + domain
        elif domain and not domain.startswith(".") and "linkedin" in domain:
            domain = "." + domain.lstrip(".")

        same_site_raw = str(item.get("sameSite") or item.get("same_site") or "None")
        same_site_map = {
            "no_restriction": "None",
            "unspecified": "Lax",
            "lax": "Lax",
            "strict": "Strict",
            "none": "None",
        }
        same_site = same_site_map.get(same_site_raw.lower(), "None")

        cookie: dict[str, Any] = {
            "name": str(name),
            "value": str(value),
            "domain": domain or ".linkedin.com",
            "path": item.get("path") or "/",
            "httpOnly": bool(item.get("httpOnly", item.get("http_only", False))),
            "secure": bool(item.get("secure", True)),
            "sameSite": same_site,
        }
        expires = item.get("expires") or item.get("expirationDate")
        if isinstance(expires, (int, float)) and expires > 0:
            cookie["expires"] = float(expires)
        return cookie

    def _parse_profile_page(self, page: Any, final_url: str) -> dict[str, str | None]:
        name = self._first_text(
            page,
            [
                "h1",
                "[data-anonymize='person-name']",
                ".text-heading-xlarge",
                ".pv-text-details__left-panel h1",
                "main h1",
            ],
        )

        about = self._first_text(
            page,
            [
                "[data-anonymize='headline']",
                ".text-body-medium.break-words",
                ".pv-text-details__left-panel .text-body-medium",
                "section.pv-about-section .inline-show-more-text",
                "#about ~ div .inline-show-more-text",
                "[data-anonymize='job-title']",
            ],
        )

        company = self._first_text(
            page,
            [
                "[data-anonymize='company-name']",
                ".pv-text-details__right-panel li a",
                "button[aria-label*='Current company']",
                ".experience-section li:first-child .t-14.t-normal span[aria-hidden='true']",
                "section#experience ~ div li:first-child span[aria-hidden='true']",
            ],
        )

        # Fallback: parse "Title at Company" style headline.
        if not company and about and " at " in about:
            company = about.rsplit(" at ", 1)[-1].strip() or None

        # Sales Nav title often includes "| LinkedIn" — strip noise from document title.
        if not name:
            doc_title = (page.title() or "").strip()
            if doc_title:
                name = re.split(r"\s*\|\s*", doc_title)[0].strip() or None

        # Last resort: first non-empty line of body for Sales Nav lead pages.
        if not name or not about:
            body = self._safe_body_text(page, limit=2500)
            lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
            if not name and lines:
                # Prefer a line that looks like a person name (2–4 words, no URL junk).
                for line in lines[:20]:
                    if self._looks_like_name(line):
                        name = line
                        break
            if not about and lines:
                for line in lines[:40]:
                    if line.lower() == (name or "").lower():
                        continue
                    if len(line) > 12 and not line.startswith("http"):
                        about = line
                        break

        _ = final_url  # reserved for future path-specific parsers
        return {
            "name": name,
            "about": about,
            "company": company,
        }

    @staticmethod
    def _first_text(page: Any, selectors: list[str]) -> str | None:
        for selector in selectors:
            try:
                loc = page.locator(selector)
                if loc.count() == 0:
                    continue
                text = (loc.first.inner_text(timeout=2_000) or "").strip()
                text = re.sub(r"\s+", " ", text)
                if text and text.lower() not in {"null", "none", "n/a"}:
                    return text
            except Exception:
                continue
        return None

    @staticmethod
    def _safe_body_text(page: Any, limit: int = 4000) -> str:
        try:
            return (page.locator("body").inner_text(timeout=5_000) or "")[:limit]
        except Exception:
            return ""

    @staticmethod
    def _looks_like_login(final_url: str, title: str, body_text: str) -> bool:
        body = (body_text or "").lower()
        return (
            "/login" in final_url
            or "uas/login" in final_url
            or "authwall" in final_url
            or "sign in" in title
            or "session expired" in body
            or "join linkedin" in body
        )

    @staticmethod
    def _looks_like_name(line: str) -> bool:
        if not line or len(line) > 80:
            return False
        words = line.split()
        if not (2 <= len(words) <= 5):
            return False
        if any(ch.isdigit() for ch in line):
            return False
        blocked = ("linkedin", "sales navigator", "message", "connect", "follow", "http")
        lower = line.lower()
        return not any(b in lower for b in blocked)


def is_profile_url(url: str) -> bool:
    """True for /in/, /sales/lead/, or /sales/people/ profile-like URLs."""
    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    if host not in {"www.linkedin.com", "linkedin.com"}:
        return False
    path = parsed.path or ""
    return bool(
        re.search(
            r"/(in/[^/?#]+|sales/lead/[^/?#]+|sales/people/[^/?#]+)",
            path,
            re.I,
        )
    )
