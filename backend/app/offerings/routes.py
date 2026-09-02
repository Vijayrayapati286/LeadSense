"""Offerings REST API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.offerings.ai_service import offering_ai_service
from app.offerings.campaign_recipients import prepare_campaign_recipients
from app.offerings.match_batch_runner import start_match_job_async
from app.offerings.match_jobs import create_match_job, get_latest_job, serialize_job
from app.offerings.matching_service import (
    get_match,
    list_matches,
    serialize_match,
    set_match_status,
)
from app.offerings.schemas import (
    GenerateIcpRequest,
    GeneratedIcpPayload,
    GenerateOfferingEmailRequest,
    GenerateOfferingEmailResponse,
    MatchingJobStatusResponse,
    MatchStatusUpdate,
    OfferingCreate,
    OfferingEmailTemplateMeta,
    OfferingListResponse,
    OfferingMatchListResponse,
    OfferingMatchResponse,
    OfferingResponse,
    OfferingStatsResponse,
    OfferingUpdate,
    PrepareCampaignRecipientsRequest,
    PrepareCampaignRecipientsResponse,
    RecommendationFeedbackCreate,
)
from app.offerings.models import MATCH_STATUS_APPROVED, MATCH_STATUS_REJECTED
from app.offerings.service import (
    create_offering,
    delete_offering,
    get_offering,
    list_offerings,
    offering_stats,
    serialize_offering,
    update_offering,
)
from app.offerings.email_template_parser import parse_email_template_file
from app.storage.exceptions import FileValidationError

router = APIRouter(prefix="/offerings", tags=["Offerings"])


@router.get("", response_model=OfferingListResponse)
def list_offerings_route(
    search: str = Query(""),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    page_size: int | None = Query(None, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    size = page_size or limit
    return list_offerings(
        db,
        user_id=getattr(current_user, "id", None),
        search=search or None,
        page=page,
        page_size=size,
    )


@router.post("", response_model=OfferingResponse, status_code=201)
def create_offering_route(
    body: OfferingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        row = create_offering(
            db,
            user_id=getattr(current_user, "id", None),
            data=body.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        msg = str(getattr(exc, "orig", exc))
        if "email_template" in msg or "vouchers" in msg:
            detail = (
                "Database schema is out of date (missing offering email columns). "
                "Restart the backend server to apply migrations."
            )
        else:
            detail = f"Database error while saving offering: {msg}"
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail) from exc
    db.commit()
    db.refresh(row)
    return serialize_offering(row)


@router.post("/generate-icp", response_model=GeneratedIcpPayload)
def generate_icp_route(
    body: GenerateIcpRequest,
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    return offering_ai_service.generate_icp(body.description)


@router.post("/generate-email-templates", response_model=GenerateOfferingEmailResponse)
def generate_email_templates_route(
    body: GenerateOfferingEmailRequest,
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    result = offering_ai_service.generate_email_templates(body)
    return GenerateOfferingEmailResponse(**result)


@router.post("/parse-email-template", response_model=OfferingEmailTemplateMeta)
async def parse_email_template_route(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    filename = file.filename or "template.txt"
    content = await file.read()
    try:
        parsed = parse_email_template_file(filename=filename, content=content)
    except FileValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OfferingEmailTemplateMeta(**parsed)


@router.get("/by-icp/{icp_record_id}")
def list_matches_for_icp(
    icp_record_id: int,
    min_score: int = Query(50, ge=0, le=100),
    limit: int = Query(5, ge=1, le=25),
    sort_by: str = Query("fit_score"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Top recommended offerings for a verified ICP record."""
    from app.icp.models import IcpRecordRow
    from app.offerings.matching_service import list_recommendations_for_icp

    user_id = getattr(current_user, "id", None)
    icp_q = db.query(IcpRecordRow).filter(IcpRecordRow.id == icp_record_id)
    if user_id is not None:
        icp_q = icp_q.filter(IcpRecordRow.user_id == user_id)
    if not icp_q.first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ICP record not found")

    items = list_recommendations_for_icp(
        db,
        icp_record_id=icp_record_id,
        user_id=user_id,
        min_score=min_score,
        limit=limit,
        sort_by=sort_by,
    )
    return {"items": items, "total": len(items)}


