"""The demo project must actually exercise the features it ships alongside.

The demo is both the shop window and the e2e fixture, so a feature with no demo
data gets almost no end-to-end coverage. System states shipped with no demo data
at all: the System States page rendered empty from the day it was added, and
`pages.spec.ts` only ever walked it blank.

These assertions are deliberately about *presence and shape*, not exact content —
the demo should be free to change which requirement is tagged with what without
breaking a test.
"""
import pathlib
import tempfile

import pytest

from app.services.demo_seed import PROJECT_ID, seed_demo_project
from app.services.yaml_store import YamlStore


@pytest.fixture(scope="module")
def demo():
    root = pathlib.Path(tempfile.mkdtemp())
    seed_demo_project(root)
    return YamlStore(root / PROJECT_ID)


def test_project_defines_system_states(demo):
    states = demo.read_meta().get("system_states") or []
    assert len(states) >= 5, "the System States page needs content to be worth walking"
    for s in states:
        assert s.get("name"), "a state without a name cannot be referenced"
        assert s.get("description"), "the page shows descriptions; blank ones look broken"


def test_requirements_reference_the_defined_states(demo):
    defined = {s["name"] for s in demo.read_meta().get("system_states") or []}
    reqs = demo.list_requirements()
    tagged = [r for r in reqs if r.get("system_states")]

    assert tagged, "no requirement uses a system state, so the field is never exercised"

    # Every referenced state must be defined on the project. An undefined name
    # renders as an orphan chip, which is a real state the UI handles but a poor
    # thing for the demo to be teaching.
    used = {name for r in tagged for name in r["system_states"]}
    assert used <= defined, f"undefined states referenced: {sorted(used - defined)}"


def test_states_are_used_selectively(demo):
    """Not every requirement should be tagged.

    A requirement with no states applies in all of them. Tagging everything
    would make the field noise, and would stop the demo showing that filtering
    on a state is useful.
    """
    reqs = demo.list_requirements()
    tagged = [r for r in reqs if r.get("system_states")]
    assert 0 < len(tagged) < len(reqs), (
        f"{len(tagged)} of {len(reqs)} tagged — the field is only meaningful "
        "if some requirements are phase-specific and others are not"
    )
