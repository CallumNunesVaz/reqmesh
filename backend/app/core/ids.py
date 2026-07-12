from __future__ import annotations

import re

from fastapi import HTTPException

# IDs become file/directory names inside the project tree, so they must never
# contain path separators or dot-dot segments. Must start alphanumeric.
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]*$")


def safe_id(value: str, kind: str = "id") -> str:
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"Invalid {kind}")
    value = value.strip()
    if not value or ".." in value or not _ID_RE.match(value):
        raise HTTPException(status_code=400, detail=f"Invalid {kind}: {value!r}")
    return value