@router.post("/matches/{match_id}/feedback")
def submit_recommendation_feedback(
    match_id: int,
    body: RecommendationFeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import datetime, timezone

    from app.offerings.matching_service import record_feedback
    from app.offerings.models import (
        FEEDBACK_ACCEPTED,
        FEEDBACK_CONVERTED,
        FEEDBACK_RECOMMENDED,
        FEEDBACK_REJECTED,
        FEEDBACK_VIEWED,
        OfferingMatchRow,
    )

    allowed = {
        FEEDBACK_VIEWED,
        FEEDBACK_ACCEPTED,
        FEEDBACK_REJECTED,
        FEEDBACK_RECOMMENDED,
        FEEDBACK_CONVERTED,
    }
    action = body.action.strip().lower()
    if action not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid action. Allowed: {sorted(allowed)}")

    match = db.query(OfferingMatchRow).filter(OfferingMatchRow.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    row = record_feedback(
        db,
        recommendation_id=match.id,
        offering_id=match.offering_id,
        icp_record_id=match.icp_record_id,
        action=action,
        user_id=getattr(current_user, "id", None),
        score_at_action=match.fit_score,
    )
    if action == FEEDBACK_ACCEPTED:
        match.status = MATCH_STATUS_APPROVED
        match.reviewed_by = getattr(current_user, "id", None)
        match.reviewed_at = datetime.now(timezone.utc)
    elif action == FEEDBACK_REJECTED:
        match.status = MATCH_STATUS_REJECTED
        match.reviewed_by = getattr(current_user, "id", None)
        match.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "id": row.id,
        "recommendation_id": row.recommendation_id,
        "offering_id": row.offering_id,
        "icp_record_id": row.icp_record_id,
        "action": row.action,
        "score_at_action": row.score_at_action,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/{offering_id}", response_model=OfferingResponse)
def get_offering_route(
    offering_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = get_offering(db, offering_id, user_id=getattr(current_user, "id", None))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offering not found")
    return serialize_offering(row)


@router.put("/{offering_id}", response_model=OfferingResponse)
def update_offering_route(
    offering_id: int,
    body: OfferingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = get_offering(db, offering_id, user_id=getattr(current_user, "id", None))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offering not found")
    try:
        update_offering(db, row, body.model_dump(exclude_unset=True))
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        msg = str(getattr(exc, "orig", exc))
        if "email_template" in msg or "vouchers" in msg:
            detail = (
                "Database schema is out of date (missing offering email columns). "
                "Restart the backend server to apply migrations."
            )
        else:
            detail = f"Database error while saving offering: {msg}"
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail) from exc
    db.refresh(row)
    return serialize_offering(row)


@router.delete("/{offering_id}")
def delete_offering_route(
    offering_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = get_offering(db, offering_id, user_id=getattr(current_user, "id", None))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offering not found")
    delete_offering(db, row)
    db.commit()
    return {"ok": True, "id": offering_id}


@router.post("/{offering_id}/generate-icp", response_model=GeneratedIcpPayload)
def generate_icp_for_offering(
    offering_id: int,
    body: GenerateIcpRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = get_offering(db, offering_id, user_id=getattr(current_user, "id", None))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offering not found")
    return offering_ai_service.generate_icp(body.description or row.description or "")


@router.get("/{offering_id}/stats", response_model=OfferingStatsResponse)
def offering_stats_route(
    offering_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = get_offering(db, offering_id, user_id=getattr(current_user, "id", None))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offering not found")
    return offering_stats(db, offering_id)


@router.post("/{offering_id}/match", response_model=MatchingJobStatusResponse)
def start_matching(
    offering_id: int,
    force: bool = Query(False),
    verified_only: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = get_offering(db, offering_id, user_id=getattr(current_user, "id", None))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offering not found")
    job = create_match_job(
        db,
        offering=row,
        user_id=getattr(current_user, "id", None),
        force=force,
        verified_only=verified_only,
    )
    db.commit()
    start_match_job_async(job.id, force=force)
    return serialize_job(job)


@router.get("/{offering_id}/matching-status", response_model=MatchingJobStatusResponse)
def matching_status(
    offering_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = get_offering(db, offering_id, user_id=getattr(current_user, "id", None))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offering not found")
    job = get_latest_job(db, offering_id)
    if not job:
        return {
            "job_id": None,
            "status": "idle",
            "total_count": 0,
            "processed_count": 0,
            "strong_count": 0,
            "potential_count": 0,
            "poor_count": 0,
            "error_count": 0,
            "percent": 0,
            "error": None,
            "started_at": None,
            "completed_at": None,
        }
    return serialize_job(job)


@router.get("/{offering_id}/matches", response_model=OfferingMatchListResponse)
def list_matches_route(
    offering_id: int,
    search: str = Query(""),
    match_tier: str = Query(""),
    status_filter: str = Query("", alias="status"),
    industry: str = Query(""),
    company_size: str = Query(""),
    designation: str = Query(""),
    seniority: str = Query(""),
    location: str = Query(""),
    verification_status: str = Query(""),
    min_score: int | None = Query(None),
    max_score: int | None = Query(None),
    sort_by: str = Query("fit_score"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    page_size: int | None = Query(None, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = get_offering(db, offering_id, user_id=getattr(current_user, "id", None))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offering not found")
    size = page_size or limit
    return list_matches(
        db,
        offering_id=offering_id,
        search=search or None,
        match_tier=match_tier or None,
        status=status_filter or None,
        industry=industry or None,
        company_size=company_size or None,
        designation=designation or None,
        seniority=seniority or None,
        location=location or None,
        verification_status=verification_status or None,
        min_score=min_score,
        max_score=max_score,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=size,
    )


@router.get("/{offering_id}/matches/{match_id}", response_model=OfferingMatchResponse)
def get_match_route(
    offering_id: int,
    match_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = get_offering(db, offering_id, user_id=getattr(current_user, "id", None))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offering not found")
    pair = get_match(db, offering_id, match_id)
    if not pair:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    match, icp = pair
    return serialize_match(match, icp)


@router.post("/{offering_id}/matches/{match_id}/approve", response_model=OfferingMatchResponse)
def approve_match(
    offering_id: int,
    match_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = get_offering(db, offering_id, user_id=getattr(current_user, "id", None))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offering not found")
    pair = get_match(db, offering_id, match_id)
    if not pair:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    match, icp = pair
    set_match_status(
        db, match, status=MATCH_STATUS_APPROVED, reviewed_by=getattr(current_user, "id", None)
    )
    db.commit()
    db.refresh(match)
    return serialize_match(match, icp)


@router.post("/{offering_id}/matches/{match_id}/reject", response_model=OfferingMatchResponse)
def reject_match(
    offering_id: int,
    match_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = get_offering(db, offering_id, user_id=getattr(current_user, "id", None))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offering not found")
    pair = get_match(db, offering_id, match_id)
    if not pair:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    match, icp = pair
    set_match_status(
        db, match, status=MATCH_STATUS_REJECTED, reviewed_by=getattr(current_user, "id", None)
    )
    db.commit()
    db.refresh(match)
    return serialize_match(match, icp)


@router.put("/{offering_id}/matches/{match_id}", response_model=OfferingMatchResponse)
def update_match(
    offering_id: int,
    match_id: int,
    body: MatchStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = get_offering(db, offering_id, user_id=getattr(current_user, "id", None))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offering not found")
    pair = get_match(db, offering_id, match_id)
    if not pair:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    match, icp = pair
    if body.status:
        try:
            set_match_status(
                db,
                match,
                status=body.status,
                reviewed_by=getattr(current_user, "id", None),
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(match)
    return serialize_match(match, icp)


@router.post(
    "/{offering_id}/prepare-campaign-recipients",
    response_model=PrepareCampaignRecipientsResponse,
)
def prepare_campaign_recipients_route(
    offering_id: int,
    body: PrepareCampaignRecipientsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = get_offering(db, offering_id, user_id=getattr(current_user, "id", None))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offering not found")
    if not body.match_ids and not body.icp_record_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select at least one match or ICP record",
        )
    result = prepare_campaign_recipients(
        db,
        offering_id=offering_id,
        match_ids=body.match_ids,
        icp_record_ids=body.icp_record_ids,
        campaign_id=body.campaign_id,
        group_name=body.group_name,
    )
    return result


# Re-export helper used by AI apply flows
__all__ = ["router"]
