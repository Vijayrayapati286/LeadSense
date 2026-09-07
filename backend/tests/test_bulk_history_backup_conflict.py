"""History list, conflict resolve audit, and backup restore round-trip."""

from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone

import pytest

from app.database.connection import SessionLocal, init_db
from app.linkedin.backup_service import create_job_backup, restore_backup
from app.linkedin.bulk_jobs import create_job_with_items, refresh_job_counters
from app.linkedin.bulk_models import (
    ITEM_SUCCESS,
    BulkExtractJobRow,
    BulkJobItemRow,
    ConflictResolutionRow,
)
from app.linkedin.conflict_service import resolve_item_fields
from app.linkedin.verification import VERIFY_MISMATCH, VERIFY_RESOLVED


@pytest.fixture(autouse=True)
def _schema():
    init_db()


def _seed_mismatch_job(*, user_id: int = 1) -> tuple[str, int]:
    job = create_job_with_items(
        user_id=user_id,
        original_file_name="history-demo.xlsx",
        input_columns=["Name", "Company", "LinkedIn URL"],
        url_rows=[
            {
                "source_row_number": 2,
                "raw_url": "https://www.linkedin.com/in/alice",
                "normalized_url": "https://www.linkedin.com/in/alice",
                "is_valid": True,
                "source_row_json": {
                    "Name": "Alice Uploaded",
                    "Company": "UploadCo",
                    "LinkedIn URL": "https://www.linkedin.com/in/alice",
                },
            }
        ],
    )
    db = SessionLocal()
    try:
        item = db.query(BulkJobItemRow).filter(BulkJobItemRow.job_id == job.id).one()
        item.status = ITEM_SUCCESS
        item.name = "Alice Extracted"
        item.company = "ExtractCo"
        item.designation = "Engineer"
        item.location = "NYC"
        item.verification_status = VERIFY_MISMATCH
        item.name_match = False
        item.company_match = False
        item.designation_match = True
        item.location_match = True
        item.verification_score = 50
        item.completed_at = datetime.now(timezone.utc)
        job_row = db.query(BulkExtractJobRow).filter(BulkExtractJobRow.id == job.id).one()
        job_row.status = "done"
        refresh_job_counters(db, job_row)
        db.commit()
        return job.id, item.id
    finally:
        db.close()


def test_list_bulk_jobs_history(client):
    job_id, _ = _seed_mismatch_job()
    resp = client.get("/api/linkedin/bulk-jobs", params={"q": "history-demo"})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["total"] >= 1
    ids = {j["job_id"] for j in payload["items"]}
    assert job_id in ids
    match = next(j for j in payload["items"] if j["job_id"] == job_id)
    assert match["needs_review"] >= 1
    assert match["original_file_name"] == "history-demo.xlsx"


def test_conflict_resolve_keeps_originals_and_audits(client):
    job_id, item_id = _seed_mismatch_job()
    resp = client.post(
        f"/api/linkedin/bulk-jobs/{job_id}/conflicts/{item_id}/resolve",
        json={
            "decisions": [
                {"field": "name", "resolution": "KEEP_UPLOADED"},
                {"field": "company", "resolution": "KEEP_EXTRACTED"},
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verification_status"] == VERIFY_RESOLVED

    db = SessionLocal()
    try:
        item = db.query(BulkJobItemRow).filter(BulkJobItemRow.id == item_id).one()
        # originals / extracted untouched
        assert item.source_row_json["Name"] == "Alice Uploaded"
        assert item.name == "Alice Extracted"
        assert item.company == "ExtractCo"
        assert item.resolved_name == "Alice Uploaded"
        assert item.resolved_company == "ExtractCo"
        assert item.verification_status == VERIFY_RESOLVED
        rows = (
            db.query(ConflictResolutionRow)
            .filter(ConflictResolutionRow.job_item_id == item_id)
            .all()
        )
        assert {r.field for r in rows} == {"name", "company"}
        assert all(r.change_summary for r in rows)
        job = db.query(BulkExtractJobRow).filter(BulkExtractJobRow.id == job_id).one()
        assert (job.needs_review_count or 0) == 0
        assert (job.resolved_count or 0) >= 1
    finally:
        db.close()

    audit = client.get(f"/api/linkedin/bulk-jobs/{job_id}/audit")
    assert audit.status_code == 200, audit.text
    entries = audit.json()["items"]
    assert len(entries) >= 2
    assert any("changed company" in (e.get("change_summary") or "").lower() or "company" in (e.get("field") or "") for e in entries)


def test_backup_restore_creates_new_job(client):
    job_id, item_id = _seed_mismatch_job()
    # resolve so backup has resolution rows
    db = SessionLocal()
    try:
        item = db.query(BulkJobItemRow).filter(BulkJobItemRow.id == item_id).one()
        resolve_item_fields(
            db,
            item,
            decisions={
                "name": {"resolution": "KEEP_EXISTING"},
                "company": {"resolution": "MANUAL_EDIT", "edited_value": "Acme Corp"},
            },
            user_id=1,
        )
        job = db.query(BulkExtractJobRow).filter(BulkExtractJobRow.id == job_id).one()
        refresh_job_counters(db, job)
        db.commit()
    finally:
        db.close()

    backup = create_job_backup(job_id, user_id=1)
    assert backup.status == "ready"
    from app.linkedin.backup_service import resolve_backup_path

    path = resolve_backup_path(backup.file_path)
    assert path is not None and path.is_file()
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "job.json" in names
        assert "items.json" in names

    content = path.read_bytes()
    restored = restore_backup(content, user_id=1)
    assert restored.id != job_id
    assert restored.original_file_name.startswith("RESTORED-")

    # API restore
    resp = client.post(
        "/api/linkedin/bulk-backups/restore",
        files={"file": ("backup.zip", content, "application/zip")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["job_id"] != job_id


def test_items_filter_needs_review(client):
    job_id, _ = _seed_mismatch_job()
    resp = client.get(
        f"/api/linkedin/bulk-jobs/{job_id}/items",
        params={"needs_review": True},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    assert payload["items"][0]["needs_review"] is True


def test_manual_edit_preserves_original_and_extracted():
    job_id, item_id = _seed_mismatch_job()
    db = SessionLocal()
    try:
        item = db.query(BulkJobItemRow).filter(BulkJobItemRow.id == item_id).one()
        resolve_item_fields(
            db,
            item,
            decisions={
                "name": {"resolution": "KEEP_EXISTING"},
                "company": {"resolution": "MANUAL_EDIT", "edited_value": "Microsoft Corporation"},
            },
            user_id=1,
        )
        db.commit()
        item = db.query(BulkJobItemRow).filter(BulkJobItemRow.id == item_id).one()
        assert item.source_row_json["Company"] == "UploadCo"
        assert item.company == "ExtractCo"
        assert item.resolved_company == "Microsoft Corporation"
        assert item.resolved_name == "Alice Uploaded"
        assert item.verification_status == VERIFY_RESOLVED
        rows = db.query(ConflictResolutionRow).filter(ConflictResolutionRow.job_item_id == item_id).all()
        by_field = {r.field: r for r in rows}
        assert by_field["company"].resolution == "MANUAL_EDIT"
        assert by_field["company"].resolved_value == "Microsoft Corporation"
        assert by_field["name"].resolution == "KEEP_UPLOADED"
    finally:
        db.close()

