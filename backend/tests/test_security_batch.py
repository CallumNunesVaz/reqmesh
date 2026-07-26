"""SEC-4, SEC-6 and SEC-10b/c/d.

* SEC-4 — ``git.remote_url`` decides where a project's whole history is pushed,
  yet any maintainer could set it to an arbitrary host (exfiltration, and a
  blind SSRF probe). Remote URLs were also logged verbatim, so
  ``https://user:token@host`` landed in the log files.
* SEC-6 — ``Reference.path`` was joined onto the server's cwd with no
  confinement. ``Path(root) / "/etc/shadow"`` discards the root entirely, so
  the freshness endpoint reported existence and a content-hash match for
  arbitrary host files.
* SEC-10b — spreadsheet exports wrote a leading ``=`` as a live formula.
* SEC-10c — ReqIF import accepted a DTD, so internal entity expansion applied.
* SEC-10d — the scanner's rglob fallback followed symlinks out of the tree.
"""
import pytest

from app.core import auth
from app.core.config import settings
from tests.conftest import make_req


class TestGitRemoteIsAdminGated:
    """SEC-4 — the write gate, not just who can read the setting back."""

    @pytest.fixture()
    def http_cookies(self, monkeypatch):
        monkeypatch.setattr(settings, "cookie_secure", False)
        monkeypatch.setattr(settings, "require_auth", False)

    def _login(self, client, name, role):
        auth.register_user(name, "Password123!", role)
        res = client.post("/api/auth/login", json={"username": name, "password": "Password123!"})
        assert res.status_code == 200, res.text
        return res.json()["csrf_token"]

    def test_maintainer_cannot_change_the_remote(self, guest_client, http_cookies):
        csrf = self._login(guest_client, "adm", "admin")
        guest_client.post("/api/projects", json={"id": "p", "name": "P"},
                          headers={"X-CSRF-Token": csrf})
        guest_client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})

        csrf = self._login(guest_client, "mo", "maintainer")
        res = guest_client.patch("/api/projects/p",
                                 json={"git": {"remote_url": "https://attacker.test/x.git"}},
                                 headers={"X-CSRF-Token": csrf})
        assert res.status_code == 403, res.text

    def test_admin_can_change_it(self, guest_client, http_cookies):
        csrf = self._login(guest_client, "adm", "admin")
        guest_client.post("/api/projects", json={"id": "p", "name": "P"},
                          headers={"X-CSRF-Token": csrf})
        res = guest_client.patch("/api/projects/p",
                                 json={"git": {"remote_url": "https://ok.test/x.git"}},
                                 headers={"X-CSRF-Token": csrf})
        assert res.status_code == 200, res.text

    def test_dangerous_schemes_are_refused(self, guest_client, http_cookies):
        csrf = self._login(guest_client, "adm", "admin")
        guest_client.post("/api/projects", json={"id": "p", "name": "P"},
                          headers={"X-CSRF-Token": csrf})
        for bad in ("file:///etc/passwd", "http://169.254.169.254/x.git", "ext::sh -c whoami"):
            res = guest_client.patch("/api/projects/p", json={"git": {"remote_url": bad}},
                                     headers={"X-CSRF-Token": csrf})
            assert res.status_code == 400, f"{bad} -> {res.status_code}"

    def test_maintainer_may_still_set_other_git_fields(self, guest_client, http_cookies):
        """The gate is on the remote only — identity/cadence stay maintainer-tier."""
        csrf = self._login(guest_client, "adm", "admin")
        guest_client.post("/api/projects", json={"id": "p", "name": "P"},
                          headers={"X-CSRF-Token": csrf})
        guest_client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})

        csrf = self._login(guest_client, "mo", "maintainer")
        res = guest_client.patch("/api/projects/p",
                                 json={"git": {"user_name": "CI", "push_interval_minutes": 5}},
                                 headers={"X-CSRF-Token": csrf})
        assert res.status_code == 200, res.text


class TestCredentialsAreRedactedInLogs:
    def test_userinfo_is_stripped(self):
        from app.services.git_service import redact_url
        out = redact_url("git push failed: https://alice:ghp_secret@github.com/o/r.git denied")
        assert "ghp_secret" not in out and "alice" not in out
        assert "https://***@github.com/o/r.git" in out

    def test_plain_urls_are_untouched(self):
        from app.services.git_service import redact_url
        url = "https://github.com/owner/repo.git"
        assert redact_url(url) == url

    def test_handles_empty_and_multiline(self):
        from app.services.git_service import redact_url
        assert redact_url("") == ""
        multi = "line1 ssh://u:p@host/r\nline2 https://a:b@h/r"
        assert "u:p@" not in redact_url(multi) and "a:b@" not in redact_url(multi)


