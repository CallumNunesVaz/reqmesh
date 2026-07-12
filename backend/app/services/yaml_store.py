from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ruamel.yaml import YAML

from app.core.ids import safe_id

yaml = YAML()
yaml.indent(mapping=2, sequence=4, offset=2)
yaml.preserve_quotes = True
yaml.width = 120

# Every entity type is a directory of one-YAML-file-per-item. New entity
# types only need an entry here.
COLLECTIONS = (
    "requirements",
    "specifications",
    "verification_cases",
    "change_requests",
    "risks",
    "comments",
    "decisions",
    "baselines",
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

    def _read_yaml(self, path: Path) -> dict:
        with open(path) as f:
            return yaml.load(f) or {}

    def _write_yaml(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                yaml.dump(data, f)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
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
            raise ValueError(f"Unknown collection: {collection}")
        return self._root / collection / f"{safe_id(item_id)}.yaml"

    def list_items(self, collection: str) -> list[dict]:
        d = self._root / collection
        if not d.exists():
            return []
        return [self._read_yaml(f) for f in sorted(d.glob("*.yaml"))]

    def get_item(self, collection: str, item_id: str) -> Optional[dict]:
        path = self._item_path(collection, item_id)
        if not path.exists():
            return None
        return self._read_yaml(path)

    def create_item(self, collection: str, data: dict) -> dict:
        now = _now()
        data.setdefault("created", now)
        data["modified"] = now
        self._write_yaml(self._item_path(collection, data["id"]), data)
        return data

    def update_item(self, collection: str, item_id: str, data: dict) -> Optional[dict]:
        existing = self.get_item(collection, item_id)
        if existing is None:
            return None
        existing.update(data)
        existing["modified"] = _now()
        existing["id"] = item_id
        self._write_yaml(self._item_path(collection, item_id), existing)
        return existing

    def delete_item(self, collection: str, item_id: str) -> bool:
        path = self._item_path(collection, item_id)
        if not path.exists():
            return False
        os.remove(path)
        return True

    def write_item(self, collection: str, item_id: str, data: dict) -> dict:
        self._write_yaml(self._item_path(collection, item_id), data)
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

    # --- Traces ---

    def read_traces(self) -> dict:
        if not self._traces_file.exists():
            return {"links": []}
        return self._read_yaml(self._traces_file)

    def write_traces(self, data: dict) -> None:
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

    # --- Bulk ---

    def all_data(self) -> dict:
        return {
            "meta": self.read_meta(),
            "requirements": self.list_requirements(),
            "specifications": self.list_specifications(),
            "verification_cases": self.list_verification_cases(),
            "traces": self.read_traces(),
        }
