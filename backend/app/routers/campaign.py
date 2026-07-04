"""Campaign CRUD routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.schemas.schemas import (
    CampaignCreate,
    CampaignResponse,
    CampaignUpdate,
    MessageResponse,
    TemplateCreate,
    TemplateResponse,
)
from app.services.campaign_service import CampaignService

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
