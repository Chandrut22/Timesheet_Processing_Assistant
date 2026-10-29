"""Password hashing and RS256 JWTs.

auth-service signs tokens with its PRIVATE key. Any service that has the
PUBLIC key can check a token is genuine, but cannot create one.
"""

import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import jwt
from pwdlib import PasswordHash

from src.config.settings import settings

TokenType = Literal["access", "refresh"]

# Argon2, the current recommended algorithm. Each hash includes its own salt.
password_hasher = PasswordHash.recommended()

# Used when the email does not exist, so a login with an unknown email takes
# as long as a login with a wrong password (no timing hint about which it was).
_DUMMY_HASH = password_hasher.hash("not-a-real-password")


def hash_password(plain: str) -> str:
    return str(password_hasher.hash(plain))


def verify_password(plain: str, hashed: str | None) -> bool:
    if hashed is None:
        password_hasher.verify(plain, _DUMMY_HASH)
        return False
    return password_hasher.verify(plain, hashed)


# --- keys (read from disk once, then cached) ------------------------------------


class KeyNotFoundError(RuntimeError):
    pass


def _read_key(path: Path, what: str) -> str:
    try:
        return path.read_text()
    except FileNotFoundError:
        raise KeyNotFoundError(
            f"JWT {what} key not found at {path}. Run `uv run python -m "
            "scripts.generate_keys`."
        ) from None


@lru_cache
def private_key() -> str:
    return _read_key(settings.jwt_private_key_path, "private")


@lru_cache
def public_key() -> str:
    return _read_key(settings.jwt_public_key_path, "public")


# --- tokens ------------------------------------------------------------------


def _create_token(
    user_id: uuid.UUID, token_type: TokenType, lifetime: timedelta, **extra: Any
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),  # JWT spec: "sub" is a string
        "type": token_type,  # stops a refresh token being used as an access token
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": uuid.uuid4().hex,  # unique id: every token is different
        "iat": now,
        "exp": now + lifetime,
        **extra,
    }
    return str(jwt.encode(payload, private_key(), algorithm=settings.jwt_algorithm))


def create_access_token(user_id: uuid.UUID, role: str, name: str, email: str) -> str:
    # name/email ride along so other services can show "who" without calling us.
    return _create_token(
        user_id,
        "access",
        timedelta(minutes=settings.access_token_minutes),
        role=role,
        name=name,
        email=email,
    )


def create_refresh_token(user_id: uuid.UUID) -> str:
    return _create_token(
        user_id, "refresh", timedelta(days=settings.refresh_token_days)
    )


class InvalidTokenError(Exception):
    """The token is missing, malformed, expired, forged or of the wrong type."""


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            public_key(),  # verifying needs only the PUBLIC key
            algorithms=[settings.jwt_algorithm],  # never let the token choose
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "exp", "type", "iss", "aud"]},
        )
    except jwt.PyJWTError as exc:  # expired, bad signature, wrong iss/aud, garbage...
        raise InvalidTokenError(str(exc)) from exc
    if payload.get("type") != expected_type:
        raise InvalidTokenError(f"Not an {expected_type} token")
    return payload


def decode_access_token(token: str) -> dict[str, Any]:
    return decode_token(token, "access")


def decode_refresh_token(token: str) -> dict[str, Any]:
    return decode_token(token, "refresh")


def user_id_from(payload: dict[str, Any]) -> uuid.UUID:
    """The user id inside a decoded token. Raises InvalidTokenError if it is not a UUID
    (for example an old token from before the switch to UUIDs)."""
    try:
        return uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError):
        raise InvalidTokenError("Invalid subject") from None
