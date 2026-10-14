"""Public one-click unsubscribe (List-Unsubscribe / RFC 8058)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.services.suppression_service import SuppressionService
from app.utils.unsubscribe import valid_unsubscribe_token

router = APIRouter(prefix="/public", tags=["Public"])
suppression_service = SuppressionService()


def _unsubscribe(email: str, token: str, db: Session) -> dict:
    normalized = (email or "").strip().lower()
    if not normalized or "@" not in normalized:
        raise HTTPException(status_code=400, detail="Invalid email")
    if not valid_unsubscribe_token(normalized, token):
        raise HTTPException(status_code=400, detail="Invalid unsubscribe link")
    if not suppression_service.is_suppressed(db, normalized):
        suppression_service.add_by_email(
            db,
            email=normalized,
            reason="unsubscribe",
            detail="One-click List-Unsubscribe",
        )
    return {"status": "unsubscribed", "email": normalized}


@router.get("/unsubscribe")
def unsubscribe_get(
    email: str = Query(...),
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    return _unsubscribe(email, token, db)


@router.post("/unsubscribe")
async def unsubscribe_post(
    request: Request,
    email: str | None = Query(None),
    token: str | None = Query(None),
    db: Session = Depends(get_db),
):
    form_email, form_token = email, token
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        form_email = form_email or str(form.get("email") or "")
        form_token = form_token or str(form.get("token") or "")
    if not form_email or not form_token:
        raise HTTPException(status_code=400, detail="Missing email or token")
    return _unsubscribe(form_email, form_token, db)
