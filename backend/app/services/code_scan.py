from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

TAG_RE = r"\[(?P<kind>[a-z]+)\s*->\s*(?P<id>[A-Za-z0-9._-]+)\]"
LOOSE_RE = r"@covers\s+(?P<id>[A-Za-z0-9._-]+)"

COMMENT_PREFIXES: dict[str, str] = {
    ".py": "# ",
    ".java": "// ",
    ".js": "// ",
    ".ts": "// ",
    ".tsx": "// ",
    ".c": "// ",
    ".cpp": "// ",
    ".h": "// ",
    ".go": "// ",
    ".rs": "// ",
    ".swift": "// ",
    ".sql": "-- ",
    ".sh": "# ",
    ".yaml": "# ",
    ".yml": "# ",
    ".rb": "# ",
    ".proto": "// ",
    ".kt": "// ",
    ".lua": "-- ",
    ".pl": "# ",
    ".pm": "# ",
    ".php": "// ",
    ".r": "# ",
    ".bat": "REM ",
    ".ps1": "# ",
}

DEFAULT_SCAN_EXTENSIONS = set(COMMENT_PREFIXES.keys())
BINARY_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dll", ".exe", ".o", ".obj", ".a", ".lib",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv",
    ".ttf", ".otf", ".woff", ".woff2",
}

SKIP_DIRS = {".git", ".svn", ".hg", "__pycache__", "node_modules", ".venv",
             "venv", "build", "dist", ".tox", ".eggs", "target", ".mypy_cache",
             ".pytest_cache", ".ruff_cache", "coverage", "htmlcov"}


def compute_sha(path: Path) -> str | None:
    try:
        sha = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                sha.update(chunk)
        return sha.hexdigest()
    except (FileNotFoundError, OSError):
        return None


def scan_tree(
    code_root: Path,
    patterns: dict | None = None,
    scan_extensions: set | None = None,
) -> list[dict]:
    import re

    tag_re = re.compile(patterns.get("tag", TAG_RE).encode() if patterns else TAG_RE)
    loose_re = re.compile(patterns.get("loose", LOOSE_RE).encode() if patterns else LOOSE_RE)
    ext_set = scan_extensions or DEFAULT_SCAN_EXTENSIONS

    hits: list[dict] = []
    files = _list_files(code_root)

    for rel_path in sorted(files):
        full_path = code_root / rel_path
        ext = full_path.suffix.lower()
        if ext in BINARY_EXTENSIONS or ext not in ext_set:
            continue
        try:
            with open(full_path, "rb") as f:
                lines = f.read().split(b"\n")
        except (OSError, UnicodeDecodeError):
            continue

        file_sha = hashlib.sha256()
        for line in lines:
            file_sha.update(line + b"\n")
        file_hash = file_sha.hexdigest()

        for i, line in enumerate(lines, start=1):
            try:
                decoded = line.decode("utf-8", errors="replace")
            except UnicodeDecodeError:
                continue

            for m in tag_re.finditer(decoded):
                hits.append({
                    "req_id": m.group("id"),
                    "kind": m.group("kind"),
                    "path": str(rel_path),
                    "line": i,
                    "sha256": file_hash,
                })

            for m in loose_re.finditer(decoded):
                hits.append({
                    "req_id": m.group("id"),
                    "kind": "covers",
                    "path": str(rel_path),
                    "line": i,
                    "sha256": file_hash,
                })

    return hits


def _list_files(code_root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=str(code_root),
            capture_output=True,
            text=False,
            timeout=30,
        )
        if result.returncode == 0:
            paths = result.stdout.rstrip(b"\0").split(b"\0")
            return [Path(p.decode("utf-8", errors="replace")) for p in paths if p]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    paths = []
    for entry in sorted(code_root.rglob("*")):
        if entry.is_dir():
            continue
        rel = entry.relative_to(code_root)
        parts = rel.parts
        if any(p in SKIP_DIRS for p in parts):
            continue
        paths.append(rel)
    return paths


def merge_references(store, hits: list[dict]) -> dict:
    reqs = store.list_requirements()
    req_map = {r["id"]: r for r in reqs}
    created = 0
    updated = 0
    touched = set()

    for h in hits:
        rid = h["req_id"]
        req = req_map.get(rid)
        if req is None:
            continue

        refs = list(req.get("references", []))
        existing = next((r for r in refs if r["path"] == h["path"] and r.get("kind") == h["kind"]), None)
        if existing:
            if existing.get("sha256") == h["sha256"]:
                continue
            existing["sha256"] = h["sha256"]
            existing["line"] = h.get("line")
            updated += 1
        else:
            refs.append({
                "path": h["path"],
                "kind": h["kind"],
                "sha256": h["sha256"],
                "line": str(h.get("line")),
            })
            created += 1

        store.update_requirement(rid, {"references": refs})
        touched.add(rid)

    return {
        "created": created,
        "updated": updated,
        "files_scanned": len(hits),
        "requirements_touched": len(touched),
    }
