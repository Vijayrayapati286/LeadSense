"""Delivery-event webhook routes.

Only a dev-only simulate endpoint exists today (gated behind settings.debug).
The real internet-facing SNS listener that AWS SES would call in production
is deferred until the AWS-side setup (SES receiving rules, SNS topic/
subscription, a public HTTPS URL) is in place — see the project plan. When
that's added, it should parse the SNS envelope and call the exact same
event_service handlers this endpoint calls, so behavior stays identical.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.schemas.schemas import MessageResponse, SimulateEventRequest
from app.services import event_service

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
settings = get_settings()


@router.post("/simulate-event", response_model=MessageResponse)
def simulate_event(
    data: SimulateEventRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dev-only: manually trigger a bounce/complaint/reply event to exercise
    the suppression/tracking logic without real AWS SES/SNS wiring."""
    if not settings.debug:
        raise HTTPException(status_code=404, detail="Not found")

    if data.event_type == "bounce":
        event_service.handle_bounce(
            db, data.email, bounce_type=data.bounce_type, campaign_id=data.campaign_id
        )
    elif data.event_type == "complaint":
        event_service.handle_complaint(db, data.email, campaign_id=data.campaign_id)
    elif data.event_type == "reply":
        event_service.handle_reply(db, data.email, campaign_id=data.campaign_id)

    return MessageResponse(message=f"Simulated {data.event_type} event for {data.email}")
