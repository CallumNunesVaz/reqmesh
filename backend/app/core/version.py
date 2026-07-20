"""Runtime version + build metadata for the reqmesh backend.

The version is single-sourced from the repo-root ``VERSION`` file and baked into
``_version.py`` by ``scripts/set_version.py`` at release time. Build metadata
(git sha, build timestamp) is read from a ``manifest.json`` written into release
bundles, or from environment variables when running from source.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

try:
    from app.core._version import __version__ as _BAKED_VERSION
except Exception:  # pragma: no cover - _version.py is always generated in-tree
    _BAKED_VERSION = "0.0.0+dev"


def get_version() -> str:
    """Semantic version of this build. RT_VERSION overrides for testing."""
    return os.environ.get("RT_VERSION") or _BAKED_VERSION


def _find_manifest() -> Path | None:
    # Bundles place manifest.json at their root; walk up from this module.
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "manifest.json"
        if candidate.is_file():
            return candidate
        if (parent / ".git").exists():
            break
    return None


@lru_cache(maxsize=1)
def get_build_info() -> dict:
    """Version plus best-effort build provenance (git sha, build time, channel)."""
    info = {
        "name": "reqmesh",
        "version": get_version(),
        "git_sha": os.environ.get("RT_GIT_SHA", ""),
        "built_at": os.environ.get("RT_BUILT_AT", ""),
        # "release" only once a bundle manifest is found below; a bare source
        # checkout reports "dev".
        "channel": "dev",
    }
    manifest_path = _find_manifest()
    if manifest_path is not None:
        try:
            data = json.loads(manifest_path.read_text())
            for key in ("version", "git_sha", "built_at"):
                if not info[key] and data.get(key):
                    info[key] = data[key]
            info["channel"] = "release"
        except (OSError, ValueError):
            pass
    return info
