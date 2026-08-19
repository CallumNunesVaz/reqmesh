"""The DRAFT watermark must never take down the whole report.

``draftwatermark`` is not in a minimal TeX install — tectonic fetches it from its
bundle on demand, so it is absent from a warmed cache until fetched and
unreachable in ``offline_mode``. It used to be loaded unconditionally, so a
draft report failed to build while a non-draft one built fine. The load is now
guarded the same way ``tikz`` is: a missing or incompatible package costs the
watermark and nothing else, and the omission is reported rather than silently
shipping an unmarked draft.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest

import app.services.publisher as publisher_module
from app.core.config import settings as global_settings
from app.services.demo_seed import PROJECT_ID, seed_demo_project
from app.services.publisher import (
    Publisher,
    compile_latex_to_pdf,
    compile_latex_to_pdf_detailed,
    watermark_preamble,
)
from app.services.publishers import latex_helpers
from app.services.publishers.latex_helpers import (
    WATERMARK_OMITTED_MARKER,
    CompileResult,
    latex_engine_available,
    latex_escape,
)
from app.services.yaml_store import YamlStore

# Every status string the report treats as a draft (publisher._header_config).
DRAFT_STATUSES = ["draft", "working", "preliminary", "in review", "in_review", "wip"]


requires_tectonic = pytest.mark.skipif(
    latex_engine_available() is None,
    reason="no LaTeX engine installed",
)


@pytest.fixture
def seeded(tmp_path):
    seed_demo_project(tmp_path, force=True)
    return YamlStore(tmp_path / PROJECT_ID)


def _draft_latex(seeded, monkeypatch, status: str) -> str:
    monkeypatch.setattr(global_settings, "report_status", status)
    return Publisher(seeded).build_latex()


# ── preamble guard ─────────────────────────────────────────────────────────────


class TestWatermarkGuard:
    def test_preamble_guards_watermark_load(self, seeded, monkeypatch):
        r"""A draft preamble loads draftwatermark behind \IfFileExists, never bare."""
        latex = _draft_latex(seeded, monkeypatch, "draft")

        assert r"\IfFileExists{draftwatermark.sty}" in latex
        assert r"\ifdefined\rmhaswatermark" in latex
        # No line may be a bare \usepackage{draftwatermark}.
        for line in latex.splitlines():
            assert line.strip() != r"\usepackage{draftwatermark}"

    @pytest.mark.parametrize("status", DRAFT_STATUSES)
    def test_every_draft_status_triggers_watermark(self, seeded, monkeypatch, status):
        latex = _draft_latex(seeded, monkeypatch, status)
        assert r"\IfFileExists{draftwatermark.sty}" in latex

    @pytest.mark.parametrize("status", ["released", "final", "", "drafting"])
    def test_non_draft_status_skips_watermark(self, seeded, monkeypatch, status):
        latex = _draft_latex(seeded, monkeypatch, status)
        assert r"\IfFileExists{draftwatermark.sty}" not in latex

    def test_watermark_preamble_is_escaped(self):
        """The watermark text is pre-escaped; raw specials must not survive."""
        escaped = latex_escape("100%_draft & final")
        text_line = next(l for l in watermark_preamble(escaped) if "SetWatermarkText" in l)
        assert "100%_draft & final" not in text_line
        assert escaped in text_line


# ── draft renders end-to-end ───────────────────────────────────────────────────


class TestDraftRenders:
    @requires_tectonic
    def test_draft_report_renders_pdf(self, seeded, monkeypatch, tmp_path):
        """A draft-status project produces a PDF under a real engine."""
        latex = _draft_latex(seeded, monkeypatch, "draft")
        out = tmp_path / "draft.pdf"
        result = compile_latex_to_pdf_detailed(latex, str(out))
        assert result.ok is True
        assert out.exists() and out.stat().st_size > 0

    @requires_tectonic
    def test_status_with_latex_specials_builds(self, seeded, monkeypatch, tmp_path):
        """A report status carrying LaTeX specials is escaped, not fatal.

        The status is user-supplied and reaches the footer/cover even when it is
        not a draft, so it must be escaped (task 118 found one such bug already).
        """
        monkeypatch.setattr(global_settings, "report_status", "Draft_100% & final")
        latex = Publisher(seeded).build_latex()
        assert latex_escape("Draft_100% & final") in latex
        assert "Draft_100% & final" not in latex

        out = tmp_path / "out.pdf"
        assert compile_latex_to_pdf(latex, str(out)) is True
        assert out.exists() and out.stat().st_size > 0


# ── missing package: still builds, and the omission is reported ────────────────


class TestMissingWatermark:
    def test_omitted_marker_is_detected_from_the_log(self, monkeypatch, tmp_path):
        """A compile that succeeds but drops the watermark is flagged."""
        monkeypatch.setattr(latex_helpers, "latex_engine_available", lambda: "tectonic")

        def fake_run(cmd, **kwargs):
            cwd = Path(kwargs["cwd"])
            (cwd / "report.pdf").write_bytes(b"%PDF-1.4 fake")
            (cwd / "report.log").write_text(
                f"some log ... {WATERMARK_OMITTED_MARKER} ...", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(latex_helpers.subprocess, "run", fake_run)
        out = tmp_path / "o.pdf"
        result = compile_latex_to_pdf_detailed(r"\documentclass{article}", str(out))
        assert result.ok is True
        assert result.watermark_omitted is True
        assert out.exists()

    def test_applied_marker_is_not_reported_as_omitted(self, monkeypatch, tmp_path):
        monkeypatch.setattr(latex_helpers, "latex_engine_available", lambda: "tectonic")

        def fake_run(cmd, **kwargs):
            cwd = Path(kwargs["cwd"])
            (cwd / "report.pdf").write_bytes(b"%PDF-1.4 fake")
            (cwd / "report.log").write_text(
                "reqmesh:watermark=applied", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(latex_helpers.subprocess, "run", fake_run)
        result = compile_latex_to_pdf_detailed(r"\documentclass{article}",
                                               str(tmp_path / "o.pdf"))
        assert result.ok is True
        assert result.watermark_omitted is False

    def test_watermark_omission_is_reported(self, seeded, monkeypatch, caplog, tmp_path):
        """Dropping the watermark is logged — a silent omission is unacceptable."""
        monkeypatch.setattr(global_settings, "report_status", "draft")
        monkeypatch.setattr(
            publisher_module,
            "compile_latex_to_pdf_detailed",
            lambda latex, out, timeout=300: CompileResult(ok=True, watermark_omitted=True),
        )
        with caplog.at_level(logging.WARNING, logger=publisher_module.__name__):
            Publisher(seeded).to_pdf_file(str(tmp_path / "out.pdf"))
        assert any(
            r.levelno >= logging.WARNING and "watermark" in r.getMessage().lower()
            for r in caplog.records
        )
