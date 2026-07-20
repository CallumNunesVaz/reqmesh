"""Tests for release tooling helpers (scripts/set_version.py)."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "set_version.py"


def _load():
    spec = importlib.util.spec_from_file_location("set_version", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bump_semver():
    sv = _load()
    assert sv.bump("0.4.0", "patch") == "0.4.1"
    assert sv.bump("0.4.0", "minor") == "0.5.0"
    assert sv.bump("0.4.9", "minor") == "0.5.0"
    assert sv.bump("0.4.0", "major") == "1.0.0"
    assert sv.bump("1.2.3", "major") == "2.0.0"


def test_bump_rejects_unknown_part():
    sv = _load()
    with pytest.raises(ValueError):
        sv.bump("0.4.0", "sideways")


def test_version_file_matches_baked_module():
    """The VERSION file and the baked backend _version.py must stay in sync."""
    root = Path(__file__).resolve().parents[2]
    file_ver = (root / "VERSION").read_text().strip()
    from app.core._version import __version__
    assert file_ver == __version__
