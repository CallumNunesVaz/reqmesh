"""The hand-written TypeScript read interfaces must match the Pydantic read models.

The write contract is generated (`gen_write_models.py`) and CI-diffed; the read
side is ~80 `export interface` blocks in `frontend/src/api/client.ts` maintained
by hand, so a backend field rename mismatches silently and only surfaces at
runtime. Codegen cannot close the gap — no route declares `response_model`, so
every OpenAPI response schema is `{}` — so this test gates the drift instead.

Seventeen TS interfaces share a name with a Pydantic read model (the classes in
`app/models/` that are not `*Create` / `*Update` / `*Request`). This test parses
`client.ts`, finds those name-matched interfaces, and asserts the field *names*
agree — in both directions, so a Pydantic field the interface omits and an
interface field the model never serialises are both failures.

It checks names only. Optional/`| null` on the TS side and `Optional[...]` on
the Pydantic side are not compared — a field is a field whether or not it may be
absent. Do not assume this test covers type or nullability parity.

Like `test_write_models_currency.py` and `test_search_kind_coverage.py`, this
lives in the backend suite because `frontend/tsconfig.json` sets ``"types": []``
— no `@types/node`, so a vitest file cannot read a file off disk.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
import re
from pathlib import Path

import pytest
from pydantic import BaseModel

import app.models

REPO = Path(__file__).resolve().parents[2]
CLIENT_TS = REPO / "frontend" / "src" / "api" / "client.ts"

#: The name-matched pairs this test was written around. A parser that matches
#: nothing — or the wrong seventeen — must fail, not pass.
EXPECTED_PAIRS = {
    "AnalysisCase", "BaselineDef", "ChangeRequest", "Comment", "Component",
    "Constraint", "DecisionRecord", "Definition", "Measurement", "Parameter",
    "Reference", "Requirement", "RequirementTreeNode", "Risk",
    "Specification", "TraceLink", "VerificationCase",
}

#: Exclude the write models. `Request` is deliberately absent — the entity is
#: literally named `ChangeRequest`, and it is a read model (its `*Create` /
#: `*Update` siblings are the write models). The `*Request` DTOs all live in
#: `app/api/`, which this walk never touches.
_READ_MODEL_SUFFIXES = ("Create", "Update")

_INTERFACE_RE = re.compile(r"export\s+interface\s+([A-Za-z_]\w*)\s*\{")
_FIELD_LINE_RE = re.compile(r"^\s*([A-Za-z_]\w*)(\s*\?)?\s*:", re.MULTILINE)


# ── Pydantic side ─────────────────────────────────────────────────────────────

def discover_read_models() -> list[type[BaseModel]]:
    """Every Pydantic class in `app.models` that is not a `*Create`/`*Update`
    write model. `ChangeRequest` counts as a read model despite the name —
    its write forms are `ChangeRequestCreate`/`ChangeRequestUpdate`.

    Walks the package the same way `gen_write_models.discover_write_models`
    does, and restricts to classes *defined* in their module — `risk.py`
    re-exports `Comment`/`DecisionRecord` and would otherwise duplicate them.
    """
    found: list[type[BaseModel]] = []
    for info in pkgutil.iter_modules(app.models.__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"app.models.{info.name}")
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if obj is BaseModel or not issubclass(obj, BaseModel):
                continue
            if obj.__module__ != module.__name__:
                continue
            if obj.__name__.endswith(_READ_MODEL_SUFFIXES):
                continue
            found.append(obj)
    found.sort(key=lambda m: m.__name__)
    return found


def json_field_names(model: type[BaseModel]) -> set[str]:
    """Field names as they reach JSON — the serialisation alias wins over the
    Python attribute name, since the alias is what the client actually sees."""
    return {
        field.serialization_alias or field.alias or name
        for name, field in model.model_fields.items()
    }


# ── TypeScript side ───────────────────────────────────────────────────────────

def _interface_body(source: str, start: int) -> tuple[str, int]:
    """The text of the interface body opened at *start*, and the index just past
    its closing brace. Braces are counted so inline object/`Record<>` types do
    not truncate the body."""
    depth = 1
    i = start
    while i < len(source):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i], i + 1
        i += 1
    raise ValueError("interface opened but never closed")


def parse_ts_interfaces(source: str) -> dict[str, set[str]]:
    """Map each `export interface <Name>` to its top-level field names.

    The interfaces are flat, generated-style blocks, so a line-start regex is
    enough; but a block that yields no fields raises rather than passing
    vacuously.
    """
    interfaces: dict[str, set[str]] = {}
    for match in _INTERFACE_RE.finditer(source):
        name = match.group(1)
        body, _ = _interface_body(source, match.end())
        fields = {m.group(1) for m in _FIELD_LINE_RE.finditer(body)}
        if not fields:
            raise ValueError(f"interface {name} parsed with no fields")
        interfaces[name] = fields
    return interfaces


READ_MODEL_FIELDS = {m.__name__: json_field_names(m) for m in discover_read_models()}
TS_INTERFACES = parse_ts_interfaces(CLIENT_TS.read_text())
MATCHED = {
    name: (READ_MODEL_FIELDS[name], TS_INTERFACES[name])
    for name in READ_MODEL_FIELDS.keys() & TS_INTERFACES.keys()
}


#: TS-only fields that are correct: the API computes them on read and serves
#: them, so `client.ts` declaring them is right and the Pydantic model not
#: carrying them is also right. These are NOT drift.
#:
#: An allowlist like this is exactly how a real drift gets hidden, so every
#: entry is paid for: `test_computed_fields_are_actually_served` below asserts
#: each one appears in a live response. Delete `rating` from the API and that
#: test fails — the allowlist cannot cover for it.
COMPUTED_FIELDS = {
    # router.py:863 / collab_routes.py:300 — 1-based index in `_meta.yaml`.
    "BaselineDef": {"order"},
    # extra_routes.py:292 via risk_matrix.apply_rating — derived from the
    # project's risk matrix on read, never stored, so re-tuning the matrix
    # re-rates the whole register at once.
    "Risk": {"rating"},
}


def _pair_params():
    for name in sorted(MATCHED):
        yield pytest.param(name)


# ── Anti-vacuity ──────────────────────────────────────────────────────────────

def test_parser_finds_the_seventeen_matching_interfaces():
    """The parser must match at least the 17 known pairs and see a real field;
    a parser that silently matches nothing passes this whole module for free."""
    missing = sorted(EXPECTED_PAIRS - set(MATCHED))
    assert not missing, f"parser matched no interface for: {missing}"
    assert "id" in MATCHED["Requirement"][1], "Requirement.id did not parse from client.ts"


# ── Field-name parity ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", list(_pair_params()))
def test_interface_and_model_field_names_agree(name):
    pydantic_fields, ts_fields = MATCHED[name]
    pydantic_only = sorted(pydantic_fields - ts_fields)
    ts_only = sorted(ts_fields - pydantic_fields - COMPUTED_FIELDS.get(name, set()))
    assert not pydantic_only, (
        f"{name}: Pydantic serialises {pydantic_only}, which client.ts omits — "
        "the client cannot see data the API sends"
    )
    assert not ts_only, (
        f"{name}: client.ts declares {ts_only}, which the Pydantic read model "
        "does not serialise"
    )


# ── Live responses ────────────────────────────────────────────────────────────

LIVE_ROUTES = [
    ("Requirement", "requirements", "REQ-1"),
    ("Component", "components", "CMP-1"),
    ("ChangeRequest", "change-requests", "CR-1"),
]


def _create(client, project_id: str, kind: str, entity_id: str) -> None:
    res = client.post(f"/api/projects/{project_id}/{kind}", json={"id": entity_id})
    assert res.status_code == 201, res.text


@pytest.mark.parametrize("interface_name, kind, entity_id", LIVE_ROUTES)
def test_live_response_keys_are_a_subset_of_the_interface(
    client, project, interface_name, kind, entity_id
):
    _create(client, project, kind, entity_id)
    res = client.get(f"/api/projects/{project}/{kind}/{entity_id}")
    assert res.status_code == 200, res.text
    body = res.json()
    ts_fields = MATCHED[interface_name][1]
    extra = sorted(set(body) - ts_fields)
    assert not extra, (
        f"{interface_name} detail response carries keys client.ts does not "
        f"declare: {extra}"
    )


#: Each computed field in COMPUTED_FIELDS, and the list route that serves it.
COMPUTED_FIELD_ROUTES = [
    ("Risk", "rating", "risks", "RISK-1"),
    ("BaselineDef", "order", "baselines", None),
]


@pytest.mark.parametrize("interface_name, field, kind, entity_id", COMPUTED_FIELD_ROUTES)
def test_computed_fields_are_actually_served(
    client, project, interface_name, field, kind, entity_id
):
    """The COMPUTED_FIELDS allowlist must be paid for by a real response.

    Without this, the allowlist is just a quieter `xfail`: anyone could silence
    a genuine drift by adding a name to it. Here each entry has to prove the API
    still serves the field it excuses — delete `rating` from the risks route and
    this fails, even though the parity test above would go on passing.
    """
    assert field in COMPUTED_FIELDS[interface_name], (
        f"{interface_name}.{field} is asserted here but not allowlisted — "
        "the two lists have drifted apart"
    )
    if entity_id is not None:
        _create(client, project, kind, entity_id)
    else:
        # Baseline definitions live in `_meta.yaml`, not a collection — there is
        # no POST /baselines to seed one, and an empty project would make the
        # assertion below pass vacuously.
        res = client.patch(f"/api/projects/{project}", json={"baselines": ["BL1"]})
        assert res.status_code == 200, res.text
    res = client.get(f"/api/projects/{project}/{kind}")
    assert res.status_code == 200, res.text
    items = res.json()
    if isinstance(items, dict):
        items = items.get("items", [])
    assert items, f"no {kind} returned; the check would pass vacuously"
    assert all(field in item for item in items), (
        f"{kind} response no longer carries the computed `{field}` that "
        f"COMPUTED_FIELDS[{interface_name!r}] exists to excuse — either the API "
        f"changed or the allowlist entry is now wrong"
    )
