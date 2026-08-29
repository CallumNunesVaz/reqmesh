"""Inter-process advisory file locking.

Shared by the YAML store and the user store so a read-modify-write on the same
file can't interleave between workers. Lives in ``core`` because ``core.auth``
needs it and must not depend on ``services``.
"""
from __future__ import annotations

import contextlib
import hashlib
import tempfile
import threading
import types
from pathlib import Path

fcntl: types.ModuleType | None
try:
    import fcntl  # POSIX advisory locking
except ImportError:  # pragma: no cover - non-POSIX (e.g. Windows)
    fcntl = None

#: Process-wide fallback locks, keyed by the target's absolute path, for
#: platforms without ``fcntl`` (Windows). A single registry so every caller of
#: ``file_lock`` on the same path shares one lock; the registry itself is
#: guarded so two threads resolving a path for the first time race safely.
_fallback_registry: dict[str, threading.Lock] = {}
_fallback_registry_lock = threading.Lock()


def _fallback_lock(target: Path) -> threading.Lock:
    key = str(Path(target).absolute())
    with _fallback_registry_lock:
        lock = _fallback_registry.get(key)
        if lock is None:
            lock = threading.Lock()
            _fallback_registry[key] = lock
        return lock


@contextlib.contextmanager
def file_lock(target: Path):
    """Best-effort exclusive lock guarding a read-modify-write on ``target``.

    The lock file lives in the OS temp dir (keyed by the target's absolute
    path) so it never lands in the project's git tree. Where ``fcntl`` is
    unavailable the lock is a process-wide ``threading.Lock`` keyed by the
    target's absolute path — serialising read-modify-write between threads of
    a single process, though not across processes.
    """
    if fcntl is None:
        with _fallback_lock(target):
            yield
        return
    lock_dir = Path(tempfile.gettempdir()) / "reqmesh-locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    # sha256 purely to name the lock file; not a security boundary, but there
    # is no reason to keep sha1 here and trip every scanner that looks.
    digest = hashlib.sha256(str(Path(target).absolute()).encode()).hexdigest()
    lock_file = lock_dir / f"{digest}.lock"
    with open(lock_file, "w") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
