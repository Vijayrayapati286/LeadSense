"""Server-side LinkedIn /in/ profile extraction via Playwright.

Cookies stay on the server (LINKEDIN_LI_AT / LINKEDIN_COOKIES_JSON).
Extracts only: full_name, company, job_title, about.
Never scrapes location, email, phone, connections, or messages.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2.0


@dataclass(frozen=True)
class ProfileResult:
    ok: bool
    message: str
    full_name: str | None = None
    company: str | None = None
    job_title: str | None = None
    about: str | None = None
    source: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "full_name": self.full_name,
            "company": self.company,
            "job_title": self.job_title,
            "about": self.about,
        }


class LinkedInProfileExtractor:
    """Reusable Playwright extractor for public /in/ profiles."""

    def extract(self, profile_url: str) -> ProfileResult:
        settings = get_settings()
        li_at = (settings.linkedin_li_at or "").strip()
        if not li_at:
            return ProfileResult(
                ok=False,
                message="LINKEDIN_LI_AT is not configured on the server",
            )

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return ProfileResult(ok=False, message="Playwright is not installed on the server")

        last_error = "Extraction failed"
        for attempt in range(1, MAX_RETRIES + 1):
            logger.info(
                "LinkedIn profile extract attempt %s/%s url=%s",
                attempt,
                MAX_RETRIES,
                self._safe_url_for_log(profile_url),
            )
            try:
                result = self._extract_once(sync_playwright, profile_url, li_at, settings)
                if result.ok:
                    return result
                last_error = result.message
                # Do not retry permanent config / login failures.
                if any(
                    token in result.message.lower()
                    for token in ("not configured", "invalid or expired", "not installed")
                ):
                    return result
            except Exception as exc:
                last_error = self._friendly_goto_error(exc)
                logger.exception("LinkedIn profile extract attempt %s failed", attempt)

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS * attempt)

        return ProfileResult(ok=False, message=last_error)

    def _extract_once(
        self,
        sync_playwright: Any,
        profile_url: str,
        li_at: str,
        settings: Any,
    ) -> ProfileResult:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = self._new_context(browser, li_at, settings.linkedin_cookies_json)
                page = context.new_page()
                self._warm_linkedin_session(page)
                try:
                    page.goto(profile_url, wait_until="domcontentloaded", timeout=60_000)
                except Exception as exc:
                    return ProfileResult(ok=False, message=self._friendly_goto_error(exc))

                page.wait_for_timeout(2_000)
                final_url = (page.url or "").lower()
                title = (page.title() or "").lower()
                body_text = self._safe_body_text(page)

                if self._looks_like_login(final_url, title, body_text):
                    return ProfileResult(
                        ok=False,
                        message="LinkedIn session is invalid or expired. Update LINKEDIN_LI_AT.",
                    )

                if "/in/" not in final_url:
                    return ProfileResult(
                        ok=False,
                        message="Could not open the LinkedIn profile with the current session.",
                    )

                self._prepare_profile_page(page)
                fields = self._parse_profile_page(page)
                if not any(fields.values()):
                    return ProfileResult(
                        ok=False,
                        message="Profile opened but no visible Name/Company/Title/About found.",
                    )

                logger.info(
                    "LinkedIn profile extract succeeded name=%s",
                    (fields.get("full_name") or "")[:40],
                )
                return ProfileResult(ok=True, message="ok", **fields)
            finally:
                browser.close()

    def _new_context(self, browser: Any, li_at: str, cookies_json: str) -> Any:
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1365, "height": 900},
            locale="en-US",
        )
        cookies = self._build_playwright_cookies(li_at, cookies_json or "")
        if cookies:
            context.add_cookies(cookies)
        return context

    def _build_playwright_cookies(self, li_at: str, cookies_json: str) -> list[dict[str, Any]]:
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

    @staticmethod
    def _warm_linkedin_session(page: Any) -> None:
        try:
            page.goto(
                "https://www.linkedin.com/feed/",
                wait_until="domcontentloaded",
                timeout=45_000,
            )
            page.wait_for_timeout(1_500)
        except Exception:
            logger.warning("LinkedIn session warm-up navigation failed; continuing")

    def _prepare_profile_page(self, page: Any) -> None:
        """Wait for top card, expand About, scroll so lazy sections render."""
        try:
            page.wait_for_selector("main h1, h1.text-heading-xlarge, section.artdeco-card h1", timeout=15_000)
        except Exception:
            logger.warning("Profile h1 did not appear quickly; continuing parse")

        page.wait_for_timeout(1_500)

        # Expand truncated About ("…see more").
        for selector in (
            "#about ~ div button:has-text('see more')",
            "#about ~ div .inline-show-more-text__button",
            "section:has(#about) button:has-text('see more')",
            "button.inline-show-more-text__button",
        ):
            try:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click(timeout=2_000)
                    page.wait_for_timeout(500)
                    break
            except Exception:
                continue

        try:
            page.evaluate("window.scrollTo(0, Math.min(document.body.scrollHeight, 1800))")
            page.wait_for_timeout(800)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(400)
        except Exception:
            pass

    def _parse_profile_page(self, page: Any) -> dict[str, str | None]:
        """Parse only Full Name, Company, Designation, About — no location/contact."""
        full_name = self._clean_text(
            self._first_text(
                page,
                [
                    "main section.artdeco-card h1",
                    "main h1.inline",
                    "h1.text-heading-xlarge",
                    "main h1",
                    "[data-anonymize='person-name']",
                    ".pv-text-details__left-panel h1",
                ],
            )
        )

        # Headline sits directly under the name in the top card — not nav chrome.
        job_title = self._clean_text(
            self._first_text(
                page,
                [
                    "main section.artdeco-card div.text-body-medium.break-words",
                    "main .mt2.relative div.text-body-medium.break-words",
                    "main div.ph5 div.text-body-medium.break-words",
                    "[data-anonymize='headline']",
                    ".pv-text-details__left-panel .text-body-medium",
                ],
            )
        )

        company = self._clean_text(
            self._first_text(
                page,
                [
                    "main button[aria-label*='Current company'] span[aria-hidden='true']",
                    "main button[aria-label*='Current company']",
                    "button[aria-label*='Current company'] span",
                    "button[aria-label*='Current company']",
                    "[data-anonymize='company-name']",
                    "main #experience ~ div ul > li:first-child .hoverable-link-text span[aria-hidden='true']",
                    "main #experience ~ div ul > li:first-child span.t-14.t-normal span[aria-hidden='true']",
                ],
            )
        )
        if company and company.lower().startswith("current company"):
            company = re.sub(r"(?i)^current company\s*", "", company).strip() or None

        about = self._clean_text(
            self._first_text(
                page,
                [
                    "section:has(#about) .inline-show-more-text span[aria-hidden='true']",
                    "section:has(#about) .inline-show-more-text",
                    "#about ~ div .inline-show-more-text span[aria-hidden='true']",
                    "#about ~ div .inline-show-more-text",
                    "section.pv-about-section .inline-show-more-text",
                    "#about ~ div .full-width span[aria-hidden='true']",
                ],
                allow_multiline=True,
            )
        )

        # Headline patterns: "Title @ Company | ..." or "Title at Company"
        if job_title:
            derived_company = self._company_from_headline(job_title)
            if derived_company and not company:
                company = derived_company

        if not full_name:
            doc_title = (page.title() or "").strip()
            if doc_title:
                full_name = self._clean_text(re.split(r"\s*\|\s*", doc_title)[0])

        if not full_name or not job_title or not about or not company:
            filled = self._body_fallback_fields(page, full_name, job_title, company, about)
            full_name = filled["full_name"]
            job_title = filled["job_title"]
            company = filled["company"]
            about = filled["about"]

        return {
            "full_name": full_name,
            "company": company,
            "job_title": job_title,
            "about": about,
        }

    def _body_fallback_fields(
        self,
        page: Any,
        full_name: str | None,
        job_title: str | None,
        company: str | None,
        about: str | None,
    ) -> dict[str, str | None]:
        """Soft fallbacks from visible body text — never emails/phones/location."""
        body = self._safe_body_text(page, limit=6000)
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        useful = [ln for ln in lines if not self._is_junk_line(ln)]

        if not full_name:
            for line in useful[:25]:
                if self._looks_like_name(line):
                    full_name = line
                    break

        if not job_title and full_name:
            for line in useful[:50]:
                if line.lower() == full_name.lower():
                    continue
                if self._looks_like_headline(line):
                    job_title = line
                    break

        if job_title and not company:
            company = self._company_from_headline(job_title)

        if not about and full_name:
            # About is usually a long paragraph after the top card chrome.
            for line in useful:
                if line.lower() in {(full_name or "").lower(), (job_title or "").lower()}:
                    continue
                if len(line) >= 80 and not self._looks_like_headline(line):
                    if not re.search(r"@|\+?\d[\d\s\-()]{7,}", line):
                        about = line
                        break

        return {
            "full_name": full_name,
            "job_title": job_title,
            "company": company,
            "about": about,
        }

    @staticmethod
    def _company_from_headline(headline: str) -> str | None:
        text = (headline or "").strip()
        if not text:
            return None
        # "Senior Manager @ Clearwater Analytics | PGCP ..."
        at_match = re.search(r"\s@\s([^|•\n]+)", text)
        if at_match:
            return at_match.group(1).strip(" .") or None
        # "Title at Company"
        if " at " in text:
            return text.rsplit(" at ", 1)[-1].split("|")[0].strip(" .") or None
        return None

    @staticmethod
    def _looks_like_headline(line: str) -> bool:
        if not line or len(line) < 8 or len(line) > 220:
            return False
        if LinkedInProfileExtractor._is_junk_line(line):
            return False
        lower = line.lower()
        if lower in {"about", "experience", "education", "activity", "skills"}:
            return False
        # Typical headlines contain role words, @, |, or "at".
        if "@" in line or " | " in line or " at " in lower:
            return True
        role_hints = (
            "manager",
            "engineer",
            "developer",
            "director",
            "lead",
            "analyst",
            "consultant",
            "founder",
            "officer",
            "specialist",
            "architect",
        )
        return any(h in lower for h in role_hints)

    @staticmethod
    def _is_junk_line(line: str) -> bool:
        lower = (line or "").strip().lower()
        if not lower:
            return True
        junk = (
            "skip to main content",
            "skip to content",
            "skip to search",
            "keyboard shortcuts",
            "close jump menu",
            "linkedin",
            "sign in",
            "join now",
            "accept",
            "reject",
            "cookie",
            "privacy",
            "messaging",
            "notifications",
            "home",
            "my network",
            "jobs",
            "connect",
            "message",
            "follow",
            "more",
            "contact info",
            "500+ connections",
            "connections",
            "followers",
        )
        if lower in junk:
            return True
        if lower.startswith("skip to"):
            return True
        if re.fullmatch(r"\d+\+?\s*(connections|followers)", lower):
            return True
        return False

    @staticmethod
    def _clean_text(value: str | None, *, keep_newlines: bool = False) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if keep_newlines:
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
        else:
            text = re.sub(r"\s+", " ", text).strip()
        if not text or text.lower() in {"null", "none", "n/a"}:
            return None
        if LinkedInProfileExtractor._is_junk_line(text.split("\n", 1)[0]):
            return None
        # Drop trailing "see more" / "see less" UI chrome.
        text = re.sub(r"(?i)\s*see more\s*$", "", text).strip()
        text = re.sub(r"(?i)\s*see less\s*$", "", text).strip()
        return text or None

    @staticmethod
    def _first_text(
        page: Any,
        selectors: list[str],
        *,
        allow_multiline: bool = False,
    ) -> str | None:
        for selector in selectors:
            try:
                loc = page.locator(selector)
                count = loc.count()
                if count == 0:
                    continue
                for i in range(min(count, 8)):
                    raw = (loc.nth(i).inner_text(timeout=2_000) or "").strip()
                    cleaned = LinkedInProfileExtractor._clean_text(
                        raw,
                        keep_newlines=allow_multiline,
                    )
                    if cleaned:
                        return cleaned
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
        if LinkedInProfileExtractor._is_junk_line(line):
            return False
        words = line.split()
        if not (2 <= len(words) <= 5):
            return False
        if any(ch.isdigit() for ch in line):
            return False
        blocked = ("linkedin", "sales navigator", "message", "connect", "follow", "http")
        lower = line.lower()
        return not any(b in lower for b in blocked)

    @staticmethod
    def _friendly_goto_error(exc: Exception) -> str:
        text = str(exc)
        if "ERR_TOO_MANY_REDIRECTS" in text:
            return (
                "LinkedIn redirected in a loop (usually an invalid/expired session). "
                "Refresh LINKEDIN_LI_AT on the server and retry."
            )
        return f"Failed to open profile page: {exc}"

    @staticmethod
    def _safe_url_for_log(url: str) -> str:
        """Log path only — never cookies or tokens."""
        try:
            from urllib.parse import urlparse

            p = urlparse(url)
            return f"{p.scheme}://{p.netloc}{p.path}"
        except Exception:
            return "[url]"
