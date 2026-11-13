import logging
import smtplib
import ssl

from email.message import EmailMessage
from typing import TypedDict

from app.core.config import get_settings


logger = logging.getLogger(__name__)


class EmailAttachment(TypedDict):
    filename: str
    content: bytes
    maintype: str
    subtype: str


def send_email(
    recipient: str,
    subject: str,
    html_body: str,
    attachments: list[EmailAttachment] | None = None,
) -> None:
    """
    Send an HTML email using Microsoft 365 SMTP.

    Optional attachments:
        filename: Attachment filename
        content: File contents as bytes
        maintype: MIME main type, e.g. "application"
        subtype: MIME subtype, e.g. "pdf"
    """

    settings = get_settings()

    recipient = recipient.strip()
    sender = settings.email_sender.strip()
    smtp_username = settings.smtp_username.strip()

    if not recipient:
        raise ValueError("Email recipient cannot be empty.")

    if not sender:
        raise ValueError("Email sender cannot be empty.")

    if sender.casefold() != smtp_username.casefold():
        logger.warning(
            "Email sender differs from SMTP username. "
            "Sender: %s, SMTP username: %s",
            sender,
            smtp_username,
        )

    message = EmailMessage()

    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient

    # Plain-text fallback
    message.set_content(
        "This email contains HTML content. "
        "Please open it in an email client that supports HTML."
    )

    # HTML email content
    message.add_alternative(
        html_body,
        subtype="html",
    )

    # Optional attachments
    for attachment in attachments or []:
        message.add_attachment(
            attachment["content"],
            maintype=attachment["maintype"],
            subtype=attachment["subtype"],
            filename=attachment["filename"],
        )

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP(
            settings.smtp_host.strip(),
            settings.smtp_port,
            timeout=30,
        ) as server:

            server.set_debuglevel(0)

            server.ehlo()

            server.starttls(
                context=context,
            )

            server.ehlo()

            server.login(
                smtp_username,
                settings.smtp_password,
            )

            refused_recipients = server.send_message(message)

            if refused_recipients:
                logger.error(
                    "SMTP refused recipient(s): %s",
                    list(refused_recipients.keys()),
                )

                raise smtplib.SMTPRecipientsRefused(
                    refused_recipients
                )

        logger.info(
            "Email successfully accepted by SMTP server. "
            "Recipient: %s",
            recipient,
        )

    except smtplib.SMTPAuthenticationError:
        logger.exception("SMTP authentication failed.")
        raise

    except smtplib.SMTPRecipientsRefused:
        logger.exception("SMTP recipient was refused.")
        raise

    except smtplib.SMTPException:
        logger.exception("SMTP email delivery failed.")
        raise

    except Exception:
        logger.exception("Unexpected email sending error.")
        raise