"""Match an offering against ICP records and persist scores."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.icp.models import IcpRecordRow
from app.offerings.ai_service import offering_ai_service
from app.offerings.embeddings import ensure_icp_embedding, ensure_offering_embedding, semantic_similarity_score
from app.offerings.models import (
    FEEDBACK_ACCEPTED,
    FEEDBACK_REJECTED,
    HISTORICAL_NEUTRAL_SCORE,
    MATCH_STATUS_AI_MATCHED,
    MATCH_STATUS_APPROVED,
    MATCH_STATUS_NEEDS_REVIEW,
    MATCH_STATUS_REJECTED,
    MATCH_TIER_POOR,
    OfferingMatchRow,
    OfferingRecommendationFeedbackRow,
    OfferingRow,
    POTENTIAL_THRESHOLD,
    SCORE_WEIGHTS_V2,
)
from app.offerings.scoring import SCORE_WEIGHTS, calculate_fit_score

logger = logging.getLogger(__name__)


def serialize_match(row: OfferingMatchRow, icp: IcpRecordRow | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row.id,
        "offering_id": row.offering_id,
        "icp_record_id": row.icp_record_id,
        "fit_score": row.fit_score,
        "industry_score": row.industry_score,
        "job_title_score": row.job_title_score,
        "department_score": row.department_score,
        "company_size_score": row.company_size_score,
        "pain_use_case_score": row.pain_use_case_score,
        "seniority_score": row.seniority_score,
        "buying_signal_score": row.buying_signal_score,
        "icp_fit_score": getattr(row, "icp_fit_score", 0) or 0,
        "problem_fit_score": getattr(row, "problem_fit_score", 0) or row.pain_use_case_score or 0,
        "role_fit_score": getattr(row, "role_fit_score", 0) or row.job_title_score or 0,
        "company_fit_score": getattr(row, "company_fit_score", 0) or row.company_size_score or 0,
        "historical_score": getattr(row, "historical_score", HISTORICAL_NEUTRAL_SCORE)
        or HISTORICAL_NEUTRAL_SCORE,
        "semantic_similarity": getattr(row, "semantic_similarity", 0) or 0,
        "missing_information": getattr(row, "missing_information", None) or [],
        "explanation": getattr(row, "explanation", None),
        "match_tier": row.match_tier,
        "match_reasons": row.match_reasons or [],
        "ai_analysis": row.ai_analysis,
        "status": row.status,
        "offering_definition_version": row.offering_definition_version,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if icp is not None:
        out.update(
            {
                "name": icp.name,
                "company_name": icp.company_name,
                "designation": icp.designation,
                "industry": icp.industry,
                "company_size": icp.company_size,
                "location": icp.location,
                "linkedin_url": icp.linkedin_url,
                "about": icp.about,
                "icp_verification_status": icp.verification_status,
            }
        )
    return out


def get_existing_match(
    db: Session, offering_id: int, icp_record_id: int
) -> OfferingMatchRow | None:
    return (
        db.query(OfferingMatchRow)
        .filter(
            OfferingMatchRow.offering_id == offering_id,
            OfferingMatchRow.icp_record_id == icp_record_id,
        )
        .first()
    )


def should_skip_match(existing: OfferingMatchRow | None, offering: OfferingRow) -> bool:
    if existing is None:
        return False
    if existing.status in (MATCH_STATUS_APPROVED, MATCH_STATUS_REJECTED):
        if existing.offering_definition_version == (offering.definition_version or 1):
            return True
    if existing.offering_definition_version == (offering.definition_version or 1):
        return True
    return False


def historical_score_for_offering(db: Session, offering_id: int) -> int:
    """Neutral until enough feedback exists; then blend accept vs reject."""
    rows = (
        db.query(OfferingRecommendationFeedbackRow.action, func.count())
        .filter(OfferingRecommendationFeedbackRow.offering_id == offering_id)
        .group_by(OfferingRecommendationFeedbackRow.action)
        .all()
    )
    counts = {a: c for a, c in rows}
    accepted = counts.get(FEEDBACK_ACCEPTED, 0) + counts.get("recommended", 0) + counts.get("converted", 0)
    rejected = counts.get(FEEDBACK_REJECTED, 0)
    total = accepted + rejected
    if total < 5:
        return HISTORICAL_NEUTRAL_SCORE
    rate = accepted / total
    return max(0, min(100, int(round(40 + rate * 60))))


def match_icp_to_offering(
    db: Session,
    offering: OfferingRow,
    icp: IcpRecordRow,
    *,
    use_ai: bool = True,
    force: bool = False,
) -> OfferingMatchRow:
    existing = get_existing_match(db, offering.id, icp.id)
    if not force and should_skip_match(existing, offering):
        assert existing is not None
        return existing

    ensure_offering_embedding(offering)
    ensure_icp_embedding(icp)
    sem = semantic_similarity_score(offering, icp)
    hist = historical_score_for_offering(db, offering.id)

    result = calculate_fit_score(
        offering,
        icp,
        semantic_similarity=sem,
        historical_score=hist,
    )
    ai_payload: dict[str, Any] | None = None

    if use_ai and not result.excluded and (result.needs_ai_pain or result.needs_ai_title):
        try:
            evidence = offering_ai_service.semantic_evidence(offering, icp)
            ai_payload = evidence.model_dump()
            result = calculate_fit_score(
                offering,
                icp,
                ai_pain_score=evidence.pain_use_case_score if result.needs_ai_pain else None,
                ai_pain_reason=evidence.pain_use_case_reason if result.needs_ai_pain else None,
                ai_buying_score=evidence.buying_signal_score or None,
                ai_buying_reason=evidence.buying_signal_reason or None,
                ai_title_boost=evidence.job_title_boost if result.needs_ai_title else 0,
                ai_title_reason=evidence.job_title_reason if result.needs_ai_title else None,
                semantic_similarity=sem,
                historical_score=hist,
            )
        except Exception as exc:
            logger.warning("AI semantic match failed for icp=%s: %s", icp.id, exc)

    reasons = list(result.match_reasons)
    dim_analysis = {}
    for key, dim in result.dimensions.items():
        dim_analysis[f"{key}_match"] = {
            "score": dim.score,
            "max": dim.max,
            "reason": dim.reason,
            "matched": dim.matched,
        }

    status = MATCH_STATUS_AI_MATCHED
    if (
        not result.excluded
        and result.fit_score >= POTENTIAL_THRESHOLD
        and result.fit_score < 90
        and result.match_tier != MATCH_TIER_POOR
    ):
        if not all(d.matched for d in result.dimensions.values() if d.max >= 50 and d.score < 100):
            # Mid-confidence recommendations often need review
            if result.fit_score < 80:
                status = MATCH_STATUS_NEEDS_REVIEW

    preserve_status = None
    if existing and existing.status in (MATCH_STATUS_APPROVED, MATCH_STATUS_REJECTED):
        if existing.offering_definition_version != (offering.definition_version or 1):
            status = MATCH_STATUS_NEEDS_REVIEW
        else:
            preserve_status = existing.status

    if existing is None:
        existing = OfferingMatchRow(
            offering_id=offering.id,
            icp_record_id=icp.id,
        )
        db.add(existing)

    existing.fit_score = result.fit_score
    existing.industry_score = result.industry_score
    existing.job_title_score = result.job_title_score
    existing.department_score = result.department_score
    existing.company_size_score = result.company_size_score
    existing.pain_use_case_score = result.pain_use_case_score
    existing.seniority_score = result.seniority_score
    existing.buying_signal_score = result.buying_signal_score
    existing.icp_fit_score = result.icp_fit_score
    existing.problem_fit_score = result.problem_fit_score
    existing.role_fit_score = result.role_fit_score
    existing.company_fit_score = result.company_fit_score
    existing.historical_score = result.historical_score
    existing.semantic_similarity = result.semantic_similarity
    existing.missing_information = result.missing_information
    existing.explanation = result.explanation
    existing.match_tier = result.match_tier
    existing.match_reasons = reasons
    existing.ai_analysis = {
        "score": result.fit_score,
        "weights": SCORE_WEIGHTS_V2,
        "legacy_weights": SCORE_WEIGHTS,
        "dimensions": dim_analysis,
        "semantic": ai_payload,
        "semantic_similarity": result.semantic_similarity,
        "excluded": result.excluded,
        "hard_filtered": result.hard_filtered,
        "missing_information": result.missing_information,
        "explanation": result.explanation,
    }
    existing.offering_definition_version = offering.definition_version or 1
    existing.status = preserve_status or status
    db.flush()
    return existing


def list_matches(
    db: Session,
    *,
    offering_id: int,
    search: str | None = None,
    match_tier: str | None = None,
    status: str | None = None,
    industry: str | None = None,
    company_size: str | None = None,
    designation: str | None = None,
    seniority: str | None = None,
    location: str | None = None,
    min_score: int | None = None,
    max_score: int | None = None,
    verification_status: str | None = None,
    sort_by: str = "fit_score",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    q = (
        db.query(OfferingMatchRow, IcpRecordRow)
        .join(IcpRecordRow, IcpRecordRow.id == OfferingMatchRow.icp_record_id)
        .filter(OfferingMatchRow.offering_id == offering_id)
    )
    if match_tier:
        q = q.filter(OfferingMatchRow.match_tier == match_tier.strip().lower())
    if status:
        q = q.filter(OfferingMatchRow.status == status.strip().lower())
    if min_score is not None:
        q = q.filter(OfferingMatchRow.fit_score >= min_score)
    if max_score is not None:
        q = q.filter(OfferingMatchRow.fit_score <= max_score)
    if industry:
        q = q.filter(IcpRecordRow.industry.ilike(f"%{industry.strip()}%"))
    if company_size:
        q = q.filter(IcpRecordRow.company_size.ilike(f"%{company_size.strip()}%"))
    if designation:
        q = q.filter(IcpRecordRow.designation.ilike(f"%{designation.strip()}%"))
    if location:
        q = q.filter(IcpRecordRow.location.ilike(f"%{location.strip()}%"))
    if verification_status:
        q = q.filter(IcpRecordRow.verification_status == verification_status.strip().upper())
    if seniority:
        q = q.filter(IcpRecordRow.designation.ilike(f"%{seniority.strip()}%"))
    if search and search.strip():
        like = f"%{search.strip()}%"
        q = q.filter(
            or_(
                IcpRecordRow.name.ilike(like),
                IcpRecordRow.company_name.ilike(like),
                IcpRecordRow.designation.ilike(like),
                IcpRecordRow.industry.ilike(like),
            )
        )

    total = q.count()
    sort_map = {
        "fit_score": OfferingMatchRow.fit_score,
        "highest": OfferingMatchRow.fit_score,
        "lowest": OfferingMatchRow.fit_score,
        "recently_matched": OfferingMatchRow.updated_at,
        "recently_added": OfferingMatchRow.created_at,
        "created_at": OfferingMatchRow.created_at,
        "updated_at": OfferingMatchRow.updated_at,
        "name": IcpRecordRow.name,
    }
    col = sort_map.get(sort_by, OfferingMatchRow.fit_score)
    if sort_by == "lowest":
        order = col.asc()
    elif sort_order.lower() == "asc" and sort_by not in ("highest",):
        order = col.asc()
    else:
        order = col.desc()

    rows = q.order_by(order).offset(max(0, (page - 1) * page_size)).limit(page_size).all()
    items = [serialize_match(m, icp) for m, icp in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def get_match(
    db: Session, offering_id: int, match_id: int, *, user_id: int | None = None
) -> tuple[OfferingMatchRow, IcpRecordRow] | None:
    q = (
        db.query(OfferingMatchRow, IcpRecordRow)
        .join(IcpRecordRow, IcpRecordRow.id == OfferingMatchRow.icp_record_id)
        .filter(OfferingMatchRow.id == match_id, OfferingMatchRow.offering_id == offering_id)
    )
    _ = user_id
    row = q.first()
    return row


def set_match_status(
    db: Session,
    match: OfferingMatchRow,
    *,
    status: str,
    reviewed_by: int | None,
) -> OfferingMatchRow:
    allowed = {
        MATCH_STATUS_APPROVED,
        MATCH_STATUS_REJECTED,
        MATCH_STATUS_NEEDS_REVIEW,
        MATCH_STATUS_AI_MATCHED,
        "new",
    }
    if status not in allowed:
        raise ValueError(f"Invalid status: {status}")
    match.status = status
    if status in (MATCH_STATUS_APPROVED, MATCH_STATUS_REJECTED):
        match.reviewed_by = reviewed_by
        match.reviewed_at = datetime.now(timezone.utc)
        action = FEEDBACK_ACCEPTED if status == MATCH_STATUS_APPROVED else FEEDBACK_REJECTED
        record_feedback(
            db,
            recommendation_id=match.id,
            offering_id=match.offering_id,
            icp_record_id=match.icp_record_id,
            action=action,
            user_id=reviewed_by,
            score_at_action=match.fit_score,
        )
    db.flush()
    return match


def record_feedback(
    db: Session,
    *,
    recommendation_id: int,
    offering_id: int,
    icp_record_id: int,
    action: str,
    user_id: int | None,
    score_at_action: int | None = None,
) -> OfferingRecommendationFeedbackRow:
    row = OfferingRecommendationFeedbackRow(
        recommendation_id=recommendation_id,
        offering_id=offering_id,
        icp_record_id=icp_record_id,
        user_id=user_id,
        action=action.strip().lower(),
        score_at_action=score_at_action,
    )
    db.add(row)
    db.flush()
    return row


def list_icp_ids_for_user(
    db: Session,
    user_id: int | None,
    *,
    verified_only: bool = True,
) -> list[int]:
    q = db.query(IcpRecordRow.id)
    if user_id is not None:
        q = q.filter(IcpRecordRow.user_id == user_id)
    if verified_only:
        q = q.filter(IcpRecordRow.verification_status == "VERIFIED")
    return [r[0] for r in q.all()]


def list_recommendations_for_icp(
    db: Session,
    *,
    icp_record_id: int,
    user_id: int | None = None,
    min_score: int = POTENTIAL_THRESHOLD,
    limit: int = 5,
    sort_by: str = "fit_score",
) -> list[dict[str, Any]]:
    q = (
        db.query(OfferingMatchRow, OfferingRow)
        .join(OfferingRow, OfferingRow.id == OfferingMatchRow.offering_id)
        .filter(OfferingMatchRow.icp_record_id == icp_record_id)
        .filter(OfferingMatchRow.fit_score >= min_score)
        .filter(OfferingMatchRow.match_tier != MATCH_TIER_POOR)
    )
    if user_id is not None:
        q = q.filter(OfferingRow.user_id == user_id)

    if sort_by == "recently_added":
        q = q.order_by(OfferingMatchRow.created_at.desc())
    elif sort_by == "strongest":
        q = q.order_by(OfferingMatchRow.fit_score.desc(), OfferingMatchRow.updated_at.desc())
    else:
        q = q.order_by(OfferingMatchRow.fit_score.desc())

    rows = q.limit(limit).all()
    items = []
    for m, o in rows:
        items.append(
            {
                "match_id": m.id,
                "offering_id": o.id,
                "offering_name": o.name,
                "short_description": o.short_description,
                "fit_score": m.fit_score,
                "match_tier": m.match_tier,
                "status": m.status,
                "match_reasons": m.match_reasons or [],
                "missing_information": getattr(m, "missing_information", None) or [],
                "explanation": getattr(m, "explanation", None),
                "icp_fit_score": getattr(m, "icp_fit_score", 0),
                "problem_fit_score": getattr(m, "problem_fit_score", 0),
                "role_fit_score": getattr(m, "role_fit_score", 0),
                "industry_score": m.industry_score,
                "company_fit_score": getattr(m, "company_fit_score", 0),
                "buying_signal_score": m.buying_signal_score,
                "historical_score": getattr(m, "historical_score", HISTORICAL_NEUTRAL_SCORE),
            }
        )
    return items
