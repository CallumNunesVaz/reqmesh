from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


class IntegrityChecker:
    def __init__(self, store):
        self.store = store
        self.reqs = store.list_requirements()
        self.vcs = store.list_verification_cases()
        self.issues: list[dict] = []
        self.suspect_links: list[dict] = []
        self._req_ids = {r["id"] for r in self.reqs}
        self._vc_ids = {v["id"] for v in self.vcs}
        self._parent_of = {r["id"]: r.get("parent") for r in self.reqs}

    def check_all(self) -> dict:
        self._check_dangling_links()
        self._check_missing_verification()
        self._check_orphan_requirements()
        self._check_circular_parents()
        self._check_relation_cycles()
        self._check_broken_cascades()
        self._check_duplicate_ids()
        self._check_suspect_links()
        self._check_unreviewed()
        return {
            "issues": self.issues,
            "suspect_links": self.suspect_links,
            "issue_count": len(self.issues),
            "suspect_count": len(self.suspect_links),
            "valid": len(self.issues) == 0,
        }

    def _check_dangling_links(self):
        for r in self.reqs:
            for rel in r.get("relations", []):
                target = rel["target"]
                if target not in self._req_ids and target not in self._vc_ids:
                    self.issues.append({
                        "type": "dangling_link",
                        "source": r["id"],
                        "target": target,
                        "relation": rel["type"],
                        "severity": "error",
                    })

    def _check_missing_verification(self):
        for r in self.reqs:
            if r.get("normative", True) is False:
                continue
            if r.get("status") in ("approved", "implemented", "verified"):
                if not r.get("verification_cases"):
                    self.issues.append({
                        "type": "no_verification",
                        "id": r["id"],
                        "name": r.get("name", ""),
                        "severity": "warning",
                    })

    def _check_orphan_requirements(self):
        for r in self.reqs:
            if r.get("derived", False):
                continue
            parent = r.get("parent")
            if parent and parent not in self._req_ids and parent not in self._vc_ids:
                self.issues.append({
                    "type": "orphan_parent",
                    "id": r["id"],
                    "parent": parent,
                    "severity": "warning",
                })

    def _check_circular_parents(self):
        for r in self.reqs:
            visited = set()
            current = r["id"]
            chain = [current]
            while True:
                parent = self._parent_of.get(current)
                if not parent:
                    break
                if parent in visited:
                    self.issues.append({
                        "type": "circular_parent",
                        "id": r["id"],
                        "chain": chain,
                        "severity": "error",
                    })
                    break
                visited.add(current)
                chain.append(parent)
                current = parent

    def _check_relation_cycles(self):
        edges: dict[str, set[str]] = {}
        for r in self.reqs:
            rid = r["id"]
            edges.setdefault(rid, set())
            for rel in r.get("relations", []):
                target = rel["target"]
                if target in self._req_ids:
                    edges[rid].add(target)

        index = 0
        stack: list[str] = []
        on_stack: set[str] = set()
        indices: dict[str, int] = {}
        lowlink: dict[str, int] = {}
        sccs: list[list[str]] = []

        def strongconnect(v: str):
            nonlocal index
            indices[v] = index
            lowlink[v] = index
            index += 1
            stack.append(v)
            on_stack.add(v)

            for w in edges.get(v, set()):
                if w not in indices:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], indices[w])

            if lowlink[v] == indices[v]:
                scc: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    scc.append(w)
                    if w == v:
                        break
                if len(scc) > 1:
                    sccs.append(scc)

        for node in list(edges.keys()):
            if node not in indices:
                strongconnect(node)

        for scc in sccs:
            self.issues.append({
                "type": "circular_relation",
                "ids": scc,
                "severity": "error",
            })

    def _check_broken_cascades(self):
        for r in self.reqs:
            casc_from = r.get("cascade_from")
            if casc_from and casc_from not in self._req_ids:
                self.issues.append({
                    "type": "broken_cascade",
                    "id": r["id"],
                    "source": casc_from,
                    "severity": "error",
                })

    def _check_duplicate_ids(self):
        seen = {}
        for r in self.reqs:
            rid = r["id"]
            if rid in seen:
                self.issues.append({
                    "type": "duplicate_id",
                    "id": rid,
                    "severity": "error",
                })
            seen[rid] = True

    def _check_suspect_links(self):
        try:
            from app.services.fingerprint import check_suspect_links
            self.suspect_links = check_suspect_links(self.store)
        except ImportError:
            pass

    def _check_unreviewed(self):
        try:
            from app.services.fingerprint import check_unreviewed
            unreviewed = check_unreviewed(self.store)
            for u in unreviewed:
                self.issues.append({
                    "type": "unreviewed",
                    "id": u["id"],
                    "name": u.get("name", ""),
                    "severity": "warning",
                })
        except ImportError:
            pass


def mark_links_suspect(store, updated_req_id: str):
    reqs = store.list_requirements()
    suspect_file = store.root / "_suspect.yaml"
    existing = store._read_yaml(suspect_file) if suspect_file.exists() else {}
    links = existing.get("links", [])

    for r in reqs:
        for rel in r.get("relations", []):
            if rel["target"] == updated_req_id:
                entry = {
                    "source": r["id"],
                    "target": updated_req_id,
                    "type": rel["type"],
                    "marked": datetime.now(timezone.utc).isoformat(),
                    "reason": f"Target requirement {updated_req_id} was modified",
                }
                if not any(l["source"] == entry["source"] and l["target"] == entry["target"] for l in links):
                    links.append(entry)

    store.ensure_dirs()
    store._write_yaml(suspect_file, {"links": links, "updated": datetime.now(timezone.utc).isoformat()})


def clear_suspect_links(store, ids: list[str] | None = None):
    suspect_file = store.root / "_suspect.yaml"
    if not suspect_file.exists():
        return
    if ids is None:
        import os; os.remove(suspect_file)
        return
    existing = store._read_yaml(suspect_file) if suspect_file.exists() else {}
    links = [l for l in existing.get("links", []) if f"{l['source']}-{l['target']}" not in ids]
    store._write_yaml(suspect_file, {"links": links, "updated": datetime.now(timezone.utc).isoformat()})
