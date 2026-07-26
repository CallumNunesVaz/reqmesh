"""Deployment profiles, and the anonymous-read control they switch.

``profile`` was previously inert: it was declared, warned about at startup and
reported by /health, but no code applied the posture its comments described.
``RT_PROFILE=personal`` did not enable anonymous read or self-registration, and
did not relax Secure cookies — so a plain-HTTP LAN deployment silently dropped
the session cookie.

``require_auth`` was likewise only half-wired: it refused *guest logins* while
every read endpoint stayed anonymous, so "no anonymous read" was never true.
"""
import pytest

from app.core import auth
from app.core.config import PROFILE_PRESETS, Settings, settings


def _settings(monkeypatch, **env) -> Settings:
    """Build a Settings instance from a clean environment."""
    for key in list(__import__("os").environ):
        if key.startswith("RT_"):
            monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings()


class TestProfilePresets:
    @pytest.mark.parametrize("profile", ["personal", "team", "hardened"])
    def test_preset_is_applied(self, monkeypatch, profile):
        s = _settings(monkeypatch, RT_PROFILE=profile)
        for field, expected in PROFILE_PRESETS[profile].items():
            assert getattr(s, field) == expected, f"{profile}.{field}"

    def test_personal_allows_plain_http_and_anonymous_read(self, monkeypatch):
        s = _settings(monkeypatch, RT_PROFILE="personal")
        assert s.cookie_secure is False, "Secure cookies are dropped over plain HTTP"
        assert s.require_auth is False
        assert s.allow_self_registration is True

    def test_team_is_the_default_and_is_locked_down(self, monkeypatch):
        s = _settings(monkeypatch)
        assert s.profile == "team"
        assert s.require_auth is True
        assert s.allow_self_registration is False
        assert s.cookie_secure is True

    def test_hardened_adds_email_verification_and_a_stricter_csp(self, monkeypatch):
        s = _settings(monkeypatch, RT_PROFILE="hardened")
        assert s.require_email_verification is True
        assert "upgrade-insecure-requests" in s.csp_default

    def test_unknown_profile_falls_back_to_team(self, monkeypatch):
        s = _settings(monkeypatch, RT_PROFILE="nonsense")
        assert s.require_auth is True and s.cookie_secure is True


class TestExplicitSettingsWin:
    """A profile is a starting posture, not a straitjacket."""

    def test_explicit_env_var_overrides_the_preset(self, monkeypatch):
        s = _settings(monkeypatch, RT_PROFILE="personal", RT_COOKIE_SECURE="true")
        assert s.cookie_secure is True, "explicit RT_COOKIE_SECURE was clobbered"

    def test_explicit_require_auth_overrides_team(self, monkeypatch):
        s = _settings(monkeypatch, RT_PROFILE="team", RT_REQUIRE_AUTH="false")
        assert s.require_auth is False

    def test_unrelated_settings_are_untouched(self, monkeypatch):
        s = _settings(monkeypatch, RT_PROFILE="hardened", RT_MAX_UPLOAD_SIZE_MB="7")
        assert s.max_upload_size_mb == 7


class TestAnonymousReadIsActuallyBlocked:
    """The control the profile switches — not just a flag on an object."""

    @pytest.fixture()
    def authed(self, monkeypatch):
        monkeypatch.setattr(settings, "cookie_secure", False)
        auth.register_user("mo", "Password123!", "maintainer")

    def test_reads_are_denied_without_a_session(self, guest_client, monkeypatch, authed):
        monkeypatch.setattr(settings, "require_auth", True)
        assert guest_client.get("/api/projects").status_code == 401

    def test_reads_are_allowed_once_signed_in(self, guest_client, monkeypatch, authed):
        monkeypatch.setattr(settings, "require_auth", True)
        res = guest_client.post("/api/auth/login",
                                json={"username": "mo", "password": "Password123!"})
        assert res.status_code == 200
        assert guest_client.get("/api/projects").status_code == 200

    def test_login_and_whoami_stay_reachable(self, guest_client, monkeypatch, authed):
        """Locking the API must not lock users out of signing in."""
        monkeypatch.setattr(settings, "require_auth", True)
        assert guest_client.get("/api/auth/whoami").status_code == 200
        assert guest_client.post("/api/auth/login",
                                 json={"username": "mo", "password": "Password123!"}
                                 ).status_code == 200

    def test_health_probe_is_not_behind_auth(self, guest_client, monkeypatch, authed):
        monkeypatch.setattr(settings, "require_auth", True)
        assert guest_client.get("/health").status_code == 200

    def test_personal_profile_keeps_anonymous_read(self, guest_client, monkeypatch, authed):
        monkeypatch.setattr(settings, "require_auth", False)
        assert guest_client.get("/api/projects").status_code == 200
