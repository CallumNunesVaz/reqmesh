"""Regressions for three defects that each broke something in production only.

None of them could fail a test that used the defaults: the config crash needed
an env var written the way the installer writes it, the fsync ordering needed
the syscall sequence inspected, and the presence eviction needed a session
older than its TTL.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import Settings
from app.services.event_bus import EventBus


# ── Settings: the forms an operator's env file actually contains ─────────────

@pytest.fixture()
def clean_env(monkeypatch):
    """Drop RT_ vars inherited from the developer's shell, and the .env file.

    Settings reads `.env` from the CWD, so a stray one would mask the values
    under test.
    """
    for key in list(os.environ):
        if key.startswith("RT_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/tests")
    return monkeypatch


@pytest.mark.parametrize("value", ["", "   ", "\t"])
def test_blank_list_env_var_falls_back_to_default(clean_env, value):
    """A blank value means "not configured", not a parse error.

    Every generated deployment writes these keys unconditionally
    (`RT_CORS_ORIGINS=${RT_CORS_ORIGINS:-}`), and the wizard leaves
    ALLOWED_HOSTS blank for any install without a domain. Before this, that
    raised SettingsError at import and the container crash-looped.
    """
    clean_env.setenv("RT_CORS_ORIGINS", value)
    clean_env.setenv("RT_ALLOWED_HOSTS", value)
    clean_env.setenv("RT_REGISTRATION_DOMAIN_ALLOWLIST", value)

    s = Settings()
    assert s.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]
    assert s.allowed_hosts == ["*"]
    assert s.registration_domain_allowlist == []


def test_comma_separated_list_env_var(clean_env):
    """The form the wizard writes, and the 12-factor convention."""
    clean_env.setenv("RT_ALLOWED_HOSTS", "example.com,192.168.0.5,localhost,127.0.0.1")
    assert Settings().allowed_hosts == ["example.com", "192.168.0.5", "localhost", "127.0.0.1"]


def test_comma_separated_tolerates_spacing_and_trailing_comma(clean_env):
    clean_env.setenv("RT_CORS_ORIGINS", " https://a.example , https://b.example , ")
    assert Settings().cors_origins == ["https://a.example", "https://b.example"]


def test_single_value_without_commas(clean_env):
    clean_env.setenv("RT_ALLOWED_HOSTS", "example.com")
    assert Settings().allowed_hosts == ["example.com"]


def test_json_list_still_parses(clean_env):
    """The documented form must keep working — this is not a replacement."""
    clean_env.setenv("RT_CORS_ORIGINS", '["https://a.example","https://b.example"]')
    assert Settings().cors_origins == ["https://a.example", "https://b.example"]


def test_wildcard_still_reaches_the_startup_guard(clean_env):
    """Both spellings must survive parsing so main.py can refuse them."""
    clean_env.setenv("RT_CORS_ORIGINS", "*")
    assert "*" in Settings().cors_origins
    clean_env.setenv("RT_CORS_ORIGINS", '["*"]')
    assert "*" in Settings().cors_origins


def test_non_list_settings_keep_blank_as_blank(clean_env):
    """The coercion is scoped to list[str]; a blank string field stays blank."""
    clean_env.setenv("RT_SMTP_HOST", "")
    clean_env.setenv("RT_GIT_REMOTE_URL", "")
    s = Settings()
    assert s.smtp_host == ""
    assert s.git_remote_url == ""


# ── Durability: the directory fsync must cover the rename ────────────────────

def test_directory_fsync_happens_after_the_rename(tmp_path, monkeypatch):
    """Fsyncing the directory before os.replace() protects nothing.

    The entry it flushes is the temp file's, which the rename then replaces —
    so the crash window the fsync exists to close stayed open.
    """
    from app.services.yaml_store import YamlStore

    calls: list[str] = []
    real_fsync, real_replace = os.fsync, os.replace

    def spy_fsync(fd):
        import stat
        kind = "dir" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file"
        calls.append(f"fsync:{kind}")
        return real_fsync(fd)

    def spy_replace(src, dst):
        calls.append("replace")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", spy_fsync)
    monkeypatch.setattr(os, "replace", spy_replace)

    store = YamlStore(tmp_path)
    store._write_yaml(tmp_path / "requirements" / "R1.yaml", {"id": "R1", "title": "t"})

    assert calls == ["fsync:file", "replace", "fsync:dir"], calls


def test_written_yaml_is_readable_after_write(tmp_path):
    """The reordering must not disturb the write itself."""
    from app.services.yaml_store import YamlStore

    store = YamlStore(tmp_path)
    path = tmp_path / "requirements" / "R1.yaml"
    store._write_yaml(path, {"id": "R1", "title": "hello"})
    assert store._read_yaml(path)["title"] == "hello"


# ── Presence: prune the disconnected, keep the merely long-lived ─────────────

def _age(bus: EventBus, project: str, client: str, *, minutes: float) -> None:
    stamp = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    bus._presence[project][client]["last_seen"] = stamp


def test_long_lived_session_survives_another_join():
    """The defect: `since` was the join time, so pruning on it evicted anyone
    whose session outlived the TTL — while still connected."""
    bus = EventBus()
    bus.join("p", "alice", "alice", "editor")
    _age(bus, "p", "alice", minutes=60)          # an hour in, still heartbeating
    bus.touch("p", "alice")                       # the SSE loop's 30 s heartbeat

    bus.join("p", "bob", "bob", "editor")
    assert sorted(u["username"] for u in bus.roster("p")) == ["alice", "bob"]


def test_silent_connection_is_pruned():
    """The behaviour that was actually wanted: no heartbeat, no roster entry."""
    bus = EventBus()
    bus.join("p", "ghost", "ghost", "editor")
    bus.join("p", "alice", "alice", "editor")
    _age(bus, "p", "ghost", minutes=10)           # TTL is 5 minutes

    names = [u["username"] for u in bus.roster("p")]
    assert names == ["alice"]


def test_roster_prunes_without_a_join():
    """A ghost must clear on a quiet project too, not only when someone joins."""
    bus = EventBus()
    bus.join("p", "ghost", "ghost", "editor")
    _age(bus, "p", "ghost", minutes=10)
    assert bus.roster("p") == []


def test_touch_keeps_a_connection_alive_indefinitely():
    bus = EventBus()
    bus.join("p", "alice", "alice", "editor")
    for _ in range(20):                            # ten minutes of heartbeats
        _age(bus, "p", "alice", minutes=4)
        bus.touch("p", "alice")
    assert [u["username"] for u in bus.roster("p")] == ["alice"]


def test_touch_on_unknown_client_is_a_no_op():
    bus = EventBus()
    bus.touch("nosuch", "nobody")                  # must not raise or resurrect
    assert bus.roster("nosuch") == []


def test_roster_does_not_leak_internal_bookkeeping():
    """last_seen is internal; the presence payload shape must not change."""
    bus = EventBus()
    bus.join("p", "alice", "alice", "editor")
    assert set(bus.roster("p")[0]) == {"username", "role", "since"}


def test_touch_does_not_broadcast():
    """Idle clients heartbeat every 30 s; broadcasting each one would be
    O(clients^2) cross-traffic on a busy project."""
    bus = EventBus()
    bus.join("p", "alice", "alice", "editor")
    q = bus.subscribe("p")
    bus.touch("p", "alice")
    assert q.empty()
