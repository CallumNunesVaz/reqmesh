"""Tests for component-scoped export and broken-link rendering.

Uses the seeded Cessna 172S demo project for component-scope assertions and
a small API-created project for broken-link edge cases.
"""
from __future__ import annotations

import pytest

from app.services.publisher import Publisher
from app.services.yaml_store import YamlStore
from app.services.demo_seed import seed_demo_project, PROJECT_ID


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def seeded(tmp_path):
    """The bundled demo project — 57 requirements, 80 components, 24 cases."""
    seed_demo_project(tmp_path, force=True)
    return YamlStore(tmp_path / PROJECT_ID)


# ── component scope ───────────────────────────────────────────────────────────


class TestComponentScope:
    def test_includes_satisfied_requirements(self, seeded):
        """Scoping to a component includes requirements that component satisfies."""
        pub = Publisher(seeded, components=["FUSE"])
        req_ids = {r["id"] for r in pub.reqs}
        # FUSE → AFRM0001; children COCK → AFRM0003, YOKE → FLTC0001,
        # SEAT/RSEAT/HARN → AFRM0002, DOOR → AFRM0001
        assert "AFRM0001" in req_ids
        assert "AFRM0003" in req_ids
        assert "FLTC0001" in req_ids
        assert "AFRM0002" in req_ids

    def test_excludes_requirements_not_satisfied(self, seeded):
        """Scoping to a component excludes requirements it does not satisfy."""
        pub = Publisher(seeded, components=["YOKE"])
        req_ids = {r["id"] for r in pub.reqs}
        assert "FLTC0001" in req_ids  # YOKE satisfies FLTC0001
        # Top-level reqs not satisfied by YOKE or its children (it has none)
        assert "ACFT0000" not in req_ids
        assert "PROP0001" not in req_ids
        assert "AFRM0001" not in req_ids

    def test_tree_descends_to_children(self, seeded):
        """Scope descends the component tree: scoping to a parent picks up
        the requirements its children satisfy."""
        # FUSE → COCK → YOKE → FLTC0001 (three levels)
        pub = Publisher(seeded, components=["FUSE"])
        req_ids = {r["id"] for r in pub.reqs}
        assert "FLTC0001" in req_ids

    def test_nonexistent_component_yields_empty(self, seeded):
        """A component id that matches nothing yields an empty report, not an error."""
        pub = Publisher(seeded, components=["NONEXIST"])
        assert len(pub.reqs) == 0
        # The report should still build without raising
        html = pub.build_html()
        assert html  # not empty string
        latex = pub.build_latex()
        assert latex  # not empty string

    def test_subsystems_alone_unchanged(self, seeded):
        """subsystems alone behaves exactly as before (regression guard)."""
        pub = Publisher(seeded, subsystems=["AFRM0000"])
        req_ids = {r["id"] for r in pub.reqs}
        # AFRM0000 expands down to children
        assert "AFRM0001" in req_ids
        assert "AFRM0004" in req_ids
        assert "AFRM0007" in req_ids
        # Top-level ACFT0000 is parent of AFRM0000, not a child
        assert "ACFT0000" not in req_ids

    def test_both_filters_intersect(self, seeded):
        """Both together intersect: a requirement must satisfy both filters."""
        # YOKE satisfies FLTC0001, which is NOT under AFRM0000 hierarchy
        pub = Publisher(seeded, subsystems=["AFRM0000"], components=["YOKE"])
        assert len(pub.reqs) == 0

        # FUSE satisfies AFRM0001, which IS under AFRM0000 — intersection works
        pub = Publisher(seeded, subsystems=["AFRM0000"], components=["FUSE"])
        req_ids = {r["id"] for r in pub.reqs}
        assert "AFRM0001" in req_ids
        # ACFT0000 is not under AFRM0000, even though C172 satisfies it
        assert "ACFT0000" not in req_ids


# ── broken links ──────────────────────────────────────────────────────────────


