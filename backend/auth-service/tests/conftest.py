"""Test settings for auth-service: a throw-away RSA key pair and safe values, set as
environment variables BEFORE the app is imported (they win over any local .env)."""

import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_KEYS = Path(tempfile.mkdtemp(prefix="auth-test-keys-"))
_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
(_KEYS / "private.pem").write_bytes(
    _key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
)
(_KEYS / "public.pem").write_bytes(
    _key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
)

os.environ.update(
    {
        "OTP_SECRET": "test-only-otp-secret",
        "JWT_PRIVATE_KEY_PATH": str(_KEYS / "private.pem"),
        "JWT_PUBLIC_KEY_PATH": str(_KEYS / "public.pem"),
        "DOCS_ENABLED": "false",
        "OTEL_ENABLED": "false",
        "CORS_ORIGINS": '["http://localhost:5173"]',
        "RATE_LIMIT_ENABLED": "false",  # rate-limit tests switch it on themselves
    }
)
