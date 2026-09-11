"""Company fallback from headline when Apify omits companyName."""

from __future__ import annotations

from app.linkedin.apify_extractor import LinkedInApifyProfileExtractor
from app.linkedin.extractor import LinkedInProfileExtractor


def test_company_from_headline_at_pattern():
    assert (
        LinkedInApifyProfileExtractor._company_from_headline(
            "Director of IT at First South Farm Credit"
        )
        == "First South Farm Credit"
    )


def test_company_from_headline_case_insensitive_at():
    assert (
        LinkedInApifyProfileExtractor._company_from_headline(
            "Director Of IT At First South Farm Credit"
        )
        == "First South Farm Credit"
    )


def test_company_from_texts_prefers_headline_when_job_title_has_no_company():
    company = LinkedInApifyProfileExtractor._company_from_texts(
        "Director of Information Technology",
        "Director of IT at First South Farm Credit",
    )
    assert company == "First South Farm Credit"


def test_normalize_item_fills_company_from_headline_when_job_title_lacks_it():
    extractor = LinkedInApifyProfileExtractor.__new__(LinkedInApifyProfileExtractor)
    mapped = extractor._normalize_item(
        {
            "fullName": "Mark Huff",
            "jobTitle": "Director of Information Technology",
            "headline": "Director of IT at First South Farm Credit",
            "summary": "IT leader",
        }
    )
    assert mapped["company"] == "First South Farm Credit"
    assert mapped["job_title"] == "Director of Information Technology"


def test_map_rich_item_fills_company_from_headline():
    extractor = LinkedInApifyProfileExtractor.__new__(LinkedInApifyProfileExtractor)
    mapped = extractor._map_rich_item(
        {
            "firstName": "Mark",
            "lastName": "Huff",
            "jobTitle": "Director of Information Technology",
            "headline": "Director of IT at First South Farm Credit",
            "summary": "IT leader",
        }
    )
    assert mapped["company"] == "First South Farm Credit"


def test_playwright_extractor_company_from_headline():
    assert (
        LinkedInProfileExtractor._company_from_headline(
            "Director of IT at First South Farm Credit"
        )
        == "First South Farm Credit"
    )
    assert (
        LinkedInProfileExtractor._company_from_texts(
            "Director of Information Technology",
            "Director of IT at First South Farm Credit",
        )
        == "First South Farm Credit"
    )
