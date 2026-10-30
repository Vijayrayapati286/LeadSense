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
    normalize_name,
    original_fields,
    plan_field_updates,
    values_equivalent,
)


def test_name_ignores_linkedin_credentials():
    assert normalize_name("Harold Rogers, J.D.,SHRM-CP, GBA") == normalize_name("Harold Rogers")
    result = compare_uploaded_vs_extracted(
        {
            "Name": "Harold Rogers",
            "Designation": "Vice President, Human Resources",
            "Company": "Blue Cross & Blue Shield of Mississippi",
            "Location": "Flowood, Mississippi, United States",
            "Company Location": "Flowood, Mississippi, United States",
        },
        extracted_name="Harold Rogers, J.D.,SHRM-CP, GBA",
        extracted_designation="Vice President, Human Resources",
        extracted_company="Blue Cross & Blue Shield of Mississippi",
        extracted_location="Flowood, Mississippi, United States",
    )
    assert result.name_match is True
    assert result.designation_match is True
    assert result.company_match is True
    assert result.status == VERIFY_VERIFIED


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


def test_usa_location_matches_when_linkedin_omits_country():
    """A USA sheet location matches a US metro that does not name the country."""
    assert compare_field("location", "United States", "Greater Boston Area") is True
    assert compare_field("location", "USA", "Dallas-Fort Worth Metroplex") is True
    assert compare_field("location", "USA, Texas", "New York, NY") is True
    assert compare_field(
        "location", "United States", "London, England, United Kingdom"
    ) is False
    assert compare_field("location", "United States", None) is False
    assert compare_field("location", "United States", "") is False
    assert compare_field("location", "India", "Greater Boston Area") is False


def test_usa_company_location_matches_metro_without_country():
    row = {"Company Country": "USA", "Company City": "Boston"}
    assert compare_field(
        "company_location",
        "Boston, USA",
        "Greater Boston Area",
        source_row=row,
    ) is True
    result = compare_uploaded_vs_extracted(
        {
            "Name": "Alex",
            "Company": "Acme",
            "Country": "United States",
            "Company Country": "USA",
        },
        extracted_name="Alex",
        extracted_designation=None,
        extracted_company="Acme",
        extracted_location="Greater Boston Area",
    )
    assert result.location_match is True
    assert result.company_location_match is True


def test_same_sheet_state_matches_different_city():
    """Sheet state equals the extracted state: city differences are not a mismatch."""
    row = {"Location": "Pune", "State": "Maharashtra", "Country": "India"}
    assert compare_field(
        "location", "Pune", "Nagpur, Maharashtra", source_row=row
    ) is True
    assert compare_field(
        "location", "Pune", "London, United Kingdom", source_row=row
    ) is False
    us_row = {"Location": "100 Main Street", "State": "MS"}
    assert compare_field(
        "location", "100 Main Street", "Columbus, Mississippi", source_row=us_row
    ) is True
    assert compare_field(
        "location", "100 Main Street", "Columbus, Ohio", source_row=us_row
    ) is True


def test_state_in_sheet_country_is_verified():
    """A state that belongs to the sheet country verifies, even when the state name differs."""
    usa = {"Location": "Macon", "State": "Mississippi", "Country": "United States"}
    assert compare_field("location", "Macon", "Austin, Texas", source_row=usa) is True
    assert compare_field(
        "location", "Macon", "London, United Kingdom", source_row=usa
    ) is False
    state_only = {"Location": "100 Main Street", "State": "MS"}
    assert compare_field(
        "location", "100 Main Street", "Columbus, Ohio", source_row=state_only
    ) is True
    assert compare_field(
        "location", "100 Main Street", "London, United Kingdom", source_row=state_only
    ) is False
    india = {"Location": "Pune", "State": "Maharashtra", "Country": "India"}
    assert compare_field("location", "Pune", "Austin, Texas", source_row=india) is False
    company = {"Company City": "Jackson", "Company State": "MS"}
    assert compare_field(
        "company_location", "Jackson", "Austin, Texas", source_row=company
    ) is True


