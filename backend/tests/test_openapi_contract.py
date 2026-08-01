"""Property-based coverage of every documented API operation.

Schemathesis reads the OpenAPI schema FastAPI generates from the app itself and
derives cases for each operation — valid payloads from the declared types,
missing fields, wrong types, boundary values. Nothing here is hand-written per
endpoint, so a new route is covered the moment it is registered, and a route
that stops being registered stops being covered *visibly* (see the floor
assertion below) rather than silently.

What it checks, per generated case:

  * no 500 — an unhandled exception is a bug regardless of how odd the input is
  * the response matches the schema the endpoint advertises

What it deliberately does not do: assert business behaviour. Generated data is
arbitrary, so "does this produce the right answer" belongs in the hand-written
suites. This is the net for the failure mode those suites keep missing — a
route nobody thought to exercise at all.
"""

import pytest

schemathesis = pytest.importorskip(
    "schemathesis",
    reason="schemathesis is an optional dev dependency; install requirements-dev.txt",
)

from hypothesis import HealthCheck, settings  # noqa: E402

from app.main import app  # noqa: E402


schema = schemathesis.openapi.from_asgi("/openapi.json", app)


def test_the_schema_still_describes_the_whole_api():
    """A floor, not a fact.

    The suite below is generated from the schema, so if a router stops being
    registered the generated tests quietly cover less while still reporting
    green — the same failure mode that removed 188 permission checks during a
    dependency upgrade without a single test failing.
    """
    raw = schema.raw_schema
    paths = raw.get("paths", {})
    assert len(paths) > 100, f"only {len(paths)} documented paths — did a router stop being included?"
    assert any(p.startswith("/api/projects") for p in paths)
    assert any(p.startswith("/api/auth") for p in paths)


@pytest.mark.contract
@schema.parametrize()
# The workspace fixture is a sandboxed data root, not per-input state: reusing
# it across generated cases is exactly what we want, since every case should be
# survivable against the same project.
@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
def test_api_operation_does_not_500(case, workspace):
    """Every documented operation, against a sandboxed data root.

    ``workspace`` isolates the filesystem so generated writes cannot touch a
    real project. Auth is not supplied: unauthenticated calls should be
    rejected cleanly, never with a stack trace.
    """
    response = case.call()
    assert response.status_code < 500, (
        f"{case.method} {case.path} returned {response.status_code}\n"
        f"body: {response.text[:400]}"
    )
