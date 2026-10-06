"""Pre-Apify cost guard: skip ICP hits, duplicates, in-flight URLs, and reuse prior extractions.

Must run immediately before every ``apify.run_rich_batch`` call when
``APIFY_ENABLE_COST_GUARD`` is enabled.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.linkedin.bulk_models import (
    ITEM_FINAL_FAILED,
    ITEM_PROCESSING,
    ITEM_RETRY_WAIT,
    ITEM_SUCCESS,
    BulkJobItemRow,
)
from app.linkedin.validator import is_linkedin_in_profile_url, normalize_profile_url
from app.linkedin.verification import apply_verification

logger = logging.getLogger(__name__)

REASON_ALREADY_IN_ICP = "ALREADY_IN_ICP"
REASON_DUPLICATE_IN_UPLOAD = "DUPLICATE_IN_UPLOAD"
REASON_INVALID_URL = "INVALID_URL"
REASON_REUSE_PRIOR_EXTRACTION = "REUSE_PRIOR_EXTRACTION"
REASON_ALREADY_PROCESSING = "ALREADY_PROCESSING"

# How long to wait before retrying a URL that another job is currently extracting.
IN_FLIGHT_RETRY_SECONDS = 20


@dataclass
class CostGuardStats:
    claimed: int = 0
    eligible: int = 0
    skipped_icp: int = 0
    skipped_reuse: int = 0
    skipped_in_flight: int = 0
    skipped_invalid: int = 0
    skipped_duplicate: int = 0

    def as_log_fields(self) -> str:
        return (
            f"claimed={self.claimed} eligible={self.eligible} "
            f"already_in_icp={self.skipped_icp} reused_prior={self.skipped_reuse} "
            f"already_processing={self.skipped_in_flight} invalid={self.skipped_invalid} "
            f"duplicates={self.skipped_duplicate}"
        )


@dataclass
class CostGuardResult:
    eligible_items: list[BulkJobItemRow] = field(default_factory=list)
    stats: CostGuardStats = field(default_factory=CostGuardStats)


def _str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _copy_extracted_fields(dest: BulkJobItemRow, src: BulkJobItemRow, *, now: datetime) -> None:
    dest.status = ITEM_SUCCESS
    dest.name = src.name
    dest.company = src.company
    dest.designation = src.designation
    dest.about = src.about
    dest.headline = src.headline
    dest.location = src.location
    dest.followers = src.followers
    dest.connections = src.connections
    dest.image = src.image
    dest.extraction_response = src.extraction_response
    dest.last_error = None
    dest.retry_after = None
    dest.completed_at = now
    dest.verification_status = src.verification_status or dest.verification_status
    dest.verification_score = int(src.verification_score or 0)
    dest.verification_reason = (
        src.verification_reason or "Reused prior LinkedIn extraction (no Apify call)"
    )
    dest.name_match = src.name_match
    dest.designation_match = src.designation_match
    dest.company_match = src.company_match
    dest.location_match = src.location_match
    dest.company_location_match = src.company_location_match


def _log_skip(*, job_id: str, reason: str, profile_url: str, item_id: int | None = None) -> None:
    logger.info(
        "SKIP_APIFY reason=%s job_id=%s item_id=%s profile_url=%s",
        reason,
        job_id,
        item_id or "-",
        profile_url or "-",
    )


def find_prior_success(
    db: Session, *, normalized_url: str, exclude_job_id: str, exclude_item_id: int | None = None
) -> BulkJobItemRow | None:
    """Return the newest successful extraction for this URL outside the current item."""
    if not normalized_url:
        return None
    q = (
        db.query(BulkJobItemRow)
        .filter(
            BulkJobItemRow.normalized_url == normalized_url,
            BulkJobItemRow.status == ITEM_SUCCESS,
            BulkJobItemRow.dedupe_of_id.is_(None),
            BulkJobItemRow.name.isnot(None),
            BulkJobItemRow.name != "",
        )
        .order_by(BulkJobItemRow.completed_at.desc(), BulkJobItemRow.id.desc())
    )
    for row in q.limit(25).all():
        if exclude_item_id is not None and row.id == exclude_item_id:
            continue
        # Prefer other jobs; same-job SUCCESS is unusual for PROCESSING items.
        if row.job_id == exclude_job_id and exclude_item_id is not None:
            continue
        return row
    return None


def find_in_flight(
    db: Session, *, normalized_url: str, exclude_job_id: str, exclude_item_ids: set[int]
) -> BulkJobItemRow | None:
    """Another job (or item) currently extracting the same URL."""
    if not normalized_url:
        return None
    rows = (
        db.query(BulkJobItemRow)
        .filter(
            BulkJobItemRow.normalized_url == normalized_url,
            BulkJobItemRow.status == ITEM_PROCESSING,
            BulkJobItemRow.dedupe_of_id.is_(None),
        )
        .order_by(BulkJobItemRow.updated_at.desc(), BulkJobItemRow.id.desc())
        .limit(20)
        .all()
    )
    for row in rows:
        if row.id in exclude_item_ids:
            continue
        if row.job_id == exclude_job_id and row.id in exclude_item_ids:
            continue
        # Same batch claim — ignore peers we already hold.
        if row.job_id == exclude_job_id:
            continue
        return row
    return None


def apply_cost_guard_to_claimed_items(
    db: Session,
    *,
    job_id: str,
    items: list[BulkJobItemRow],
    user_id: int | None,
    org_id: str | None = None,
    match_threshold: int = 100,
    review_threshold: int = 75,
) -> CostGuardResult:
    """Filter claimed PROCESSING items; mark skips in-place; return Apify-eligible subset."""
    from app.icp.service import (
        _apply_icp_record_to_bulk_item,
        find_icp_by_linkedin_urls,
        resolve_org_id,
    )

    result = CostGuardResult()
    result.stats.claimed = len(items)
    if not items:
        return result

    org_id = resolve_org_id(db, user_id=user_id, org_id=org_id)
    urls = [i.normalized_url for i in items if i.normalized_url]
    icp_map = find_icp_by_linkedin_urls(db, user_id=user_id, org_id=org_id, urls=urls)

    now = datetime.now(timezone.utc)
    exclude_ids = {int(i.id) for i in items}
    seen_urls: set[str] = set()

    for item in items:
        raw = (item.normalized_url or item.profile_url or "").strip()
        if not raw or not is_linkedin_in_profile_url(raw):
            item.status = ITEM_FINAL_FAILED
            item.last_error = "Invalid LinkedIn profile URL"
            item.completed_at = now
            item.retry_after = None
            apply_verification(
                item, match_threshold=match_threshold, review_threshold=review_threshold
            )
            result.stats.skipped_invalid += 1
            _log_skip(job_id=job_id, reason=REASON_INVALID_URL, profile_url=raw, item_id=item.id)
            continue

        normalized = normalize_profile_url(raw)
        if item.normalized_url != normalized:
            item.normalized_url = normalized

        if normalized in seen_urls:
            # Within this claimed batch — treat as in-batch duplicate (should be rare).
            result.stats.skipped_duplicate += 1
            _log_skip(
                job_id=job_id,
                reason=REASON_DUPLICATE_IN_UPLOAD,
                profile_url=normalized,
                item_id=item.id,
            )
            # Leave PROCESSING briefly; caller should not send to Apify. Re-queue as pending
            # by linking wait — safer to mark FINAL via mirror after peer succeeds is complex;
            # put on short retry so peer in same batch finishes first then reuse.
            item.status = ITEM_RETRY_WAIT
            item.retry_after = now + timedelta(seconds=IN_FLIGHT_RETRY_SECONDS)
            item.last_error = "Duplicate URL in same Apify claim batch — waiting for peer"
            continue
        seen_urls.add(normalized)

        icp = icp_map.get(normalized)
        if icp is not None:
            _apply_icp_record_to_bulk_item(item, icp, now=now)
            result.stats.skipped_icp += 1
            _log_skip(
                job_id=job_id, reason=REASON_ALREADY_IN_ICP, profile_url=normalized, item_id=item.id
            )
            continue

        prior = find_prior_success(
            db, normalized_url=normalized, exclude_job_id=job_id, exclude_item_id=item.id
        )
        if prior is not None:
            _copy_extracted_fields(item, prior, now=now)
            apply_verification(
                item, match_threshold=match_threshold, review_threshold=review_threshold
            )
            if not item.verification_reason:
                item.verification_reason = "Reused prior LinkedIn extraction (no Apify call)"
            result.stats.skipped_reuse += 1
            _log_skip(
                job_id=job_id,
                reason=REASON_REUSE_PRIOR_EXTRACTION,
                profile_url=normalized,
                item_id=item.id,
            )
            continue

        in_flight = find_in_flight(
            db, normalized_url=normalized, exclude_job_id=job_id, exclude_item_ids=exclude_ids
        )
        if in_flight is not None:
            item.status = ITEM_RETRY_WAIT
            item.retry_after = now + timedelta(seconds=IN_FLIGHT_RETRY_SECONDS)
            item.last_error = (
                f"Same profile already processing in job {in_flight.job_id} — deferring Apify"
            )
            result.stats.skipped_in_flight += 1
            _log_skip(
                job_id=job_id,
                reason=REASON_ALREADY_PROCESSING,
                profile_url=normalized,
                item_id=item.id,
            )
            continue

        result.eligible_items.append(item)

    result.stats.eligible = len(result.eligible_items)
    return result


def log_apify_request(
    *,
    job_id: str,
    batch_id: str,
    stats: CostGuardStats,
    batch_size: int,
    urls_sent: int,
) -> None:
    logger.info(
        "APIFY_REQUEST job_id=%s batch_id=%s new_urls=%s batch_size=%s %s",
        job_id,
        batch_id,
        urls_sent,
        batch_size,
        stats.as_log_fields(),
    )
