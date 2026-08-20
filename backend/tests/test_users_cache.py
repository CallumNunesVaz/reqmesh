"""The users.yaml read cache.

``load_users()`` used to open and round-trip-parse the whole account file on
every authenticated request — linear in the number of accounts, before any
application work. It is now an mtime+size-keyed cache, invalidated on save and
re-validated on every read so an out-of-band edit is picked up without a
restart. These tests pin the caching, the invalidation, and the deep copy that
keeps one request's half-finished mutation out of another's view.
"""
import os

from app.core import auth


def test_two_loads_parse_the_file_once(workspace, monkeypatch):
    auth.save_users({"alice": {"username": "alice", "role": "admin"}})

    real_yaml = auth.YAML
    load_calls = []

    class CountingYAML:
        def __init__(self, *args, **kwargs):
            self._inner = real_yaml(*args, **kwargs)

        def load(self, f):
            load_calls.append(1)
            return self._inner.load(f)

    monkeypatch.setattr(auth, "YAML", CountingYAML)

    first = auth.load_users()
    second = auth.load_users()

    assert first == second
    assert len(load_calls) == 1


def test_save_users_then_load_returns_new_content(workspace):
    auth.save_users({"admin": {"username": "admin", "role": "admin"}})
    assert auth.load_users() == {"admin": {"username": "admin", "role": "admin"}}

    auth.save_users({"admin": {"username": "admin", "role": "admin"},
                     "bob": {"username": "bob", "role": "contributor"}})
    assert "bob" in auth.load_users()


def test_out_of_band_edit_is_picked_up(workspace):
    auth.save_users({"admin": {"username": "admin", "role": "admin"}})
    assert auth.load_users()["admin"]["role"] == "admin"  # fill the cache

    auth.USERS_FILE.write_text("hacker:\n  username: hacker\n  role: admin\n")
    # Force the mtime to differ even on filesystems with coarse resolution, so
    # the signature must change regardless of content size.
    st = auth.USERS_FILE.stat()
    os.utime(auth.USERS_FILE, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))

    users = auth.load_users()
    assert "hacker" in users
    assert "admin" not in users


def test_mutating_the_result_does_not_poison_the_cache(workspace):
    auth.save_users({"alice": {"username": "alice", "role": "contributor"}})

    first = auth.load_users()
    first["alice"]["role"] = "admin"
    first["intruder"] = {"username": "intruder", "role": "admin"}

    second = auth.load_users()
    assert second["alice"]["role"] == "contributor"
    assert "intruder" not in second


def test_authenticate_change_password_authenticate_cycle(workspace):
    auth.register_user("carol", "OldPassword123!", "contributor")
    assert auth.authenticate("carol", "OldPassword123!")["status"] == "ok"

    assert auth.set_user_password("carol", "NewPassword456!")

    assert auth.authenticate("carol", "NewPassword456!")["status"] == "ok"
    assert auth.authenticate("carol", "OldPassword123!")["status"] == "invalid"
