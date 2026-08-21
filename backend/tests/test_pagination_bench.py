"""Pagination benchmark: is a maintained index worth it?

The requirements list endpoint materialises the whole collection (and, with the
collection cache, copies the whole cached list on every request) and only then
slices out the requested page — so ``limit=1`` costs the same as ``limit=500``.
This test measures that cost at 100, 1,000 and 10,000 requirements: wall time
for the first, middle and last page, plus the peak memory of the cold
materialisation.

The benchmark is marked ``contract`` (the repo's registered "slow" marker — see
pytest.ini) so it does not run in the default fast suite. Run it explicitly:

    pytest tests/test_pagination_bench.py -m contract -s

The numbers it prints are the deliverable: they decide whether a maintained
index earns its complexity, or whether the collection cache already makes
pagination cheap enough to leave alone.

A fast, always-run test (`test_pagination_pages_are_correct_and_complete`)
pins the pagination contract the benchmark relies on, so the default suite
still guards first/middle/last-page ordering even when the benchmark itself is
deselected.
"""
from __future__ import annotations

import time
import tracemalloc

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import yaml_store
from tests.conftest import make_req

PAGE_SIZE = 50
SIZES = (100, 1_000, 10_000)


def _write_requirement(d, i: int) -> None:
    """One minimal requirement file, written directly (not via the API) so
    generating 10,000 of them is a matter of seconds, not minutes."""
    (d / f"REQ-{i:05d}.yaml").write_text(
        f"id: REQ-{i:05d}\n"
        f"name: Requirement {i:05d}\n"
        f"description: >-\n  Requirement number {i:05d}.\n",
    )


@pytest.fixture(scope="session")
def pagination_projects(tmp_path_factory):
    """The three benchmark projects, generated once for the whole session."""
    root = tmp_path_factory.mktemp("pagination_bench")
    for n in SIZES:
        proj = root / f"n{n}"
        (proj / "requirements").mkdir(parents=True)
        (proj / "verification_cases").mkdir(parents=True)
        (proj / "_meta.yaml").write_text(
            "name: bench\ncreated: 2026-01-01T00:00:00+00:00\n",
        )
        for i in range(n):
            _write_requirement(proj / "requirements", i)
    return root


def _get_page(client: TestClient, project_id: str, offset: int) -> dict:
    r = client.get(
        f"/api/projects/{project_id}/requirements",
        params={"offset": offset, "limit": PAGE_SIZE},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_pagination_pages_are_correct_and_complete(client, project):
    """First/middle/last pages slice the full ordered collection correctly.

    This is the correctness baseline the benchmark rests on, and the contract
    any future index must not break: same ids, same order, and ``total`` is
    always the full collection size rather than the page size.
    """
    for i in range(120):
        make_req(client, project, f"REQ-{i:03d}")

    def ids(offset: int, limit: int = PAGE_SIZE) -> list[str]:
        res = client.get(
            f"/api/projects/{project}/requirements",
            params={"offset": offset, "limit": limit},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["total"] == 120
        return [it["id"] for it in body["items"]]

    assert ids(0) == [f"REQ-{i:03d}" for i in range(50)]
    assert ids(50) == [f"REQ-{i:03d}" for i in range(50, 100)]
    assert ids(100) == [f"REQ-{i:03d}" for i in range(100, 120)]
    assert ids(200) == []
    assert ids(0, limit=1) == ["REQ-000"]


@pytest.mark.contract
def test_pagination_benchmark(pagination_projects, monkeypatch):
    """Print the cost of a page, at each size, and leave the numbers visible.

    Only asserts correctness (page shapes and ordering); the timing and memory
    figures are printed, not asserted, because they are the evidence the index
    decision is made on, not a property to flake on a busy CI box.
    """
    monkeypatch.setattr(settings, "data_root", str(pagination_projects))
    monkeypatch.setattr(settings, "git_autocommit", False)
    monkeypatch.setattr(settings, "seed_demo", False)
    monkeypatch.setattr(settings, "require_auth", False)

    with TestClient(app) as client:
        rows = []
        for n in SIZES:
            project_id = f"n{n}"
            mid_offset = (n // 2) // PAGE_SIZE * PAGE_SIZE
            last_offset = max(0, n - PAGE_SIZE)

            # Cold materialisation: first request for this directory, so the
            # cache is filled here. Peak memory is measured on this path — it is
            # the worst case, parsing every file and holding the whole
            # collection at once.
            yaml_store.invalidate_cache()
            tracemalloc.start()
            t0 = time.perf_counter()
            cold_page = _get_page(client, project_id, 0)
            cold = time.perf_counter() - t0
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            # Sanity: the cold first page is complete and correctly ordered.
            assert cold_page["total"] == n
            assert [it["id"] for it in cold_page["items"]] == [
                f"REQ-{i:05d}" for i in range(PAGE_SIZE)
            ]

            def timed(offset: int, project_id: str = project_id, n: int = n) -> float:
                t0 = time.perf_counter()
                page = _get_page(client, project_id, offset)
                assert page["total"] == n
                return time.perf_counter() - t0

            warm_first = timed(0)
            warm_mid = timed(mid_offset)
            warm_last = timed(last_offset)

            rows.append((n, cold, warm_first, warm_mid, warm_last, peak))

    print("\nPagination benchmark (page size=%d):" % PAGE_SIZE)
    print("  requirements  cold 1st pg  warm 1st pg  warm middle  warm last   peak mem")
    for n, cold, warm_first, warm_mid, warm_last, peak in rows:
        print(
            "  %12d  %9.1f ms  %10.1f ms  %11.1f ms  %9.1f ms  %7.1f MiB"
            % (n, cold * 1000, warm_first * 1000, warm_mid * 1000, warm_last * 1000, peak / 2**20)
        )
