"""Step 8: two roles. Admin-only routes refuse a reviewer before any work is done,
and a token carrying an old role (super_admin / viewer) is rejected."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.rest.dependencies import get_principal
from src.api.rest.routes import companies, employees, exports, holidays
from src.config.settings import settings
from src.constants.roles import RoleName
from src.core.rbac import tokens
from src.core.rbac.permissions import ADMINS, REVIEWERS
from src.core.rbac.principal import Principal

SOME_ID = uuid.uuid4()


def test_only_two_roles() -> None:
    assert {r.value for r in RoleName} == {"admin", "reviewer"}
    assert {RoleName.ADMIN} == ADMINS
    assert {RoleName.ADMIN, RoleName.REVIEWER} == REVIEWERS


# --- admin-only routes refuse a reviewer -------------------------------------------

ADMIN_ONLY = [
    ("POST", "/companies", {"name": "X"}),
    ("PATCH", f"/companies/{SOME_ID}", {"name": "X"}),
    ("GET", f"/companies/{SOME_ID}/whitelist", None),
    ("POST", f"/companies/{SOME_ID}/whitelist", {"value": "a@b.io"}),
    ("DELETE", f"/companies/{SOME_ID}/whitelist/{SOME_ID}", None),
    ("POST", "/employees", {"full_name": "X"}),
    ("PATCH", f"/employees/{SOME_ID}", {"full_name": "X"}),
    ("POST", "/holidays", {"holiday_date": "2026-12-25"}),
    ("DELETE", f"/holidays/{SOME_ID}", None),
    ("GET", f"/exports/preview?company_id={SOME_ID}&week_start=2026-10-05", None),
    ("POST", "/exports", {"company_id": str(SOME_ID), "week_start": "2026-10-05"}),
    ("GET", "/exports", None),
    ("GET", f"/exports/{SOME_ID}", None),
]


def client_as(role: RoleName) -> TestClient:
    app = FastAPI()
    for module in (companies, employees, exports, holidays):
        app.include_router(module.router)

    async def principal() -> Principal:
        return Principal(id=uuid.uuid4(), role=role, name="Test", email="t@example.com")

    app.dependency_overrides[get_principal] = principal
    return TestClient(app)


@pytest.mark.parametrize(("method", "path", "body"), ADMIN_ONLY)
def test_reviewer_is_refused_on_admin_routes(
    method: str, path: str, body: dict[str, str] | None
) -> None:
    response = client_as(RoleName.REVIEWER).request(method, path, json=body)
    assert response.status_code == 403, response.text


# --- tokens ------------------------------------------------------------------------


@pytest.fixture
def signing_key(monkeypatch: pytest.MonkeyPatch) -> rsa.RSAPrivateKey:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    monkeypatch.setattr(tokens, "public_key", lambda: public.decode())
    return key


def make_token(key: rsa.RSAPrivateKey, role: str) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(uuid.uuid4()),
        "role": role,
        "type": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    return jwt.encode(claims, key, algorithm="RS256")


def test_admin_and_reviewer_tokens_are_accepted(signing_key: rsa.RSAPrivateKey) -> None:
    for role in ("admin", "reviewer"):
        assert tokens.decode_access_token(make_token(signing_key, role)).role == role


def test_old_role_tokens_are_rejected(signing_key: rsa.RSAPrivateKey) -> None:
    for role in ("super_admin", "viewer"):
        with pytest.raises(tokens.InvalidTokenError):
            tokens.decode_access_token(make_token(signing_key, role))
