from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


class IntegrityChecker:
    def __init__(self, store):
        self.store = store
        self.reqs = store.list_requirements()
        self.vcs = store.list_verification_cases()
        self.components = store.list_components()
        self.issues: list[dict] = []
        self.suspect_links: list[dict] = []
        self._req_ids = {r["id"] for r in self.reqs}
        self._vc_ids = {v["id"] for v in self.vcs}
        self._component_ids = {c["id"] for c in self.components}
        self._parent_of = {r["id"]: r.get("parent") for r in self.reqs}

    def check_all(self) -> dict:
        self._check_dangling_references()
        self._check_asymmetric_derived_links()
        self._check_dangling_links()
        self._check_missing_verification()
        self._check_orphan_requirements()
        self._check_circular_parents()
        self._check_relation_cycles()
        self._check_broken_cascades()
        self._check_duplicate_ids()
        self._check_suspect_links()
        self._check_unreviewed()
        self._check_component_links()
        self._check_corrupt_files()
        return {
            "issues": self.issues,
            "suspect_links": self.suspect_links,
            "issue_count": len(self.issues),
            "suspect_count": len(self.suspect_links),
            "valid": len(self.issues) == 0,
        }

    def _check_corrupt_files(self):
        """Entity files that couldn't be parsed. These are skipped by every
        ``list_*`` call, so without this they'd just silently disappear from
        the UI with no indication that data is missing."""
        try:
            corrupt = self.store.corrupt_files()
        except Exception:
            return
        for c in corrupt:
            self.issues.append({
                "type": "corrupt_file",
                "id": c["path"],
                "name": c["path"],
                "detail": c["error"],
                "severity": "error",
            })

    def _check_dangling_references(self):
        """Every reference in the model whose target no longer exists.

        Driven by the link registry rather than a hand-written list per
        collection. The hand-written version covered requirements and
        components only, so deleting a requirement cited by a specification or
        a decision left a dangling reference that nothing ever reported.
        """
        from app.services.link_registry import find_dangling
        self.issues.extend(find_dangling(self.store))

    def _check_asymmetric_derived_links(self):
        """A derived inverse that disagrees with the field it is derived from.

        These are reqmesh bugs rather than user mistakes — the server maintains
        both sides — so finding one means a write path skipped its sync step.
        Previously nothing checked, and the verify relationship in particular
        could be desynced by one ordinary PUT and stay that way indefinitely,
        with coverage and SysML export silently disagreeing about it.
        """
        from app.services.link_registry import LINKS, targets_of

        for link in LINKS:
            if not link.derived_inverse or not link.inverse_stored:
                continue
            try:
                holders = self.store.list_items(link.holder)
                targets = self.store.list_items(link.target)
            except Exception:
                continue

            # Some inverses store ids (requirement.verification_cases), others a
            # comma-joined display string of holder *names* (allocated_to, built
            # by set_allocation as `name or id`). Compare like with like.
            string_inverse = any(isinstance(t.get(link.derived_inverse), str)
                                 for t in targets)

            forward: dict[str, set] = {}
            for h in holders:
                token = (h.get("name") or h["id"]) if string_inverse else h["id"]
                for t in targets_of(h, link):
                    forward.setdefault(t, set()).add(token)

            for t in targets:
                raw = t.get(link.derived_inverse)
                if isinstance(raw, str):
                    back = {x.strip() for x in raw.split(",") if x.strip()}
                else:
                    back = {str(x) for x in (raw or [])}
                expected = forward.get(t["id"], set())
                if back != expected:
                    self.issues.append({
                        "type": "asymmetric_link",
                        "id": t["id"],
                        "field": link.derived_inverse,
                        "source": f"{link.holder}.{link.field}",
                        "expected": sorted(expected),
                        "found": sorted(back),
                        "severity": "warning",
                    })

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
            # `cascade_from` is what records that this requirement was derived
            # from another, and carries which one. The `derived` boolean it
            # replaced asserted the same thing with less information and could
            # disagree with it, so the exemption now follows the link.
            if r.get("cascade_from"):
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

        # Iterative Tarjan to avoid RecursionError on deep ``derives`` chains.
        # Each call-stack frame is (node, next_edge_position).
        call_stack: list[tuple[str, int]] = []

        for node in list(edges.keys()):
            if node in indices:
                continue
            call_stack.append((node, 0))
            while call_stack:
                v, ei = call_stack[-1]
                if ei == 0:
                    indices[v] = index
                    lowlink[v] = index
                    index += 1
                    stack.append(v)
                    on_stack.add(v)

                edges_v = list(edges.get(v, set()))
                advanced = False
                while ei < len(edges_v):
                    w = edges_v[ei]
                    ei += 1
                    call_stack[-1] = (v, ei)
                    if w not in indices:
                        call_stack.append((w, 0))
                        advanced = True
                        break
                    elif w in on_stack:
                        lowlink[v] = min(lowlink[v], indices[w])
                if advanced:
                    continue

                # All outgoing edges processed.
                call_stack.pop()
                if call_stack:
                    parent = call_stack[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[v])

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

    def _check_component_links(self):
        """The design tree can rot independently of the requirements: a linked
        requirement or verification case may be deleted out from under it."""
        for c in self.components:
            parent = c.get("parent")
            if parent and parent not in self._component_ids:
                self.issues.append({
                    "type": "component_orphan_parent",
                    "id": c["id"],
                    "parent": parent,
                    "severity": "error",
                })
            for req_id in c.get("satisfies") or []:
                if req_id not in self._req_ids:
                    self.issues.append({
                        "type": "component_dangling_requirement",
                        "id": c["id"],
                        "target": req_id,
                        "severity": "error",
                    })
            for vc_id in c.get("verification_cases") or []:
                if vc_id not in self._vc_ids:
                    self.issues.append({
                        "type": "component_dangling_verification",
                        "id": c["id"],
                        "target": vc_id,
                        "severity": "error",
                    })


def mark_links_suspect(store, updated_req_id: str):
    reqs = store.list_requirements()
    suspect_file = store.root / "_suspect.yaml"
    existing = store._read_yaml(suspect_file) if suspect_file.exists() else {}
    links = existing.get("links", [])

    now = datetime.now(timezone.utc).isoformat()

    def add(source: str, rel_type: str, reason: str) -> None:
        if any(l["source"] == source and l["target"] == updated_req_id for l in links):
            return
        links.append({"source": source, "target": updated_req_id, "type": rel_type,
                      "marked": now, "reason": reason})

    for r in reqs:
        for rel in r.get("relations", []):
            if rel["target"] == updated_req_id:
                add(r["id"], rel["type"],
                    f"Target requirement {updated_req_id} was modified")

    # NOTE: this function has no callers. The live suspect-link mechanism is
    # fingerprint-based (services/fingerprint.py, surfaced by GET
    # /suspect-links); this writes a _suspect.yaml that nothing reads. Left
    # as-is rather than extended — cross-entity propagation belongs on the
    # path that actually runs. See check_suspect_links.

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
