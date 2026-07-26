from __future__ import annotations

from pathlib import Path

from app.services.code_scan import compute_sha


def _resolve_within(code_root: Path, path: str) -> Path | None:
    """Resolve a reference path inside *code_root*, or None if it escapes.

    ``Reference.path`` is free-form text stored on a requirement. ``root / path``
    silently discards the root when *path* is absolute (``Path("/a") / "/etc/shadow"``
    is ``/etc/shadow``), and ``..`` walks out — which turned this into an
    existence and content-hash oracle for arbitrary files on the host. The
    sibling scan endpoint already confines itself this way.
    """
    if not path:
        return None
    try:
        root = Path(code_root).resolve()
        candidate = (root / path).resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    return candidate if candidate.is_relative_to(root) else None


def check_reference_freshness(store, code_root: Path) -> list[dict]:
    reqs = store.list_requirements()
    results = []

    for r in reqs:
        for ref in r.get("references", []):
            path = ref.get("path", "")
            stored_sha = ref.get("sha256")
            full_path = _resolve_within(code_root, path)

            if full_path is None:
                # Outside the project: reported as such rather than probed, so
                # the response can't be used to test for files on the host.
                results.append({
                    "req_id": r["id"],
                    "path": path,
                    "status": "outside_project",
                })
            elif not full_path.exists():
                results.append({
                    "req_id": r["id"],
                    "path": path,
                    "status": "missing",
                })
            elif stored_sha is not None:
                current = compute_sha(full_path)
                if current == stored_sha:
                    results.append({
                        "req_id": r["id"],
                        "path": path,
                        "status": "ok",
                    })
                else:
                    results.append({
                        "req_id": r["id"],
                        "path": path,
                        "status": "changed",
                    })

    return results
