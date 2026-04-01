from email.mime.text import MIMEText

import aiosmtplib

from memlord.config import settings


async def send_email(to: str, subject: str, body: str) -> None:
    """Send an email asynchronously via SMTP. No-op if smtp_host is not configured."""
    if not settings.smtp_host:
        raise RuntimeError("SMTP is not configured (MEMLORD_SMTP_HOST is not set)")

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
        start_tls=settings.smtp_tls,
    )
