"""Compare uploaded Excel values with extracted LinkedIn profile fields.

Extraction SUCCESS/FAILED is independent of verification VERIFIED/MISMATCH.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.services.excel_service import _normalize_header

VERIFY_NOT_VERIFIED = "NOT_VERIFIED"
VERIFY_VERIFIED = "VERIFIED"
VERIFY_MISMATCH = "MISMATCH"
VERIFY_REVIEW = "REVIEW"

_COMPANY_SUFFIXES = (
    "incorporated",
    "corporation",
    "company",
    "limited",
    "llc",
    "ltd",
    "inc",
    "corp",
    "gmbh",
    "plc",
    "co",
    "lp",
    "llp",
    "pty",
    "pvt",
    "private",
)

_LOCATION_NOISE = {
    "usa",
    "us",
    "unitedstates",
    "unitedstatesofamerica",
    "uk",
    "unitedkingdom",
    "india",
    "canada",
    "australia",
    "germany",
    "france",
    "area",
    "metro",
    "greater",
    "region",
    "county",
}

_US_STATE_ABBR = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il",
    "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt",
    "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri",
    "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc",
}

NAME_ALIASES = {"name", "fullname", "full_name", "originalname", "contactname"}
DESIGNATION_ALIASES = {
    "designation",
    "jobtitle",
    "title",
    "position",
    "role",
    "job",
}
COMPANY_ALIASES = {
    "company",
    "organization",
    "organisation",
    "employer",
    "companyname",
    "org",
}
LOCATION_ALIASES = {"location", "city", "geo", "address", "locality", "region"}


@dataclass
class VerificationResult:
    status: str
    score: int
    compared: int
    matched: int
    reason: str
    name_match: bool | None
    designation_match: bool | None
    company_match: bool | None
    location_match: bool | None
    original_name: str | None
    original_designation: str | None
    original_company: str | None
    original_location: str | None


def _strip_punct(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    text = _strip_punct(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_company(value: Any) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    tokens = text.split()
    while tokens and tokens[-1] in _COMPANY_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def normalize_location(value: Any) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    tokens = [t for t in re.split(r"[\s,]+", text) if t]
    kept: list[str] = []
    for token in tokens:
        compact = re.sub(r"[^a-z0-9]", "", token)
        if not compact or compact in _LOCATION_NOISE or compact in _US_STATE_ABBR:
            continue
        kept.append(compact)
    return " ".join(kept) if kept else re.sub(r"[^a-z0-9]", "", text)


def normalize_name(value: Any) -> str:
    return normalize_text(value)


def _pick_from_row(source: dict[str, Any] | None, aliases: set[str]) -> str | None:
    if not isinstance(source, dict):
        return None
    for key, value in source.items():
        if _normalize_header(str(key)) in aliases:
            text = str(value).strip() if value is not None else ""
            if text and text.lower() not in {"none", "nan", "null", "n/a", "-"}:
                return text
    return None


def original_fields(source_row: dict[str, Any] | None) -> dict[str, str | None]:
    fields = {
        "name": _pick_from_row(source_row, NAME_ALIASES),
        "designation": _pick_from_row(source_row, DESIGNATION_ALIASES),
        "company": _pick_from_row(source_row, COMPANY_ALIASES),
        "location": _pick_from_row(source_row, LOCATION_ALIASES),
    }
    if not fields["name"] and isinstance(source_row, dict):
        first = _pick_from_row(source_row, {"firstname", "first", "givenname"})
        last = _pick_from_row(source_row, {"lastname", "last", "surname", "familyname"})
        combined = " ".join(p for p in (first, last) if p).strip()
        fields["name"] = combined or None
    return fields


def _compare_generic(original: str | None, extracted: str | None, normalizer) -> bool | None:
    if not original or not str(original).strip():
        return None
    left = normalizer(original)
    right = normalizer(extracted)
    if not left:
        return None
    if not right:
        return False
    return left == right


def _compare_company(original: str | None, extracted: str | None) -> bool | None:
    if not original or not str(original).strip():
        return None
    left = normalize_company(original)
    right = normalize_company(extracted)
    if not left:
        return None
    if not right:
        return False
    if left == right:
        return True
    # Conservative containment after suffix strip only (Microsoft vs Microsoft Corporation).
    if len(left) >= 4 and (left in right or right in left):
        shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
        if longer.startswith(shorter + " ") or longer.endswith(" " + shorter):
            return True
    return False


def compare_uploaded_vs_extracted(
    source_row: dict[str, Any] | None,
    *,
    extracted_name: str | None,
    extracted_designation: str | None,
    extracted_company: str | None,
    extracted_location: str | None,
    match_threshold: int = 100,
    review_threshold: int = 100,
) -> VerificationResult:
    originals = original_fields(source_row)
    name_match = _compare_generic(originals["name"], extracted_name, normalize_name)
    designation_match = _compare_generic(
        originals["designation"], extracted_designation, normalize_text
    )
    company_match = _compare_company(originals["company"], extracted_company)
    location_match = _compare_generic(
        originals["location"], extracted_location, normalize_location
    )

    flags = [name_match, designation_match, company_match, location_match]
    compared = sum(1 for f in flags if f is not None)
    matched = sum(1 for f in flags if f is True)
    if compared == 0:
        return VerificationResult(
            status=VERIFY_NOT_VERIFIED,
            score=0,
            compared=0,
            matched=0,
            reason="No original Name/Designation/Company/Location values to compare",
            name_match=name_match,
            designation_match=designation_match,
            company_match=company_match,
            location_match=location_match,
            original_name=originals["name"],
            original_designation=originals["designation"],
            original_company=originals["company"],
            original_location=originals["location"],
        )

    score = int(round((matched / compared) * 100))
    mismatches = []
    if name_match is False:
        mismatches.append("name")
    if designation_match is False:
        mismatches.append("designation")
    if company_match is False:
        mismatches.append("company")
    if location_match is False:
        mismatches.append("location")

    if not mismatches and score >= match_threshold:
        status = VERIFY_VERIFIED
        reason = f"{matched}/{compared} fields matched"
    elif not mismatches:
        status = VERIFY_REVIEW
        reason = f"{matched}/{compared} fields matched"
    elif score >= review_threshold:
        status = VERIFY_REVIEW
        reason = "Partial match: " + ", ".join(mismatches)
    else:
        status = VERIFY_MISMATCH
        reason = "Mismatch: " + ", ".join(mismatches)

    return VerificationResult(
        status=status,
        score=score,
        compared=compared,
        matched=matched,
        reason=reason,
        name_match=name_match,
        designation_match=designation_match,
        company_match=company_match,
        location_match=location_match,
        original_name=originals["name"],
        original_designation=originals["designation"],
        original_company=originals["company"],
        original_location=originals["location"],
    )


def apply_verification(item: Any, *, match_threshold: int, review_threshold: int) -> VerificationResult:
    """Write verification fields onto a bulk job item. Does not change extraction status."""
    if getattr(item, "status", None) != "SUCCESS":
        item.verification_status = VERIFY_NOT_VERIFIED
        item.verification_score = 0
        item.name_match = None
        item.designation_match = None
        item.company_match = None
        item.location_match = None
        item.verification_reason = "Extraction did not succeed"
        return VerificationResult(
            status=VERIFY_NOT_VERIFIED,
            score=0,
            compared=0,
            matched=0,
            reason=item.verification_reason,
            name_match=None,
            designation_match=None,
            company_match=None,
            location_match=None,
            original_name=None,
            original_designation=None,
            original_company=None,
            original_location=None,
        )

    result = compare_uploaded_vs_extracted(
        getattr(item, "source_row_json", None),
        extracted_name=getattr(item, "name", None),
        extracted_designation=getattr(item, "designation", None),
        extracted_company=getattr(item, "company", None),
        extracted_location=getattr(item, "location", None),
        match_threshold=match_threshold,
        review_threshold=review_threshold,
    )
    item.verification_status = result.status
    item.verification_score = result.score
    item.name_match = result.name_match
    item.designation_match = result.designation_match
    item.company_match = result.company_match
    item.location_match = result.location_match
    item.verification_reason = result.reason
    return result
