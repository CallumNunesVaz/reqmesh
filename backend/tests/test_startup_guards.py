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


# ── Multiple workers ─────────────────────────────────────────────────────────

class TestMultiWorkerRefused:
    """Every piece of collaboration state is per-process, so uvicorn must never
    be allowed to spawn more than one worker. Detected at import time — uvicorn
    spawns children via ``multiprocessing`` ``spawn``, each of which re-imports
    ``app.main`` — so the refusal fires in every worker.
    """

    def _reimport_main(self, monkeypatch, argv, web_concurrency=None):
        monkeypatch.setattr(sys, "argv", argv)
        if web_concurrency is None:
            monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
        else:
            monkeypatch.setenv("WEB_CONCURRENCY", web_concurrency)
        sys.modules.pop("app.main", None)
        try:
            importlib.import_module("app.main")
        finally:
            sys.modules.pop("app.main", None)
            importlib.import_module("app.main")

    def test_workers_two_refuses_to_start(self, monkeypatch):
        with pytest.raises(RuntimeError, match="reqmesh does not support multiple workers"):
            self._reimport_main(monkeypatch, ["reqmesh", "--workers", "2"])

    def test_workers_equals_two_refuses_to_start(self, monkeypatch):
        with pytest.raises(RuntimeError, match="reqmesh does not support multiple workers"):
            self._reimport_main(monkeypatch, ["reqmesh", "--workers=2"])

    def test_short_w_four_refuses_to_start(self, monkeypatch):
        with pytest.raises(RuntimeError, match="reqmesh does not support multiple workers"):
            self._reimport_main(monkeypatch, ["reqmesh", "-w", "4"])

    def test_single_worker_boots(self, monkeypatch):
        self._reimport_main(monkeypatch, ["reqmesh", "--workers", "1"])

    def test_no_worker_flag_boots(self, monkeypatch):
        self._reimport_main(monkeypatch, ["reqmesh"])

    def test_web_concurrency_three_refuses_to_start(self, monkeypatch):
        with pytest.raises(RuntimeError, match="reqmesh does not support multiple workers"):
            self._reimport_main(monkeypatch, ["reqmesh"], web_concurrency="3")

    def test_web_concurrency_one_boots(self, monkeypatch):
        self._reimport_main(monkeypatch, ["reqmesh"], web_concurrency="1")

    def test_argv_workers_flag_wins_over_web_concurrency(self, monkeypatch):
        self._reimport_main(monkeypatch, ["reqmesh", "--workers", "1"], web_concurrency="8")

    def test_unparseable_web_concurrency_is_ignored(self, monkeypatch):
        self._reimport_main(monkeypatch, ["reqmesh"], web_concurrency="banana")


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


# ── State dir must not live inside the data root ─────────────────────────────

class TestStateDirNotInsideDataRoot:
    """`users.yaml` inside a project directory would be committed and pushed by
    git auto-commit, which runs `git add -A` in project roots. Password hashes
    on a remote cannot be recalled, so this refuses to start rather than warn.
    """

    def _start(self, monkeypatch, state_dir, data_root):
        from fastapi.testclient import TestClient

        from app.core import config
        from app.main import app

        monkeypatch.setattr(config.settings, "data_root", str(data_root))
        monkeypatch.setattr(auth, "USERS_FILE", state_dir / "users.yaml")
        with TestClient(app):
            pass

    def test_state_dir_equal_to_the_data_root_refuses(self, tmp_path, monkeypatch):
        both = tmp_path / "data"
        both.mkdir()
        with pytest.raises(RuntimeError, match="RT_STATE_DIR"):
            self._start(monkeypatch, both, both)

    def test_state_dir_inside_the_data_root_refuses(self, tmp_path, monkeypatch):
        data = tmp_path / "projects"
        state = data / ".reqmesh"
        state.mkdir(parents=True)
        with pytest.raises(RuntimeError, match="RT_STATE_DIR"):
            self._start(monkeypatch, state, data)

    def test_the_default_layout_starts_normally(self, tmp_path, monkeypatch):
        """The shipped bare-metal default is the *inverse* nesting — the data
        root sits inside the state dir — and it is safe, because a git repo is
        only ever one project directory. This test exists so nobody later
        "simplifies" the guard into a disjointness check and breaks every
        default install.
        """
        state = tmp_path / ".reqmesh"
        data = state / "projects"
        data.mkdir(parents=True)
        self._start(monkeypatch, state, data)

    def test_fully_separate_paths_start_normally(self, tmp_path, monkeypatch):
        state = tmp_path / "state"
        data = tmp_path / "projects"
        state.mkdir()
        data.mkdir()
        self._start(monkeypatch, state, data)


class TestUsersFileIsPrivate:
    """Password hashes. The mode must not depend on the process umask."""

    def test_the_bootstrap_users_file_is_owner_only(self, workspace):
        auth.load_users()  # seeds the admin account on first read
        assert auth.USERS_FILE.stat().st_mode & 0o777 == 0o600

    def test_it_stays_owner_only_after_a_write(self, workspace):
        auth.register_user("modecheck", "Password123!", "contributor")
        assert auth.USERS_FILE.stat().st_mode & 0o777 == 0o600
