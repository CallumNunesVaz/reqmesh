"""The search endpoint and the frontend's translation map must agree.

`services/search.py` returns kind names that are not all `EntityKind` values —
`change_request` where the frontend calls it `change` — so `SearchPage` runs
results through `BACKEND_KIND_TO_ENTITY`. Nothing kept the two in step, and the
map fell two kinds behind: `baseline` and `comment` were both returned by the
backend and missing from the map, so those hits rendered as bare unclickable
ids with no icon, and `baseline` was not even offered as a filter option.

This lives in the backend suite rather than the frontend one because
`tsconfig.json` sets ``"types": []`` — the frontend is browser-only and has no
`@types/node`, so a vitest file cannot read `search.py` off disk without adding
a dependency. pytest has no such constraint. The direction of the check is what
matters, not which runner performs it.

The obvious version of this test — comparing the map against a second list of
backend kinds kept beside it in TypeScript — passes happily while both of the
kinds it exists to catch are missing. So parse both real sources.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SEARCH_PY = REPO / "backend" / "app" / "services" / "search.py"
SEARCH_KINDS_TS = REPO / "frontend" / "src" / "lib" / "searchKinds.ts"

# `if not kind or kind == "requirement":` — one branch per searchable kind.
_BRANCH_RE = re.compile(r'if not kind or kind == "([a-z_]+)":')


def backend_kinds() -> list[str]:
    return list(dict.fromkeys(_BRANCH_RE.findall(SEARCH_PY.read_text())))


def _ts_block(name: str) -> str:
    """The body of a top-level `export const <name> = ... ;` declaration."""
    source = SEARCH_KINDS_TS.read_text()
    start = source.index(f"export const {name}")
    end = source.index("\n};", start) if "Record<" in source[start:start + 120] \
        else source.index("\n]", start)
    return source[start:end]


def frontend_mapped_kinds() -> list[str]:
    """Keys of `BACKEND_KIND_TO_ENTITY`."""
    return re.findall(r"^\s+([a-z_]+):", _ts_block("BACKEND_KIND_TO_ENTITY"),
                      re.MULTILINE)


def frontend_filter_kinds() -> list[str]:
    """Entries of `SEARCHABLE_KINDS`."""
    return re.findall(r"'([a-z_]+)'", _ts_block("SEARCHABLE_KINDS"))


def test_the_parsers_find_something():
    """Without this the rest of the module passes vacuously the moment either
    source is refactored past its regex — a rename would silence these tests
    rather than fail them."""
    assert len(backend_kinds()) >= 10, f"no kind branches parsed from {SEARCH_PY}"
    assert len(frontend_mapped_kinds()) >= 10, "BACKEND_KIND_TO_ENTITY did not parse"
    assert len(frontend_filter_kinds()) >= 10, "SEARCHABLE_KINDS did not parse"


@pytest.mark.parametrize("kind", backend_kinds())
def test_every_backend_kind_is_mapped(kind):
    assert kind in frontend_mapped_kinds(), (
        f'search.py returns "{kind}" but BACKEND_KIND_TO_ENTITY has no entry, '
        f"so those results render as an unlinked id"
    )


@pytest.mark.parametrize("kind", backend_kinds())
def test_every_backend_kind_is_offered_as_a_filter(kind):
    assert kind in frontend_filter_kinds(), (
        f'search.py returns "{kind}" but the search filter does not offer it'
    )


@pytest.mark.parametrize("kind", frontend_mapped_kinds())
def test_the_map_claims_no_kind_the_backend_cannot_return(kind):
    assert kind in backend_kinds(), (
        f'BACKEND_KIND_TO_ENTITY maps "{kind}", which search.py never returns'
    )
