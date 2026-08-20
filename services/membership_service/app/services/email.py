import aiosmtplib
from email.message import EmailMessage
from enum import Enum
from app.config import settings


class EmailType(Enum):
    VERIFY = "verify"
    INVITATION = "invitation"
    PASSWORD_RESET = "reset"


def build_email(to: str, subject: str, html_body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(html_body, subtype="html")
    return msg


async def send_email(to: str, subject: str, html_body: str, email_type: EmailType) -> None:
    msg = build_email(to, subject, html_body)
    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )
    except Exception:
        # Log but don't fail - email delivery is non-critical for MVP
        pass
