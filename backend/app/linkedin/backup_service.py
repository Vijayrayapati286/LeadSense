"""Create and restore ZIP backups of bulk LinkedIn extraction jobs.

backup_version = 1 package:
  manifest.json, job.json, items.json, attempts.json, resolutions.json, result.xlsx
"""

from __future__ import annotations

import io
import json
import logging
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.linkedin.bulk_excel_service import BulkExcelService, OUTPUTS_DIR
from app.linkedin.bulk_models import (
    BACKUP_FAILED,
    BACKUP_READY,
    ITEM_FINAL_FAILED,
    ITEM_PENDING,
    ITEM_QUEUED,
    ITEM_SUCCESS,
    PHASE_COMPLETED,
    PHASE_REVIEW,
    BulkBackupRow,
    BulkExtractJobRow,
    BulkJobItemRow,
    ConflictResolutionRow,
    ExtractionAttemptRow,
)

logger = logging.getLogger(__name__)

BACKUP_VERSION = 1
BACKUPS_DIR = OUTPUTS_DIR / "backups"


class BackupError(ValueError):
    """Invalid or incompatible backup package."""


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _dump(obj: Any) -> bytes:
    return json.dumps(obj, default=_json_default, indent=2).encode("utf-8")


def create_job_backup(job_id: str, *, user_id: int | None) -> BulkBackupRow:
    db = SessionLocal()
    try:
        job = db.query(BulkExtractJobRow).filter(BulkExtractJobRow.id == job_id).first()
        if not job:
            raise BackupError("Job not found")
        if job.user_id is not None and user_id is not None and job.user_id != user_id:
            raise BackupError("Job not found")

        items = (
            db.query(BulkJobItemRow)
            .filter(BulkJobItemRow.job_id == job_id)
            .order_by(BulkJobItemRow.source_row_number.asc())
            .all()
        )
        item_ids = [i.id for i in items]
        attempts = []
        resolutions = []
        if item_ids:
            attempts = (
                db.query(ExtractionAttemptRow)
                .filter(ExtractionAttemptRow.job_item_id.in_(item_ids))
                .order_by(ExtractionAttemptRow.job_item_id, ExtractionAttemptRow.attempt_number)
                .all()
            )
            resolutions = (
                db.query(ConflictResolutionRow)
                .filter(ConflictResolutionRow.job_item_id.in_(item_ids))
                .order_by(ConflictResolutionRow.id.asc())
                .all()
            )

        job_payload = {
            "id": job.id,
            "user_id": job.user_id,
            "original_file_name": job.original_file_name,
            "input_columns": job.input_columns,
            "total_urls": job.total_urls,
            "processed_count": job.processed_count,
            "success_count": job.success_count,
            "failed_count": job.failed_count,
            "retrying_count": job.retrying_count,
            "verified_count": job.verified_count,
            "mismatch_count": job.mismatch_count,
            "review_count": job.review_count,
            "needs_review_count": getattr(job, "needs_review_count", 0),
            "resolved_count": getattr(job, "resolved_count", 0),
            "phase": job.phase,
            "status": job.status,
            "excel_finalized": job.excel_finalized,
            "result_file_path": job.result_file_path,
            "error": job.error,
            "created_at": job.created_at,
            "completed_at": job.completed_at,
        }
        items_payload = [
            {
                "id": i.id,
                "source_row_number": i.source_row_number,
                "profile_url": i.profile_url,
                "normalized_url": i.normalized_url,
                "status": i.status,
                "attempt_count": i.attempt_count,
                "dedupe_of_id": i.dedupe_of_id,
                "source_row_json": i.source_row_json,
                "name": i.name,
                "company": i.company,
                "designation": i.designation,
                "about": i.about,
                "headline": i.headline,
                "location": i.location,
                "followers": i.followers,
                "connections": i.connections,
                "extraction_response": i.extraction_response,
                "last_error": i.last_error,
                "verification_status": i.verification_status,
                "verification_score": i.verification_score,
                "name_match": i.name_match,
                "designation_match": i.designation_match,
                "company_match": i.company_match,
                "location_match": i.location_match,
                "company_location_match": getattr(i, "company_location_match", None),
                "verification_reason": i.verification_reason,
                "resolved_name": getattr(i, "resolved_name", None),
                "resolved_designation": getattr(i, "resolved_designation", None),
                "resolved_company": getattr(i, "resolved_company", None),
                "resolved_location": getattr(i, "resolved_location", None),
                "resolved_company_location": getattr(i, "resolved_company_location", None),
                "resolution_summary": getattr(i, "resolution_summary", None),
                "resolved_by": getattr(i, "resolved_by", None),
                "resolved_at": getattr(i, "resolved_at", None),
                "completed_at": i.completed_at,
            }
            for i in items
        ]
        attempts_payload = [
            {
                "job_item_id": a.job_item_id,
                "attempt_number": a.attempt_number,
                "request_started_at": a.request_started_at,
                "request_finished_at": a.request_finished_at,
                "status": a.status,
                "response": a.response,
                "error": a.error,
                "apify_run_id": a.apify_run_id,
            }
            for a in attempts
        ]
        resolutions_payload = [
            {
                "job_item_id": r.job_item_id,
                "field": r.field,
                "uploaded_value": r.uploaded_value,
                "extracted_value": r.extracted_value,
                "edited_value": getattr(r, "edited_value", None),
                "resolution": r.resolution,
                "resolved_value": r.resolved_value,
                "resolved_by": r.resolved_by,
                "resolved_by_name": getattr(r, "resolved_by_name", None),
                "resolved_by_email": getattr(r, "resolved_by_email", None),
                "change_summary": getattr(r, "change_summary", None),
                "resolved_at": r.resolved_at,
            }
            for r in resolutions
        ]
        manifest = {
            "backup_version": BACKUP_VERSION,
            "job_id": job.id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "item_count": len(items_payload),
            "attempt_count": len(attempts_payload),
            "resolution_count": len(resolutions_payload),
        }

        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"bulk-job-{job.id}-backup.zip"
        path = BACKUPS_DIR / filename
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", _dump(manifest))
            zf.writestr("job.json", _dump(job_payload))
            zf.writestr("items.json", _dump(items_payload))
            zf.writestr("attempts.json", _dump(attempts_payload))
            zf.writestr("resolutions.json", _dump(resolutions_payload))
            if job.result_file_path:
                result_name = Path(job.result_file_path).name
                result_path = BulkExcelService().resolve_safe_path(result_name)
                if result_path and result_path.is_file():
                    zf.write(result_path, arcname="result.xlsx")

        path.write_bytes(buffer.getvalue())
        relative = f"outputs/backups/{filename}"
        row = BulkBackupRow(
            job_id=job.id,
            user_id=user_id if user_id is not None else job.user_id,
            backup_version=BACKUP_VERSION,
            file_path=relative,
            status=BACKUP_READY,
        )
        db.add(row)
        job.backup_status = BACKUP_READY
        job.backup_file_path = relative
        db.commit()
        db.refresh(row)
        return row
    except BackupError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Backup failed job_id=%s", job_id)
        db2 = SessionLocal()
        try:
            job = db2.query(BulkExtractJobRow).filter(BulkExtractJobRow.id == job_id).first()
            if job:
                job.backup_status = BACKUP_FAILED
                db2.commit()
        finally:
            db2.close()
        raise BackupError(str(exc)) from exc
    finally:
        db.close()


