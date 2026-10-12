"""Things routes ask for with Depends(...): a DB session, the current user, a role check."""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.roles import RoleName
from src.core.security import InvalidTokenError, decode_access_token, user_id_from
from src.data.clients.postgres import get_session
from src.data.clients.redis import get_redis
from src.data.models import User
from src.data.repositories.user_repository import UserRepository

SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]

# auto_error=False: we raise our own 401 with a clear message instead.
bearer_scheme = HTTPBearer(auto_error=False)

UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not signed in or session expired.",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None:
        raise UNAUTHORIZED
    try:
        user_id = user_id_from(decode_access_token(credentials.credentials))
    except InvalidTokenError:
        raise UNAUTHORIZED from None

    user = await UserRepository(session).get_by_id(user_id)
    # Checked on every request, so a deactivated user is locked out at once.
    if user is None or not user.is_active:
        raise UNAUTHORIZED
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*allowed: RoleName) -> Callable[[User], Awaitable[User]]:
    """Dependency factory: `Depends(require_roles(RoleName.SUPER_ADMIN))`.

    The role comes from the database (loaded with the user), not from the
    token, so a role change applies on the very next request.
    """

    async def checker(user: CurrentUser) -> User:
        if user.role.name not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to do this.",
            )
        return user

    return checker


# Ready-made guards, so routes read like a sentence.
SuperAdmin = Annotated[User, Depends(require_roles(RoleName.SUPER_ADMIN))]
UserDirectoryReader = Annotated[
    User, Depends(require_roles(RoleName.SUPER_ADMIN, RoleName.ADMIN))
]
# May create users. WHICH roles they may give is checked in UserService.create.
UserCreator = Annotated[
    User, Depends(require_roles(RoleName.SUPER_ADMIN, RoleName.ADMIN))
]
