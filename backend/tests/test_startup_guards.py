"""Startup-time refusals and the bootstrap-credential lifecycle."""

import importlib
import sys

import pytest

from app.core import auth


# ── CORS ─────────────────────────────────────────────────────────────────────

class TestCorsWildcardRefused:
    """Sessions are cookie-based, so credentials are always sent. A wildcard
    origin would let any site make authenticated requests — and Starlette
    silently degrades the wildcard to an origin echo in this combination, which
    reflects *every* origin rather than refusing as the spec requires.
    """

    def _reimport_main(self, monkeypatch, origins):
        from app.core import config
        monkeypatch.setattr(config.settings, "cors_origins", origins)
        sys.modules.pop("app.main", None)
        try:
            importlib.import_module("app.main")
        finally:
            sys.modules.pop("app.main", None)
            importlib.import_module("app.main")

    def test_wildcard_origin_refuses_to_start(self, monkeypatch):
        with pytest.raises(RuntimeError, match="RT_CORS_ORIGINS"):
            self._reimport_main(monkeypatch, ["*"])

    def test_wildcard_among_real_origins_also_refuses(self, monkeypatch):
        with pytest.raises(RuntimeError, match="RT_CORS_ORIGINS"):
            self._reimport_main(monkeypatch, ["https://reqmesh.example", "*"])

    def test_explicit_allowlist_starts_normally(self, monkeypatch):
        self._reimport_main(monkeypatch, ["https://reqmesh.example"])

    def test_empty_allowlist_starts_normally(self, monkeypatch):
        """Single-origin deployments need no CORS at all."""
        self._reimport_main(monkeypatch, [])


# ── Bootstrap admin credential ───────────────────────────────────────────────

class TestInitialAdminFile:
    """The generated password is written to a 0600 file rather than the log.
    It must survive until the admin has actually used and rotated it.
    """

    @pytest.fixture
    def bootstrapped(self, tmp_path, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "data_root", str(tmp_path))
        monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "users.yaml")
        monkeypatch.delenv("RT_ADMIN_PASSWORD", raising=False)
        auth.load_users()
        pw_file = tmp_path / ".initial-admin"
        return pw_file, pw_file.read_text().strip()

    def test_password_goes_to_a_private_file_not_the_log(self, bootstrapped):
        pw_file, password = bootstrapped
        assert password
        assert pw_file.stat().st_mode & 0o777 == 0o600

    def test_another_users_login_does_not_destroy_it(self, bootstrapped):
        """Deleting on *any* successful login means a self-registered user
        logging in first burns the credential before the operator reads it,
        locking them out of the admin account with no reset path."""
        pw_file, _ = bootstrapped
        auth.register_user("bob", "correct-horse-battery", "contributor")

        assert auth.authenticate("bob", "correct-horse-battery")["status"] == "ok"
        assert pw_file.exists()

    def test_survives_the_admins_login_until_the_password_is_rotated(self, bootstrapped):
        pw_file, password = bootstrapped

        result = auth.authenticate("admin", password)
        assert result["status"] == "ok"
        assert result["password_change_required"] is True
        assert pw_file.exists(), "credential burned before rotation"

    def test_is_deleted_once_the_admin_has_rotated(self, bootstrapped):
        pw_file, password = bootstrapped
        auth.authenticate("admin", password)

        auth.set_user_password("admin", "a-new-strong-password")
        assert auth.authenticate("admin", "a-new-strong-password")["status"] == "ok"
        assert not pw_file.exists()

    def test_no_file_when_the_operator_supplied_a_password(self, tmp_path, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "data_root", str(tmp_path))
        monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "users.yaml")
        monkeypatch.setenv("RT_ADMIN_PASSWORD", "operator-chosen-password")

        auth.load_users()
        assert not (tmp_path / ".initial-admin").exists()
