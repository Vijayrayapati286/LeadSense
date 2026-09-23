"""SmartOps / machine-client integration endpoints (PAT Bearer auth)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.middleware.pat_auth import PatPrincipal, get_pat_principal, whoami_response
from app.schemas.schemas import IntegrationWhoamiResponse

router = APIRouter(prefix="/v1/integrations", tags=["Integrations"])


@router.get("/me", response_model=IntegrationWhoamiResponse)
def integration_whoami(principal: PatPrincipal = Depends(get_pat_principal)):
    """Validate PAT and return the bound organization (SmartOps Test connection).

    Invalid / missing / revoked / expired tokens → 401.
    Preferred validate path for SmartOps is GET /api/auth/me with the same PAT.
    """
    return whoami_response(principal)
