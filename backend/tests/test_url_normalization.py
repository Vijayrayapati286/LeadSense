"""Unit tests for LinkedIn / profile URL normalization."""

from __future__ import annotations

import pytest

from app.linkedin.validator import is_valid_extraction
from app.linkedin.validator import normalize_profile_url as li_normalize
from app.linkedin.validator import validate_profile_url as li_validate
from app.profile_extractor.validator import normalize_profile_url as pe_normalize
from app.profile_extractor.validator import url_hash
from app.profile_extractor.validator import validate_profile_url as pe_validate


@pytest.mark.parametrize(
    "raw,expected",
    [
        (
            "https://www.linkedin.com/in/jane-doe",
            "https://www.linkedin.com/in/jane-doe/",
        ),
        (
            "http://linkedin.com/in/jane-doe/?trk=abc#section",
            "https://www.linkedin.com/in/jane-doe/",
        ),
        (
            "https://www.linkedin.com/in/JaneDoe/",
            "https://www.linkedin.com/in/JaneDoe/",
        ),
    ],
)
def test_linkedin_url_normalization(raw: str, expected: str):
    assert li_normalize(raw) == expected
    assert li_validate(raw) == expected
    assert pe_normalize(raw) == expected
    assert pe_validate(raw) == expected


def test_rejects_sales_nav_and_non_profile_urls():
    with pytest.raises(ValueError):
        li_validate("https://www.linkedin.com/sales/search/people")
    with pytest.raises(ValueError):
        pe_validate("https://www.linkedin.com/company/acme")
    with pytest.raises(ValueError):
        pe_validate("https://example.com/in/someone")


def test_url_hash_stable_across_tracking_params():
    a = "https://linkedin.com/in/same-person/?trk=one"
    b = "https://www.linkedin.com/in/same-person/"
    assert url_hash(a) == url_hash(b)


def test_is_valid_extraction_requires_usable_fields():
    assert is_valid_extraction(
        {"status": "ok", "data": {"name": "Jane", "company": "", "job_title": "", "summary": ""}}
    )
    assert not is_valid_extraction({"status": "failed", "data": {"name": "Jane"}, "error": "x"})
    assert not is_valid_extraction({"success": True, "data": {}})
    assert not is_valid_extraction(None)
