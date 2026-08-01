"""User-controlled text must not reach an email body as live HTML.

A maintainer can set any project name and any comment text. Both are
interpolated into notification bodies that go to every subscribed user, so an
unescaped value is an injection point for tracking pixels and phishing links —
delivered by the server, from a trusted sender, to the whole team.

The first fix escaped the comment and the review text but left the project name
and the usernames, which is why these assert every interpolated value rather
than the two that were noticed.
"""

import pytest

from app.services import email_service


PAYLOAD = '<img src=x onerror=alert(1)>'


@pytest.fixture
def sent(monkeypatch, tmp_path):
    """Capture what would be sent, with SMTP considered configured."""
    captured = []
    monkeypatch.setattr(email_service, "_is_configured", lambda: True)
    monkeypatch.setattr(email_service, "_send_email",
                        lambda to, subject, body, text="": captured.append(
                            {"to": to, "subject": subject, "body": body}))
    monkeypatch.setattr(email_service, "_user_emails", lambda store, pid: ["dev@example.com"])
    return captured


class _Store:
    """Minimal stand-in — only read_meta is used by the notifiers."""
    def __init__(self, name):
        self._name = name

    def read_meta(self):
        return {"name": self._name}


def test_project_name_is_escaped_in_every_notifier(sent):
    store = _Store(PAYLOAD)
    email_service.notify_change_request(store, "p", "CR1", "created", "bob")
    email_service.notify_risk(store, "p", "RSK1", "created", "bob")
    email_service.notify_decision(store, "p", "DEC1", "created", "bob")
    email_service.notify_reviewed(store, "p", "R1", "bob", "")
    email_service.notify_comment(store, "p", "R1", "bob", "hello")

    assert len(sent) == 5
    for msg in sent:
        assert PAYLOAD not in msg["body"], f"unescaped project name in: {msg['subject']}"
        assert "&lt;img" in msg["body"]


def test_username_is_escaped(sent):
    store = _Store("Safe Project")
    email_service.notify_risk(store, "p", "RSK1", "created", PAYLOAD)
    email_service.notify_reviewed(store, "p", "R1", PAYLOAD, "")
    email_service.notify_comment(store, "p", "R1", PAYLOAD, "hello")
    for msg in sent:
        assert PAYLOAD not in msg["body"]


def test_comment_text_is_escaped(sent):
    store = _Store("Safe Project")
    email_service.notify_comment(store, "p", "R1", "bob", PAYLOAD)
    email_service.notify_reviewed(store, "p", "R1", "bob", PAYLOAD)
    for msg in sent:
        assert PAYLOAD not in msg["body"]
        assert "&lt;img" in msg["body"]


def test_the_link_is_still_a_working_anchor(sent):
    """Escaping must not break the one piece of markup that is meant to be live."""
    email_service.notify_risk(_Store("Proj"), "p", "RSK1", "created", "bob")
    assert '<a href="' in sent[0]["body"]


def test_a_newline_in_the_project_name_cannot_inject_a_header():
    """Python refuses to serialize a header containing an embedded header, so
    this is a failed send rather than a BCC to an attacker. Pinned because the
    subject is built by interpolation and that guarantee is not obvious."""
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.errors import HeaderParseError

    msg = MIMEMultipart("alternative")
    msg["From"] = "a@b.c"
    msg["To"] = "d@e.f"
    msg["Subject"] = "[reqmesh] Project\nBcc: attacker@evil.example"
    msg.attach(MIMEText("hi", "html", "utf-8"))
    with pytest.raises(HeaderParseError):
        msg.as_string()
