"""Badge macro values must be LaTeX-escaped before interpolation.

A risk whose severity/status is ``no_effect`` (or any user-supplied string
carrying ``_``, ``%``, ``&``, …) used to be interpolated straight into
``\\statusbadge{}`` / ``\\prioritybadge{}``. The ``_`` then read as a math-mode
subscript, Tectonic failed with "Missing $ inserted", and the failure fell back
to a degraded render without an error. Values are escaped at the call site, and
the fallback render — which stays, because the engine is not guaranteed to be
installed — now announces itself in the log instead of passing for a good one.
"""
from __future__ import annotations

import logging

import pytest

import app.services.publisher as publisher_module
from app.services.publisher import Publisher, compile_latex_to_pdf
from app.services.yaml_store import YamlStore
from app.services.demo_seed import seed_demo_project, PROJECT_ID
from app.services.publishers.latex_helpers import latex_engine_available, latex_escape


# ── fixtures ──────────────────────────────────────────────────────────────────

requires_tectonic = pytest.mark.skipif(
    latex_engine_available() is None,
    reason="no LaTeX engine installed",
)


@pytest.fixture
def seeded(tmp_path):
    seed_demo_project(tmp_path, force=True)
    return YamlStore(tmp_path / PROJECT_ID)


@pytest.fixture
def store_with_bad_values(seeded):
    """A project holding the reported values: underscore severity, ``%`` status,
    ``&`` priority."""
    seeded.create_item("risks", {
        "id": "RISK-ESC",
        "title": "Escaping probe",
        "severity": "no_effect",
        "status": "50%",
        "likelihood": "possible",
    })
    seeded.create_requirement({
        "id": "REQ-ESC",
        "name": "Ampersand priority",
        "description": "",
        "type": "functional",
        "status": "proposed",
        "priority": "high&critical",
        "parent": None,
        "rationale": "",
        "source": "",
        "verification_method": "test",
        "verification_status": "pending",
        "baselines": [],
        "allocated_to": "",
        "cascade_from": None,
        "attributes": [],
        "relations": [],
        "verification_cases": [],
        "references": [],
        "needs": [],
        "derived": False,
        "normative": True,
        "priorities": {},
        "reviewed": None,
    })
    return seeded


# ── escaping ──────────────────────────────────────────────────────────────────


class TestBadgeEscaping:
    def test_source_contains_escaped_forms(self, store_with_bad_values):
        """The generated LaTeX carries the escaped value, not the raw one.

        Source-level so it means something on a machine without Tectonic.
        """
        latex = Publisher(store_with_bad_values).build_latex()

        # Severity is rendered through \prioritybadge, status through
        # \statusbadge, priority through \prioritybadge.
        assert f"\\prioritybadge{{{latex_escape('no_effect')}}}" in latex
        assert f"\\statusbadge{{{latex_escape('50%')}}}" in latex
        assert f"\\prioritybadge{{{latex_escape('high&critical')}}}" in latex

        # The raw forms must not survive — each is exactly the bug.
        assert "\\prioritybadge{no_effect}" not in latex
        assert "\\statusbadge{50%}" not in latex
        assert "\\prioritybadge{high&critical}" not in latex

    @requires_tectonic
    def test_bad_values_compile_to_pdf(self, store_with_bad_values, tmp_path):
        """End-to-end: the reported values now produce a document."""
        out = tmp_path / "out.pdf"
        latex = Publisher(store_with_bad_values).build_latex()
        assert compile_latex_to_pdf(latex, str(out)) is True
        assert out.exists() and out.stat().st_size > 0


class TestBadgeColourSelection:
    def test_ordinary_value_keeps_its_colour(self, seeded):
        """A value with no LaTeX specials reaches the macro unchanged, so
        ``\\IfStrEqCase`` still matches its raw label and picks a colour rather
        than falling through to the grey default."""
        seeded.create_item("risks", {
            "id": "RISK-COL",
            "title": "Colour probe",
            "severity": "high",
            "status": "open",
        })
        latex = Publisher(seeded).build_latex()

        # The macro still maps the raw labels onto their coloured pills.
        assert r"{open}{\pill{prop}{open}}" in latex
        assert r"{high}{\pill{prihigh}{high}}" in latex

        # The stored value is passed through exactly as written, so it matches.
        assert r"\statusbadge{open}" in latex
        assert r"\prioritybadge{high}" in latex


# ── silent failure ────────────────────────────────────────────────────────────


class TestSilentFailure:
    def test_failed_compile_still_produces_a_pdf(self, seeded, monkeypatch, tmp_path):
        """The weasyprint fallback stays: a missing engine must not mean no PDF.

        Both images download tectonic at build time and tolerate that failing,
        and a bare-metal install may have no engine at all.
        """
        monkeypatch.setattr(
            publisher_module,
            "compile_latex_to_pdf",
            lambda latex, out, timeout=300: False,
        )
        out = tmp_path / "out.pdf"
        assert Publisher(seeded).to_pdf_file(str(out)) == str(out)
        assert out.exists() and out.stat().st_size > 0

    def test_failed_compile_is_not_silent(self, seeded, monkeypatch, tmp_path, caplog):
        """Falling back is allowed; doing it quietly is not.

        A degraded render used to be indistinguishable from a good one, which
        is how a LaTeX compile failing on every project carrying an underscored
        enum went unnoticed.
        """
        monkeypatch.setattr(
            publisher_module,
            "compile_latex_to_pdf",
            lambda latex, out, timeout=300: False,
        )
        with caplog.at_level(logging.WARNING, logger=publisher_module.__name__):
            Publisher(seeded).to_pdf_file(str(tmp_path / "out.pdf"))
        assert any(
            r.levelno >= logging.WARNING and "fall" in r.getMessage().lower()
            for r in caplog.records
        ), "a fallback render must announce itself at WARNING or above"
