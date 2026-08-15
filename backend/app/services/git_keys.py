"""Per-project git SSH deploy keys.

A GitHub/GitLab deploy key may be attached to exactly one repository, so a
single instance-wide key breaks the moment two projects push to two different
repos. Each project therefore gets its own ed25519 keypair, generated on demand
and stored *outside* the project's working tree (``.ssh`` is a sibling of the
project directory) so no auto-commit can ever pick the private half up.

The private key is written by ``ssh-keygen`` and read only by ``ssh`` itself.
Nothing in this module returns it; the routes hand back the public key and its
fingerprint, never the private bytes.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

KEY_TYPE = "ed25519"
PRIVATE_KEY_NAME = "id_ed25519"
PUBLIC_KEY_NAME = "id_ed25519.pub"


class SshKeygenNotFoundError(RuntimeError):
    """``ssh-keygen`` is not on PATH (only ``openssh-client`` provides it)."""


def key_dir_for_root(project_root: Path) -> Path:
    """The per-project key directory, a sibling of the project directory.

    ``<data_root>/.ssh/<project_id>`` — under the data root (the only volume
    that persists in production) but *outside* every git working tree, so a key
    can never be picked up by an auto-commit and pushed to the remote.
    """
    root = Path(project_root)
    return root.parent / ".ssh" / root.name


def private_key_path(project_root: Path) -> Path:
    return key_dir_for_root(project_root) / PRIVATE_KEY_NAME


def public_key_path(project_root: Path) -> Path:
    return key_dir_for_root(project_root) / PUBLIC_KEY_NAME


def find_ssh_keygen() -> str | None:
    return shutil.which("ssh-keygen")


def _run_ssh_keygen(args: list[str]) -> subprocess.CompletedProcess:
    exe = find_ssh_keygen()
    if exe is None:
        # 503 rather than a 500 traceback: ssh-keygen exists only because
        # openssh-client was added to both images, and a missing binary is a
        # deployment problem with a clear fix.
        raise SshKeygenNotFoundError(
            "ssh-keygen not found — install the openssh-client package"
        )
    return subprocess.run([exe, *args], capture_output=True, text=True, timeout=30)


def _fingerprint(pub_path: Path) -> str:
    """The real ``ssh-keygen -lf`` output, as the operator will match it against
    GitHub/GitLab — never recomputed by hand, so it cannot drift."""
    result = _run_ssh_keygen(["-lf", str(pub_path)])
    for token in result.stdout.split():
        if token.startswith("SHA256:"):
            return token
    raise RuntimeError(f"ssh-keygen -lf produced no SHA256 fingerprint: {result.stdout!r}")


def _info(project_root: Path) -> dict:
    private = private_key_path(project_root)
    public = public_key_path(project_root)
    public_key = public.read_text().strip()
    created = datetime.fromtimestamp(private.stat().st_mtime, tz=timezone.utc).isoformat()
    return {
        "public_key": public_key,
        "fingerprint": _fingerprint(public),
        "type": KEY_TYPE,
        "created": created,
    }


def get_info(project_root: Path) -> dict | None:
    """``KeyInfo`` for the project's key, or ``None`` when none exists."""
    if not private_key_path(project_root).exists():
        return None
    return _info(project_root)


def generate(project_root: Path) -> dict:
    """Create a fresh ed25519 keypair for the project. Raises
    :class:`SshKeygenNotFoundError` when ``ssh-keygen`` is not available."""
    key_dir = key_dir_for_root(project_root)
    key_dir.mkdir(parents=True, exist_ok=True)
    # 0700 on the key directory (and its ``.ssh`` parent): ssh refuses a key
    # that lives in a world-readable directory, so this is functional, not
    # decorative.
    key_dir.chmod(0o700)
    key_dir.parent.chmod(0o700)

    _generate_into(key_dir, comment=f"reqmesh:{Path(project_root).name}")
    logger.info("Generated git deploy key for %s", Path(project_root).name)
    return _info(project_root)


def _generate_into(key_dir: Path, *, comment: str) -> None:
    """Write a fresh keypair into *key_dir*, which must already exist.

    Shared by ``generate`` and ``rotate`` so the two cannot disagree about key
    type, passphrase or permissions.
    """
    private = key_dir / PRIVATE_KEY_NAME

    # The empty passphrase is forced, not chosen. `_ssh_env` sets BatchMode=yes,
    # so there is no tty to answer a prompt and a passphrased key could never be
    # used for an unattended push. Do not "fix" the empty `-N` later.
    result = _run_ssh_keygen([
        "-t", KEY_TYPE,
        "-N", "",
        "-C", comment,
        "-f", str(private),
    ])
    if result.returncode != 0:
        raise RuntimeError(f"ssh-keygen failed: {result.stderr.strip()}")

    # ssh-keygen creates the private key 0600, but pin both explicitly: ssh
    # refuses a private key with looser permissions.
    private.chmod(0o600)
    (key_dir / PUBLIC_KEY_NAME).chmod(0o644)


def rotate(project_root: Path) -> dict:
    """Replace the keypair, keeping the old one until the new one exists.

    Deleting first and generating second is the obvious order and the wrong
    one: if generation then fails — ssh-keygen gone, disk full, directory not
    writable — the project is left with *no* key and a broken push, which is
    worse than the stale key it started with. The new pair is built in a
    scratch directory and only swapped in once it is complete, so a failure
    anywhere leaves the existing key untouched.
    """
    key_dir = key_dir_for_root(project_root)
    scratch = key_dir.parent / f".{key_dir.name}.rotating"
    if scratch.exists():
        shutil.rmtree(scratch)

    try:
        scratch.mkdir(parents=True)
        scratch.chmod(0o700)
        scratch.parent.chmod(0o700)
        _generate_into(scratch, comment=f"reqmesh:{Path(project_root).name}")
        # The old key is discarded only now, with a complete replacement in
        # hand. The window where neither is in place is the rmtree/rename pair
        # below, which touches no network call.
        if key_dir.exists():
            shutil.rmtree(key_dir)
        scratch.rename(key_dir)
    except Exception:
        if scratch.exists():
            shutil.rmtree(scratch, ignore_errors=True)
        raise

    logger.info("Rotated git deploy key for %s", Path(project_root).name)
    return _info(project_root)


def delete(project_root: Path) -> None:
    """Remove the keypair and its directory (idempotent)."""
    key_dir = key_dir_for_root(project_root)
    if key_dir.exists():
        shutil.rmtree(key_dir)
