"""Email template routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.schemas.schemas import (
    AITemplateRequest,
    AITemplateResponse,
    PreviewTemplateRequest,
    PreviewTemplateResponse,
)
from app.services.ai_service import AIService
from app.utils.helpers import extract_placeholders, render_template

router = APIRouter(prefix="/templates", tags=["Templates"])
ai_service = AIService()

# Hardcoded placeholder templates
PLACEHOLDER_TEMPLATES = [
    {
        "id": 1,
        "name": "Introduction Outreach",
        "subject": "Quick introduction — {{{{Company}}}} & Our Solution",
        "body": (
            "Hello {{{{Name}}}},\n\n"
            "I came across {{{{Company}}}} and was impressed by your work in the {{{{Industry}}}} space. "
            "As {{{{Designation}}}}, I thought you might be interested in how we've helped similar companies.\n\n"
            "Would you be open to a brief chat?"
        ),
    },
    {
        "id": 2,
        "name": "Product Demo Invite",
        "subject": "Exclusive demo for {{{{Company}}}} — Limited slots",
        "body": (
            "Hi {{{{Name}}}},\n\n"
            "We're offering select {{{{Industry}}}} leaders an exclusive product demo. "
            "Given your role as {{{{Designation}}}} at {{{{Company}}}}, I believe this could be valuable.\n\n"
            "Can I reserve a slot for you this week?"
        ),
    },
    {
        "id": 3,
        "name": "Follow-up Email",
        "subject": "Following up — {{{{Name}}}}",
        "body": (
            "Dear {{{{Name}}}},\n\n"
            "I wanted to follow up on my previous email. I understand you're busy as {{{{Designation}}}} "
            "at {{{{Company}}}}, but I believe our solution could significantly benefit your team.\n\n"
            "Would a 10-minute call work for you?"
        ),
    },
]


@router.get("/placeholder-templates")
def get_placeholder_templates(
    current_user: User = Depends(get_current_user),
):
    """Return hardcoded placeholder templates."""
    enriched = []
    for t in PLACEHOLDER_TEMPLATES:
        placeholders = extract_placeholders(t["subject"] + " " + t["body"])
        enriched.append({**t, "placeholders": placeholders})
    return enriched


@router.post("/generate-ai-template", response_model=AITemplateResponse)
def generate_ai_template(
    data: AITemplateRequest,
    current_user: User = Depends(get_current_user),
):
    """Generate email template using OpenAI."""
    result = ai_service.generate_email(data.model_dump())
    return AITemplateResponse(**result)


@router.post("/preview-template", response_model=PreviewTemplateResponse)
def preview_template(
    data: PreviewTemplateRequest,
    current_user: User = Depends(get_current_user),
):
    """Render template with sample recipient data for preview."""
    context = {
        "Name": data.recipient_name,
        "Company": data.recipient_company,
        "Designation": data.recipient_designation,
        "Industry": data.recipient_industry,
    }

    rendered_subject = render_template(data.subject, context)
    rendered_body = render_template(data.body, context)
    rendered_html = rendered_body.replace("\n", "<br>")

    return PreviewTemplateResponse(
        subject=rendered_subject,
        body=rendered_body,
        rendered_html=rendered_html,
    )
