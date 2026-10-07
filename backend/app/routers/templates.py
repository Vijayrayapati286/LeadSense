"""Email template routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.offerings.models import OfferingRow
from app.offerings.service import get_offering
from app.schemas.schemas import (
    AITemplateRequest,
    AITemplateResponse,
    PreviewTemplateRequest,
    PreviewTemplateResponse,
)
from app.services.ai_service import AIService
from app.utils.helpers import add_known_field_case_aliases, extract_placeholders, markdown_to_html, render_template

router = APIRouter(prefix="/templates", tags=["Templates"])
ai_service = AIService()

# Fallback when no offering is selected
PLACEHOLDER_TEMPLATES = [
    {
        "id": 1,
        "name": "Introduction Outreach",
        "subject": "Quick introduction — {{Company}} & Our Solution",
        "body": (
            "Hello {{Name}},\n\n"
            "I came across {{Company}} and was impressed by your work in the {{Industry}} space. "
            "As {{Designation}}, I thought you might be interested in how we've helped similar companies.\n\n"
            "Would you be open to a brief chat?"
        ),
    },
    {
        "id": 2,
        "name": "Product Demo Invite",
        "subject": "Exclusive demo for {{Company}} — Limited slots",
        "body": (
            "Hi {{Name}},\n\n"
            "We're offering select {{Industry}} leaders an exclusive product demo. "
            "Given your role as {{Designation}} at {{Company}}, I believe this could be valuable.\n\n"
            "Can I reserve a slot for you this week?"
        ),
    },
    {
        "id": 3,
        "name": "Follow-up Email",
        "subject": "Following up — {{Name}}",
        "body": (
            "Dear {{Name}},\n\n"
            "I wanted to follow up on my previous email. I understand you're busy as {{Designation}} "
            "at {{Company}}, but I believe our solution could significantly benefit your team.\n\n"
            "Would a 10-minute call work for you?"
        ),
    },
]


def _offering_template_display_name(offering_name: str | None, stored_name: str | None) -> str:
    if stored_name and stored_name != "Introduction Outreach":
        return stored_name
    if offering_name and offering_name.strip():
        return f"{offering_name.strip()} — Outreach"
    return "Introduction Outreach"


def _resolve_offering_for_templates(
    db: Session,
    offering_id: int,
    current_user: User,
) -> OfferingRow | None:
    """Load offering for campaign templates (user-owned or same-org SmartOps sync)."""
    user_id = getattr(current_user, "id", None)
    org_id = getattr(current_user, "org_id", None)
    row = get_offering(db, offering_id, user_id=user_id)
    if row:
        return row
    row = get_offering(db, offering_id, user_id=None, organization_id=org_id)
    if row:
        return row
    if org_id:
        return (
            db.query(OfferingRow)
            .filter(OfferingRow.id == offering_id, OfferingRow.organization_id == org_id)
            .first()
        )
    return None


def _templates_from_offering(row: OfferingRow) -> list[dict]:
    """Build Introduction / Product Demo / Follow-up from offering docs (AI-by-type)."""
    from app.offerings.ai_service import OfferingAIService

    offering_name = (row.name or "Our Solution").strip()
    raw_content = (row.content or row.description or row.short_description or "").strip()
    oid = row.id

    generated = OfferingAIService().generate_campaign_type_templates(
        offering_name=offering_name,
        content=raw_content,
    )
    id_by_name = {
        "Introduction Outreach": f"offering-{oid}-intro",
        "Product Demo Invite": f"offering-{oid}-demo",
        "Follow-up Email": f"offering-{oid}-followup",
    }
    templates = []
    for item in generated:
        name = item.get("name") or "Introduction Outreach"
        templates.append(
            {
                "id": id_by_name.get(name, f"offering-{oid}-intro"),
                "name": name,
                "subject": item["subject"],
                "body": item["body"],
                "source": "offering",
                "template_source": item.get("template_source") or "offering_ai",
                "offering_id": oid,
                "offering_name": offering_name,
            }
        )

    email_template = getattr(row, "email_template", None) or {}
    if email_template.get("subject") and email_template.get("body") and templates:
        templates[0] = {
            "id": f"offering-{oid}-intro",
            "name": "Introduction Outreach",
            "subject": email_template["subject"],
            "body": email_template["body"],
            "source": "offering",
            "template_source": email_template.get("source") or "upload",
            "source_filename": email_template.get("source_filename"),
            "offering_id": oid,
            "offering_name": offering_name,
            "display_name": _offering_template_display_name(
                offering_name, email_template.get("name")
            ),
        }
    return templates


@router.get("/placeholder-templates")
def get_placeholder_templates(
    offering_id: int | None = Query(None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return Offering Email templates for campaign compose.

    When ``offering_id`` is set, Introduction / Product Demo / Follow-up are
    grounded in that offering's synced SmartOps content.
    """
    if offering_id is not None:
        row = _resolve_offering_for_templates(db, offering_id, current_user)
        templates = _templates_from_offering(row) if row else list(PLACEHOLDER_TEMPLATES)
    else:
        templates = list(PLACEHOLDER_TEMPLATES)
    enriched = []
    for t in templates:
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
    add_known_field_case_aliases(context)

    rendered_subject = render_template(data.subject, context)
    rendered_body = render_template(data.body, context)
    rendered_html = markdown_to_html(rendered_body)

    return PreviewTemplateResponse(
        subject=rendered_subject,
        body=rendered_body,
        rendered_html=rendered_html,
    )
