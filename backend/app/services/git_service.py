from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# Cache of per-project git identities to avoid re-reading _meta.yaml
# for every git subprocess call. Invalidated when the meta file's mtime changes.
_identity_cache: dict[Path, tuple[float, list[str]]] = {}

# https://user:token@host/repo.git — git echoes remote URLs back in its stderr,
# so both the URLs we log ourselves and anything git prints must be scrubbed
# before it reaches a log file or a log shipper.
_USERINFO_RE = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)(?P<userinfo>[^/@\s]+)@")


def redact_url(text: str) -> str:
    """Replace credentials embedded in any URL within *text* with ``***``."""
    if not text:
        return text
    return _USERINFO_RE.sub(lambda m: f"{m.group('scheme')}***@", str(text))

# Fallback identity so auto-commits work in containers with no git config.
_FALLBACK_NAME = "reqmesh"
_FALLBACK_EMAIL = "reqmesh@localhost"


def is_repo(project_root: Path) -> bool:
    return (Path(project_root) / ".git").exists()


def init_repo(project_root: Path, username: str = "") -> bool:
    """Make *project_root* a git repository. Returns True if one now exists.

    Nothing in the application used to do this. A newly created project was a
    plain directory, so ``auto_commit`` took the ``is_repo`` early return and
    reported "nothing to commit" — indistinguishable from a genuine no-op. On a
    fresh deployment with ``git_autocommit=true`` the result was that every
    change was written to disk and none was ever versioned, silently, which is
    the one thing this tool exists to do.

    Safe to call on a directory that is already a repo, and deliberately not
    called on one nested inside an existing repository: there the parent already
    tracks these files, and initialising a child would quietly detach them from
    the history the operator set up.
    """
    project_root = Path(project_root)
    if is_repo(project_root):
        return True
    if not project_root.is_dir():
        return False

    # `git rev-parse --show-toplevel` walks upward; if it finds a repo above us,
    # leave the directory alone.
    try:
        probe = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(project_root), capture_output=True, text=True, timeout=10,
        )
        if probe.returncode == 0 and probe.stdout.strip():
            logger.info("Not initialising %s — already inside the repo at %s",
                        project_root, probe.stdout.strip())
            return True
    except Exception:
        pass

    try:
        ident = _identity_for(project_root, username)
        result = subprocess.run(
            ["git", *ident, "init", "-q"],
            cwd=str(project_root), capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            logger.warning("git init failed in %s: %s",
                           project_root, redact_url(result.stderr.strip()))
            return False
    except Exception as exc:
        logger.warning("git init failed in %s: %s", project_root, exc)
        return False

    logger.info("Initialised a git repository for %s", project_root)
    return True


# Batched push state
_push_queue: set[Path] = set()
_push_timer: threading.Timer | None = None
_push_lock = threading.Lock()

# Recorded push outcomes so the status endpoint can report them.  Keyed by
# resolved project root; kept in-memory — when the process restarts the
# outcome is lost, but the next push (or the first status that triggers one)
# will refresh it, and a missing record is indistinguishable from "never
# pushed", which is the truthful state.
_push_outcomes: dict[Path, dict] = {}


def _record_push_outcome(project_root: Path, ok: bool, error: str | None) -> None:
    from datetime import datetime, timezone
    _push_outcomes[Path(project_root).resolve()] = {
        "at": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "error": redact_url(error) if error else None,
    }


def _identity_for(project_root: Path, username: str = "") -> list[str]:
    """Build git identity args for a commit.
    
    Priority: 1) per-project meta.yaml git settings, 2) passed username,
    3) global fallback.
    """
    name = _FALLBACK_NAME
    email = _FALLBACK_EMAIL

    meta_file = project_root.resolve() / "_meta.yaml"
    try:
        mtime = meta_file.stat().st_mtime
    except OSError:
        mtime = 0.0

    cached = _identity_cache.get(meta_file)
    if cached is not None and cached[0] == mtime:
        name_email = cached[1]
    else:
        try:
            from app.services.yaml_store import YamlStore
            store = YamlStore(project_root)
            meta = store.read_meta()
            git_cfg = meta.get("git", {})
            if git_cfg.get("user_name"):
                name = git_cfg["user_name"]
            if git_cfg.get("user_email"):
                email = git_cfg["user_email"]
        except Exception:
            pass
        name_email = [name, email]
        _identity_cache[meta_file] = (mtime, name_email)
    name, email = name_email

    if username and name == _FALLBACK_NAME:
        name = username

    return ["-c", f"user.name={name}", "-c", f"user.email={email}"]


def _git(project_root: Path, *args: str, remote_url: str = "") -> subprocess.CompletedProcess:
    """Run git in a project. Pass ``remote_url`` for calls that touch the network.

    Network calls need the SSH options from `_ssh_env`, otherwise `test_remote`
    (which sets them) succeeds on a host whose key is unknown while the push
    that follows blocks on a prompt it can never answer.
    """
    return subprocess.run(
        ["git", *_identity_for(project_root), *args],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=30,
        env=_ssh_env(remote_url) if remote_url else None,
    )


def auto_commit(project_root: Path, message: str, username: str = "") -> bool:
    """Best-effort commit of all pending changes in a project working tree.
    
    Only acts when the project directory itself is a git repository. Returns
    True if a commit was created. Uses per-project git identity from _meta.yaml
    when configured, falling back to the acting username.
    """
    project_root = Path(project_root)
    if not is_repo(project_root):
        return False
    try:
        # Build identity flags for this specific commit
        ident = _identity_for(project_root, username)
        subprocess.run(["git", *ident, "add", "-A"], cwd=str(project_root),
                       capture_output=True, text=True, timeout=30)
        result = subprocess.run(["git", *ident, "commit", "-m", message],
                               cwd=str(project_root), capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            if "nothing to commit" not in result.stdout + result.stderr:
                logger.warning("git auto-commit failed in %s: %s", project_root, redact_url(result.stderr.strip()))
            return False
        return True
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("git auto-commit error in %s: %s", project_root, exc)
        return False


def log(project_root: Path, limit: int = 50) -> list[dict]:
    """Recent commits for a project, newest first. Empty if not a repo."""
    project_root = Path(project_root)
    if not is_repo(project_root):
        return []
    result = _git(project_root, "log", f"-{limit}", "--format=%H%x1f%an%x1f%aI%x1f%s")
    if result.returncode != 0:
        return []
    commits = []
    for line in result.stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4:
            commits.append({"hash": parts[0], "author": parts[1], "date": parts[2], "message": parts[3]})
    return commits


def ensure_remote(project_root: Path, remote_url: str) -> bool:
    """Ensure a git remote named 'origin' is configured.
    
    If no remote exists, adds one. If one exists with a different URL, updates it.
    Returns True if a remote was added or updated.
    """
    project_root = Path(project_root)
    if not is_repo(project_root):
        return False
    try:
        result = _git(project_root, "remote", "get-url", "origin")
        if result.returncode == 0:
            current = result.stdout.strip()
            if current == remote_url:
                return False
            _git(project_root, "remote", "set-url", "origin", remote_url)
            logger.info("git remote origin updated to %s in %s", redact_url(remote_url), project_root)
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass

    try:
        _git(project_root, "remote", "add", "origin", remote_url)
        logger.info("git remote origin set to %s in %s", redact_url(remote_url), project_root)
        return True
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("git remote add failed in %s: %s", project_root, redact_url(str(exc)))
        return False


def _project_git_config(project_root: Path) -> dict:
    """Read git configuration from the project's _meta.yaml."""
    try:
        from app.services.yaml_store import YamlStore
        store = YamlStore(project_root)
        meta = store.read_meta()
        return meta.get("git", {})
    except Exception:
        return {}


# Schemes a project may push to. `file://`, bare local paths and `http://` are
# refused: the first two turn any git operation into a reader of repositories
# elsewhere on the host, and the third ships history in clear text. Enforced on
# both the write path (router._guard_git_settings) and here, so a new endpoint
# cannot reach `git` with an unchecked URL again.
ALLOWED_REMOTE_SCHEMES = ("https://", "ssh://", "git@")

REMOTE_SCHEME_ERROR = ("git remote URL must start with https://, ssh:// or git@ "
                       "(file://, http:// and local paths are refused)")


def is_allowed_remote(remote_url: str) -> bool:
    return str(remote_url).startswith(ALLOWED_REMOTE_SCHEMES)


def _ssh_env(remote_url: str) -> dict:
    """Environment for a git network call.

    SSH remotes get a non-interactive, bounded handshake: without this git can
    block forever on an unknown-host prompt with no tty to answer it.
    """
    env = os.environ.copy()
    if str(remote_url).startswith(("git@", "ssh://")):
        env["GIT_SSH_COMMAND"] = (
            "ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -o BatchMode=yes")
    return env


def test_remote(project_root: Path, remote_url: str) -> dict:
    """Test whether a git remote URL is reachable and return basic info.

    Uses ``git ls-remote`` — a lightweight handshake, no clone. Returns
    ``{"ok": True, "branches": [...]}`` or ``{"ok": False, "error": "..."}``.

    The URL is checked against the same allowlist as the write path *before*
    reaching git. Without that, this became a way to read branch names out of
    any repository on the host (`file://` and bare paths both work with
    ls-remote), to confirm the existence of arbitrary filesystem paths from the
    error text, and to probe internal hosts and ports.
    """
    project_root = Path(project_root)
    if not is_repo(project_root):
        return {"ok": False, "error": "Project directory is not a git repository. Run 'git init' first."}
    if not remote_url:
        return {"ok": False, "error": "No remote URL configured."}
    if not is_allowed_remote(remote_url):
        return {"ok": False, "error": REMOTE_SCHEME_ERROR}
    try:
        ident = _identity_for(project_root)
        env = _ssh_env(remote_url)
        result = subprocess.run(
            ["git", *ident, "ls-remote", "--heads", remote_url],
            cwd=str(project_root), capture_output=True, text=True, timeout=20,
            env=env,
        )
        if result.returncode != 0:
            msg = result.stderr.strip() or "Unknown error"
            return {"ok": False, "error": redact_url(msg)}
        branches = []
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) == 2 and parts[1].startswith("refs/heads/"):
                branches.append(parts[1][len("refs/heads/"):])
        return {
            "ok": True,
            "branches": branches[:20],
            "branch_count": len(branches),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Connection timed out after 20 seconds. Check the URL and network access."}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def push_to_remote(project_root: Path, branch: str = "main") -> bool:
    """Push commits to the configured remote.
    
    Returns True if a push was attempted successfully. Logs warnings on failure
    (no exception raised — push failures are non-fatal).
    """
    from app.core.config import settings

    if settings.offline_mode:
        _record_push_outcome(project_root, False, "Offline mode — push skipped")
        return False

    project_root = Path(project_root)
    if not is_repo(project_root):
        _record_push_outcome(project_root, False, "Not a git repository")
        return False

    cfg = _project_git_config(project_root)
    remote_url = cfg.get("remote_url") or settings.git_remote_url
    if not remote_url:
        _record_push_outcome(project_root, False, "No remote URL configured")
        return False

    try:
        ensure_remote(project_root, remote_url)

        # Determine the current branch if not specified
        actual_branch = branch
        branch_result = _git(project_root, "rev-parse", "--abbrev-ref", "HEAD")
        if branch_result.returncode == 0 and branch_result.stdout.strip():
            actual_branch = branch_result.stdout.strip()

        result = _git(project_root, "push", "-u", "origin", actual_branch,
                      remote_url=remote_url)
        if result.returncode != 0:
            error_msg = result.stderr.strip()
            logger.warning("git push failed in %s: %s", project_root, redact_url(error_msg))
            _record_push_outcome(project_root, False, redact_url(error_msg))
            return False

        logger.info("git push succeeded in %s (%s)", project_root, actual_branch)
        _record_push_outcome(project_root, True, None)
        return True
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("git push error in %s: %s", project_root, exc)
        _record_push_outcome(project_root, False, redact_url(str(exc)))
        return False


def schedule_push(project_root: Path, interval_minutes: int | None = None) -> None:
    """Queue a project for a batched push, or push immediately.

    With a positive interval, pushes are batched — calling this repeatedly
    within the window only pushes once when the timer fires (cheap: only
    queues, safe to call from the event loop). With interval 0 the push runs
    synchronously via push_to_remote(), so call that path from a worker
    thread. When interval_minutes is None the global setting applies.
    """
    if interval_minutes is None:
        from app.core.config import settings
        interval_minutes = settings.git_push_interval_minutes
    if interval_minutes <= 0:
        push_to_remote(project_root)
        return
    with _push_lock:
        _push_queue.add(Path(project_root))
        _ensure_timer(interval_minutes)


def _ensure_timer(interval_minutes: int) -> None:
    global _push_timer
    if _push_timer is not None:
        return
    _push_timer = threading.Timer(interval_minutes * 60.0, _flush_all)
    _push_timer.daemon = True
    _push_timer.start()


def _flush_all() -> None:
    global _push_timer
    with _push_lock:
        roots = list(_push_queue)
        _push_queue.clear()
        _push_timer = None
    for root in roots:
        push_to_remote(root)


_HASH_RE = re.compile(r"^[0-9a-fA-F]{4,40}$")


def restore_commit(project_root: Path, commit_hash: str, username: str = "") -> bool:
    """Restore the working tree to the state of a past commit.

    Does ``git checkout <hash> -- .`` then creates a new commit recording the
    restoration so the operation itself is always reversible.
    """
    project_root = Path(project_root)
    if not is_repo(project_root):
        return False
    # `commit_hash` comes straight from the API request. Reject anything that
    # isn't hex up front, then resolve it through `rev-parse` and check out
    # *that* output rather than the raw input — this guarantees the value
    # handed to `checkout` is always a real commit object in this repo, never
    # a crafted string that git could parse as an option (e.g. "--orphan=x").
    if not _HASH_RE.match(commit_hash):
        logger.warning("git restore rejected: %r is not a valid commit hash", commit_hash)
        return False
    try:
        ident = _identity_for(project_root, username)
        verify = subprocess.run(
            ["git", "rev-parse", "--verify", "-q", commit_hash + "^{commit}"],
            cwd=str(project_root), capture_output=True, text=True, timeout=10,
        )
        resolved = verify.stdout.strip()
        if verify.returncode != 0 or not resolved:
            logger.warning("git restore: %r does not resolve to a commit in %s", commit_hash, project_root)
            return False
        r = subprocess.run(
            ["git", *ident, "checkout", resolved, "--", "."],
            cwd=str(project_root), capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            logger.warning("git checkout %s failed in %s: %s", commit_hash, project_root, redact_url(r.stderr.strip()))
            return False
        subprocess.run(
            ["git", *ident, "add", "-A"],
            cwd=str(project_root), capture_output=True, text=True, timeout=30,
        )
        who = username or _FALLBACK_NAME
        msg = f"rt: restored to {commit_hash[:8]} ({who})"
        subprocess.run(
            ["git", *ident, "commit", "-m", msg, "--allow-empty"],
            cwd=str(project_root), capture_output=True, text=True, timeout=30,
        )
        return True
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("git restore error in %s: %s", project_root, exc)
        return False


def get_status(project_root: Path) -> dict:
    """Return the git status for a project directory.

    Returns a dict matching the shape described in the ``GET /git/status``
    contract.  Performs **no network access**: ``ahead`` is computed against the
    local remote-tracking ref, not the live remote, so the call never hangs when
    the remote is unreachable.
    """
    project_root = Path(project_root)
    cfg = _project_git_config(project_root)
    raw_remote_url = cfg.get("remote_url", "")

    base: dict = {
        "is_repo": False,
        "branch": "",
        "dirty": False,
        "commit_count": 0,
        "head": None,
        "remote_url": redact_url(raw_remote_url) if raw_remote_url else "",
        "has_remote": bool(raw_remote_url),
        "ahead": None,
        "last_push": None,
        "hook_installed": False,
    }

    if not is_repo(project_root):
        return base

    base["is_repo"] = True

    # branch
    rev = _git(project_root, "rev-parse", "--abbrev-ref", "HEAD")
    if rev.returncode == 0:
        base["branch"] = rev.stdout.strip()

    # dirty
    st = _git(project_root, "status", "--porcelain")
    if st.returncode == 0 and st.stdout.strip():
        base["dirty"] = True

    # commit_count
    cnt = _git(project_root, "rev-list", "--count", "HEAD")
    if cnt.returncode == 0 and cnt.stdout.strip():
        try:
            base["commit_count"] = int(cnt.stdout.strip())
        except ValueError:
            pass

    # head
    log_r = _git(project_root, "log", "-1", "--format=%H%x1f%aI%x1f%s")
    if log_r.returncode == 0:
        parts = log_r.stdout.strip().split("\x1f")
        if len(parts) == 3:
            base["head"] = {"hash": parts[0], "date": parts[1], "message": parts[2]}

    # ahead — computed from the local tracking ref, no fetch
    try:
        up = _git(project_root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        if up.returncode == 0 and up.stdout.strip():
            ahead_behind = _git(
                project_root, "rev-list", "--left-right", "--count",
                f"HEAD...@{up.stdout.strip()}",
            )
            if ahead_behind.returncode == 0:
                parts = ahead_behind.stdout.strip().split("\t")
                if len(parts) == 2:
                    base["ahead"] = int(parts[0])
    except Exception:
        pass

    # last_push
    resolved = project_root.resolve()
    base["last_push"] = _push_outcomes.get(resolved)

    # hook_installed
    hook_path = project_root / ".git" / "hooks" / "pre-commit"
    base["hook_installed"] = hook_path.exists()

    return base


def delete_remote(project_root: Path) -> bool:
    """Remove the git remote 'origin' *and* clear ``remote_url`` from the
    project's ``_meta.yaml``.  Doing only one leaves the two disagreeing,
    which is the state that makes "why is it still pushing?" unanswerable."""
    project_root = Path(project_root)

    # Remove the git remote (best-effort — if it doesn't exist, that's fine)
    if is_repo(project_root):
        try:
            remotes = _git(project_root, "remote")
            if remotes.returncode == 0 and "origin" in remotes.stdout.splitlines():
                _git(project_root, "remote", "remove", "origin")
        except Exception:
            pass

    # Clear remote_url from _meta.yaml
    try:
        from app.services.yaml_store import YamlStore
        store = YamlStore(project_root)
        meta = store.read_meta()
        git_cfg = meta.get("git", {})
        if "remote_url" in git_cfg:
            del git_cfg["remote_url"]
            meta["git"] = git_cfg
            store.write_meta(meta)
    except Exception as exc:
        logger.warning("Failed to clear remote_url from settings: %s", exc)
        return False

    return True
