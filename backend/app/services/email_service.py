"""Email notification service for reqmesh.

Sends notification emails when requirements are reviewed, change requests are
submitted, decisions are recorded, and other notable project events occur.

Configure via RT_SMTP_* environment variables. When offline_mode is enabled all
sends are silently skipped. Email delivery is best-effort: failures are logged
but never raised — an email outage should not block API responses.
"""

from __future__ import annotations

import logging
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


def _is_configured() -> bool:
    from app.core.config import settings
    return bool(settings.smtp_host and not settings.offline_mode)


def _send_email(to: str | list[str], subject: str, body_html: str, body_text: str = "") -> None:
    """Fire-and-forget: send an email on a background thread."""
    from app.core.config import settings

    if not _is_configured():
        return

    recipients = [to] if isinstance(to, str) else to
    if not recipients:
        return

    def _do_send():
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = settings.smtp_from
            msg["To"] = ", ".join(recipients)
            msg["Subject"] = f"[reqmesh] {subject}"

            if body_text:
                msg.attach(MIMEText(body_text, "plain", "utf-8"))
            msg.attach(MIMEText(body_html, "html", "utf-8"))

            if settings.smtp_use_tls:
                server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
                server.starttls()
            else:
                server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)

            if settings.smtp_username and settings.smtp_password.get_secret_value():
                server.login(settings.smtp_username, settings.smtp_password.get_secret_value())

            server.sendmail(settings.smtp_from, recipients, msg.as_string())
            server.quit()
            logger.info("email sent: subject=%r to=%s", subject, recipients)
        except Exception as exc:
            logger.warning("email send failed: subject=%r to=%s error=%s", subject, recipients, exc)

    threading.Thread(target=_do_send, daemon=True).start()