def restore_backup(
    content: bytes,
    *,
    user_id: int | None,
) -> BulkExtractJobRow:
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise BackupError("Invalid backup file (not a ZIP)") from exc

    names = set(zf.namelist())
    required = {"manifest.json", "job.json", "items.json"}
    if not required.issubset(names):
        raise BackupError("Backup is missing required files")

    try:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        job_data = json.loads(zf.read("job.json").decode("utf-8"))
        items_data = json.loads(zf.read("items.json").decode("utf-8"))
        attempts_data = (
            json.loads(zf.read("attempts.json").decode("utf-8")) if "attempts.json" in names else []
        )
        resolutions_data = (
            json.loads(zf.read("resolutions.json").decode("utf-8"))
            if "resolutions.json" in names
            else []
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BackupError("Backup JSON could not be parsed") from exc

    version = int(manifest.get("backup_version") or 0)
    if version != BACKUP_VERSION:
        raise BackupError("This backup was created with an incompatible version.")

    original_id = str(job_data.get("id") or "unknown")
    new_id = str(uuid.uuid4())
    restored_name = job_data.get("original_file_name") or "restored.xlsx"
    if not str(restored_name).startswith("RESTORED-"):
        restored_name = f"RESTORED-{original_id[:8]}-{restored_name}"

    db = SessionLocal()
    try:
        job = BulkExtractJobRow(
            id=new_id,
            user_id=user_id,
            original_file_name=restored_name,
            input_columns=job_data.get("input_columns") or [],
            total_urls=int(job_data.get("total_urls") or len(items_data)),
            processed_count=int(job_data.get("processed_count") or 0),
            success_count=int(job_data.get("success_count") or 0),
            failed_count=int(job_data.get("failed_count") or 0),
            retrying_count=0,
            verified_count=int(job_data.get("verified_count") or 0),
            mismatch_count=int(job_data.get("mismatch_count") or 0),
            review_count=int(job_data.get("review_count") or 0),
            needs_review_count=int(job_data.get("needs_review_count") or 0),
            resolved_count=int(job_data.get("resolved_count") or 0),
            phase=job_data.get("phase") or PHASE_COMPLETED,
            excel_finalized=False,
            backup_status="none",
            status=job_data.get("status") if job_data.get("status") in {"done", "failed"} else "done",
            error=job_data.get("error"),
            completed_at=datetime.now(timezone.utc),
        )
        if job.needs_review_count and job.needs_review_count > 0:
            job.phase = PHASE_REVIEW
        db.add(job)
        db.flush()

        id_map: dict[int, int] = {}
        for entry in items_data:
            old_id = int(entry.get("id") or 0)
            item = BulkJobItemRow(
                job_id=new_id,
                source_row_number=int(entry.get("source_row_number") or 0),
                profile_url=entry.get("profile_url") or "",
                normalized_url=entry.get("normalized_url") or "",
                status=entry.get("status") or ITEM_QUEUED,
                attempt_count=int(entry.get("attempt_count") or 0),
                source_row_json=entry.get("source_row_json") or {},
                name=entry.get("name"),
                company=entry.get("company"),
                designation=entry.get("designation"),
                about=entry.get("about"),
                headline=entry.get("headline"),
                location=entry.get("location"),
                followers=entry.get("followers"),
                connections=entry.get("connections"),
                extraction_response=entry.get("extraction_response"),
                last_error=entry.get("last_error"),
                verification_status=entry.get("verification_status") or "NOT_VERIFIED",
                verification_score=int(entry.get("verification_score") or 0),
                name_match=entry.get("name_match"),
                designation_match=entry.get("designation_match"),
                company_match=entry.get("company_match"),
                location_match=entry.get("location_match"),
                company_location_match=entry.get("company_location_match"),
                verification_reason=entry.get("verification_reason"),
                resolved_name=entry.get("resolved_name"),
                resolved_designation=entry.get("resolved_designation"),
                resolved_company=entry.get("resolved_company"),
                resolved_location=entry.get("resolved_location"),
                resolved_company_location=entry.get("resolved_company_location"),
                resolution_summary=entry.get("resolution_summary"),
                resolved_by=entry.get("resolved_by"),
            )
            if item.status not in {
                ITEM_SUCCESS,
                ITEM_FINAL_FAILED,
                ITEM_QUEUED,
                ITEM_PENDING,
                "PROCESSING",
                "RETRY_WAIT",
            }:
                item.status = ITEM_FINAL_FAILED
            db.add(item)
            db.flush()
            if old_id:
                id_map[old_id] = item.id

        for entry in attempts_data:
            old_item = int(entry.get("job_item_id") or 0)
            new_item = id_map.get(old_item)
            if not new_item:
                continue
            db.add(
                ExtractionAttemptRow(
                    job_item_id=new_item,
                    attempt_number=int(entry.get("attempt_number") or 1),
                    status=entry.get("status") or "FAILED",
                    response=entry.get("response"),
                    error=entry.get("error"),
                    apify_run_id=entry.get("apify_run_id"),
                )
            )

        for entry in resolutions_data:
            old_item = int(entry.get("job_item_id") or 0)
            new_item = id_map.get(old_item)
            if not new_item:
                continue
            db.add(
                ConflictResolutionRow(
                    job_item_id=new_item,
                    field=entry.get("field") or "company",
                    uploaded_value=entry.get("uploaded_value"),
                    extracted_value=entry.get("extracted_value"),
                    edited_value=entry.get("edited_value"),
                    resolution=entry.get("resolution") or "KEEP_EXTRACTED",
                    resolved_value=entry.get("resolved_value"),
                    resolved_by=entry.get("resolved_by") or user_id,
                    resolved_by_name=entry.get("resolved_by_name"),
                    resolved_by_email=entry.get("resolved_by_email"),
                    change_summary=entry.get("change_summary"),
                )
            )

        excel = BulkExcelService()
        items = (
            db.query(BulkJobItemRow)
            .filter(BulkJobItemRow.job_id == new_id)
            .order_by(BulkJobItemRow.source_row_number.asc())
            .all()
        )
        _, _fn, relative = excel.build_result_workbook_from_items(
            job_id=new_id,
            items=items,
            input_columns=list(job.input_columns or []),
        )
        job.result_file_path = relative
        job.excel_finalized = True
        db.commit()
        db.refresh(job)
        return job
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def resolve_backup_path(relative: str) -> Path | None:
    name = Path(relative or "").name
    if not name.endswith(".zip") or ".." in name:
        return None
    path = (BACKUPS_DIR / name).resolve()
    try:
        path.relative_to(BACKUPS_DIR.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None
