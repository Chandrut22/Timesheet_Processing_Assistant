"""Route dependencies: DB session, Redis, the caller, role checks and paging."""

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.roles import RoleName
from src.core.rbac.permissions import ADMINS, REVIEWERS
from src.core.rbac.principal import Principal
from src.core.rbac.tokens import InvalidTokenError, decode_access_token
from src.data.actor import current_actor
from src.data.clients.postgres import get_session
from src.data.clients.redis import get_redis

# --- database / redis ----------------------------------------------------------

SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]

# --- who is calling (verified auth-service token, no DB lookup) ----------------

bearer_scheme = HTTPBearer(auto_error=False)

UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not signed in or session expired.",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> Principal:
    """The caller verified by the auth middleware (request.state.principal): the token
    is not decoded a second time. Without the middleware (an app built in a test) the
    token is verified here instead, so a route is never open by accident."""
    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, Principal):
        if credentials is None:
            raise UNAUTHORIZED
        try:
            principal = decode_access_token(credentials.credentials)
        except InvalidTokenError:
            raise UNAUTHORIZED from None
    # Rows this request creates or changes record this user (created_by / updated_by).
    current_actor.set(principal.id)
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require_roles(
    allowed: Iterable[RoleName],
) -> Callable[[Principal], Awaitable[Principal]]:
    allowed_roles = frozenset(allowed)

    async def checker(principal: CurrentPrincipal) -> Principal:
        if principal.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to do this.",
            )
        return principal

    return checker


# Ready-made guards. Any signed-in user (admin or reviewer): use CurrentPrincipal.
Reviewer = Annotated[Principal, Depends(require_roles(REVIEWERS))]
Admin = Annotated[Principal, Depends(require_roles(ADMINS))]

# --- paging (?page=1&size=20) ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class Pagination:
    page: int
    size: int


async def get_pagination(
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Pagination:
    return Pagination(page=page, size=size)


PaginationDep = Annotated[Pagination, Depends(get_pagination)]
