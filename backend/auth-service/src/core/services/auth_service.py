"""Login and token refresh. Knows nothing about HTTP or cookies; routes do that."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.core.security import (
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    user_id_from,
    verify_password,
)
from src.data.actor import current_actor
from src.data.models import User
from src.data.repositories.user_repository import UserRepository
from src.observability.metrics.instruments import logins
from src.schemas.auth import TokenResponse


class InvalidCredentialsError(Exception):
    """Wrong email, wrong password, or inactive account (one error for all)."""


class InvalidSessionError(Exception):
    """The refresh token is missing, expired, or its user can no longer sign in."""


@dataclass
class IssuedTokens:
    """What a successful login or refresh returns: the body + the cookie value."""

    body: TokenResponse
    refresh_token: str


def _issue(user: User) -> IssuedTokens:
    return IssuedTokens(
        body=TokenResponse(
            access_token=create_access_token(
                user.id, user.role.name, user.name, user.email
            ),
            expires_in=settings.access_token_minutes * 60,
        ),
        refresh_token=create_refresh_token(user.id),
    )


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def login(self, email: str, password: str) -> IssuedTokens:
        user = await self.users.get_by_email(email)
        # Always verify (even when the user is missing) to keep timing equal.
        password_ok = verify_password(password, user.password_hash if user else None)
        if user is None or not password_ok or not user.is_active:
            logins.add(1, {"result": "failed"})
            raise InvalidCredentialsError

        user.last_login_at = datetime.now(UTC)
        current_actor.set(user.id)  # the user changed their own row (updated_by)
        await self.session.commit()
        logins.add(1, {"result": "success"})
        return _issue(user)

    async def refresh(self, refresh_token: str | None) -> IssuedTokens:
        """Swap a valid refresh token for a new access token AND a new refresh
        token (rotation). The user is loaded again, so a deactivated user or a
        changed role takes effect here."""
        if not refresh_token:
            raise InvalidSessionError
        try:
            user_id = user_id_from(decode_refresh_token(refresh_token))
        except InvalidTokenError:
            raise InvalidSessionError from None

        user = await self.users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise InvalidSessionError
        return _issue(user)