class TestBrokenLinks:
    """Rendering of references that do not resolve in the current document."""

    # ── helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _make_project(client, proj_id: str, name: str = "Broken Links Test"):
        """Create a fresh project and return its store, ready to populate."""
        client.post("/api/projects", json={"id": proj_id, "name": name})
        from app.core.config import settings
        from pathlib import Path
        return YamlStore(Path(settings.data_root) / proj_id)

    def _add_req(self, store, req_id: str, name: str = "", parent: str | None = None,
                 relations: list[dict] | None = None):
        """Write a minimal requirement directly to the store."""
        store.create_requirement({
            "id": req_id,
            "name": name or req_id,
            "description": "",
            "type": "functional",
            "status": "proposed",
            "priority": "medium",
            "parent": parent,
            "rationale": "",
            "source": "",
            "verification_method": "test",
            "verification_status": "pending",
            "baselines": [],
            "allocated_to": "",
            "cascade_from": None,
            "attributes": [],
            "relations": relations or [],
            "verification_cases": [],
            "references": [],
            "needs": [],
            "derived": False,
            "normative": True,
            "priorities": {},
            "reviewed": None,
        })

    # ── filtered out ───────────────────────────────────────────────────────

    def test_filtered_out_no_href(self, seeded):
        """A requirement filtered out of the document renders with
        (not in this document) and no href/hyperlink to it."""
        # Scope to AFRM0001 only — AFRM0000 is its parent, so it's filtered out.
        # AFRM0001 is under the AIRFRAME subsystem; scoping to just it means
        # its parent AFRM0000 is not included (expansion is downward only).
        pub = Publisher(seeded, subsystems=["AFRM0001"])

        # HTML: check that the component table still renders ACFT0000 (which
        # C172 satisfies) with the missing suffix and no anchor.
        html = pub.build_html()
        assert " (not in this document)" in html
        assert 'class="entity-missing"' in html
        # No href to ACFT0000 (it's filtered out)
        assert 'href="#req-ACFT0000"' not in html

        # LaTeX: component table emits LaTeX links for satisfies
        latex = pub.build_latex()
        assert " (not in this document)" in latex
        # No \\hyperlink to the filtered-out requirement
        assert "\\hyperlink{req-ACFT0000}" not in latex

        # Markdown: requirement parent is rendered as bare ID
        md = pub.build_markdown()
        assert " (not in this document)" in md
        assert "AFRM0000 (not in this document)" in md

    def test_unresolved_reference_html_latex(self, client, workspace):
        """A reference to an id that exists nowhere renders (unresolved reference)."""
        store = self._make_project(client, "broken-test-1")
        self._add_req(store, "REQ001", name="Test",
                      relations=[{"type": "relates_to", "target": "MISSINGREF"}])

        pub = Publisher(store)
        html = pub.build_html()
        latex = pub.build_latex()

        assert "MISSINGREF (unresolved reference)" in html
        assert "MISSINGREF (unresolved reference)" in latex
        # No href for the unresolvable id
        assert 'href="#req-MISSINGREF"' not in html
        # No \\hyperlink for it either
        assert "\\hyperlink{req-MISSINGREF}" not in latex

    def test_in_scope_normal_link(self, client, workspace):
        """An in-scope reference renders as a normal link with neither suffix."""
        store = self._make_project(client, "broken-test-2")
        self._add_req(store, "REQ001", name="First")
        self._add_req(store, "REQ002", name="Second",
                      relations=[{"type": "relates_to", "target": "REQ001"}])

        pub = Publisher(store)
        html = pub.build_html()
        latex = pub.build_latex()
        md = pub.build_markdown()

        # HTML: should have a real href
        assert 'href="#req-REQ001"' in html
        assert "REQ001 (not in this document)" not in html
        assert "REQ001 (unresolved reference)" not in html

        # LaTeX: should have a real \\hyperlink
        assert "\\hyperlink{req-REQ001}" in latex
        assert "REQ001 (not in this document)" not in latex
        assert "REQ001 (unresolved reference)" not in latex

        # Markdown: bare ID should appear without suffix
        assert "REQ001 (not in this document)" not in md
        assert "REQ001 (unresolved reference)" not in md

    def test_latex_no_hyperlink_when_unresolved(self, client, workspace):
        """The LaTeX output for an unresolved reference contains no \\hyperlink."""
        store = self._make_project(client, "broken-test-3")
        self._add_req(store, "REQ001", name="Test",
                      relations=[{"type": "relates_to", "target": "MISSINGREQ"}])

        pub = Publisher(store)
        latex = pub.build_latex()

        assert "MISSINGREQ (unresolved reference)" in latex
        assert "\\hyperlink{req-MISSINGREQ}" not in latex

    def test_filtered_out_markdown_parent(self, seeded):
        """Markdown parent reference to a filtered-out requirement carries the suffix."""
        pub = Publisher(seeded, subsystems=["AFRM0001"])
        md = pub.build_markdown()
        # AFRM0001 has parent AFRM0000, which is filtered out
        assert "AFRM0000 (not in this document)" in md