def test_same_state_does_not_hide_name_or_company_mismatch():
    result = compare_uploaded_vs_extracted(
        {
            "Name": "John Smith",
            "Company": "Microsoft",
            "Location": "Pune",
            "State": "Maharashtra",
            "Country": "India",
            "Company State": "Maharashtra",
            "Company Country": "India",
        },
        extracted_name="Jane Doe",
        extracted_designation=None,
        extracted_company="Google",
        extracted_location="Nagpur, Maharashtra",
    )
    assert result.location_match is True
    assert result.company_location_match is True
    assert result.name_match is False
    assert result.company_match is False
    assert result.status == VERIFY_MISMATCH


def test_company_state_matches_different_city():
    row = {
        "Company City": "Pune",
        "Company State": "Maharashtra",
        "Company Country": "India",
    }
    assert compare_field(
        "company_location",
        "Pune",
        "Nagpur, Maharashtra",
        source_row=row,
    ) is True


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


def test_same_country_location_change_is_updated_and_commented():
    plan = plan_field_updates(
        {
            "Name": "Asha Rao",
            "Designation": "VP",
            "Company": "3CDC",
            "Location": "Bangalore, Karnataka, India",
            "Comments": "Existing note",
        },
        extracted_name="Asha Rao",
        extracted_designation="VP",
        extracted_company="3CDC",
        extracted_location="Hyderabad, Telangana, India",
    )
    assert plan.needs_manual_review is False
    assert plan.resolved["location"] == "Hyderabad, Telangana, India"
    assert "location" in plan.auto_fields
    assert plan.comments == [
        "Location changed from Bangalore, Karnataka to Hyderabad, Telangana. "
        "Country remains India. Verified based on the available data."
    ]


def test_designation_change_with_extracted_title_is_updated():
    plan = plan_field_updates(
        {
            "Name": "Sam Lee",
            "Designation": "Senior Developer",
            "Company": "Acme",
            "Location": "Austin, Texas, United States",
        },
        extracted_name="Sam Lee",
        extracted_designation="VP",
        extracted_company="Acme",
        extracted_location="Austin, Texas, United States",
    )
    assert plan.needs_manual_review is False
    assert plan.resolved["designation"] == "VP"
    assert plan.comments == [
        "Designation changed from Senior Developer to VP. "
        "Updated based on verified extracted data."
    ]


def test_country_change_is_not_updated():
    plan = plan_field_updates(
        {
            "Name": "Asha Rao",
            "Designation": "VP",
            "Company": "3CDC",
            "Location": "Bangalore, Karnataka, India",
        },
        extracted_name="Asha Rao",
        extracted_designation="VP",
        extracted_company="3CDC",
        extracted_location="Austin, Texas, United States",
    )
    assert "location" not in plan.resolved
    assert plan.needs_manual_review is True
    assert "Manual Review Required" in plan.comments[0]
    assert "Country changed from India to United States" in plan.comments[0]


def test_matching_fields_produce_no_comment():
    plan = plan_field_updates(
        {
            "Name": "Tim Szilasi",
            "Designation": "Chief Financial Officer",
            "Company": "3CDC",
            "Location": "Cincinnati, Ohio, United States",
        },
        extracted_name="Tim Szilasi",
        extracted_designation="Chief Financial Officer",
        extracted_company="3CDC",
        extracted_location="Cincinnati, Ohio, United States",
    )
    assert plan.comments == []
    assert plan.needs_manual_review is False


def test_blank_designation_is_left_for_review():
    plan = plan_field_updates(
        {
            "Name": "Tim Szilasi",
            "Designation": "Chief Financial Officer",
            "Company": "3CDC",
            "Location": "Cincinnati, Ohio, United States",
        },
        extracted_name="Tim Szilasi",
        extracted_designation="",
        extracted_company="3CDC",
        extracted_location="Cincinnati, Ohio, United States",
    )
    assert "designation" not in plan.resolved
    assert plan.needs_manual_review is True
    assert "Existing value kept: Chief Financial Officer" in plan.comments[0]
