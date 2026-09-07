"""OCR profile fields (name / company / about) from viewport screenshots.

Runs entirely on the backend after Playwright captures images.
Prefers PaddleOCR when paddlepaddle is installed; otherwise RapidOCR.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BLOCKED_NAME_TOKENS = (
    "linkedin",
    "sales navigator",
    "message",
    "connect",
    "follow",
    "http",
    "about",
    "experience",
    "education",
    "skills",
)

_TITLE_MARKERS = (" at ", " @ ", " | ")
_ORG_MARKERS = (
    " inc",
    " ltd",
    " llc",
    " corp",
    " co.",
    " company",
    " technologies",
    " technology",
    " solutions",
    " systems",
    " group",
    " labs",
)

_JOB_TITLE_WORDS = {
    "vp",
    "svp",
    "evp",
    "ceo",
    "cto",
    "cfo",
    "coo",
    "head",
    "lead",
    "leader",
    "manager",
    "director",
    "senior",
    "junior",
    "staff",
    "principal",
    "founder",
    "cofounder",
    "owner",
    "partner",
    "consultant",
    "engineer",
    "engineering",
    "developer",
    "sales",
    "marketing",
    "product",
    "president",
    "chief",
    "officer",
    "specialist",
    "analyst",
    "architect",
}


class OcrServiceError(Exception):
    """Raised when OCR cannot run or yields no usable text."""


class OcrProfileService:
    """Extract Name / About / Company from one or more screenshot paths."""

    def extract_contact(self, screenshot_paths: list[str]) -> dict[str, str | None]:
        paths = [p for p in screenshot_paths if p and Path(p).is_file()]
        if not paths:
            raise OcrServiceError("No screenshot files available for OCR")

        lines: list[str] = []
        for path in paths:
            lines.extend(self._ocr_lines(path))

        if not lines:
            raise OcrServiceError("OCR returned no text from screenshots")

        return self._map_fields(lines)

    def _ocr_lines(self, image_path: str) -> list[str]:
        engine = _get_ocr_engine()
        kind = engine["kind"]
        try:
            if kind == "paddle":
                return self._lines_from_paddle(engine["ocr"], image_path)
            return self._lines_from_rapid(engine["ocr"], image_path)
        except OcrServiceError:
            raise
        except Exception as exc:
            logger.exception("OCR failed for %s", image_path)
            raise OcrServiceError(f"OCR failed: {exc}") from exc

    @staticmethod
    def _lines_from_paddle(ocr: Any, image_path: str) -> list[str]:
        # PaddleOCR 2.x: .ocr(); 3.x: .predict() / .ocr()
        raw = None
        if hasattr(ocr, "predict"):
            try:
                raw = ocr.predict(image_path)
            except Exception:
                raw = None
        if raw is None:
            try:
                raw = ocr.ocr(image_path, cls=True)
            except TypeError:
                raw = ocr.ocr(image_path)

        lines: list[str] = []
        for block in raw or []:
            # v3 result objects may expose rec_texts
            rec_texts = getattr(block, "rec_texts", None) or (
                block.get("rec_texts") if isinstance(block, dict) else None
            )
            if rec_texts:
                for text in rec_texts:
                    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
                    if cleaned:
                        lines.append(cleaned)
                continue

            if not block:
                continue
            for line in block:
                try:
                    text = (line[1][0] or "").strip()
                except (IndexError, TypeError, ValueError):
                    continue
                text = re.sub(r"\s+", " ", text)
                if text:
                    lines.append(text)
        return lines

    @staticmethod
    def _lines_from_rapid(ocr: Any, image_path: str) -> list[str]:
        result, _ = ocr(image_path)
        lines: list[str] = []
        for row in result or []:
            if not row or len(row) < 2:
                continue
            text = re.sub(r"\s+", " ", str(row[1] or "").strip())
            if text:
                lines.append(text)
        return lines

    def _map_fields(self, lines: list[str]) -> dict[str, str | None]:
        name = self._pick_name(lines)
        about = self._pick_about(lines, name)
        company = self._pick_company(lines, name, about)

        if not company and about:
            for sep in (" at ", " @ "):
                if sep in about:
                    company = about.rsplit(sep, 1)[-1].strip() or None
                    break

        return {
            "name": name,
            "about": about,
            "company": company,
        }

    def _pick_name(self, lines: list[str]) -> str | None:
        for line in lines[:25]:
            if self._looks_like_name(line):
                return line
        return None

    def _pick_about(self, lines: list[str], name: str | None) -> str | None:
        name_l = (name or "").lower()
        candidates: list[str] = []
        for line in lines[:60]:
            lower = line.lower()
            if name_l and lower == name_l:
                continue
            if lower in {"about", "experience", "education", "skills", "activity"}:
                continue
            if len(line) < 8:
                continue
            if line.startswith("http"):
                continue
            # Person names only — keep title/headline lines ("X at Y").
            if self._looks_like_name(line):
                continue
            candidates.append(line)

        if not candidates:
            return None
        for line in candidates:
            if 12 <= len(line) <= 180:
                return line
        return max(candidates, key=len)

    def _pick_company(
        self,
        lines: list[str],
        name: str | None,
        about: str | None,
    ) -> str | None:
        name_l = (name or "").lower()
        about_l = (about or "").lower()

        # Prefer company from headline "Title at Company"
        for source in (about, *lines[:50]):
            if not source:
                continue
            for sep in (" at ", " @ "):
                if sep in source:
                    tail = source.rsplit(sep, 1)[-1].strip()
                    if tail and tail.lower() != name_l and len(tail) >= 2:
                        return tail

        for line in lines[:50]:
            lower = line.lower()
            if name_l and lower == name_l:
                continue
            if about_l and lower == about_l:
                continue
            if any(m in lower for m in ("message", "connect", "follow", "linkedin")):
                continue
            if any(m in lower for m in _ORG_MARKERS) and 1 <= len(line.split()) <= 10:
                return line
        return None

    @staticmethod
    def _looks_like_name(line: str) -> bool:
        if not line or len(line) > 80:
            return False
        words = line.split()
        if not (2 <= len(words) <= 4):
            return False
        if any(ch.isdigit() for ch in line):
            return False
        lower = line.lower()
        if any(m in lower for m in _TITLE_MARKERS):
            return False
        if any(m in lower for m in _ORG_MARKERS):
            return False
        if any(b in lower for b in _BLOCKED_NAME_TOKENS):
            return False
        tokens = [w.lower().strip(",.|;:") for w in words]
        if any(t in _JOB_TITLE_WORDS for t in tokens):
            return False
        # Prefer capitalized person-name tokens
        alpha_words = [w for w in words if w.isalpha()]
        if len(alpha_words) < 2:
            return False
        return sum(1 for w in alpha_words if w[:1].isupper()) >= 2


@lru_cache(maxsize=1)
def _get_ocr_engine() -> dict[str, Any]:
    """Lazy-load a single OCR engine for the process."""
    if _paddlepaddle_available():
        try:
            from paddleocr import PaddleOCR

            logger.info("Initializing PaddleOCR for profile screenshots")
            # PaddleOCR 3.x API (no use_angle_cls / show_log).
            try:
                ocr = PaddleOCR(
                    lang="en",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                )
            except TypeError:
                ocr = PaddleOCR(lang="en")
            return {"kind": "paddle", "ocr": ocr}
        except Exception as paddle_exc:
            logger.warning("PaddleOCR unavailable (%s); trying RapidOCR", paddle_exc)
    else:
        logger.info("paddlepaddle not installed; using RapidOCR")

    try:
        from rapidocr_onnxruntime import RapidOCR

        logger.info("Initializing RapidOCR for profile screenshots")
        return {"kind": "rapid", "ocr": RapidOCR()}
    except Exception as rapid_exc:
        raise OcrServiceError(
            "No OCR engine available. Install rapidocr-onnxruntime "
            "(or paddleocr + paddlepaddle) on the server."
        ) from rapid_exc


def _paddlepaddle_available() -> bool:
    try:
        import paddle  # noqa: F401

        return True
    except Exception:
        return False
