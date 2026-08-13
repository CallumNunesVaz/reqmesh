"""The generated API reference must be checked in up to date.

`gen_api_reference.py` derives `docs/api.md` from the live OpenAPI schema, the
same way `gen_schemas.py` derives `schemas/` and `gen_write_models.py` derives
`frontend/src/api/generated/writeModels.ts`. CI regenerates and diffs the file;
this is the fast, local version of that check.

It also guards against the generator going silently empty — a change that made
it stop finding routes would make both this test and the CI diff pass vacuously,
exactly the failure `test_search_kind_coverage.py` guards against with its
parser sanity assertions. The route-count floor and the "nothing lands in
*Other*" check are that guard here: an uncategorised route is a signal that a
new entity kind was added without a reference section.
"""
from __future__ import annotations

import gen_api_reference


def test_generator_finds_the_routes():
    """The generator must enumerate a healthy number of routes, or this test and
    the CI gate both pass vacuously when the schema stops yielding anything."""
    rendered = gen_api_reference.render()
    route_rows = [
        line for line in rendered.splitlines()
        if line.startswith("| ") and "`/api/" in line
    ]
    assert len(route_rows) >= 150, (
        f"gen_api_reference found only {len(route_rows)} routes — the generator "
        "has gone quiet and the CI gate would no longer catch drift"
    )


def test_no_route_lands_in_the_uncategorised_section():
    """Every route must be classified into a named section. A route falling into
    *Other* means a new resource was added without a reference section, which is
    exactly the silent drop the section map exists to prevent."""
    rendered = gen_api_reference.render()
    assert "## Other" not in rendered.split("## "), (
        "a route is uncategorised — add it to _RESOURCE_SECTION in "
        "gen_api_reference.py, then regenerate"
    )


def test_generated_reference_is_current():
    assert gen_api_reference.OUT.read_text() == gen_api_reference.render(), (
        f"{gen_api_reference.OUT} is out of date — run "
        "`backend/.venv/bin/python backend/gen_api_reference.py` and commit the "
        "result."
    )
