"""LaTeX compilation helpers extracted from ``publisher.py``.

These are standalone functions (not tied to the ``Publisher`` class) so they
can be shared across rendering backends and tested independently.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# LaTeX engines we know how to drive, in order of preference. tectonic is a
# single self-contained binary that fetches its package bundle on demand, so it
# needs no full TeX Live install; the classic engines run two passes so the
# table of contents and longtables resolve.
_LATEX_ENGINES = ("tectonic", "pdflatex", "lualatex", "xelatex")

# Markers the guarded watermark preamble writes into the LaTeX log via
# ``\typeout`` (see ``Publisher``'s watermark preamble), so the compile step can
# learn whether a draft report's DRAFT watermark actually rendered. A draft that
# silently loses its mark is a document-control problem, not a cosmetic one, so
# the omission is reported rather than swallowed.
WATERMARK_APPLIED_MARKER = "reqmesh:watermark=applied"
WATERMARK_OMITTED_MARKER = "reqmesh:watermark=omitted"


@dataclass
class CompileResult:
    """Outcome of a LaTeX compile: success plus whether the DRAFT watermark was
    dropped because the ``draftwatermark`` package was unavailable."""

    ok: bool
    watermark_omitted: bool = False


def latex_engine_available() -> str | None:
    """Return the name of the first available LaTeX engine, or None."""
    for engine in _LATEX_ENGINES:
        if shutil.which(engine):
            return engine
    return None


def compile_latex_to_pdf(latex: str, out_path: str, timeout: int = 300) -> bool:
    """Compile a LaTeX document to ``out_path``.

    Returns True on success. Returns False (and logs a warning) if no engine is
    installed or the compile fails, so callers can fall back to another renderer
    rather than surface a hard error to the user.

    ``timeout`` is per engine pass. The default suits a warm cache; cache
    *warming* itself is the cold case by definition and passes a larger one
    (see ``backend/scripts/warm_tectonic.py``).

    Deliberately does not retry. A user waiting on a PDF export should fail
    fast and fall back to the HTML renderer; retrying is the caller's decision,
    and only the build-time warmer wants it.

    Callers that need to know whether a draft report's DRAFT watermark was
    dropped should use :func:`compile_latex_to_pdf_detailed` instead.
    """
    return compile_latex_to_pdf_detailed(latex, out_path, timeout).ok


def compile_latex_to_pdf_detailed(latex: str, out_path: str, timeout: int = 300) -> CompileResult:
    r"""Like :func:`compile_latex_to_pdf`, but also reports whether a draft
    report's DRAFT watermark could not be rendered.

    The watermark preamble is guarded (``\IfFileExists{draftwatermark.sty}``),
    so a missing package no longer fails the compile — but it does silently drop
    the DRAFT mark. The preamble writes a ``\typeout`` marker into the log, and
    this function reads it back so callers can tell the user what they did not
    get rather than ship an unmarked draft.
    """
    engine = latex_engine_available()
    if engine is None:
        logger.warning("No LaTeX engine found (%s); cannot render PDF from LaTeX.",
                       ", ".join(_LATEX_ENGINES))
        return CompileResult(ok=False)
    with tempfile.TemporaryDirectory(prefix="reqmesh-tex-") as tmp:
        tmp_dir = Path(tmp)
        tex_file = tmp_dir / "report.tex"
        tex_file.write_text(latex, encoding="utf-8")
        if engine == "tectonic":
            # --keep-logs leaves report.log behind so the watermark marker can
            # be read back; tectonic otherwise deletes it.
            cmds = [[engine, "--outdir", str(tmp_dir), "--keep-logs", str(tex_file)]]
        else:
            # Two passes so \tableofcontents and longtable column widths settle.
            base = [engine, "-interaction=nonstopmode", "-halt-on-error",
                    "-output-directory", str(tmp_dir), str(tex_file)]
            cmds = [base, base]
        try:
            for cmd in cmds:
                # 120s was tight enough to matter: tectonic fetches any TeX
                # package it does not have cached *inside* this call, so a cold
                # cache on a slow link timed out and the report silently
                # dropped to the HTML renderer. Deployments now ship a warmed
                # cache (see backend/scripts/warm_tectonic.py), which makes a
                # typical compile ~12s; the wider budget is for the case where
                # that warming did not happen.
                subprocess.run(cmd, cwd=tmp_dir, capture_output=True, timeout=timeout,
                               check=True)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            # Both streams, always. This read only stdout, and tectonic reports
            # on *stderr* — so a tectonic failure logged "exit status 1" and an
            # empty line, which is undiagnosable. It is the engine that runs
            # during `docker build`, where that log is the only evidence there
            # is. The classic engines do report on stdout, hence both.
            parts = []
            for name in ("stderr", "stdout"):
                stream = getattr(exc, name, None)
                if not stream:
                    continue
                if isinstance(stream, bytes):
                    stream = stream.decode("utf-8", "replace")
                text = stream.strip()
                if text:
                    parts.append(f"--- {engine} {name} (last 2000 chars) ---\n{text[-2000:]}")
            if isinstance(exc, subprocess.TimeoutExpired):
                parts.append("compile exceeded the timeout — if this deployment has a cold "
                             "TeX cache, run backend/scripts/warm_tectonic.py")
            logger.warning("LaTeX compile with %s failed: %s\n%s", engine, exc,
                           "\n".join(parts) or "(the engine produced no output)")
            return CompileResult(ok=False)
        pdf = tmp_dir / "report.pdf"
        if not pdf.exists():
            logger.warning("LaTeX compile with %s produced no PDF.", engine)
            return CompileResult(ok=False)
        watermark_omitted = _watermark_omitted(tmp_dir)
        shutil.copyfile(pdf, out_path)
        return CompileResult(ok=True, watermark_omitted=watermark_omitted)


def _watermark_omitted(tmp_dir: Path) -> bool:
    """True when the compile log records that the DRAFT watermark was dropped."""
    log_path = tmp_dir / "report.log"
    if not log_path.exists():
        return False
    try:
        return WATERMARK_OMITTED_MARKER in log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _darken(hex_color: str, factor: float) -> str:
    """Darken a hex colour by the given factor (0-1).  *factor* = 0.65 means
    the result is 65% as bright as the original."""
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r, g, b = int(r * factor), int(g * factor), int(b * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def latex_escape(text: str) -> str:
    # Standard TeX escaping first — it only touches ASCII specials, so the
    # Unicode LaTeX-macro replacements applied afterwards (which themselves
    # contain $, \, ^, {, }) are left intact rather than being re-escaped.
    text = text.replace("\\", "\x00")
    text = text.replace("_", "\x01")
    for char, repl in (
        ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
        ("{", r"\{"), ("}", r"\}"),
        ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}"),
    ):
        text = text.replace(char, repl)
    text = text.replace("\x00", r"\textbackslash{}")
    # \allowbreak after the escaped underscore gives LaTeX a break point inside
    # long snake_case identifiers (e.g. parameter names) — without it, an
    # unbroken word wider than its table column overflows into the next cell
    # instead of wrapping. Restored after the {}-escaping loop above so its
    # own braces aren't re-escaped into literal visible characters.
    text = text.replace("\x01", r"\_\allowbreak{}")
    # Then map Unicode characters that typical TeX fonts can't render to their
    # LaTeX equivalents. Safe now — these macros won't be re-escaped.
    replacements = {
        "\u2014": "---",    # em dash
        "\u2013": "--",     # en dash
        "\u2018": "`",      # left single quote
        "\u2019": "'",      # right single quote
        "\u201c": "``",     # left double quote
        "\u201d": "''",     # right double quote
        "\u2026": r"\ldots{}",   # ellipsis
        "\u00a0": "~",      # non-breaking space
        "\u00d7": r"$\times$",
        "\u2192": r"$\rightarrow$",
        "\u03b1": r"$\alpha$",
        "\u03b2": r"$\beta$",
        "\u03b3": r"$\gamma$",
        "\u03b4": r"$\delta$",
        "\u03b5": r"$\epsilon$",
        "\u03bc": r"$\mu$",
        "\u03c0": r"$\pi$",
        "\u03c3": r"$\sigma$",
        "\u03c9": r"$\omega$",
        "\u2264": r"$\leq$",
        "\u2265": r"$\geq$",
        "\u00b0": r"$^\circ$",  # degree symbol
        "\u00b1": r"$\pm$",
    }
    for char, repl in replacements.items():
        text = text.replace(char, repl)
    return text


def truncate_words(text: str, limit: int) -> str:
    """Trim text to at most ``limit`` characters at a word boundary, appending an
    ellipsis when truncated. Keeps table cells from ending mid-word."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip()
    return (cut or text[:limit].rstrip()) + "\u2026"