class TestReferencePathsAreConfined:
    """SEC-6 — the oracle."""

    def test_absolute_path_is_reported_outside_not_probed(self, client, project, tmp_path):
        from app.core.dependencies import get_store
        from app.services.references import check_reference_freshness
        secret = tmp_path / "secret.txt"
        secret.write_text("classified")

        make_req(client, project, "REQ-001")
        store = get_store(project)
        store.update_requirement("REQ-001", {"references": [{"path": str(secret), "kind": "impl"}]})

        out = check_reference_freshness(store, store.root)
        assert [r["status"] for r in out] == ["outside_project"]

    def test_dotdot_escape_is_blocked(self, client, project):
        from app.core.dependencies import get_store
        from app.services.references import check_reference_freshness
        make_req(client, project, "REQ-001")
        store = get_store(project)
        store.update_requirement("REQ-001", {
            "references": [{"path": "../../../../etc/passwd", "kind": "impl"}]})
        out = check_reference_freshness(store, store.root)
        assert [r["status"] for r in out] == ["outside_project"]

    def test_a_real_in_project_reference_still_works(self, client, project):
        from app.core.dependencies import get_store
        from app.services.references import check_reference_freshness
        from app.services.code_scan import compute_sha
        make_req(client, project, "REQ-001")
        store = get_store(project)
        impl = store.root / "impl.py"
        impl.write_text("print('x')\n")
        # A reference with no stored hash yields no row at all (pre-existing
        # behaviour), so record one to exercise the compare path.
        store.update_requirement("REQ-001", {
            "references": [{"path": "impl.py", "kind": "impl", "sha256": compute_sha(impl)}]})

        out = check_reference_freshness(store, store.root)
        assert [r["status"] for r in out] == ["ok"], out

        impl.write_text("print('changed')\n")
        out = check_reference_freshness(store, store.root)
        assert [r["status"] for r in out] == ["changed"], out


class TestSpreadsheetFormulaInjection:
    @pytest.mark.parametrize("payload", ["=cmd|'/c calc'!A0", "+1+1", "-1+1", "@SUM(A1)"])
    def test_csv_export_neutralises_formula_leads(self, client, project, payload):
        from app.core.dependencies import get_store
        from app.services.table_io import export_table
        make_req(client, project, "REQ-001", name=payload)
        csv_text = export_table(get_store(project), "csv")
        assert f'"{payload}"' not in csv_text, "value exported as a live formula"
        assert f"\"'{payload}\"" in csv_text

    def test_ordinary_text_is_unchanged(self, client, project):
        from app.core.dependencies import get_store
        from app.services.table_io import export_table
        make_req(client, project, "REQ-001", name="Cabin pressurisation")
        assert "Cabin pressurisation" in export_table(get_store(project), "csv")


class TestReqIfRejectsDtd:
    def test_entity_expansion_bomb_is_refused(self):
        from app.services.reqif_import import parse_reqif, ReqIFParseError
        bomb = (
            '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
            '<!ENTITY lol2 "&lol;&lol;&lol;">]>'
            '<REQ-IF><SPEC-OBJECTS>&lol2;</SPEC-OBJECTS></REQ-IF>'
        )
        with pytest.raises(ReqIFParseError) as exc:
            parse_reqif(bomb)
        assert "doctype" in str(exc.value).lower()

    def test_ordinary_reqif_without_a_dtd_still_parses(self):
        from app.services.reqif_import import parse_reqif, ReqIFParseError
        doc = '<?xml version="1.0"?><REQ-IF><SPEC-OBJECTS></SPEC-OBJECTS></REQ-IF>'
        # No SPEC-OBJECTs is its own error; the point is it isn't the DTD one.
        try:
            parse_reqif(doc)
        except ReqIFParseError as exc:
            assert "doctype" not in str(exc).lower()


class TestScannerSkipsSymlinks:
    def test_symlink_out_of_tree_is_not_scanned(self, tmp_path):
        from app.services.code_scan import _list_files
        root = tmp_path / "proj"; root.mkdir()
        (root / "real.py").write_text("# [impl->REQ-001]\n")
        outside = tmp_path / "outside.py"; outside.write_text("secret\n")
        try:
            (root / "link.py").symlink_to(outside)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unsupported here")

        names = {p.name for p in _list_files(root)}
        assert "real.py" in names
        assert "link.py" not in names, "symlink escaped the scan root"
