from __future__ import annotations

import contextlib
import hashlib
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from ruamel.yaml import YAML

from app.core.filelock import file_lock
from app.core.ids import safe_id


# Re-exported under the original private name so existing call sites keep
# working; the implementation moved to core so core.auth can share it.
_file_lock = file_lock

def _round_trip_yaml() -> YAML:
    """A round-trip YAML for exactly one load or dump.

    Not shared, and deliberately not shared-plus-locked, which is what this was
    before. A ruamel instance carries emitter state on the object: a dump that
    raises part-way leaves it mid-document, and *every* later dump in the process
    then fails with `expected DocumentEndEvent, but got DocumentStartEvent`. A
    lock stops two threads interleaving but cannot un-poison the object, so one
    failed write turned every subsequent save in that worker into a 500 until the
    process was restarted — 56 of them in production before a container recreate
    cleared it, with "Internal Server Error" the only thing the user saw.

    Constructing one is cheap; parsing is what costs, which is why the read-only
    list path has its own fast loader and the collection cache exists. Per-call
    instances remove the failure mode rather than narrowing it.
    """
    y = YAML()
    y.indent(mapping=2, sequence=4, offset=2)
    y.preserve_quotes = True
    y.width = 120
    return y

# Round-trip mode is what preserves a user's comments and formatting through an
# edit — a core promise of a git-native, hand-editable store — but it is ~6.5x
# slower to parse than safe mode. So: round-trip on the read-modify-write path
# (`_parse_yaml`), and this fast loader on the read-only list path, where the
# document is never written back and comments therefore can't be lost.
def _fast_reader() -> YAML:
    """Safe-mode loader for the read-only list path, also per-call.

    A poisoned loader is as fatal as a poisoned emitter, and for the same reason
    — the state lives on the object.
    """
    return YAML(typ="safe")

# Cache of parsed collections, keyed by directory. Invalidated by comparing a
# cheap signature of the directory (each file's mtime_ns + size) — one scandir
# instead of re-parsing every file on every call. Without it a single page load
# re-parsed the whole project a dozen times over.
_collection_cache: dict[str, tuple[tuple, list[dict]]] = {}
_cache_lock = threading.Lock()


def _dir_signature(d: Path) -> tuple:
    """Fingerprint a collection directory: (name, mtime_ns, size) per file."""
    try:
        with os.scandir(d) as it:
            entries = []
            for e in it:
                if not e.name.endswith(".yaml"):
                    continue
                st = e.stat()
                entries.append((e.name, st.st_mtime_ns, st.st_size))
        return tuple(sorted(entries))
    except OSError:
        return ()


def invalidate_cache(path: Optional[Path] = None) -> None:
    """Drop cached collections. Called after every write.

    When *path* is a file, only the file's parent directory is invalidated.
    This is still a whole-collection drop, but it's targeted to the affected
    collection rather than clearing everything. A per-file invalidation would
    need to re-read the directory signature and merge the changed file into
    the cached list, which is safe to add later.
    """
    with _cache_lock:
        if path is None:
            _collection_cache.clear()
        else:
            _collection_cache.pop(str(path.parent), None)

# Every entity type is a directory of one-YAML-file-per-item. New entity
# types only need an entry here.
COLLECTIONS = (
    "requirements",
    "specifications",
    "verification_cases",
    "components",
    "change_requests",
    "risks",
    "comments",
    "decisions",
    "baselines",
    "definitions",
    "analysis_cases",
)

