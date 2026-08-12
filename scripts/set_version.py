#!/usr/bin/env python3
"""Single-source the reqmesh version across every file that carries it.

The repo-root ``VERSION`` file is authoritative. This script computes the next
version (from a semver bump keyword or an explicit value) and writes it into:

  - VERSION                       (the source of truth)
  - backend/app/core/_version.py  (baked in so the backend has it after repackaging)
  - frontend/package.json
  - desktop/package.json
  - scripts/install.sh            (the git ref its standalone bootstrap fetches from)

``--files`` prints that list so release.sh can stage it without keeping a second
copy that drifts out of step.

Usage:
    python3 scripts/set_version.py --get           # print current version
    python3 scripts/set_version.py --files         # list files a bump touches
    python3 scripts/set_version.py patch           # 0.4.0 -> 0.4.1
    python3 scripts/set_version.py minor           # 0.4.0 -> 0.5.0
    python3 scripts/set_version.py major           # 0.4.0 -> 1.0.0
    python3 scripts/set_version.py 1.2.3           # set explicitly

Stdlib only — safe to run under /usr/bin/python3 (no venv needed).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def read_current() -> str:
    return VERSION_FILE.read_text().strip()


def bump(current: str, part: str) -> str:
    major, minor, patch = (int(x) for x in current.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(part)


def _sub_once(path: Path, pattern: str, replacement: str, *, required: bool = True) -> bool:
    text = path.read_text()
    new_text, n = re.subn(pattern, replacement, text, count=1)
    if n == 0:
        if required:
            raise SystemExit(f"error: no version field found in {path}")
        return False
    path.write_text(new_text)
    return True


# Docs that quote the release in an install command. Left to rot they send people
# at an installer many releases old: the README still named v0.1.3 while v0.1.11
# was current, so the documented one-liner deployed a script predating every fix
# made since. Rewritten here for the same reason install.sh's ref pin is.
DOC_FILES = ("README.md", "DEPLOYMENT.md")


def touched_files() -> list[str]:
    """Repo-relative paths that `write_all` may modify.

    release.sh stages exactly this list. It used to keep its own hardcoded copy,
    which silently went stale when install.sh was added here: v0.1.2 shipped an
    installer still pinned to v0.1.1, so the published one-liner bootstrapped the
    previous release's wizard and deploy scripts.
    """
    paths = [
        "VERSION",
        "backend/app/core/_version.py",
        "scripts/install.sh",
        "backend/app/cli.py",
        "start.sh",
    ]
    paths += [d for d in DOC_FILES if (ROOT / d).is_file()]
    paths += [p for p in ("frontend/package.json", "desktop/package.json")
              if (ROOT / p).is_file()]
    return sorted(paths)


def write_all(version: str) -> None:
    VERSION_FILE.write_text(version + "\n")
    _sub_once(
        ROOT / "backend/app/core/_version.py",
        r'__version__ = "[^"]*"',
        f'__version__ = "{version}"',
    )
    for pkg in (ROOT / "frontend/package.json", ROOT / "desktop/package.json"):
        if pkg.is_file():
            _sub_once(pkg, r'"version":\s*"[^"]*"', f'"version": "{version}"')
    # install.sh pins the git ref it fetches its companion scripts from when run
    # standalone. Bumped here so the tag cannot drift from the release it ships
    # in — a stale pin would quietly install the previous version's wizard.
    _sub_once(
        ROOT / "scripts/install.sh",
        r"REQMESH_REF:-v\d+\.\d+\.\d+",
        f"REQMESH_REF:-v{version}",
    )
    _sub_once(
        ROOT / "start.sh",
        r"reqmesh v\d+\.\d+\.\d+  \(server\)",
        f"reqmesh v{version}  (server)",
    )
    _sub_once(
        ROOT / "start.sh",
        r"reqmesh v\d+\.\d+\.\d+  \(desktop\)",
        f"reqmesh v{version}  (desktop)",
    )
    # Every occurrence, not the first: the docs quote the version in several
    # commands (the one-liner, the bundle download, the unpack directory).
    for doc in DOC_FILES:
        path = ROOT / doc
        if not path.is_file():
            continue
        text = path.read_text()
        text = re.sub(r"/reqmesh/v\d+\.\d+\.\d+/", f"/reqmesh/v{version}/", text)
        text = re.sub(r"/download/v\d+\.\d+\.\d+/", f"/download/v{version}/", text)
        text = re.sub(r"reqmesh-v\d+\.\d+\.\d+", f"reqmesh-v{version}", text)
        path.write_text(text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", help="major | minor | patch | X.Y.Z")
    parser.add_argument("--get", action="store_true", help="print current version and exit")
    parser.add_argument("--files", action="store_true",
                        help="print the files a bump touches (one per line) and exit")
    args = parser.parse_args()

    if args.files:
        print("\n".join(touched_files()))
        return

    current = read_current()
    if args.get or not args.target:
        print(current)
        return

    if args.target in ("major", "minor", "patch"):
        new = bump(current, args.target)
    elif SEMVER_RE.match(args.target):
        new = args.target
    else:
        raise SystemExit(f"error: '{args.target}' is not a bump keyword or X.Y.Z version")

    write_all(new)
    print(new)


if __name__ == "__main__":
    sys.exit(main())
