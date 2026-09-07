"""Unit tests for S3 storage service (mocked / local mock backend)."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from openpyxl import Workbook

from app.database.connection import SessionLocal, init_db
from app.storage.exceptions import FileValidationError, S3StorageError, UnauthorizedFileAccess
from app.storage.file_service import (
    batch_content_version,
    build_download_payload,
    ensure_verified_download,
    find_reusable_verified,
    list_batch_files,
    store_original_upload,
    store_verified_result,
    validate_upload,
)
from app.storage.keys import build_upload_key, sanitize_filename
from app.storage.models import FILE_ORIGINAL_UPLOAD, FILE_VERIFIED_RESULT, StoredFileRow
from app.storage.s3_service import S3Service, get_s3_service, reset_s3_service


@pytest.fixture(autouse=True)
def _schema_and_mock_s3(monkeypatch, tmp_path):
    monkeypatch.setenv("USE_MOCK_S3", "true")
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")
    reset_s3_service()
    # Point mock root at tmp
    import app.storage.s3_service as s3mod

    monkeypatch.setattr(s3mod, "_MOCK_ROOT", tmp_path / "s3_mock")
    init_db()
    yield
    reset_s3_service()


def _xlsx_bytes(name: str = "Sheet1") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = name
    ws.append(["LinkedIn URL", "Name"])
    ws.append(["https://www.linkedin.com/in/alice", "Alice"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_sanitize_and_s3_key_generation():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("customers.xlsx") == "customers.xlsx"
    key = build_upload_key(user_id=123, batch_id="batch-456", filename="customers.xlsx")
    assert key.startswith("uploads/123/batch-456/original/")
    assert key.endswith("customers.xlsx")
    assert ".." not in key


def test_validate_upload_rejects_bad_type_and_empty():
    with pytest.raises(FileValidationError):
        validate_upload(filename="x.exe", content=b"MZ")
    with pytest.raises(FileValidationError):
        validate_upload(filename="a.xlsx", content=b"")


def test_upload_file_creates_db_metadata(client):
    content = _xlsx_bytes()
    resp = client.post(
        "/api/files/upload",
        files={
            "file": (
                "customers.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["file_type"] == FILE_ORIGINAL_UPLOAD
    assert body["status"] == "uploaded"
    assert body["file_size"] == len(content)
    assert "uploads/" in body["s3_key"]

    meta = client.get(f"/api/files/{body['file_id']}")
    assert meta.status_code == 200
    assert meta.json()["filename"] == "customers.xlsx"
    assert meta.json().get("s3_key") in (None, "")


def test_s3_key_and_download_url_generation():
    s3 = get_s3_service()
    key = "verified/1/abc/verified.xlsx"
    s3.upload_bytes(key=key, data=b"hello", content_type="text/plain")
    assert s3.file_exists(key=key)
    url = s3.generate_presigned_download_url(
        key=key,
        mock_content_url="http://localhost:8000/api/files/1/content",
    )
    assert "/api/files/1/content" in url
    assert s3.download_bytes(key=key) == b"hello"


def test_verification_result_upload_and_reuse():
    db = SessionLocal()
    try:
        batch_id = "batch-reuse-1"
        content = _xlsx_bytes("Verified")
        row = store_verified_result(
            db,
            user_id=1,
            batch_id=batch_id,
            content=content,
            filename="verified.xlsx",
            content_version="v1",
        )
        db.commit()
        file_id = row.id

        again = store_verified_result(
            db,
            user_id=1,
            batch_id=batch_id,
            content=content + b"x",
            filename="verified.xlsx",
            content_version="v1",
        )
        db.commit()
        assert again.id == file_id  # same version → reuse, no duplicate row

        updated = store_verified_result(
            db,
            user_id=1,
            batch_id=batch_id,
            content=_xlsx_bytes("V2"),
            filename="verified.xlsx",
            content_version="v2",
        )
        db.commit()
        assert updated.content_version == "v2"
        assert updated.id == file_id  # replace in place
    finally:
        db.close()


def test_download_url_and_batch_files(client):
    content = _xlsx_bytes()
    up = client.post(
        "/api/files/upload",
        files={"file": ("in.xlsx", content, "application/octet-stream")},
        params={"batch_id": "batch-files-1"},
    )
    assert up.status_code == 200
    batch_id = up.json()["batch_id"]

    db = SessionLocal()
    try:
        store_verified_result(
            db,
            user_id=1,
            batch_id=batch_id,
            content=content,
            filename="verified.xlsx",
            content_version="ready",
        )
        db.commit()
    finally:
        db.close()

    listed = client.get(f"/api/batches/{batch_id}/files")
    assert listed.status_code == 200
    types = {f["type"] for f in listed.json()["files"]}
    assert FILE_ORIGINAL_UPLOAD in types
    assert FILE_VERIFIED_RESULT in types

    dl = client.get(f"/api/batches/{batch_id}/download")
    assert dl.status_code == 200
    payload = dl.json()
    assert "download_url" in payload
    assert payload["filename"]


def test_unauthorized_batch_access(client):
    db = SessionLocal()
    try:
        row = store_original_upload(
            db,
            user_id=999,
            batch_id="other-user-batch",
            filename="secret.xlsx",
            content=_xlsx_bytes(),
        )
        db.commit()
        file_id = row.id
    finally:
        db.close()

    # Default test user is not 999
    resp = client.get(f"/api/files/{file_id}")
    assert resp.status_code == 404


def test_missing_s3_object_marked_failed():
    db = SessionLocal()
    try:
        row = StoredFileRow(
            user_id=1,
            batch_id="missing-obj",
            file_type=FILE_VERIFIED_RESULT,
            original_filename="verified.xlsx",
            s3_bucket="test-bucket",
            s3_key="verified/1/missing-obj/verified.xlsx",
            file_size=1,
            status="ready",
            content_version="v1",
        )
        db.add(row)
        db.commit()
        found = find_reusable_verified(db, batch_id="missing-obj", content_version="v1")
        assert found is None
        db.refresh(row)
        assert row.status == "failed"
    finally:
        db.close()


def test_invalid_file_type_api(client):
    resp = client.post(
        "/api/files/upload",
        files={"file": ("malware.exe", b"not-an-excel", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_s3_upload_failure_does_not_mark_uploaded():
    db = SessionLocal()
    try:
        with patch.object(S3Service, "upload_bytes", side_effect=S3StorageError("boom")):
            reset_s3_service()
            with pytest.raises(S3StorageError):
                store_original_upload(
                    db,
                    user_id=1,
                    batch_id="fail-upload",
                    filename="a.xlsx",
                    content=_xlsx_bytes(),
                )
        count = (
            db.query(StoredFileRow)
            .filter(StoredFileRow.batch_id == "fail-upload", StoredFileRow.status == "uploaded")
            .count()
        )
        assert count == 0
    finally:
        db.close()
        reset_s3_service()


def test_presigned_url_generation_real_client_path():
    """When not mocking, generate_presigned_url is delegated to boto3."""
    svc = S3Service()
    svc.settings = MagicMock()
    svc.settings.use_mock_s3 = False
    svc.settings.s3_bucket_name = "prod-bucket"
    svc.settings.aws_region = "ap-south-1"
    svc.settings.aws_access_key_id = "AKIAtest"
    svc.settings.aws_secret_access_key = "secret"
    svc.settings.s3_presign_expires_seconds = 3600
    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = "https://s3.example/presigned"
    with patch.object(svc, "_get_client", return_value=mock_client):
        url = svc.generate_presigned_download_url(key="uploads/1/2/original/a.xlsx", filename="a.xlsx")
    assert url == "https://s3.example/presigned"
    mock_client.generate_presigned_url.assert_called_once()


def test_ensure_verified_reuses_existing():
    class Job:
        id = "job-ensure-1"
        user_id = 1
        resolved_count = 2
        verified_count = 1
        mismatch_count = 0
        needs_review_count = 0
        success_count = 3
        failed_count = 0
        processed_count = 3
        phase = "completed"
        excel_finalized = True
        updated_at = None

    db = SessionLocal()
    try:
        job = Job()
        version = batch_content_version(job)
        store_verified_result(
            db,
            user_id=1,
            batch_id=job.id,
            content=_xlsx_bytes(),
            filename="verified.xlsx",
            content_version=version,
        )
        db.commit()

        calls = {"n": 0}

        def gen():
            calls["n"] += 1
            return _xlsx_bytes(), "verified.xlsx"

        first = ensure_verified_download(db, job=job, user_id=1, generate_bytes=gen)
        second = ensure_verified_download(db, job=job, user_id=1, generate_bytes=gen)
        assert first["reused"] is True
        assert second["reused"] is True
        assert calls["n"] == 0
    finally:
        db.close()


def test_list_batch_files_blocks_other_user():
    db = SessionLocal()
    try:
        store_original_upload(
            db,
            user_id=42,
            batch_id="owned-42",
            filename="a.xlsx",
            content=_xlsx_bytes(),
        )
        db.commit()
        with pytest.raises(UnauthorizedFileAccess):
            list_batch_files(db, batch_id="owned-42", user_id=1)
    finally:
        db.close()
