"""Campaign CRUD routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import Campaign, CampaignRecipient, Recipient, User
from app.schemas.schemas import (
    CampaignListMemberResponse,
    CampaignListSummaryResponse,
    CampaignRecipientListResponse,
    CampaignRecipientResponse,
    CampaignRecipientStatsResponse,
    CampaignCreate,
    CampaignResponse,
    CampaignSequenceStageCreate,
    CampaignSequenceStageResponse,
    CampaignSequenceStageUpdate,
    CampaignUpdate,
    CancelFollowUpRequest,
    CancelFollowUpResponse,
    ListScheduleRequest,
    ListScheduleResponse,
    MarkEmailRepliedRequest,
    MarkRepliedRequest,
    MarkRepliedResponse,
    MessageResponse,
    RetagListRequest,
    ScheduleFollowUpRequest,
    ScheduleFollowUpResponse,
    TemplateCreate,
    TemplateResponse,
    TemplateUpdate,
    UndoMarkRepliedRequest,
    UpdateListEmailResponse,
)
from app.services.campaign_service import CampaignService, derive_follow_up_state
from app.services.millionverifier_service import (
    MillionVerifierService,
    resolve_verification_status,
    verification_lookup,
)
from app.utils.helpers import utc_now

router = APIRouter(tags=["Campaigns"])
campaign_service = CampaignService()


def _verification_fields(db: Session, emails: list[str], suppression_reasons: list[str | None]) -> list[tuple[str, str | None]]:
    lookup = verification_lookup(db, emails)
    allowed = MillionVerifierService()._allowed_results()
    out: list[tuple[str, str | None]] = []
    for email, reason in zip(emails, suppression_reasons):
        out.append(
            resolve_verification_status(
                email=email,
                suppression_reason=reason,
                cache_row=lookup.get((email or "").strip().lower()),
                allowed_results=allowed,
            )
        )
    return out

@router.post("/campaign", response_model=CampaignResponse, status_code=201)
def create_campaign(
    data: CampaignCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        campaign = campaign_service.create(db, data, user_id=current_user.id)
        return CampaignResponse.model_validate(campaign)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/campaigns", response_model=list[CampaignResponse])
def list_campaigns(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaigns = campaign_service.get_all(db, skip=skip, limit=limit)
    return [CampaignResponse.model_validate(c) for c in campaigns]


@router.get("/campaigns/for-update", response_model=list[CampaignResponse])
def list_campaigns_for_update(
    q: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update list picker: search by campaign name/ID or recipient email/name."""
    campaigns = campaign_service.search_for_update(db, q=q)
    return [CampaignResponse.model_validate(c) for c in campaigns]


