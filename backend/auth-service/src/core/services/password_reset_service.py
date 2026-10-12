"""Forgot password -> 6-digit code by email -> reset password.

Redis keys (all per email address, all expire on their own). Redis is shared
with core-service, so every auth key starts with "auth:":

    auth:pwreset:otp:<email>       hash of the current code         (OTP_TTL_MINUTES)
    auth:pwreset:attempts:<email>  wrong guesses for that code      (same TTL as the code)
    auth:pwreset:lock:<email>      present = locked out             (OTP_LOCKOUT_MINUTES)
    auth:pwreset:cooldown:<email>  present = a code was just sent   (OTP_RESEND_COOLDOWN_SECONDS)

The code itself is never stored: only an HMAC of it, so someone who can read
Redis still cannot use the codes.
"""

import hashlib
import hmac
import logging
import math
import secrets

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.core.exceptions import TooManyRequestsError, ValidationFailedError
from src.core.security import hash_password
from src.core.services.email_service import send_email
from src.data.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


REDIS_PREFIX = "auth:pwreset"


def _keys(email: str) -> dict[str, str]:
    return {
        "otp": f"{REDIS_PREFIX}:otp:{email}",
        "attempts": f"{REDIS_PREFIX}:attempts:{email}",
        "lock": f"{REDIS_PREFIX}:lock:{email}",
        "cooldown": f"{REDIS_PREFIX}:cooldown:{email}",
    }


def _as_str(value: bytes | str) -> str:
    """redis-py is typed as bytes | str; with decode_responses=True it is always str."""
    return value.decode() if isinstance(value, bytes) else value


def _hash_code(email: str, code: str) -> str:
    """HMAC of the code, bound to the email so a hash only matches for that user."""
    return hmac.new(
        settings.otp_secret.get_secret_value().encode(),
        f"{email}:{code}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _minutes(seconds: int) -> int:
    return max(1, math.ceil(seconds / 60))


class PasswordResetService:
    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self.session = session
        self.redis = redis
        self.users = UserRepository(session)

    async def _raise_if_locked(self, email: str) -> None:
        ttl = await self.redis.ttl(_keys(email)["lock"])
        if ttl > 0:
            raise TooManyRequestsError(
                f"Too many wrong codes. Try again in {_minutes(ttl)} minute(s).",
                retry_after=ttl,
            )

    async def request_code(self, raw_email: str) -> str | None:
        """Step 1. Creates and stores a code if the user exists and is active.

        Returns the code to email, or None when there is nobody to send it to.
        The caller sends the email in the background, so the response looks
        the same either way (nobody can probe which emails have accounts)."""
        email = raw_email.strip().lower()
        keys = _keys(email)
        await self._raise_if_locked(email)

        # Throttle: at most one code per cooldown window. SET NX = only if absent.
        if not await self.redis.set(
            keys["cooldown"], "1", ex=settings.otp_resend_cooldown_seconds, nx=True
        ):
            ttl = await self.redis.ttl(keys["cooldown"])
            raise TooManyRequestsError(
                f"A code was just sent. Wait {max(ttl, 1)} seconds before asking again.",
                retry_after=max(ttl, 1),
            )

        user = await self.users.get_by_email(email)
        if user is None or not user.is_active:
            return None

        code = f"{secrets.randbelow(1_000_000):06d}"  # 000000-999999, cryptographically random
        ttl = settings.otp_ttl_minutes * 60
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.set(keys["otp"], _hash_code(email, code), ex=ttl)
            pipe.delete(keys["attempts"])  # a new code starts with a clean count
            await pipe.execute()
        return code

    async def reset_password(
        self, raw_email: str, code: str, new_password: str
    ) -> None:
        """Step 2. Checks the code; 3 wrong codes lock resets for 30 minutes."""
        email = raw_email.strip().lower()
        keys = _keys(email)
        await self._raise_if_locked(email)

        stored = await self.redis.get(keys["otp"])
        if stored is None:
            raise ValidationFailedError(
                "The code has expired or was not requested. Ask for a new one."
            )

        # Constant-time compare, same arguments as when the code was stored.
        if not hmac.compare_digest(_as_str(stored), _hash_code(email, code)):
            attempts = await self.redis.incr(keys["attempts"])
            if attempts == 1:  # the counter lives as long as the code
                await self.redis.expire(
                    keys["attempts"], max(await self.redis.ttl(keys["otp"]), 1)
                )
            left = settings.otp_max_attempts - attempts
            if left <= 0:
                lock_s = settings.otp_lockout_minutes * 60
                async with self.redis.pipeline(transaction=True) as pipe:
                    pipe.set(keys["lock"], "1", ex=lock_s)
                    pipe.delete(keys["otp"], keys["attempts"])  # the code is burnt
                    await pipe.execute()
                raise TooManyRequestsError(
                    f"Too many wrong codes. Try again in {settings.otp_lockout_minutes} minutes.",
                    retry_after=lock_s,
                )
            raise ValidationFailedError(f"Invalid code. {left} attempt(s) left.")

        user = await self.users.get_by_email(email)
        if user is None or not user.is_active:
            # The account was removed or deactivated after the code was sent.
            await self.redis.delete(keys["otp"], keys["attempts"])
            raise ValidationFailedError(
                "The code has expired or was not requested. Ask for a new one."
            )

        user.password_hash = hash_password(new_password)
        await self.session.commit()
        await self.redis.delete(keys["otp"], keys["attempts"])  # one code, one use


# --- emails (sent in the background by the route) --------------------------------


async def send_code_email(to: str, code: str) -> None:
    minutes = settings.otp_ttl_minutes
    text = (
        f"Your password reset code is {code}\n\n"
        f"It expires in {minutes} minutes. If you did not ask for it, ignore this email; "
        "your password has not changed."
    )
    html = f"""\
<div style="font-family:Arial,sans-serif;max-width:480px">
  <h2 style="margin:0 0 12px">Reset your password</h2>
  <p>Use this code to reset your password:</p>
  <p style="font-size:28px;font-weight:bold;letter-spacing:6px;margin:16px 0">{code}</p>
  <p>It expires in {minutes} minutes.</p>
  <p style="color:#666;font-size:13px">If you did not ask for this, ignore this email.
  Your password has not changed.</p>
</div>"""
    try:
        await send_email(to, "Your password reset code", text, html)
    except Exception:
        # Never crash the background task; the log says what went wrong.
        logger.exception("Could not send the reset code to %s", to)


async def send_password_changed_email(to: str) -> None:
    text = (
        "Your password was just changed.\n\n"
        "If this was not you, contact your administrator immediately."
    )
    try:
        await send_email(to, "Your password was changed", text)
    except Exception:
        logger.exception("Could not send the password-changed notice to %s", to)
