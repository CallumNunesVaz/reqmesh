"""Tests for FAB-1 (SecretStr bug), FAB-2 (subject injection), and FAB-4 (report logo SSRF)."""

import email
import smtplib
import threading

import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.services.email_service import send_test_email, _send_email
from app.services.publisher import Publisher


# ── helpers ────────────────────────────────────────────────────────────────────


def _smtp_setup(monkeypatch, *, host="mail.example.com", username="",
                password=SecretStr(""), use_tls=False):
    """Set up SMTP-related settings for tests that exercise the mail path."""
    monkeypatch.setattr(settings, "offline_mode", False)
    monkeypatch.setattr(settings, "smtp_host", host)
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_use_tls", use_tls)
    monkeypatch.setattr(settings, "smtp_username", username)
    monkeypatch.setattr(settings, "smtp_password", password)
    monkeypatch.setattr(settings, "smtp_from", "from@example.com")


# ── FAB-1: send_test_email SecretStr ───────────────────────────────────────────


class TestSendTestEmailSecretStr:
    def test_unwraps_secret_before_login(self, monkeypatch):
        """With a non-empty password, login receives a str, not a SecretStr."""
        login_args = []

        class FakeSMTP:
            def __init__(self, host, port, timeout=None):
                pass

            def starttls(self):
                pass

            def login(self, user, password):
                login_args.append((user, password))

            def sendmail(self, from_addr, to_addrs, msg_string):
                pass

            def quit(self):
                pass

        monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
        _smtp_setup(monkeypatch, username="user", password=SecretStr("secret123"), use_tls=True)

        result = send_test_email("to@example.com")
        assert result["ok"] is True
        assert len(login_args) == 1
        assert login_args[0][0] == "user"
        assert login_args[0][1] == "secret123"
        assert isinstance(login_args[0][1], str)

    def test_empty_password_skips_login(self, monkeypatch):
        """An empty SecretStr must not trigger a login call (the bug)."""
        login_args = []

        class FakeSMTP:
            def __init__(self, host, port, timeout=None):
                pass

            def starttls(self):
                pass

            def login(self, user, password):
                login_args.append((user, password))

            def sendmail(self, from_addr, to_addrs, msg_string):
                pass

            def quit(self):
                pass

        monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
        _smtp_setup(monkeypatch, username="user", password=SecretStr(""))

        result = send_test_email("to@example.com")
        assert result["ok"] is True
        assert len(login_args) == 0


# ── FAB-2: subject header injection ────────────────────────────────────────────


class TestSubjectHeaderInjection:
    def test_crlf_in_subject_is_collapsed(self, monkeypatch):
        """\r\n in a subject must not produce a separate Bcc header."""
        captured_msg = {}

        class FakeSMTP:
            def __init__(self, host, port, timeout=None):
                pass

            def starttls(self):
                pass

            def login(self, user, password):
                pass

            def sendmail(self, from_addr, to_addrs, msg_string):
                captured_msg["raw"] = msg_string

            def quit(self):
                pass

        class _InlineThread:
            def __init__(self, target, daemon=False):
                self._target = target

            def start(self):
                self._target()

        monkeypatch.setattr(threading, "Thread", _InlineThread)
        monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
        _smtp_setup(monkeypatch)

        _send_email("to@x", "hello\r\nBcc: evil@x", "<p>body</p>")

        raw = captured_msg["raw"]
        msg = email.message_from_string(raw)
        assert msg["Subject"] is not None
        assert "\n" not in msg["Subject"]
        assert "\r" not in msg["Subject"]
        # A header-split injection would produce a real Bcc header.
        assert msg["Bcc"] is None


# ── FAB-4: report logo SSRF ────────────────────────────────────────────────────


class _MinimalStore:
    """Store stub that satisfies every method Publisher reads during construction
    and a cover-only ``build_html`` call."""

    def __init__(self, name="test-project"):
        self.root = type("_Root", (), {"name": name})()

    def read_meta(self):
        return {"name": self.root.name}

    def list_requirements(self):
        return []

    def list_verification_cases(self):
        return []

    def list_components(self):
        return []

    def list_specifications(self):
        return []

    def read_traces(self):
        return {"links": []}

    def list_items(self, name):
        return []

    def list_all_history(self, since="", until=""):
        return []


class TestReportLogoSsrf:
    def test_non_data_logo_is_dropped(self, monkeypatch):
        """A http:// logo URL must not appear in the cover HTML at all."""
        monkeypatch.setattr(settings, "report_logo_url",
                            "http://169.254.169.254/x")
        # Clear other branding bits so the cover is minimal and assertions are
        # unambiguous.
        monkeypatch.setattr(settings, "report_company_name", "")
        monkeypatch.setattr(settings, "report_department", "")
        monkeypatch.setattr(settings, "report_document_title", "")
        monkeypatch.setattr(settings, "report_show_git_commit", False)
        monkeypatch.setattr(settings, "report_color", "")

        store = _MinimalStore()
        pub = Publisher(store)
        html = pub.build_html(["cover"])

        assert "169.254" not in html
        assert 'class="logo"' not in html

    def test_data_logo_is_rendered(self, monkeypatch):
        """A data: URI logo must appear in the cover HTML."""
        monkeypatch.setattr(settings, "report_logo_url",
                            "data:image/png;base64,AAAA")
        monkeypatch.setattr(settings, "report_company_name", "")
        monkeypatch.setattr(settings, "report_department", "")
        monkeypatch.setattr(settings, "report_document_title", "")
        monkeypatch.setattr(settings, "report_show_git_commit", False)
        monkeypatch.setattr(settings, "report_color", "")

        store = _MinimalStore()
        pub = Publisher(store)
        html = pub.build_html(["cover"])

        assert 'class="logo"' in html
