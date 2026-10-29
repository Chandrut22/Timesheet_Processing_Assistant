"""Emails about user accounts. Sent in the background by the routes, so a slow
or broken SMTP server never fails the API call."""

import html
import logging

from src.config.settings import settings
from src.core.services.email_service import send_email

logger = logging.getLogger(__name__)


async def send_welcome_email(to: str, name: str, password: str, role: str) -> None:
    """Login details for a new user. The password is never logged."""
    product = settings.product_name
    role_label = role.replace("_", " ").title()  # "super_admin" -> "Super Admin"

    text = (
        f"Hi {name},\n\nAn account has been created for you on {product} with the role "
        f"{role_label}.\n\nSign in at: {settings.login_url}\nEmail:      "
        f"{to}\nPassword:   {password}\n\nPlease change this password after your first "
        "sign-in.\nIf you were not expecting this email, contact your administrator."
    )

    # Escape everything user-supplied: a name or password may contain < > & "
    e = html.escape
    html_body = f"""\
<div style="font-family:Arial,sans-serif;max-width:520px">
  <h2 style="margin:0 0 12px">Welcome to {e(product)}</h2>
  <p>Hi {e(name)},</p>
  <p>An account has been created for you with the role <b>{e(role_label)}</b>.</p>
  <table style="border-collapse:collapse;margin:16px 0">
    <tr><td style="padding:4px 12px 4px 0;color:#666">Email</td>
        <td><b>{e(to)}</b></td></tr>
    <tr><td style="padding:4px 12px 4px 0;color:#666">Password</td>
        <td><code style="font-size:15px">{e(password)}</code></td></tr>
  </table>
  <p><a href="{e(settings.login_url)}"
        style="background:#2563eb;color:#fff;padding:10px 18px;border-radius:6px;
               text-decoration:none;display:inline-block">Sign in</a></p>
  <p style="color:#666;font-size:13px">Please change this password after your first
  sign-in. If you were not expecting this email, contact your administrator.</p>
</div>"""

    try:
        await send_email(to, f"Your {product} account", text, html_body)
    except Exception:
        logger.exception("Could not send the welcome email to %s", to)
