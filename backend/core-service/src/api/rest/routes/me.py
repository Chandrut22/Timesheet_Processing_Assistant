from fastapi import APIRouter

from src.api.rest.dependencies import CurrentPrincipal
from src.schemas.principal import PrincipalRead

router = APIRouter(tags=["me"])


@router.get("/me", response_model=PrincipalRead)
async def me(principal: CurrentPrincipal) -> PrincipalRead:
    """Who core-service thinks you are, straight from your token (no DB lookup)."""
    return PrincipalRead(
        id=principal.id, role=principal.role, name=principal.name, email=principal.email
    )
