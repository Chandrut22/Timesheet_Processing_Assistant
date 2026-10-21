"""Default-deny authentication: no route is reachable without a valid access token
unless its path is on the public allowlist."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.api.middleware.auth import AuthMiddleware
from src.config.settings import settings
from src.core.rbac import tokens
from src.core.rbac.principal import Principal
from src.main import app

ORIGIN = "http://localhost:5173"


def new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


KEY, OTHER_KEY = new_key(), new_key()


@pytest.fixture(autouse=True)
def trusted_key(monkeypatch: pytest.MonkeyPatch) -> None:
    public = KEY.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    monkeypatch.setattr(tokens, "public_key", lambda: public.decode())


def token(key: rsa.RSAPrivateKey = KEY, **override: Any) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": str(uuid.uuid4()),
        "role": "reviewer",
        "name": "Rita Reviewer",
        "email": "r@example.com",
        "type": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    claims.update(override)
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture
def client() -> Iterator[TestClient]:
    """The real app, plus a brand-new route that asks for no dependency at all."""

    @app.get("/brand-new-route")
    async def brand_new(request: Request) -> dict[str, str]:
        principal = getattr(request.state, "principal", None)
        return {"who": principal.name if isinstance(principal, Principal) else "nobody"}

    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.router.routes[:] = [
            r for r in app.router.routes if getattr(r, "path", "") != "/brand-new-route"
        ]


def assert_401(response: Any) -> None:
    assert response.status_code == 401, response.text
    assert response.json() == {
        "detail": "Not signed in or session expired.",
        "code": "unauthorized",
    }
    assert response.headers["www-authenticate"] == "Bearer"


def test_a_brand_new_unprotected_route_is_rejected_by_default(client: TestClient) -> None:
    assert_401(client.get("/brand-new-route"))


def test_a_valid_token_reaches_the_route_with_the_principal_set(client: TestClient) -> None:
    response = client.get("/brand-new-route", headers={"Authorization": f"Bearer {token()}"})
    assert response.status_code == 200 and response.json() == {"who": "Rita Reviewer"}


def test_health_is_public(client: TestClient) -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/health/db").status_code != 401  # may fail without a database, but not 401


@pytest.mark.parametrize(
    ("headers", "why"),
    [
        ({}, "missing header"),
        ({"Authorization": "Basic dXNlcjpwYXNz"}, "not a bearer token"),
        ({"Authorization": "Bearer "}, "empty token"),
        ({"Authorization": "Bearer not.a.jwt"}, "garbage"),
    ],
)
def test_missing_or_malformed_tokens(client: TestClient, headers: dict[str, str], why: str) -> None:
    assert_401(client.get("/brand-new-route", headers=headers))


@pytest.mark.parametrize(
    ("bad", "why"),
    [
        (lambda: token(exp=datetime.now(UTC) - timedelta(minutes=1)), "expired"),
        (lambda: token(OTHER_KEY), "signed with the wrong key"),
        (lambda: token(type="refresh"), "refresh token used as access token"),
        (lambda: token(aud="someone-else"), "wrong audience"),
        (lambda: token(iss="evil"), "wrong issuer"),
        (lambda: token(role="super_admin"), "unknown role"),
    ],
)
def test_bad_tokens(client: TestClient, bad: Any, why: str) -> None:
    assert_401(client.get("/brand-new-route", headers={"Authorization": f"Bearer {bad()}"}))


def test_cors_preflight_passes_without_a_token(client: TestClient) -> None:
    response = client.options(
        "/timesheets",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN


def test_a_401_still_carries_cors_headers(client: TestClient) -> None:
    response = client.get("/timesheets", headers={"Origin": ORIGIN})
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == ORIGIN  # the browser can read it


def test_existing_routes_are_protected(client: TestClient) -> None:
    for path in ("/me", "/timesheets", "/submissions", "/companies", "/exports"):
        assert_401(client.get(path))


def small_app(docs_enabled: bool) -> TestClient:
    inner = FastAPI(openapi_url="/openapi.json")
    inner.add_middleware(
        AuthMiddleware,
        verify=tokens.decode_access_token,
        public_paths=["/health"],
        docs_enabled=docs_enabled,
    )
    return TestClient(inner)


def test_docs_are_public_only_when_enabled() -> None:
    assert small_app(docs_enabled=False).get("/openapi.json").status_code == 401
    assert small_app(docs_enabled=True).get("/openapi.json").status_code == 200


def test_trailing_slash_does_not_bypass_or_block() -> None:
    client = small_app(docs_enabled=False)
    assert client.get("/health/").status_code != 401  # public with or without the slash
