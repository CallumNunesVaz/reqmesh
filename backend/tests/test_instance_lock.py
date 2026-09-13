"""Inter-process coordination: the lock directory and the single-instance guard.

Two app processes sharing one data root race on YAML writes and the in-memory
collaboration state. The file locks must therefore live on the shared volume,
and an opt-in startup guard refuses a second process outright.
"""
import pytest

from app.core import filelock
from app.core.config import settings

pytest.importorskip("fcntl", reason="advisory locking is POSIX-only")


def test_lock_dir_defaults_to_temp(monkeypatch):
    monkeypatch.setattr(settings, "lock_dir", "")
    assert "reqmesh-locks" in str(filelock._lock_dir())


def test_lock_dir_uses_the_configured_path(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "lock_dir", str(tmp_path / "locks"))
    assert filelock._lock_dir() == tmp_path / "locks"


def test_single_instance_refuses_a_second_holder(tmp_path, monkeypatch):
    import app.main as main_mod

    monkeypatch.setattr(main_mod.settings, "single_instance", True)
    monkeypatch.setenv("RT_STATE_DIR", str(tmp_path / "state"))

    if main_mod._instance_lock_fh is not None:
        main_mod._instance_lock_fh.close()
        main_mod._instance_lock_fh = None

    main_mod._acquire_instance_lock()
    assert main_mod._instance_lock_fh is not None
    try:
        with pytest.raises(RuntimeError, match="Another reqmesh instance"):
            main_mod._acquire_instance_lock()
    finally:
        main_mod._instance_lock_fh.close()
        main_mod._instance_lock_fh = None


def test_single_instance_is_off_by_default(monkeypatch, tmp_path):
    import app.main as main_mod

    monkeypatch.setattr(main_mod.settings, "single_instance", False)
    monkeypatch.setenv("RT_STATE_DIR", str(tmp_path / "state"))
    if main_mod._instance_lock_fh is not None:
        main_mod._instance_lock_fh.close()
        main_mod._instance_lock_fh = None

    main_mod._acquire_instance_lock()
    assert main_mod._instance_lock_fh is None
