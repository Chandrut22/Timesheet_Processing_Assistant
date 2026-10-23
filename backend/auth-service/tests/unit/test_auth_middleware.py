"""Default-deny authentication in auth-service: only the sign-in endpoints and the health
checks work without a valid access token."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Request
from fastapi.testclient import TestClient

from src.config.settings import settings
from src.core.security import create_access_token, create_refresh_token, private_key
from src.main import app

ORIGIN = "http://localhost:5173"


def access(**override: Any) -> str:
    if not override:
        return create_access_token(uuid.uuid4(), "admin", "Ada Admin", "a@example.com")
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": str(uuid.uuid4()),
        "role": "admin",
        "type": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    key = override.pop("key", private_key())
    claims.update(override)
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture
def client() -> Iterator[TestClient]:
    @app.get("/brand-new-route")
    async def brand_new(request: Request) -> dict[str, Any]:
        claims = getattr(request.state, "principal", None)
        return {"sub": claims.get("sub") if isinstance(claims, dict) else None}

    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.router.routes[:] = [
            r for r in app.router.routes if getattr(r, "path", "") != "/brand-new-route"
        ]


def is_middleware_401(response: Any) -> bool:
    return bool(
        response.status_code == 401
        and response.json()
        == {"detail": "Not signed in or session expired.", "code": "unauthorized"}
        and response.headers.get("www-authenticate") == "Bearer"
    )


def test_a_brand_new_unprotected_route_is_rejected_by_default(
    client: TestClient,
) -> None:
    assert is_middleware_401(client.get("/brand-new-route"))


def test_a_valid_token_reaches_the_route_with_the_claims_set(
    client: TestClient,
) -> None:
    response = client.get(
        "/brand-new-route", headers={"Authorization": f"Bearer {access()}"}
    )
    assert response.status_code == 200 and uuid.UUID(response.json()["sub"])


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/health", None),
        ("POST", "/auth/login", {}),  # 422 from validation, not 401
        ("POST", "/auth/refresh", None),  # 401 from the route itself (no cookie)
        ("POST", "/auth/logout", None),
        ("POST", "/auth/forgot-password", {}),
        ("POST", "/auth/reset-password", {}),
    ],
)
def test_public_paths_work_without_a_token(
    client: TestClient, method: str, path: str, body: dict[str, str] | None
) -> None:
    response = client.request(method, path, json=body)
    assert not is_middleware_401(response), (path, response.status_code, response.text)


@pytest.mark.parametrize("path", ["/auth/me", "/users", "/users/" + str(uuid.uuid4())])
def test_protected_paths_need_a_token(client: TestClient, path: str) -> None:
    assert is_middleware_401(client.get(path))


def test_change_password_needs_a_token(client: TestClient) -> None:
    assert is_middleware_401(client.post("/auth/change-password", json={}))


@pytest.mark.parametrize(
    ("make", "why"),
    [
        (lambda: access(exp=datetime.now(UTC) - timedelta(minutes=1)), "expired"),
        (
            lambda: access(
                key=rsa.generate_private_key(public_exponent=65537, key_size=2048)
            ),
            "signed with the wrong key",
        ),
        (
            lambda: create_refresh_token(uuid.uuid4()),
            "refresh token used as access token",
        ),
        (lambda: access(aud="someone-else"), "wrong audience"),
    ],
)
def test_bad_tokens(client: TestClient, make: Any, why: str) -> None:
    response = client.get(
        "/brand-new-route", headers={"Authorization": f"Bearer {make()}"}
    )
    assert is_middleware_401(response), why


def test_missing_header(client: TestClient) -> None:
    assert is_middleware_401(
        client.get("/brand-new-route", headers={"Authorization": "Basic x"})
    )


def test_cors_preflight_passes(client: TestClient) -> None:
    response = client.options(
        "/auth/me", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET"}
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN


def test_a_401_still_carries_cors_headers(client: TestClient) -> None:
    response = client.get("/auth/me", headers={"Origin": ORIGIN})
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == ORIGIN


def test_docs_are_off_and_not_public_by_default(client: TestClient) -> None:
    assert settings.docs_enabled is False
    assert is_middleware_401(client.get("/openapi.json"))
    assert is_middleware_401(client.get("/docs"))
