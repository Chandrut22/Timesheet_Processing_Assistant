"""Create the RS256 key pair for signing JWTs.

    uv run python -m scripts.generate_keys

Writes keys/jwt_private.pem (keep secret, auth-service only) and
keys/jwt_public.pem (give to every service that verifies tokens).
Refuses to overwrite existing keys: new keys log every user out.
"""

import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KEYS_DIR = Path("keys")


def main() -> int:
    private_path = KEYS_DIR / "jwt_private.pem"
    public_path = KEYS_DIR / "jwt_public.pem"
    if private_path.exists():
        print(
            f"{private_path} already exists; delete it first if you really want new "
            "keys."
        )
        return 1

    KEYS_DIR.mkdir(exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    print(f"Wrote {private_path} (secret) and {public_path} (shareable).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