def send_test_email(to: str) -> dict:
    """Send a test email synchronously and report the result (for the settings
    UI). Unlike _send_email this blocks and surfaces the SMTP error."""
    from app.core.config import settings

    if settings.offline_mode:
        return {"ok": False, "error": "Offline mode is enabled — email is disabled."}
    if not settings.smtp_host:
        return {"ok": False, "error": "No SMTP host is configured."}
    if not to or "@" not in to:
        return {"ok": False, "error": "Enter a valid recipient address."}
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = settings.smtp_from
        msg["To"] = to
        msg["Subject"] = "[reqmesh] Test email"
        msg.attach(MIMEText("This is a test email from reqmesh. Your SMTP settings work.", "plain", "utf-8"))
        msg.attach(MIMEText("<p>This is a test email from reqmesh. Your SMTP settings work.</p>", "html", "utf-8"))
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)
        server.sendmail(settings.smtp_from, [to], msg.as_string())
        server.quit()
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001 - surface any SMTP failure to the admin
        logger.warning("test email failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _user_emails(store, project_id: str) -> list[str]:
    """Collect email addresses of users who have a record and an email set."""
    from app.core.auth import load_users
    users = load_users()
    emails = []
    for u in users.values():
        email = u.get("email", "").strip()
        if email:
            emails.append(email)
    return emails


def _user_email(username: str) -> Optional[str]:
    from app.core.auth import load_users
    users = load_users()
    user = users.get(username, {})
    return user.get("email", "").strip() or None


def _project_name(store) -> str:
    return store.read_meta().get("name", "project")


def _link(project_id: str, path: str = "") -> str:
    from app.core.config import settings
    base = settings.base_url.rstrip("/")
    if settings.static_dir:
        return f"{base}/{path}"
    return f"{base}/project/{project_id}{path}"


# ── notification builders ──────────────────────────────────────────────────────


def notify_reviewed(store, project_id: str, req_id: str, reviewer: str, comment: str = "") -> None:
    """A requirement was reviewed (fingerprint baselined)."""
    if not _is_configured():
        return
    pname = _project_name(store)
    url = _link(project_id, f"/requirements/{req_id}")
    subject = f"{reviewer} reviewed {req_id} in {pname}"
    body = (
        f"<p><strong>{reviewer}</strong> reviewed requirement <strong>{req_id}</strong>"
        f" in project <strong>{pname}</strong>.</p>"
    )
    if comment:
        body += f"<p><em>{comment}</em></p>"
    body += f'<p><a href="{url}">View in reqmesh</a></p>'
    emails = _user_emails(store, project_id)
    if emails:
        _send_email(emails, subject, body)


def notify_change_request(store, project_id: str, cr_id: str, action: str, user: str) -> None:
    """A change request was created or updated."""
    if not _is_configured():
        return
    pname = _project_name(store)
    subject = f"Change request {cr_id} {action} by {user} in {pname}"
    url = _link(project_id, f"/change-requests?focus={cr_id}")
    body = (
        f"<p>Change request <strong>{cr_id}</strong> was <strong>{action}</strong>"
        f" by <strong>{user}</strong> in project <strong>{pname}</strong>.</p>"
        f'<p><a href="{url}">View in reqmesh</a></p>'
    )
    emails = _user_emails(store, project_id)
    if emails:
        _send_email(emails, subject, body)


def notify_risk(store, project_id: str, risk_id: str, action: str, user: str) -> None:
    """A risk was created or updated."""
    if not _is_configured():
        return
    pname = _project_name(store)
    subject = f"Risk {risk_id} {action} by {user} in {pname}"
    url = _link(project_id, f"/risks?focus={risk_id}")
    body = (
        f"<p>Risk <strong>{risk_id}</strong> was <strong>{action}</strong>"
        f" by <strong>{user}</strong> in project <strong>{pname}</strong>.</p>"
        f'<p><a href="{url}">View in reqmesh</a></p>'
    )
    emails = _user_emails(store, project_id)
    if emails:
        _send_email(emails, subject, body)


def notify_decision(store, project_id: str, dec_id: str, action: str, user: str) -> None:
    """A decision record was created or updated."""
    if not _is_configured():
        return
    pname = _project_name(store)
    subject = f"Decision {dec_id} {action} by {user} in {pname}"
    url = _link(project_id, f"/decisions?focus={dec_id}")
    body = (
        f"<p>Decision record <strong>{dec_id}</strong> was <strong>{action}</strong>"
        f" by <strong>{user}</strong> in project <strong>{pname}</strong>.</p>"
        f'<p><a href="{url}">View in reqmesh</a></p>'
    )
    emails = _user_emails(store, project_id)
    if emails:
        _send_email(emails, subject, body)


def send_password_reset(email: str, token: str, base_url: str) -> None:
    """Send a password-reset email with a token link."""
    if not _is_configured():
        return
    reset_url = f"{base_url.rstrip('/')}/reset-password?token={token}"
    subject = "Password reset request"
    body = (
        f"<p>A password reset was requested for your reqmesh account.</p>"
        f"<p><a href=\"{reset_url}\">Click here to reset your password</a></p>"
        f"<p>This link expires in 1 hour. If you did not request this, ignore this email.</p>"
    )
    _send_email(email, subject, body)


def notify_comment(store, project_id: str, req_id: str, author: str, text: str) -> None:
    """A comment was added to a requirement."""
    if not _is_configured():
        return
    pname = _project_name(store)
    url = _link(project_id, f"/requirements/{req_id}")
    snippet = text[:120] + ("..." if len(text) > 120 else "")
    subject = f"Comment on {req_id} by {author} in {pname}"
    body = (
        f"<p><strong>{author}</strong> commented on requirement"
        f" <strong>{req_id}</strong> in project <strong>{pname}</strong>.</p>"
        f"<blockquote>{text}</blockquote>"
        f'<p><a href="{url}">View in reqmesh</a></p>'
    )
    emails = _user_emails(store, project_id)
    if emails:
        _send_email(emails, subject, body)
