"""Read-side trust boundary: YAML arriving by git pull or a hand edit.

The store's project directory is git-tracked and human-editable by design, so
these tests write files directly rather than going through the API — that is
precisely the input path the API's validators never see.
"""

import io
import tempfile
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.services.fingerprint import compute_fingerprint
from app.services.load_guard import is_safe_id, validate_on_load
from app.services.yaml_store import YamlStore


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "proj"
    (root / "requirements").mkdir(parents=True)
    return YamlStore(str(root))


def _write(store_root: Path, name: str, body: str) -> None:
    (Path(store_root) / "requirements" / name).write_text(body)


# ── Hostile ids are withheld, not patched ────────────────────────────────────

@pytest.mark.parametrize("bad_id", [
    "../../../etc/cron.d/pwn",
    "/etc/passwd",
    "..",
    "a/../../b",
    "-rf",                    # would be read as a flag by a subprocess
    "",
])
def test_hostile_id_is_withheld_from_every_reader(store, bad_id):
    _write(store._root, "evil.yaml", f"id: {bad_id!r}\nname: Bad\n")
    _write(store._root, "ok.yaml", "id: REQ-001\nname: Fine\n")

    served = [r["id"] for r in store.list_requirements()]
    assert served == ["REQ-001"], f"{bad_id!r} was served"


def test_withheld_file_is_reported_not_silently_dropped(store):
    """A file that vanishes from every view without explanation is worse than
    one that errors — the operator has no way to find out why."""
    _write(store._root, "evil.yaml", "id: ../../../etc/passwd\nname: Bad\n")

    reported = store.corrupt_files()
    assert len(reported) == 1
    assert reported[0]["path"] == "requirements/evil.yaml"
    assert "traversal" in reported[0]["error"]


def test_safe_ids_are_accepted():
    for good in ("REQ-001", "SYS 1", "a.b.c", "Z9", "REQ-001 rev B"):
        assert is_safe_id(good), good
    for bad in ("../x", "/x", "", "  ", None, 7, ".hidden", "a/b"):
        assert not is_safe_id(bad), bad


# ── Stored XSS arriving off disk ─────────────────────────────────────────────

def test_script_in_hand_edited_description_is_stripped_on_read(store):
    _write(store._root, "a.yaml",
           "id: REQ-001\ndescription: '<p>ok<script>steal()</script></p>'\n")

    assert store.list_requirements()[0]["description"] == "<p>ok</p>"


def test_event_handler_attribute_is_stripped_on_read(store):
    _write(store._root, "a.yaml",
           "id: REQ-001\ndescription: '<img src=x onerror=alert(1)>'\n")

    assert "onerror" not in store.list_requirements()[0]["description"]


def test_sanitisation_reaches_the_publisher_not_just_the_api(store):
    """The guard runs at the store's read path, so consumers that never touch
    a route — publisher, evaluator, search — are covered too."""
    _write(store._root, "a.yaml",
           "id: REQ-001\nname: N\ndescription: '<p>x<script>bad()</script></p>'\n")

    for req in store.list_requirements():
        assert "<script>" not in req["description"]


# ── What the guard must NOT do ───────────────────────────────────────────────

def test_load_does_not_change_review_fingerprints(store):
    """Filling in defaults at load time would change the canonical form of
    every requirement that omitted a field, flipping it to "unreviewed" and
    silently invalidating the review state of every existing project."""
    _write(store._root, "a.yaml",
           "id: REQ-001\nname: Minimal\ndescription: 'plain text'\n")

    on_disk = {"id": "REQ-001", "name": "Minimal", "description": "plain text"}
    loaded = store.list_requirements()[0]

    assert compute_fingerprint(loaded) == compute_fingerprint(on_disk)


def test_load_does_not_invent_absent_fields(store):
    _write(store._root, "a.yaml", "id: REQ-001\nname: Minimal\n")

    assert set(store.list_requirements()[0]) == {"id", "name"}


def test_unrecognised_enum_values_are_preserved(store):
    """`type: design` is not in RequirementType, but the coverage model matches
    a requirement's type against a downstream `needs` entry — rewriting it to
    `functional` silently breaks the trace."""
    _write(store._root, "a.yaml", "id: REQ-001\ntype: design\nstatus: bespoke\n")

    loaded = store.list_requirements()[0]
    assert loaded["type"] == "design"
    assert loaded["status"] == "bespoke"


def test_plain_text_description_is_returned_verbatim(store):
    _write(store._root, "a.yaml", "id: REQ-001\ndescription: 'no markup at all'\n")

    assert store.list_requirements()[0]["description"] == "no markup at all"


# ── Structural repair ────────────────────────────────────────────────────────

def test_scalar_where_a_list_belongs_is_coerced(store):
    """A merge conflict shouldn't 500 every consumer that iterates the field."""
    _write(store._root, "a.yaml", "id: REQ-001\nparameters: 'not a list'\n")

    assert store.list_requirements()[0]["parameters"] == []


def test_hostile_entity_references_are_dropped(store):
    _write(store._root, "a.yaml", """
id: REQ-001
parent: ../../escape
verification_cases: ['../../../etc/passwd', 'VC-1']
relations:
  - {type: derives, target: ../../../etc/passwd}
  - {type: derives, target: REQ-002}
""")

    loaded = store.list_requirements()[0]
    assert loaded["parent"] is None
    assert loaded["verification_cases"] == ["VC-1"]
    assert [r["target"] for r in loaded["relations"]] == ["REQ-002"]


def test_validate_on_load_is_a_noop_for_unknown_collections():
    """Collections with no specific validator still get the id and HTML checks
    rather than being passed through unguarded."""
    item = validate_on_load("risks", {"id": "RSK-1", "description": "<script>x</script>ok"})
    assert item is not None and "<script>" not in item["description"]
    assert validate_on_load("risks", {"id": "../../x"}) is None


# ── XLSX import bounds ───────────────────────────────────────────────────────

def _workbook_bytes(rows: int) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["ID", "Name", "Description", "Status", "Priority", "Type"])
    for i in range(rows):
        ws.append([f"REQ-{i:05d}", f"Requirement number {i}",
                   "The system shall perform the designated function.",
                   "proposed", "medium", "functional"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_zip_bomb_is_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/worksheets/sheet1.xml", b"\0" * (300 * 1024 * 1024))

    from app.services.table_io import _check_xlsx_zip_bomb
    with pytest.raises(ValueError, match="compression ratio"):
        _check_xlsx_zip_bomb(buf.getvalue())


def test_row_count_is_exact_not_estimated():
    """The bound was previously `max(row_tags, size / 100)`; the size term
    over-estimates by ~4x and dominated, so a legitimate 25k-row import was
    rejected as "107,119 rows"."""
    from app.services.table_io import _count_xlsx_rows

    assert _count_xlsx_rows(_workbook_bytes(25_000)) == 25_001  # + header


def test_oversized_workbook_is_still_rejected():
    from app.services.table_io import _count_xlsx_rows, MAX_XLSX_ESTIMATED_ROWS

    with pytest.raises(ValueError, match="exceeds limit"):
        _count_xlsx_rows(_workbook_bytes(MAX_XLSX_ESTIMATED_ROWS + 1000))
