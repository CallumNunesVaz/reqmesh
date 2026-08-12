"""The generated TypeScript write contract must be checked in up to date.

`gen_write_models.py` derives the `*Create` / `*Update` interfaces in
`frontend/src/api/generated/writeModels.ts` from the Pydantic models, the same
way `gen_schemas.py` derives `schemas/`. CI regenerates and diffs the file;
this is the fast, local version of that check.

It also guards against the generator going silently empty — a rename that made
`discover_write_models` find nothing would make both this test and the CI diff
pass vacuously, exactly the failure `test_search_kind_coverage.py` guards
against with its parser sanity assertions.

Lives in the backend suite because `tsconfig.json` sets ``"types": []`` — no
`@types/node`, so a vitest file cannot read the generated file off disk.
"""
from __future__ import annotations

import gen_write_models

#: The generated file must encode the required/optional asymmetry — a field the
#: API requires (`id`, `expr`) is required on the TS side, and a field the API
#: defaults (`name`) is optional. This is the whole value of the generator: a
#: version that marks everything optional is `Partial<Entity>` with extra steps.
REQUIRED_FIELD_PROBES = {
    "RequirementCreate": ["  id: string;"],
    "DefinitionCreate": ["  id: string;", "  expr: string;"],
    "ChangeRequestCreate": ["  id: string;"],
    "RiskCreate": ["  id: string;"],
}
OPTIONAL_FIELD_PROBES = {
    "RequirementCreate": ["  name?: string;", "  type?: string;"],
    "DefinitionCreate": ["  name?: string;"],
}


def _interface_body(name: str) -> str:
    """The text of `export interface <name> { ... }` in the committed file."""
    source = gen_write_models.render()
    start = source.index(f"export interface {name} {{")
    end = source.index("\n}", start)
    return source[start:end]


def test_generator_finds_the_write_models():
    names = {m.__name__ for m in gen_write_models.discover_write_models()}
    assert {
        "RequirementCreate", "RequirementUpdate",
        "ComponentCreate", "ComponentUpdate",
        "DecisionRecordCreate", "DecisionRecordUpdate",
    } <= names


def test_required_fields_are_required_and_defaults_are_optional():
    for name, probes in REQUIRED_FIELD_PROBES.items():
        body = _interface_body(name)
        for probe in probes:
            assert probe in body, f"{name} should require {probe.strip()}, got:\n{body}"
    for name, probes in OPTIONAL_FIELD_PROBES.items():
        body = _interface_body(name)
        for probe in probes:
            assert probe in body, f"{name} should mark {probe.strip()} optional, got:\n{body}"


def test_generated_write_models_file_is_current():
    assert gen_write_models.OUT.read_text() == gen_write_models.render(), (
        f"{gen_write_models.OUT} is out of date — run `python gen_write_models.py` "
        "from backend/ and commit the result."
    )
