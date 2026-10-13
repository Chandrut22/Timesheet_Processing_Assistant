"""Verify access tokens issued by auth-service. Public key only: core can check
a token is genuine but can never create one."""

import uuid
from functools import lru_cache
from typing import Any

import jwt

from src.config.settings import settings
from src.constants.roles import RoleName
from src.core.rbac.principal import Principal


class InvalidTokenError(Exception):
    """Missing, malformed, expired, forged, wrong audience, or not an access token."""


class KeyNotFoundError(RuntimeError):
    pass


@lru_cache
def public_key() -> str:
    path = settings.jwt_public_key_path
    try:
        return path.read_text()
    except FileNotFoundError:
        raise KeyNotFoundError(
            f"JWT public key not found at {path}. Copy auth-service/keys/jwt_public.pem here."
        ) from None


def decode_access_token(token: str) -> Principal:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            public_key(),
            algorithms=[settings.jwt_algorithm],  # never let the token choose
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "exp", "type", "iss", "aud", "role"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    if payload.get("type") != "access":  # a refresh token must not work here
        raise InvalidTokenError("Not an access token")

    try:
        return Principal(
            id=uuid.UUID(str(payload["sub"])),
            role=RoleName(payload["role"]),  # unknown role -> ValueError -> rejected
            name=str(payload.get("name", "")),
            email=str(payload.get("email", "")),
        )
    except ValueError as exc:
        raise InvalidTokenError("Invalid token claims") from exc
