"""Inter-process advisory file locking.

Shared by the YAML store and the user store so a read-modify-write on the same
file can't interleave between workers. Lives in ``core`` because ``core.auth``
needs it and must not depend on ``services``.
"""
from __future__ import annotations

import contextlib
import hashlib
import tempfile
from pathlib import Path

try:
    import fcntl  # POSIX advisory locking
except ImportError:  # pragma: no cover - non-POSIX (e.g. Windows)
    fcntl = None


@contextlib.contextmanager
def file_lock(target: Path):
    """Best-effort exclusive lock guarding a read-modify-write on ``target``.

    The lock file lives in the OS temp dir (keyed by the target's absolute
    path) so it never lands in the project's git tree. Degrades to a no-op
    where ``fcntl`` is unavailable.
    """
    if fcntl is None:
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