@router.get("/campaigns/update-emails", response_model=UpdateListEmailResponse)
def list_emails_for_update(
    q: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Email-centric Update list: each card shows every campaign that email belongs to."""
    items = campaign_service.list_emails_for_update(db, q=q)
    return UpdateListEmailResponse(items=items, total=len(items))


@router.post("/campaigns/update-emails/mark-replied", response_model=MarkRepliedResponse)
def mark_email_replied_across_campaigns(
    data: MarkEmailRepliedRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = campaign_service.mark_email_replied(
            db, data.email, campaign_ids=data.campaign_ids
        )
        return MarkRepliedResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/campaign/{campaign_id}", response_model=CampaignResponse)
def get_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = campaign_service.get_by_id(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return CampaignResponse.model_validate(campaign)


@router.get("/campaign/{campaign_id}/template", response_model=TemplateResponse)
def get_campaign_template(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    template = campaign_service.get_template(db, campaign_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return TemplateResponse.model_validate(template)


@router.get("/campaign/{campaign_id}/templates", response_model=list[TemplateResponse])
def list_campaign_templates(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    templates = campaign_service.list_templates(db, campaign_id)
    return [TemplateResponse.model_validate(t) for t in templates]


@router.delete("/campaign/template/{template_id}", response_model=MessageResponse)
def delete_campaign_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        campaign_service.delete_template(db, template_id)
        return MessageResponse(message="Template deleted")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/campaign/template/{template_id}", response_model=TemplateResponse)
def update_campaign_template(
    template_id: int,
    data: TemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        template = campaign_service.update_template(db, template_id, data.model_dump(exclude_unset=True))
        return TemplateResponse.model_validate(template)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/campaign/{campaign_id}", response_model=CampaignResponse)
def update_campaign(
    campaign_id: int,
    data: CampaignUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        campaign = campaign_service.update(db, campaign_id, data)
        return CampaignResponse.model_validate(campaign)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/campaign/{campaign_id}", response_model=MessageResponse)
def delete_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        campaign_service.delete(db, campaign_id)
        return MessageResponse(message="Campaign deleted successfully")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/campaign/{campaign_id}/template", response_model=TemplateResponse)
def save_campaign_template(
    campaign_id: int,
    data: TemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        template = campaign_service.save_template(db, campaign_id, data.model_dump())
        return TemplateResponse.model_validate(template)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/campaign/{campaign_id}/sequence", response_model=list[CampaignSequenceStageResponse])
def list_sequence_stages(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stages = campaign_service.list_sequence_stages(db, campaign_id)
    return [CampaignSequenceStageResponse.model_validate(s) for s in stages]


@router.post("/campaign/{campaign_id}/sequence", response_model=CampaignSequenceStageResponse, status_code=201)
def create_sequence_stage(
    campaign_id: int,
    data: CampaignSequenceStageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        stage = campaign_service.create_sequence_stage(db, campaign_id, data)
        return CampaignSequenceStageResponse.model_validate(stage)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/campaign/sequence/{stage_id}", response_model=CampaignSequenceStageResponse)
def update_sequence_stage(
    stage_id: int,
    data: CampaignSequenceStageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        stage = campaign_service.update_sequence_stage(db, stage_id, data.model_dump(exclude_unset=True))
        return CampaignSequenceStageResponse.model_validate(stage)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/campaign/sequence/{stage_id}", response_model=MessageResponse)
def delete_sequence_stage(
    stage_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        campaign_service.delete_sequence_stage(db, stage_id)
        return MessageResponse(message="Sequence stage deleted")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/campaign/{campaign_id}/recipients", response_model=CampaignRecipientListResponse)
def get_campaign_recipients(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(CampaignRecipient)
        .filter(CampaignRecipient.campaign_id == campaign_id)
        .join(Recipient, CampaignRecipient.recipient_id == Recipient.id)
        .all()
    )
    recipient_ids = [cr.recipient_id for cr in rows]
    campaign_meta: dict[int, tuple[int, list[str]]] = {}
    if recipient_ids:
        link_rows = (
            db.query(CampaignRecipient.recipient_id, Campaign.campaign_name)
            .join(Campaign, Campaign.id == CampaignRecipient.campaign_id)
            .filter(CampaignRecipient.recipient_id.in_(recipient_ids))
            .order_by(Campaign.created_at.desc())
            .all()
        )
        names_by_recipient: dict[int, list[str]] = {}
        for rid, name in link_rows:
            names_by_recipient.setdefault(rid, []).append(name or "Untitled")
        campaign_meta = {
            rid: (len(names), names)
            for rid, names in names_by_recipient.items()
        }

    items = []
    emails = [cr.recipient.email for cr in rows]
    reasons = [cr.recipient.suppression_reason for cr in rows]
    verifications = _verification_fields(db, emails, reasons)
    for cr, (v_status, v_result) in zip(rows, verifications):
        response = CampaignRecipientResponse.model_validate(cr)
        response.recipient_name = cr.recipient.name
        response.recipient_email = cr.recipient.email
        response.recipient_company = cr.recipient.company
        response.recipient_designation = cr.recipient.designation
        response.is_suppressed = cr.recipient.is_suppressed
        response.suppression_reason = cr.recipient.suppression_reason
        response.email_verification_status = v_status
        response.email_verification_result = v_result
        state, label = derive_follow_up_state(cr)
        response.follow_up_state = state
        response.follow_up_label = label
        count, names = campaign_meta.get(cr.recipient_id, (1, []))
        response.campaign_count = count
        response.campaign_names = names
        items.append(response)

    return CampaignRecipientListResponse(items=items, total=len(items))


@router.get("/campaign/{campaign_id}/recipients/stats", response_model=CampaignRecipientStatsResponse)
def get_campaign_recipient_stats(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = campaign_service.get_by_id(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return CampaignRecipientStatsResponse(**campaign_service.recipient_stats(db, campaign_id))


@router.post("/campaign/{campaign_id}/recipients/mark-replied", response_model=MarkRepliedResponse)
def mark_campaign_recipients_replied(
    campaign_id: int,
    data: MarkRepliedRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = campaign_service.mark_recipients_replied(db, campaign_id, data.recipient_ids)
        return MarkRepliedResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/campaign/{campaign_id}/recipients/undo-mark-replied", response_model=MarkRepliedResponse)
def undo_mark_campaign_recipients_replied(
    campaign_id: int,
    data: UndoMarkRepliedRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = campaign_service.undo_mark_recipients_replied(
            db, campaign_id, [item.model_dump() for item in data.items]
        )
        return MarkRepliedResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/campaign/{campaign_id}/recipients/schedule-followup", response_model=ScheduleFollowUpResponse)
def schedule_campaign_followup(
    campaign_id: int,
    data: ScheduleFollowUpRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = campaign_service.schedule_followups(
            db,
            campaign_id,
            data.scheduled_at,
            recipient_ids=data.recipient_ids,
            all_non_replied=data.all_non_replied,
            sender_user_id=current_user.id,
        )
        return ScheduleFollowUpResponse(**result)
    except ValueError as exc:
        detail = str(exc)
        status = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status, detail=detail)


@router.post("/campaign/{campaign_id}/recipients/cancel-followup", response_model=CancelFollowUpResponse)
def cancel_campaign_followup(
    campaign_id: int,
    data: CancelFollowUpRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = campaign_service.cancel_followups(
            db,
            campaign_id,
            recipient_ids=data.recipient_ids,
            all_scheduled=data.all_scheduled,
        )
        return CancelFollowUpResponse(**result)
    except ValueError as exc:
        detail = str(exc)
        status = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status, detail=detail)


@router.get("/campaign/{campaign_id}/lists", response_model=list[CampaignListSummaryResponse])
def list_campaign_lists(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return campaign_service.list_campaign_lists(db, campaign_id)

@router.get("/campaign/{campaign_id}/lists/{group_id}/recipients", response_model=list[CampaignListMemberResponse])
def get_campaign_list_members(
    campaign_id: int,
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = campaign_service.get_list_members(db, campaign_id, group_id)
    emails = [recipient.email for _, recipient in rows]
    reasons = [recipient.suppression_reason for _, recipient in rows]
    verifications = _verification_fields(db, emails, reasons)
    return [
        CampaignListMemberResponse(
            id=recipient.id,
            name=recipient.name,
            email=recipient.email,
            company=recipient.company,
            designation=recipient.designation,
            industry=recipient.industry,
            is_suppressed=recipient.is_suppressed,
            suppression_reason=recipient.suppression_reason,
            status=cr.status,
            template_id=cr.template_id,
            email_verification_status=v_status,
            email_verification_result=v_result,
        )
        for (cr, recipient), (v_status, v_result) in zip(rows, verifications)
    ]


@router.put("/campaign/{campaign_id}/lists/{group_id}/template", response_model=MessageResponse)
def retag_campaign_list(
    campaign_id: int,
    group_id: int,
    data: RetagListRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updated = campaign_service.retag_list(db, campaign_id, group_id, data.template_id)
    return MessageResponse(message=f"Re-tagged {updated} prospect(s)")


@router.post("/campaign/{campaign_id}/lists/{group_id}/schedule", response_model=ListScheduleResponse)
def schedule_campaign_list(
    campaign_id: int,
    group_id: int,
    data: ListScheduleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    scheduled_at = data.scheduled_at
    if scheduled_at.tzinfo is None:
        raise HTTPException(status_code=400, detail="scheduled_at must include a timezone")
    if scheduled_at <= utc_now():
        raise HTTPException(status_code=400, detail="scheduled_at must be in the future")

    result = campaign_service.schedule_list(db, campaign_id, group_id, scheduled_at, current_user.id)
    if result["scheduled"] == 0 and result["skipped_suppressed"] == 0:
        raise HTTPException(status_code=404, detail="List not found or has no unsent prospects")
    return ListScheduleResponse(**result)
