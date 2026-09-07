from app.linkedin.verification import (
    VERIFY_MISMATCH,
    VERIFY_REVIEW,
    VERIFY_VERIFIED,
    compare_field,
    compare_uploaded_vs_extracted,
    country_from_location_text,
    evaluate_matches,
    normalize_company,
    normalize_country,
    normalize_location,
    original_fields,
    values_equivalent,
)


def test_company_suffix_normalizes_to_same_core():
    assert normalize_company("Microsoft Corporation") == normalize_company("Microsoft")


def test_location_city_vs_city_state():
    assert normalize_location("NEW YORK, NY") == normalize_location("New York")


def test_country_normalize_aliases():
    assert normalize_country("United States") == "us"
    assert normalize_country("USA") == "us"
    assert normalize_country("India") == "in"
    assert country_from_location_text("Macon, Mississippi") == "us"
    assert country_from_location_text("Macon, Mississippi, United States") == "us"
    assert country_from_location_text("Bengaluru, Karnataka, India") == "in"
    assert country_from_location_text("London, England, United Kingdom") == "uk"


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
    assert result.company_location_match is None


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
    # Identical "Seattle" on both sides counts as a compared, matching field.
    assert result.location_match is True
    assert result.score == 75


def test_original_fields_compose_person_and_company_locations():
    fields = original_fields(
        {
            "First Name": "Josh",
            "Last Name": "Hailey",
            "Title": "VP, Director of Technology",
            "Company Name": "BankFirst Financial Services",
            "City": "Macon",
            "State": "Mississippi",
            "Country": "United States",
            "Company City": "Columbus",
            "Company State": "Mississippi",
            "Company Country": "United States",
            "Company Address": "900 Main Street, Columbus, Mississippi, United States, 39701",
        }
    )
    assert fields["name"] == "Josh Hailey"
    assert fields["location"] == "Macon, Mississippi, United States"
    assert fields["company_location"] == "Columbus, Mississippi, United States"


def test_same_country_different_cities_is_verified():
    """Person city may differ from LinkedIn; country match → approve locations."""
    result = compare_uploaded_vs_extracted(
        {
            "First Name": "Josh",
            "Last Name": "Hailey",
            "Title": "VP, Director of Technology",
            "Company Name": "BankFirst Financial Services",
            "City": "Macon",
            "State": "Mississippi",
            "Country": "United States",
            "Company City": "Columbus",
            "Company State": "Mississippi",
            "Company Country": "United States",
            "Company Address": "900 Main Street, Columbus, Mississippi, United States, 39701",
        },
        extracted_name="Josh Hailey",
        extracted_designation="VP, Director of Technology",
        extracted_company="BankFirst Financial Services",
        extracted_location="Columbus, Mississippi, United States",
    )
    assert result.location_match is True
    assert result.company_location_match is True
    assert result.status == VERIFY_VERIFIED


def test_identical_person_location_strings_match_country():
    """Screenshot case: same full string on both sides must not flag a difference."""
    result = compare_uploaded_vs_extracted(
        {
            "Name": "Phillip Sprayberry",
            "Title": "Director of Human Resources",
            "Company Name": "BankFirst Financial Services",
            "City": "Columbus",
            "State": "Mississippi",
            "Country": "United States",
            "Company City": "Columbus",
            "Company State": "Mississippi",
            "Company Country": "United States",
        },
        extracted_name="Phillip Sprayberry",
        extracted_designation="Director of Human Resources",
        extracted_company="BankFirst Financial Services",
        extracted_location="Columbus, Mississippi, United States",
    )
    assert result.location_match is True
    assert result.company_location_match is True
    assert result.status == VERIFY_VERIFIED


def test_person_location_country_mismatch():
    result = compare_uploaded_vs_extracted(
        {
            "Name": "Josh Hailey",
            "Company": "BankFirst",
            "City": "Macon",
            "Country": "United States",
            "Company Country": "United States",
        },
        extracted_name="Josh Hailey",
        extracted_designation=None,
        extracted_company="BankFirst",
        extracted_location="London, England, United Kingdom",
    )
    assert result.location_match is False
    assert result.company_location_match is False
    assert result.status in {VERIFY_MISMATCH, VERIFY_REVIEW}
    assert "location" in result.reason


def test_company_location_country_mismatch():
    result = compare_uploaded_vs_extracted(
        {
            "Name": "Alex",
            "Company": "Acme",
            "City": "London",
            "Country": "United Kingdom",
            "Company City": "Bengaluru",
            "Company Country": "India",
        },
        extracted_name="Alex",
        extracted_designation=None,
        extracted_company="Acme",
        extracted_location="London, England, United Kingdom",
    )
    assert result.location_match is True
    assert result.company_location_match is False
    assert "company_location" in result.reason
    assert "person_vs_company_country" in result.reason


def test_identical_values_never_conflict():
    """Whatever the field rules say, the same text on both sides is a match."""
    same = "Macon, Mississippi, United States"
    assert values_equivalent(same, same) is True
    for field in ("name", "designation", "company", "location", "company_location"):
        assert compare_field(field, same, same, source_row={}) is True


def test_compare_field_shrugs_off_formatting_noise():
    assert compare_field("name", "David J. Johnson", "David Johnson") is True
    assert compare_field("name", "Hailey, Josh", "Josh Hailey") is True
    assert compare_field("name", "Dr. Alan Turing Jr.", "Alan Turing") is True
    assert compare_field("designation", "VP of Sales", "Vice President, Sales") is True
    assert compare_field("designation", "Director of Technology", "Technology Director") is True
    assert compare_field("company", "Johnson & Johnson", "Johnson and Johnson") is True
    assert compare_field("company", "Acme", "Globex") is False


def test_location_country_match_regardless_of_city():
    row = {"City": "Macon", "State": "Mississippi", "Country": "United States"}
    assert compare_field(
        "location", "Macon, Mississippi, United States", "Boston, Massachusetts, United States", source_row=row
    ) is True
    assert compare_field(
        "location", "Macon, Mississippi, United States", "London, England, United Kingdom", source_row=row
    ) is False


def test_location_without_country_falls_back_to_city_overlap():
    """An unresolvable country is inconclusive, never a fabricated conflict."""
    assert compare_field("location", "Boston, MA", "Greater Boston Area") is True
    assert compare_field("location", "Sector 5", "Remote") is None


def test_evaluate_matches_mirrors_the_score():
    row = {
        "Name": "Phillip Sprayberry",
        "Title": "Director of Human Resources",
        "Company Name": "BankFirst Financial Services",
        "City": "Columbus",
        "State": "Mississippi",
        "Country": "United States",
        "Company City": "Columbus",
        "Company State": "Mississippi",
        "Company Country": "United States",
    }
    extracted = {
        "name": "Phillip Sprayberry",
        "designation": "Director of Human Resources",
        "company": "BankFirst Financial Services",
        "location": "Columbus, Mississippi, United States",
    }
    matches = evaluate_matches(row, extracted)
    assert all(value is True for value in matches.values())


def test_company_country_vs_address_country_mismatch():
    result = compare_uploaded_vs_extracted(
        {
            "Name": "Alex",
            "Company": "Acme",
            "Company City": "London",
            "Company Country": "India",
            "Company Address": "1 King Street, London, United Kingdom",
        },
        extracted_name="Alex",
        extracted_designation=None,
        extracted_company="Acme",
        extracted_location="London, United Kingdom",
    )
    assert result.company_location_match is False
    assert "company_country_vs_address" in result.reason
