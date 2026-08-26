"""Tests for the tectonic bundle fetch helper (scripts/fetch_tectonic_bundle.py).

The helper is a build-time script, not runtime code, so the only thing worth
unit-testing without a tectonic binary or a network is the cache-key function:
``_sanitize`` must produce byte-for-byte the same key tectonic uses to index its
bundle cache under ``bundles/hashes/``. If it ever drifts, the pre-fetched cache
stops matching the default bundle URL and the offline warm silently fails.
"""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch_tectonic_bundle.py"


def _load():
    spec = importlib.util.spec_from_file_location("fetch_tectonic_bundle", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sanitize_matches_tectonic_cache_key():
    """The pinned bundle URL sanitizes to the key tectonic uses for its cache."""
    fb = _load()
    assert fb._sanitize(
        "https://relay.fullyjustified.net/default_bundle_v33.tar"
    ) == "https,58,,47,,47,relay.fullyjustified.net,47,default_bundle_v33.tar"


def test_sanitize_escapes_specials_only():
    """Colons and slashes become codepoint escapes; word chars stay literal."""
    fb = _load()
    assert fb._sanitize("a:b/c") == "a,58,b,47,c"
    # Period is kept only when not the first character (hidden-file guard).
    assert fb._sanitize(".hidden.sty") == ",46,hidden.sty"
    assert fb._sanitize("hyphen-underscore_12") == "hyphen-underscore_12"


def test_needed_files_are_complete_and_unique():
    """The manifest covers the packages the task exists for, without duplicates."""
    fb = _load()
    files = fb.NEEDED_FILES
    assert len(set(files)) == len(files)
    assert all(name for name in files)
    # The packages whose on-demand fetch motivated this task must be present.
    assert "inter.sty" in files
    assert "Inter-Regular.otf" in files
    assert "draftwatermark.sty" in files
    assert "fontspec.sty" in files
