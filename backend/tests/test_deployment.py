import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.services.git_service import ensure_remote, push_to_remote, is_repo


def test_is_repo_true(tmp_path):
    import subprocess
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    assert is_repo(tmp_path) is True


def test_is_repo_false(tmp_path):
    assert is_repo(tmp_path) is False


def test_ensure_remote_adds_new_remote(tmp_path, monkeypatch):
    import subprocess
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=str(tmp_path))
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(tmp_path))
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=str(tmp_path), capture_output=True)

    result = ensure_remote(tmp_path, "git@example.com:org/repo.git")
    assert result is True

    r = subprocess.run(["git", "remote", "get-url", "origin"], cwd=str(tmp_path), capture_output=True, text=True)
    assert r.stdout.strip() == "git@example.com:org/repo.git"


def test_ensure_remote_updates_existing(tmp_path, monkeypatch):
    import subprocess
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=str(tmp_path))
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(tmp_path))
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", "git@old:org/repo.git"], cwd=str(tmp_path), capture_output=True)

    result = ensure_remote(tmp_path, "git@new:org/repo.git")
    assert result is True

    r = subprocess.run(["git", "remote", "get-url", "origin"], cwd=str(tmp_path), capture_output=True, text=True)
    assert r.stdout.strip() == "git@new:org/repo.git"


def test_push_to_remote_skips_offline(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "offline_mode", True)
    monkeypatch.setattr(settings, "git_remote_url", "git@example.com:org/repo.git")
    result = push_to_remote(Path("/tmp"))
    assert result is False


def test_push_to_remote_skips_no_url(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "git_remote_url", "")
    result = push_to_remote(Path("/tmp"))
    assert result is False


def test_email_service_not_configured():
    from app.services.email_service import _is_configured
    assert _is_configured() is False


def test_email_send_skips_when_not_configured():
    from app.services.email_service import _send_email
    _send_email("test@test.com", "Subject", "<p>Body</p>")


def test_offline_mode_blocks_send(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "offline_mode", True)
    from app.services.email_service import _is_configured
    assert _is_configured() is False
