"""SmartOps / machine-client integration endpoints (PAT Bearer auth)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.middleware.pat_auth import PatPrincipal, get_pat_principal
from app.schemas.schemas import IntegrationWhoamiResponse

router = APIRouter(prefix="/v1/integrations", tags=["Integrations"])


@router.get("/me", response_model=IntegrationWhoamiResponse)
def integration_whoami(principal: PatPrincipal = Depends(get_pat_principal)):
    """Validate PAT and return the bound organization (SmartOps Test connection).

    Invalid / missing / revoked / expired tokens → 401.
    """
    org = principal.organization
    token = principal.token
    return IntegrationWhoamiResponse(
        organization_id=org.org_id,
        organization_name=org.org_name,
        type=org.org_type,
        token_status=token.status.lower() if token.status else "active",
        token_id=None if token.token_id == "tok_legacy" else token.token_id,
        token_name=token.name,
    )
