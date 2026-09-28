"""Tests for ICP CRM export-mapping enrichment and backfill."""

from __future__ import annotations

from app.database.connection import SessionLocal, init_db
from app.icp.models import IcpRecordRow
from app.icp.service import (
    _enrich_export_mapping_fields,
    _parse_location,
    _split_name,
    backfill_icp_export_mapping_fields,
)


def test_split_name_and_parse_location():
    assert _split_name("John Matthews") == ("John", "Matthews")
    parsed = _parse_location("Ocean Springs, Mississippi, United States")
    assert parsed["city"] == "Ocean Springs"
    assert parsed["state"] == "Mississippi"
    assert parsed["country"] == "United States"
    assert parsed["country_code"] == "US"


def test_enrich_uses_sheet_company_city():
    source = {
        "First Name": "John",
        "Last Name": "Matthews",
        "City": "Ocean Springs",
        "State": "Mississippi",
        "Country": "United States",
        "Company City": "Biloxi",
        "Company State": "Mississippi",
        "Company Country": "United States",
    }
    payload = _enrich_export_mapping_fields(
        {"name": "John Matthews", "location": "Ocean Springs, Mississippi, United States"},
        source,
    )
    assert payload["name"] == "John Matthews"
    assert "first_name" not in payload
    assert "last_name" not in payload
    assert payload["city"] == "Ocean Springs"
    assert payload["company_city"] == "Biloxi"
    assert payload["account_city"] == "Biloxi"
    assert payload["company_location"] == "Biloxi, Mississippi, United States"
    assert payload["country_code"] == "US"


def test_enrich_composes_name_from_sheet_parts_without_storing_them():
    payload = _enrich_export_mapping_fields(
        {},
        {"First Name": "Ada", "Last Name": "Lovelace"},
    )
    assert payload["name"] == "Ada Lovelace"
    assert "first_name" not in payload
    assert "last_name" not in payload


def test_backfill_fills_null_city_from_location():
    init_db()
    db = SessionLocal()
    try:
        row = IcpRecordRow(
            user_id=1,
            org_id="org-export-test",
            name="Patricia Curtis",
            location="Biloxi, Mississippi, United States",
            company_name="Beau Rivage",
            source="manual",
            verification_status="VERIFIED",
            icp_status="verified",
        )
        db.add(row)
        db.commit()
        row_id = row.id

        updated = backfill_icp_export_mapping_fields(db, org_id="org-export-test")
        db.commit()
        row = db.query(IcpRecordRow).filter(IcpRecordRow.id == row_id).one()

        assert updated >= 1
        assert row.name == "Patricia Curtis"
        assert "first_name" not in IcpRecordRow.__table__.columns
        assert "last_name" not in IcpRecordRow.__table__.columns
        assert row.city == "Biloxi"
        assert row.state == "Mississippi"
        assert row.country == "United States"
        assert row.country_code == "US"
        assert row.contact_state == "Mississippi"
        assert row.contact_country == "United States"
    finally:
        db.query(IcpRecordRow).filter(IcpRecordRow.org_id == "org-export-test").delete()
        db.commit()
        db.close()
