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
    CampaignCreate,
    CampaignResponse,
    CampaignUpdate,
    EngagementStudioListsRequest,
    EngagementStudioListsResponse,
    EngagementStudioOverviewResponse,
    EngagementStudioStageCreate,
    EngagementStudioStageResponse,
    EngagementStudioStageUpdate,
    ListScheduleRequest,
    ListScheduleResponse,
    MessageResponse,
    RetagListRequest,
    TemplateCreate,
    TemplateResponse,
    TemplateUpdate,
)
from app.services.campaign_service import CampaignService
from app.utils.helpers import utc_now

router = APIRouter(tags=["Campaigns"])
campaign_service = CampaignService()


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


def _stage_to_response(stage) -> EngagementStudioStageResponse:
    response = EngagementStudioStageResponse.model_validate(stage)
    if stage.mailer_id and stage.mailer:
        response.mailer_name = stage.mailer.name
    return response


@router.get("/campaign/{campaign_id}/engagement-studio/stages", response_model=list[EngagementStudioStageResponse])
def list_engagement_studio_stages(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stages = campaign_service.list_engagement_studio_stages(db, campaign_id)
    return [_stage_to_response(s) for s in stages]


@router.post(
    "/campaign/{campaign_id}/engagement-studio/stages",
    response_model=EngagementStudioStageResponse,
    status_code=201,
)
def create_engagement_studio_stage(
    campaign_id: int,
    data: EngagementStudioStageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        stage = campaign_service.create_engagement_studio_stage(db, campaign_id, data)
        return _stage_to_response(stage)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/campaign/engagement-studio/stages/{stage_id}", response_model=EngagementStudioStageResponse)
def update_engagement_studio_stage(
    stage_id: int,
    data: EngagementStudioStageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        stage = campaign_service.update_engagement_studio_stage(db, stage_id, data.model_dump(exclude_unset=True))
        return _stage_to_response(stage)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/campaign/engagement-studio/stages/{stage_id}", response_model=MessageResponse)
def delete_engagement_studio_stage(
    stage_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        campaign_service.delete_engagement_studio_stage(db, stage_id)
        return MessageResponse(message="Engagement Studio stage deleted")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/campaign/{campaign_id}/engagement-studio/lists", response_model=EngagementStudioListsResponse)
def get_engagement_studio_lists(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return EngagementStudioListsResponse(group_ids=campaign_service.get_engagement_studio_lists(db, campaign_id))


@router.put("/campaign/{campaign_id}/engagement-studio/lists", response_model=EngagementStudioListsResponse)
def set_engagement_studio_lists(
    campaign_id: int,
    data: EngagementStudioListsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        group_ids = campaign_service.set_engagement_studio_lists(db, campaign_id, data.group_ids)
        return EngagementStudioListsResponse(group_ids=group_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/campaign/{campaign_id}/engagement-studio/overview", response_model=EngagementStudioOverviewResponse)
def get_engagement_studio_overview(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    overview = campaign_service.get_engagement_studio_overview(db, campaign_id)
    return EngagementStudioOverviewResponse(
        total=overview["total"],
        responded=overview["responded"],
        non_responsive=overview["non_responsive"],
        non_responsive_recipients=[
            CampaignListMemberResponse(
                id=cr.recipient.id,
                name=cr.recipient.name,
                email=cr.recipient.email,
                company=cr.recipient.company,
                designation=cr.recipient.designation,
                industry=cr.recipient.industry,
                is_suppressed=cr.recipient.is_suppressed,
                suppression_reason=cr.recipient.suppression_reason,
                status=cr.status,
                template_id=cr.template_id,
            )
            for cr in overview["non_responsive_recipients"]
        ],
    )


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
    items = []
    for cr in rows:
        response = CampaignRecipientResponse.model_validate(cr)
        response.recipient_name = cr.recipient.name
        response.recipient_email = cr.recipient.email
        response.recipient_company = cr.recipient.company
        items.append(response)

    return CampaignRecipientListResponse(items=items, total=len(items))


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
        )
        for cr, recipient in rows
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
