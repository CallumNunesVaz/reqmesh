"""Every installed distribution must match its pinned version.

A stale venv — where ``pip install -r requirements.txt`` was not rerun after
the pins changed — exercises different library versions than CI.  The bug
behind the YAML round-trip corruption was invisible locally because the local
venv held ruamel.yaml 0.18.6, not the pinned 0.19.1 that CI installed.

This test guards against that class of drift: it parses ``requirements.txt``
(and ``requirements-dev.txt``, which includes the former via ``-r``) and
asserts each ``name==version`` pin matches ``importlib.metadata.version(name)``.
"""

from __future__ import annotations

import sys

import re
from importlib.metadata import version
from pathlib import Path

import pytest

# --- helpers (extracted so they can be unit-tested without the venv) ---


def _parse_requirements(path: Path) -> dict[str, str]:
    """Parse a requirements file into ``{name: version}`` for every ``==`` pin.

    Skips comments, blanks, and ``-r …`` include directives.
    Names like ``uvicorn[standard]`` have their ``[...]`` extras stripped
    before lookup.
    """
    pins: dict[str, str] = {}
    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("-r "):
                continue
            # Extract name==version, ignoring any extras marker
            m = re.match(r"^([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?\s*==\s*([^\s;]+)", stripped)
            if m:
                name = m.group(1)
                pinned_version = m.group(2)
                pins[name] = pinned_version
    return pins


def _collect_mismatches(pins: dict[str, str]) -> dict[str, tuple[str, str]]:
    """Check each pin against the installed version.

    Returns ``{name: (pinned, installed)}`` for every mismatch.
    """
    mismatches: dict[str, tuple[str, str]] = {}
    for name, pinned in sorted(pins.items()):
        try:
            installed = version(name)
        except Exception:
            installed = "NOT INSTALLED"
        if installed != pinned:
            mismatches[name] = (pinned, installed)
    return mismatches


def _format_mismatch_report(mismatches: dict[str, tuple[str, str]]) -> str:
    """Build a human-readable report of every version mismatch."""
    lines = [f"Found {len(mismatches)} package(s) with mismatched versions:"]
    for name, (pinned, installed) in sorted(mismatches.items()):
        lines.append(f"  {name}: pinned {pinned}, installed {installed}")
    lines.append("")
    lines.append("Run: pip install -r requirements-dev.txt")
    return "\n".join(lines)


# --- helpers tests (safety: does not touch the real venv) ---

def test_parse_skips_comments_and_blanks(tmp_path):
    req = tmp_path / "req.txt"
    req.write_text(
        "# a comment\n"
        "\n"
        "fastapi==0.141.1\n"
        "\n"
        "# another comment\n"
        "pydantic==2.13.4\n"
    )
    pins = _parse_requirements(req)
    assert pins == {"fastapi": "0.141.1", "pydantic": "2.13.4"}


def test_parse_handles_extras(tmp_path):
    req = tmp_path / "req.txt"
    req.write_text("uvicorn[standard]==0.51.0\n")
    pins = _parse_requirements(req)
    assert pins == {"uvicorn": "0.51.0"}


def test_parse_handles_include_directive(tmp_path):
    req = tmp_path / "req.txt"
    req.write_text(
        "-r requirements.txt\n"
        "pytest==9.1.1\n"
    )
    pins = _parse_requirements(req)
    assert pins == {"pytest": "9.1.1"}


def test_parse_ignores_non_pin_lines(tmp_path):
    req = tmp_path / "req.txt"
    req.write_text(
        "somepackage\n"
        "other>=1.0\n"
        "pinned==2.0\n"
    )
    pins = _parse_requirements(req)
    assert pins == {"pinned": "2.0"}


def test_collect_mismatches_is_empty_when_everything_matches(monkeypatch):
    """The clean case, asserted rather than skipped.

    This replaces a stub that called the helper, discarded the result and then
    `pass`ed — it could not fail, which is the one thing a test must be able to
    do. Injecting the versions keeps it off the real venv, so it stays true
    whatever is installed.
    """
    monkeypatch.setattr(
        sys.modules[__name__], "version",
        lambda name: {"alpha": "1.0", "beta": "2.0"}[name],
    )
    assert _collect_mismatches({"alpha": "1.0", "beta": "2.0"}) == {}


def test_collect_mismatches_reports_all(monkeypatch):
    """The helper reports every mismatch, not just the first."""
    pins = {"alpha": "1.0", "beta": "2.0", "gamma": "3.0"}

    def fake_version(name):
        fake_map = {"alpha": "1.0", "beta": "1.9", "gamma": "2.9"}
        if name in fake_map:
            return fake_map[name]
        raise Exception("not found")

    # _collect_mismatches uses the module-level `version` import, so we must
    # patch that reference, not importlib.metadata itself.
    monkeypatch.setattr("tests.test_pinned_environment.version", fake_version)
    mismatches = _collect_mismatches(pins)
    assert mismatches == {"beta": ("2.0", "1.9"), "gamma": ("3.0", "2.9")}


def test_format_mismatch_report_includes_instruction():
    report = _format_mismatch_report({"foo": ("1.0", "0.9")})
    assert "pip install -r requirements-dev.txt" in report
    assert "foo: pinned 1.0, installed 0.9" in report


# --- the real gate ---


def test_installed_packages_match_pins():
    """Every ``name==version`` pin matches the installed distribution.

    Fails with a report of *all* mismatches and an instruction to reinstall.
    """
    backend_dir = Path(__file__).resolve().parent.parent
    req_txt = backend_dir / "requirements.txt"
    req_dev_txt = backend_dir / "requirements-dev.txt"

    assert req_txt.is_file(), f"missing {req_txt}"
    assert req_dev_txt.is_file(), f"missing {req_dev_txt}"

    pins: dict[str, str] = {}
    pins.update(_parse_requirements(req_txt))
    pins.update(_parse_requirements(req_dev_txt))
    # dev overrides base on conflict — the dev pin wins.

    mismatches = _collect_mismatches(pins)
    if mismatches:
        pytest.fail(_format_mismatch_report(mismatches))
