"""Regression tests for the cookie-session + CSRF migration.

Auth moved from a localStorage bearer token to an HttpOnly cookie, with a
double-submit CSRF token. These tests pin the behaviours that were wrong or
unenforced in the first cut:

* CSRF was keyed off the *csrftoken* cookie, so a request carrying a valid
  session cookie but no csrftoken skipped the check and was still authenticated.
* Logout cleared client state only; the HttpOnly cookie survived, so whoami()
  restored the session on the next load.
* ``get_project`` read the Authorization header to decide whether to expose git
  settings — which the UI stopped sending, silently hiding them from maintainers.
* ``_client_ip`` trusted X-Forwarded-For whenever the peer was loopback (the
  normal reverse-proxy case), letting a caller mint a fresh rate-limit bucket
  per request and walk through the login limit.

They use ``guest_client`` (no dependency overrides) so the real guards,
middleware and cookie plumbing all run.
"""
import pytest

from app.core import auth
from app.core.config import settings


@pytest.fixture()
def http_cookies(monkeypatch):
    """TestClient speaks http://testserver, so Secure cookies would be dropped."""
    monkeypatch.setattr(settings, "cookie_secure", False)
    monkeypatch.setattr(settings, "require_auth", False)


def _login(client, username="mo", password="Password123!", role="maintainer") -> str:
    auth.register_user(username, password, role)
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["csrf_token"]


def _project(client, csrf, pid="p"):
    res = client.post("/api/projects", json={"id": pid, "name": "P"},
                      headers={"X-CSRF-Token": csrf})
    assert res.status_code == 201, res.text
    return pid


class TestCsrfEnforcement:
    def test_mutation_without_csrf_header_is_rejected(self, guest_client, http_cookies):
        csrf = _login(guest_client)
        _project(guest_client, csrf)
        res = guest_client.post("/api/projects/p/requirements", json={"id": "R1", "name": "x"})
        assert res.status_code == 403
        assert "csrf" in res.json()["detail"].lower()

    def test_mutation_with_matching_csrf_header_succeeds(self, guest_client, http_cookies):
        csrf = _login(guest_client)
        _project(guest_client, csrf)
        res = guest_client.post("/api/projects/p/requirements",
                                json={"id": "R1", "name": "x"},
                                headers={"X-CSRF-Token": csrf})
        assert res.status_code == 201, res.text

    def test_mismatched_csrf_header_is_rejected(self, guest_client, http_cookies):
        csrf = _login(guest_client)
        _project(guest_client, csrf)
        res = guest_client.post("/api/projects/p/requirements",
                                json={"id": "R1", "name": "x"},
                                headers={"X-CSRF-Token": "not-the-token"})
        assert res.status_code == 403

    def test_session_cookie_without_csrf_cookie_is_still_checked(self, guest_client, http_cookies):
        """The original bypass: no csrftoken cookie meant no CSRF check at all,
        while the session cookie still authenticated the request."""
        csrf = _login(guest_client)
        _project(guest_client, csrf)
        del guest_client.cookies["csrftoken"]
        res = guest_client.post("/api/projects/p/requirements", json={"id": "R2", "name": "y"})
        assert res.status_code == 403, "CSRF check skipped when csrftoken cookie absent"

    def test_get_requests_are_not_blocked(self, guest_client, http_cookies):
        csrf = _login(guest_client)
        _project(guest_client, csrf)
        assert guest_client.get("/api/projects/p/requirements").status_code == 200

    def test_login_itself_is_exempt(self, guest_client, http_cookies):
        auth.register_user("mo", "Password123!", "maintainer")
        res = guest_client.post("/api/auth/login",
                                json={"username": "mo", "password": "Password123!"})
        assert res.status_code == 200


class TestLogoutEndsTheServerSession:
    def test_logout_clears_cookies_and_session(self, guest_client, http_cookies):
        csrf = _login(guest_client)
        assert guest_client.get("/api/auth/whoami").json()["role"] == "maintainer"

        res = guest_client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
        assert res.status_code == 200

        assert "token" not in guest_client.cookies, "session cookie survived logout"
        assert guest_client.get("/api/auth/whoami").json()["role"] == "guest"


class TestGitSettingsVisibility:
    def test_maintainer_sees_git_via_cookie_session(self, guest_client, http_cookies):
        csrf = _login(guest_client)
        _project(guest_client, csrf)
        guest_client.patch("/api/projects/p",
                           json={"git": {"remote_url": "https://tok@example.test/r.git"}},
                           headers={"X-CSRF-Token": csrf})
        assert "git" in guest_client.get("/api/projects/p").json()

    def test_anonymous_and_contributor_do_not(self, guest_client, http_cookies):
        csrf = _login(guest_client)
        _project(guest_client, csrf)
        guest_client.patch("/api/projects/p",
                           json={"git": {"remote_url": "https://tok@example.test/r.git"}},
                           headers={"X-CSRF-Token": csrf})
        guest_client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
        assert "git" not in guest_client.get("/api/projects/p").json()

        _login(guest_client, "cont", "Password123!", "contributor")
        assert "git" not in guest_client.get("/api/projects/p").json()


class TestClientIpCannotBeSpoofed:
    """X-Forwarded-For is attacker-supplied; honouring it unconditionally let a
    caller rotate the header for a fresh rate-limit bucket every request."""

    class _Req:
        def __init__(self, peer, xff=None):
            self.client = type("C", (), {"host": peer})()
            self.headers = {"X-Forwarded-For": xff} if xff else {}

    def test_untrusted_peer_header_is_ignored(self):
        from app.core.rate_limit import _client_ip
        assert _client_ip(self._Req("203.0.113.9", "1.2.3.4")) == "203.0.113.9"

    def test_trusted_proxy_header_is_honoured(self):
        from app.core.rate_limit import _client_ip
        assert _client_ip(self._Req("127.0.0.1", "198.51.100.7")) == "198.51.100.7"

    def test_prepended_spoof_is_stripped(self):
        """A client can prepend entries but cannot append them, so the
        right-most untrusted hop is the real caller."""
        from app.core.rate_limit import _client_ip
        assert _client_ip(self._Req("127.0.0.1", "9.9.9.9, 198.51.100.7")) == "198.51.100.7"

    def test_no_header_falls_back_to_peer(self):
        from app.core.rate_limit import _client_ip
        assert _client_ip(self._Req("127.0.0.1")) == "127.0.0.1"

    def test_login_limit_not_bypassable_by_rotating_the_header(self, guest_client, http_cookies, monkeypatch):
        """Same untrusted peer + rotating XFF must share one bucket."""
        monkeypatch.setattr(settings, "lockout_max_attempts", 0)  # isolate the IP limit
        seen = set()
        from app.core.rate_limit import _client_ip
        for i in range(10):
            seen.add(_client_ip(self._Req("203.0.113.5", f"10.0.0.{i}")))
        assert seen == {"203.0.113.5"}, f"rotating XFF produced {len(seen)} buckets"