# Created eagerly so an empty project has a recognizable shape.
CORE_COLLECTIONS = ("requirements", "specifications", "verification_cases")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class YamlStore:
    """One project directory of human-readable YAML files.

    All writes are atomic (temp file + rename) so a crash mid-write never
    leaves a truncated file in the git working tree.
    """

    def __init__(self, project_root: Path):
        self._root = Path(project_root)
        self._traces_file = self._root / "traces" / "traces.yaml"
        self._meta_file = self._root / "_meta.yaml"

    @property
    def root(self) -> Path:
        return self._root

    def ensure_dirs(self) -> None:
        for name in CORE_COLLECTIONS:
            (self._root / name).mkdir(parents=True, exist_ok=True)
        self._traces_file.parent.mkdir(parents=True, exist_ok=True)

    def _parse_yaml(self, path: Path) -> dict:
        """Parse one YAML file, **raising** on malformed content.

        Callers that can meaningfully skip or refuse (entity collections,
        read-modify-write) use this; structural reads that have a sensible
        empty value use :meth:`_read_yaml`.
        """
        with open(path) as f:
            data = _round_trip_yaml().load(f)
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ValueError(f"expected a mapping, got {type(data).__name__}")
        return data

    def _read_yaml(self, path: Path) -> dict:
        """Tolerant read for structural files (meta, traces, history) where an
        empty mapping is a reasonable fallback. Never use this for entity files:
        an unparseable requirement must be skipped, not turned into ``{}``."""
        try:
            return self._parse_yaml(path)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Failed to read YAML %s: %s", path, exc)
            return {}

    def _write_yaml(self, path: Path, data: dict) -> None:
        # Any write invalidates the cached parse of its collection. The mtime
        # signature would catch it anyway, but only at ~1s granularity on some
        # filesystems — an explicit drop avoids a stale read right after a save.
        invalidate_cache(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                _round_trip_yaml().dump(data, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
            # Fsync the directory *after* the rename, so the new directory
            # entry itself is durable. Doing it before only flushes the entry
            # for the temp file, which the rename then replaces — the crash
            # window this exists to close stayed wide open.
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            os.unlink(tmp)
            raise

    # --- _meta ---

    def read_meta(self) -> dict:
        if not self._meta_file.exists():
            return {"name": self._root.name, "created": _now()}
        return self._read_yaml(self._meta_file)

    def write_meta(self, data: dict) -> None:
        self._write_yaml(self._meta_file, data)

    # --- Generic collections ---

    def _item_path(self, collection: str, item_id: str) -> Path:
        if collection not in COLLECTIONS:
            # A 400 rather than a bare ValueError: an unknown collection is a
            # bad request, and a typo in a route must not surface as a 500.
            raise HTTPException(status_code=400, detail=f"Unknown collection: {collection}")
        return self._root / collection / f"{safe_id(item_id)}.yaml"

    def _parse_fast(self, path: Path) -> dict:
        """Parse for read-only use. Same validation as :meth:`_parse_yaml`, but
        with the safe loader — never use the result for a write-back, as it
        carries no comments or formatting."""
        with open(path) as f:
            data = _fast_reader().load(f)
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ValueError(f"expected a mapping, got {type(data).__name__}")
        return data

    def list_items(self, collection: str) -> list[dict]:
        d = self._root / collection
        if not d.exists():
            return []

        key = str(d)
        signature = _dir_signature(d)
        with _cache_lock:
            hit = _collection_cache.get(key)
            if hit is not None and hit[0] == signature:
                # Copy so a caller mutating a result can't poison the cache.
                return [dict(item) for item in hit[1]]

        items = self._read_collection(d)
        with _cache_lock:
            _collection_cache[key] = (signature, [dict(i) for i in items])
        return items

    def _read_collection(self, d: Path) -> list[dict]:
        from app.services.load_guard import validate_on_load

        items = []
        for f in sorted(d.glob("*.yaml")):
            # A hand-edited file that no longer parses is skipped, not coerced
            # into `{}` — an empty dict flows downstream and raises KeyError
            # on `item["id"]`, taking out evaluation/validate/metrics with a
            # 500 that never mentions the offending file. See corrupt_files().
            try:
                item = self._parse_fast(f)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("Skipping corrupt YAML %s: %s", f, exc)
                continue
            if not item.get("id"):
                import logging
                logging.getLogger(__name__).warning("Skipping %s: no 'id' field", f)
                continue
            # Disk is not a trusted input: these dicts may have arrived by a
            # direct edit or a `git pull` rather than through the API. Doing
            # this here, on the cache-fill path, means every consumer of the
            # store gets it and the cost is paid once per directory generation.
            checked = validate_on_load(d.name, item)
            if checked is None:
                import logging
                logging.getLogger(__name__).warning(
                    "Skipping %s: unusable 'id' %r", f, item.get("id"))
                continue
            items.append(checked)
        return items

    def corrupt_files(self, collection: Optional[str] = None) -> list[dict]:
        """Entity files that ``list_items`` had to skip.

        Without this, corruption is invisible: the file simply stops appearing
        in the UI. Surfaced through the integrity check so it is reported
        rather than silently dropped.
        """
        from app.services.load_guard import id_rejection_reason

        out: list[dict] = []
        for name in ([collection] if collection else COLLECTIONS):
            d = self._root / name
            if not d.exists():
                continue
            for f in sorted(d.glob("*.yaml")):
                try:
                    item = self._parse_yaml(f)
                except Exception as exc:
                    out.append({"path": f"{name}/{f.name}", "error": str(exc)})
                    continue
                if not item.get("id"):
                    out.append({"path": f"{name}/{f.name}", "error": "missing 'id' field"})
                    continue
                # An id the store refuses to serve is a silent disappearance
                # otherwise — the file is on disk and in git, but absent from
                # every view. Report it with the reason.
                reason = id_rejection_reason(item.get("id"))
                if reason:
                    out.append({"path": f"{name}/{f.name}", "error": reason})
        return out

    def get_item(self, collection: str, item_id: str) -> Optional[dict]:
        path = self._item_path(collection, item_id)
        if not path.exists():
            return None
        return self._read_yaml(path)

    def create_item(self, collection: str, data: dict) -> dict:
        now = _now()
        data.setdefault("created", now)
        data["modified"] = now
        path = self._item_path(collection, data["id"])
        # Locked like update_item: a create racing an update of the same id
        # would otherwise interleave read-modify-write against a fresh write.
        with _file_lock(path):
            self._write_yaml(path, data)
        return data

    def update_item(self, collection: str, item_id: str, data: dict) -> Optional[dict]:
        path = self._item_path(collection, item_id)
        # Hold an advisory lock across the read-modify-write so concurrent updates
        # to the same item can't clobber each other (lost-update race).
        with _file_lock(path):
            if not path.exists():
                return None
            # Refuse to merge into a file we couldn't parse — `_read_yaml`
            # would hand back `{}` and the write would silently replace the
            # user's (recoverable) broken file with only the patch fields.
            try:
                existing = self._parse_yaml(path)
            except Exception as exc:
                raise HTTPException(
                    status_code=409,
                    detail=f"Cannot update {item_id}: {collection}/{item_id}.yaml is not valid "
                           f"YAML ({exc}). Fix the file and retry.",
                )
            existing.update(data)
            existing["modified"] = _now()
            existing["id"] = item_id
            self._write_yaml(path, existing)
            return existing

    def delete_item(self, collection: str, item_id: str) -> bool:
        path = self._item_path(collection, item_id)
        with _file_lock(path):
            if not path.exists():
                return False
            try:
                os.remove(path)
            except FileNotFoundError:
                return False
        invalidate_cache(path)
        return True

    def write_item(self, collection: str, item_id: str, data: dict) -> dict:
        path = self._item_path(collection, item_id)
        with _file_lock(path):
            self._write_yaml(path, data)
        return data

    # --- Requirements ---

    def list_requirements(self) -> list[dict]:
        return self.list_items("requirements")

    def get_requirement(self, req_id: str) -> Optional[dict]:
        return self.get_item("requirements", req_id)

    def create_requirement(self, data: dict) -> dict:
        self.ensure_dirs()
        return self.create_item("requirements", data)

    def update_requirement(self, req_id: str, data: dict) -> Optional[dict]:
        return self.update_item("requirements", req_id, data)

    def delete_requirement(self, req_id: str) -> bool:
        return self.delete_item("requirements", req_id)

    # --- Specifications ---

    def list_specifications(self) -> list[dict]:
        return self.list_items("specifications")

    def get_specification(self, spec_id: str) -> Optional[dict]:
        return self.get_item("specifications", spec_id)

    def create_specification(self, data: dict) -> dict:
        self.ensure_dirs()
        return self.create_item("specifications", data)

    def update_specification(self, spec_id: str, data: dict) -> Optional[dict]:
        return self.update_item("specifications", spec_id, data)

    def delete_specification(self, spec_id: str) -> bool:
        return self.delete_item("specifications", spec_id)

    # --- Verification Cases ---

    def list_verification_cases(self) -> list[dict]:
        return self.list_items("verification_cases")

    def get_verification_case(self, vc_id: str) -> Optional[dict]:
        return self.get_item("verification_cases", vc_id)

    def create_verification_case(self, data: dict) -> dict:
        self.ensure_dirs()
        return self.create_item("verification_cases", data)

    def update_verification_case(self, vc_id: str, data: dict) -> Optional[dict]:
        return self.update_item("verification_cases", vc_id, data)

    def delete_verification_case(self, vc_id: str) -> bool:
        return self.delete_item("verification_cases", vc_id)

    # --- Components ---

    def list_components(self) -> list[dict]:
        return self.list_items("components")

    def get_component(self, component_id: str) -> Optional[dict]:
        return self.get_item("components", component_id)

    def create_component(self, data: dict) -> dict:
        self.ensure_dirs()
        return self.create_item("components", data)

    def update_component(self, component_id: str, data: dict) -> Optional[dict]:
        return self.update_item("components", component_id, data)

    def delete_component(self, component_id: str) -> bool:
        return self.delete_item("components", component_id)

    # --- Traces ---

    def read_traces(self) -> dict:
        if not self._traces_file.exists():
            return {"links": []}
        return self._read_yaml(self._traces_file)

    def traces_version(self) -> str:
        """Cheap fingerprint of the trace matrix, for optimistic concurrency.

        ``PUT /traces`` replaces the whole document from a client-side snapshot,
        so without a version check a client that loaded the page an hour ago
        silently erases every link added since.
        """
        try:
            st = self._traces_file.stat()
        except OSError:
            return "0-0"
        return f"{int(st.st_mtime_ns)}-{st.st_size}"

    def write_traces(self, data: dict, expected_version: Optional[str] = None) -> None:
        """Replace the trace matrix.

        When ``expected_version`` is given it must still match, or the write is
        refused with 409 so the caller can reload rather than clobber.
        """
        with _file_lock(self._traces_file):
            if expected_version is not None and expected_version != self.traces_version():
                raise HTTPException(
                    status_code=409,
                    detail="Trace matrix changed since you loaded it. "
                           "Reload and reapply your change.",
                )
            self._write_yaml(self._traces_file, data)

    # --- History (append-only audit trail, one file per entry) ---

    def history_dir(self, item_id: str) -> Path:
        return self._root / "history" / safe_id(item_id)

    def list_history(self, item_id: str) -> list[dict]:
        d = self.history_dir(item_id)
        if not d.exists():
            return []
        entries = [self._read_yaml(f) for f in d.glob("*.yaml")]
        return sorted(entries, key=lambda e: e.get("timestamp", ""), reverse=True)

    def append_history(self, item_id: str, entry: dict) -> None:
        d = self.history_dir(item_id)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        self._write_yaml(d / f"{stamp}.yaml", entry)

    def list_all_history(self, since: str = "", until: str = "") -> list[dict]:
        """Every audit entry across every item, oldest first.

        ``since``/``until`` are inclusive ISO date (or datetime) bounds; an
        empty string means unbounded. Each returned entry carries the owning
        ``item_id`` (the history subdirectory name, which ``safe_id`` leaves
        equal to the item's id).
        """
        root = self._root / "history"
        if not root.exists():
            return []
        # A bare end date means "that whole day", not midnight — otherwise a
        # range ending today would exclude everything done today.
        if until and len(until) == 10:
            until = until + "T23:59:59.999999+00:00"
        out: list[dict] = []
        for item_dir in root.iterdir():
            if not item_dir.is_dir():
                continue
            for f in item_dir.glob("*.yaml"):
                entry = self._read_yaml(f)
                if not entry:
                    continue
                ts = str(entry.get("timestamp", ""))
                if since and ts < since:
                    continue
                if until and ts > until:
                    continue
                entry["item_id"] = item_dir.name
                out.append(entry)
        return sorted(out, key=lambda e: str(e.get("timestamp", "")))

    # --- Bulk ---

    def all_data(self) -> dict:
        return {
            "meta": self.read_meta(),
            "requirements": self.list_requirements(),
            "specifications": self.list_specifications(),
            "verification_cases": self.list_verification_cases(),
            "components": self.list_components(),
            "traces": self.read_traces(),
        }
