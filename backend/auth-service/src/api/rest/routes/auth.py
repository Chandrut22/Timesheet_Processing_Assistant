from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Cookie, HTTPException, Response, status

from src.api.rest.dependencies import CurrentUser, RedisDep, SessionDep
from src.config.settings import settings
from src.core.services.auth_service import (
    AuthService,
    InvalidCredentialsError,
    InvalidSessionError,
    IssuedTokens,
)
from src.core.services.password_reset_service import (
    PasswordResetService,
    send_code_email,
    send_password_changed_email,
)
from src.core.services.user_service import UserService
from src.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    ResetPasswordRequest,
    TokenResponse,
)
from src.schemas.user import ChangePasswordRequest, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])

# Reads the refresh token from the cookie named in settings.
RefreshCookie = Annotated[str | None, Cookie(alias=settings.refresh_cookie_name)]


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        httponly=True,  # JavaScript cannot read it (XSS can't steal it)
        secure=settings.refresh_cookie_secure,  # only sent over HTTPS
        samesite="strict",  # not sent on requests from other sites (CSRF)
        path=settings.refresh_cookie_path,  # only sent to /auth/*
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite="strict",
    )


def _respond(response: Response, tokens: IssuedTokens) -> TokenResponse:
    _set_refresh_cookie(response, tokens.refresh_token)
    return tokens.body  # the access token goes in the body; the app keeps it in memory


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest, response: Response, session: SessionDep
) -> TokenResponse:
    try:
        tokens = await AuthService(session).login(body.email, body.password)
    except InvalidCredentialsError:
        # Same message for every failure: never reveal which part was wrong.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        ) from None
    return _respond(response, tokens)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response, session: SessionDep, refresh_token: RefreshCookie = None
) -> TokenResponse:
    try:
        tokens = await AuthService(session).refresh(refresh_token)
    except InvalidSessionError:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please sign in again.",
            headers=dict(response.headers),  # keep the Set-Cookie that clears it
        ) from None
    return _respond(response, tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    """Works even with an expired access token: it only clears the cookie.
    The app also forgets its in-memory access token."""
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> UserRead:
    return UserRead.from_user(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest, user: CurrentUser, session: SessionDep
) -> None:
    await UserService(session).change_own_password(
        user, body.current_password, body.new_password
    )


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    body: ForgotPasswordRequest,
    background: BackgroundTasks,
    session: SessionDep,
    redis: RedisDep,
) -> MessageResponse:
    """Step 1: email a 6-digit code if the account exists.

    The answer is the same whether or not the email has an account, and the
    email is sent after the response, so neither the text nor the timing
    tells an outsider which addresses are registered."""
    code = await PasswordResetService(session, redis).request_code(body.email)
    if code is not None:
        background.add_task(send_code_email, body.email.strip().lower(), code)
    return MessageResponse(
        message="If an account exists for this email, a 6-digit code has been sent to "
        "it."
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    body: ResetPasswordRequest,
    background: BackgroundTasks,
    session: SessionDep,
    redis: RedisDep,
) -> MessageResponse:
    """Step 2: check the code and set the new password. 3 wrong codes lock
    password resets for this email for 30 minutes."""
    await PasswordResetService(session, redis).reset_password(
        body.email, body.code, body.new_password
    )
    background.add_task(send_password_changed_email, body.email.strip().lower())
    return MessageResponse(message="Your password has been reset. You can sign in now.")
