"""Per-project git SSH deploy keys: generate, read, rotate, delete.

The private key is written by ``ssh-keygen`` and must never cross the network —
these tests assert against raw response text, not parsed fields, so a stray
private-key byte cannot hide behind a JSON decoder.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from app.core.config import settings
from app.services import git_keys, git_service


# ── helpers ───────────────────────────────────────────────────────────────────

def _key_dir(project: str) -> Path:
    return Path(settings.data_root) / ".ssh" / project


def _private_bytes(project: str) -> bytes:
    return (_key_dir(project) / "id_ed25519").read_bytes()


def _generate(client, project: str):
    res = client.post(f"/api/projects/{project}/git/key")
    assert res.status_code == 201, res.text
    return res


# ── generation ────────────────────────────────────────────────────────────────

def test_generate_returns_public_key_and_real_fingerprint(client, project):
    res = _generate(client, project)
    body = res.json()

    assert body["public_key"].startswith("ssh-ed25519 ")
    assert body["type"] == "ed25519"
    assert body["fingerprint"].startswith("SHA256:")

    # The fingerprint must be the real `ssh-keygen -lf` output, recomputed
    # independently against the on-disk public key — the thing the operator
    # matches against the value GitHub shows.
    pub_path = _key_dir(project) / "id_ed25519.pub"
    probe = subprocess.run(
        ["ssh-keygen", "-lf", str(pub_path)],
        capture_output=True, text=True, check=True,
    )
    assert body["fingerprint"] in probe.stdout


def test_key_permissions_are_private(client, project):
    _generate(client, project)
    key_dir = _key_dir(project)
    private = key_dir / "id_ed25519"
    assert stat.S_IMODE(private.stat().st_mode) == 0o600
    assert stat.S_IMODE(key_dir.stat().st_mode) == 0o700


def test_private_key_never_appears_in_any_response(client, project):
    _generate(client, project)
    private_bytes = _private_bytes(project)

    # GET, POST (conflict), rotate, delete — assert against the raw text so a
    # parsed-field assertion cannot miss a leaked key.
    for resp in (
        client.get(f"/api/projects/{project}/git/key"),
        client.post(f"/api/projects/{project}/git/key"),
        client.post(f"/api/projects/{project}/git/key/rotate"),
        client.delete(f"/api/projects/{project}/git/key"),
    ):
        assert private_bytes not in resp.content
        assert b"PRIVATE KEY" not in resp.content


def test_second_generate_is_409_and_key_unchanged(client, project):
    _generate(client, project)
    before = _private_bytes(project)

    res = client.post(f"/api/projects/{project}/git/key")
    assert res.status_code == 409

    assert _private_bytes(project) == before


# ── rotate ────────────────────────────────────────────────────────────────────

def test_rotate_replaces_key_and_discards_old_private(client, project):
    first = _generate(client, project).json()
    old_private = _private_bytes(project)
    old_fingerprint = first["fingerprint"]

    res = client.post(f"/api/projects/{project}/git/key/rotate")
    assert res.status_code == 200, res.text
    new = res.json()

    assert new["fingerprint"] != old_fingerprint
    assert new["fingerprint"].startswith("SHA256:")
    # The old private key must not still be on disk.
    assert _private_bytes(project) != old_private


def test_a_failed_rotation_leaves_the_existing_key_intact(client, project, monkeypatch):
    """Rotation must not be destructive-then-hopeful.

    Deleting the old key before generating the new one is the obvious order and
    the wrong one: a generation that fails afterwards leaves the project with no
    key at all and a broken push, which is worse than the stale key it had.
    """
    _generate(client, project)
    before = _private_bytes(project)

    def boom(_args):
        raise RuntimeError("ssh-keygen exploded")

    monkeypatch.setattr(git_keys, "_run_ssh_keygen", boom)

    res = client.post(f"/api/projects/{project}/git/key/rotate")
    assert res.status_code >= 500

    # The original key survived untouched, and no scratch directory was left.
    assert _private_bytes(project) == before
    leftovers = [p.name for p in _key_dir(project).parent.iterdir() if "rotating" in p.name]
    assert leftovers == [], leftovers


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_then_get_is_404(client, project):
    _generate(client, project)

    res = client.delete(f"/api/projects/{project}/git/key")
    assert res.status_code == 204
    assert res.content == b""

    assert client.get(f"/api/projects/{project}/git/key").status_code == 404


def test_get_without_key_is_404(client, project):
    assert client.get(f"/api/projects/{project}/git/key").status_code == 404


# ── authorisation ─────────────────────────────────────────────────────────────

def test_every_route_rejects_maintainer_and_guest(maintainer_client, guest_client):
    """All four routes are admin-only, matching the other admin git routes."""
    for cl in (maintainer_client, guest_client):
        assert cl.get("/api/projects/demo/git/key").status_code == 403
        assert cl.post("/api/projects/demo/git/key").status_code == 403
        assert cl.post("/api/projects/demo/git/key/rotate").status_code == 403
        assert cl.delete("/api/projects/demo/git/key").status_code == 403


# ── .ssh is invisible to project listing ──────────────────────────────────────

def test_dot_ssh_is_not_listed_as_a_project(client, project):
    _generate(client, project)

    res = client.get("/api/projects")
    assert res.status_code == 200
    ids = [p["id"] for p in res.json()]
    assert ".ssh" not in ids
    assert project in ids


# ── the key is outside every git working tree ─────────────────────────────────

def test_generating_a_key_does_not_dirty_the_repo(client, project):
    client.post(f"/api/projects/{project}/git/init")

    root = Path(settings.data_root) / project
    subprocess.run(["git", "add", "-A"], cwd=str(root), capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "initial"],
        cwd=str(root), capture_output=True, text=True,
    )

    # The key directory is a sibling of the project, never inside it: a key
    # that lives under the working tree would be picked up by an auto-commit
    # and pushed to the remote.
    assert _key_dir(project).resolve().parent == (Path(settings.data_root) / ".ssh").resolve()
    assert not str(_key_dir(project).resolve()).startswith(str(root.resolve()) + os.sep)

    _generate(client, project)

    # git must never see the key files (the audit-trail entry for generation is
    # unrelated and, like every entity write, is versioned by autocommit).
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True, text=True,
    ).stdout
    assert "id_ed25519" not in status
    assert ".ssh" not in status


# ── _ssh_env wiring ───────────────────────────────────────────────────────────

_SSH_URL = "git@github.com:org/repo.git"
_BASE_COMMAND = "ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -o BatchMode=yes"


def test_ssh_env_uses_key_when_present(client, project):
    _generate(client, project)
    root = Path(settings.data_root) / project

    env = git_service._ssh_env(_SSH_URL, root)
    cmd = env["GIT_SSH_COMMAND"]
    assert "-i " in cmd
    assert "IdentitiesOnly=yes" in cmd
    assert "-o BatchMode=yes" in cmd


def test_ssh_env_is_byte_identical_without_key(client, project):
    root = Path(settings.data_root) / project

    env = git_service._ssh_env(_SSH_URL, root)
    assert env["GIT_SSH_COMMAND"] == _BASE_COMMAND


def test_ssh_env_ignores_non_ssh_remotes(client, project):
    root = Path(settings.data_root) / project
    assert "GIT_SSH_COMMAND" not in git_service._ssh_env("https://github.com/org/repo.git", root)


# ── missing ssh-keygen ────────────────────────────────────────────────────────

def test_missing_ssh_keygen_returns_503(client, project, monkeypatch):
    monkeypatch.setattr(git_keys, "find_ssh_keygen", lambda: None)

    res = client.post(f"/api/projects/{project}/git/key")
    assert res.status_code == 503
    assert "openssh-client" in res.text
