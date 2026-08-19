from app.linkedin.verification import (
    VERIFY_MISMATCH,
    VERIFY_VERIFIED,
    compare_uploaded_vs_extracted,
    normalize_company,
    normalize_location,
)


def test_company_suffix_normalizes_to_same_core():
    assert normalize_company("Microsoft Corporation") == normalize_company("Microsoft")


def test_location_city_vs_city_state():
    assert normalize_location("NEW YORK, NY") == normalize_location("New York")


def test_verified_when_all_fields_match():
    result = compare_uploaded_vs_extracted(
        {
            "Name": "John Smith",
            "Designation": "Software Engineer",
            "Company": "Microsoft",
            "Location": "Seattle",
        },
        extracted_name="John Smith",
        extracted_designation="Software Engineer",
        extracted_company="Microsoft Corporation",
        extracted_location="Seattle, WA",
    )
    assert result.status == VERIFY_VERIFIED
    assert result.score == 100
    assert result.company_match is True


def test_mismatch_does_not_require_fuzzy_false_positive():
    result = compare_uploaded_vs_extracted(
        {"Name": "John Smith", "Company": "Microsoft", "Designation": "Engineer", "Location": "Seattle"},
        extracted_name="John Smith",
        extracted_designation="Engineer",
        extracted_company="Google",
        extracted_location="Seattle",
    )
    assert result.status == VERIFY_MISMATCH
    assert result.company_match is False
    assert result.name_match is True
    assert result.score == 75
