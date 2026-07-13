from __future__ import annotations

from pathlib import Path

from app.services.code_scan import compute_sha


def check_reference_freshness(store, code_root: Path) -> list[dict]:
    reqs = store.list_requirements()
    results = []

    for r in reqs:
        for ref in r.get("references", []):
            path = ref.get("path", "")
            stored_sha = ref.get("sha256")
            full_path = code_root / path

            if not full_path.exists():
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
