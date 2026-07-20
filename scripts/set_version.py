#!/usr/bin/env python3
"""Single-source the reqmesh version across every file that carries it.

The repo-root ``VERSION`` file is authoritative. This script computes the next
version (from a semver bump keyword or an explicit value) and writes it into:

  - VERSION                       (the source of truth)
  - backend/app/core/_version.py  (baked in so the backend has it after repackaging)
  - frontend/package.json
  - desktop/package.json

Usage:
    python3 scripts/set_version.py --get           # print current version
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", help="major | minor | patch | X.Y.Z")
    parser.add_argument("--get", action="store_true", help="print current version and exit")
    args = parser.parse_args()

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
