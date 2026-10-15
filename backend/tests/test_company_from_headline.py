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


def test_title_from_headline_at_pattern():
    assert (
        LinkedInApifyProfileExtractor._title_from_headline(
            "Chief Financial Officer at 3CDC"
        )
        == "Chief Financial Officer"
    )


def test_title_from_headline_case_insensitive_at():
    assert (
        LinkedInApifyProfileExtractor._title_from_headline(
            "Director Of IT At First South Farm Credit"
        )
        == "Director Of IT"
    )


def test_title_from_headline_at_sign():
    assert (
        LinkedInApifyProfileExtractor._title_from_headline(
            "Chief Financial Officer @ 3CDC"
        )
        == "Chief Financial Officer"
    )


def test_title_from_headline_ignores_tagline():
    assert LinkedInApifyProfileExtractor._title_from_headline("Building better cities") is None


def test_designation_or_headline_title_keeps_explicit_title():
    assert (
        LinkedInApifyProfileExtractor.designation_or_headline_title(
            "Director of Information Technology",
            "Director of IT at First South Farm Credit",
        )
        == "Director of Information Technology"
    )


def test_designation_or_headline_title_fills_blank():
    assert (
        LinkedInApifyProfileExtractor.designation_or_headline_title(
            "",
            "Chief Legal Officer & EVP of Human Resources at 3CDC",
        )
        == "Chief Legal Officer & EVP of Human Resources"
    )


def test_map_rich_item_fills_job_title_from_headline_when_missing():
    extractor = LinkedInApifyProfileExtractor.__new__(LinkedInApifyProfileExtractor)
    mapped = extractor._map_rich_item(
        {
            "firstName": "Tim",
            "lastName": "Szilasi",
            "companyName": "3CDC",
            "headline": "Chief Financial Officer at 3CDC",
        }
    )
    assert mapped["job_title"] == "Chief Financial Officer"
    assert mapped["company"] == "3CDC"
    assert mapped["headline"] == "Chief Financial Officer at 3CDC"


def test_map_rich_item_keeps_explicit_job_title():
    extractor = LinkedInApifyProfileExtractor.__new__(LinkedInApifyProfileExtractor)
    mapped = extractor._map_rich_item(
        {
            "firstName": "Mark",
            "lastName": "Huff",
            "jobTitle": "Director of Information Technology",
            "headline": "Director of IT at First South Farm Credit",
        }
    )
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


def test_map_rich_item_uses_nested_position_title_and_company():
    """Grouped experience: title lives under positions[0].positions[0], company under company.name."""
    extractor = LinkedInApifyProfileExtractor.__new__(LinkedInApifyProfileExtractor)
    mapped = extractor._map_rich_item(
        {
            "firstName": "Amit",
            "lastName": "Chaudhri",
            "headline": "Director Data Architecture at HCA",
            "jobTitle": "",
            "positions": [
                {
                    "company": {"name": "HCA Healthcare"},
                    "positions": [
                        {"title": "Director Data Architecture"},
                    ],
                }
            ],
        }
    )
    assert mapped["job_title"] == "Director Data Architecture"
    assert mapped["company"] == "HCA Healthcare"
    assert mapped["headline"] == "Director Data Architecture at HCA"


def test_map_rich_item_prefers_nested_title_when_job_title_copies_headline():
    extractor = LinkedInApifyProfileExtractor.__new__(LinkedInApifyProfileExtractor)
    mapped = extractor._map_rich_item(
        {
            "firstName": "Amit",
            "lastName": "Chaudhri",
            "headline": "Director Data Architecture at HCA",
            "jobTitle": "Director Data Architecture at HCA",
            "positions": [
                {
                    "company": {"name": "HCA Healthcare"},
                    "positions": [{"title": "Director Data Architecture"}],
                }
            ],
        }
    )
    assert mapped["job_title"] == "Director Data Architecture"
    assert mapped["company"] == "HCA Healthcare"


def test_normalize_item_uses_nested_role_instead_of_full_headline():
    extractor = LinkedInApifyProfileExtractor.__new__(LinkedInApifyProfileExtractor)
    mapped = extractor._normalize_item(
        {
            "firstName": "Amit",
            "lastName": "Chaudhri",
            "headline": "Director Data Architecture at HCA",
            "jobTitle": "",
            "positions": [
                {
                    "company": {"name": "HCA Healthcare"},
                    "positions": [{"title": "Director Data Architecture"}],
                }
            ],
        }
    )
    assert mapped["job_title"] == "Director Data Architecture"
    assert mapped["company"] == "HCA Healthcare"


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
