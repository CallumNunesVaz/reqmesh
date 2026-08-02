"""A failed LaTeX compile must say why.

``compile_latex_to_pdf`` swallows failures on purpose — callers fall back to the
HTML renderer rather than surfacing a hard error — so the log line is the only
evidence a failure leaves. It read ``exc.stdout`` only, and tectonic reports on
*stderr*, so a tectonic failure logged the exit status and an empty line. That
is the engine that runs during ``docker build`` (``scripts/warm_tectonic.py``),
where there is nothing else to go on.
"""
import subprocess

from app.services.publishers import latex_helpers
from app.services.publishers.latex_helpers import compile_latex_to_pdf


def _fail_with(monkeypatch, engine, *, stdout=None, stderr=None, timeout=False):
    """Drive a compile that fails, with the given streams on the exception."""
    monkeypatch.setattr(latex_helpers, "latex_engine_available", lambda: engine)

    def fake_run(cmd, **kwargs):
        if timeout:
            raise subprocess.TimeoutExpired(cmd, 300, output=stdout, stderr=stderr)
        raise subprocess.CalledProcessError(1, cmd, output=stdout, stderr=stderr)

    monkeypatch.setattr(latex_helpers.subprocess, "run", fake_run)


class TestFailureIsDiagnosable:
    def test_tectonic_stderr_reaches_the_log(self, monkeypatch, caplog, tmp_path):
        # The regression: tectonic writes diagnostics to stderr and nothing to
        # stdout, which used to produce an empty log.
        _fail_with(monkeypatch, "tectonic",
                   stderr=b"error: unable to open bundle: network unreachable")
        with caplog.at_level("WARNING"):
            assert compile_latex_to_pdf("\\documentclass{article}", str(tmp_path / "o.pdf")) is False
        log = "\n".join(r.getMessage() for r in caplog.records)
        assert "unable to open bundle" in log
        assert "network unreachable" in log

    def test_classic_engine_stdout_reaches_the_log(self, monkeypatch, caplog, tmp_path):
        # pdflatex and friends report on stdout; that path must keep working.
        _fail_with(monkeypatch, "pdflatex",
                   stdout=b"! LaTeX Error: File `tabularx.sty' not found.")
        with caplog.at_level("WARNING"):
            assert compile_latex_to_pdf("x", str(tmp_path / "o.pdf")) is False
        log = "\n".join(r.getMessage() for r in caplog.records)
        assert "tabularx.sty" in log

    def test_both_streams_when_both_are_populated(self, monkeypatch, caplog, tmp_path):
        _fail_with(monkeypatch, "tectonic",
                   stdout=b"note: writing report.pdf", stderr=b"error: Sty not found")
        with caplog.at_level("WARNING"):
            compile_latex_to_pdf("x", str(tmp_path / "o.pdf"))
        log = "\n".join(r.getMessage() for r in caplog.records)
        assert "Sty not found" in log
        assert "writing report.pdf" in log

    def test_str_streams_are_handled(self, monkeypatch, caplog, tmp_path):
        # TimeoutExpired carries str when the call used text mode; decoding
        # unconditionally would raise inside the error handler and mask the
        # original failure entirely.
        _fail_with(monkeypatch, "tectonic", stderr="error: timed out fetching", timeout=True)
        with caplog.at_level("WARNING"):
            assert compile_latex_to_pdf("x", str(tmp_path / "o.pdf")) is False
        log = "\n".join(r.getMessage() for r in caplog.records)
        assert "timed out fetching" in log
        assert "warm_tectonic" in log      # the actionable hint survives

    def test_silent_engine_says_so_rather_than_nothing(self, monkeypatch, caplog, tmp_path):
        _fail_with(monkeypatch, "tectonic")
        with caplog.at_level("WARNING"):
            compile_latex_to_pdf("x", str(tmp_path / "o.pdf"))
        log = "\n".join(r.getMessage() for r in caplog.records)
        assert "no output" in log

    def test_timeout_is_passed_through_and_defaults(self, monkeypatch, tmp_path):
        # Cache *warming* is the cold-fetch case and asks for a longer budget
        # than a normal export; a silently ignored argument would leave the
        # build failing on slow links exactly as before.
        seen = {}
        monkeypatch.setattr(latex_helpers, "latex_engine_available", lambda: "tectonic")

        def fake_run(cmd, **kwargs):
            seen["timeout"] = kwargs.get("timeout")
            raise subprocess.CalledProcessError(1, cmd)

        monkeypatch.setattr(latex_helpers.subprocess, "run", fake_run)

        compile_latex_to_pdf("x", str(tmp_path / "o.pdf"))
        assert seen["timeout"] == 300, "default budget"

        compile_latex_to_pdf("x", str(tmp_path / "o.pdf"), timeout=600)
        assert seen["timeout"] == 600, "caller's budget must reach subprocess.run"

    def test_no_engine_is_still_a_clean_false(self, monkeypatch, caplog, tmp_path):
        monkeypatch.setattr(latex_helpers, "latex_engine_available", lambda: None)
        with caplog.at_level("WARNING"):
            assert compile_latex_to_pdf("x", str(tmp_path / "o.pdf")) is False
        assert "No LaTeX engine" in "\n".join(r.getMessage() for r in caplog.records)
