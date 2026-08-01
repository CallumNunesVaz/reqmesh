"""Protocol interfaces for pluggable backends.

Define contracts that services and route handlers depend on, so a concrete
implementation can be swapped without touching call sites. Currently stubs
only; the codebase still uses monolithic concrete classes internally, but
new code (and any future refactoring) can program against these protocols.

See review.md §10 (Extensible).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmailBackend(Protocol):
    """Sends transactional email — reviews, change requests, comments."""

    def send(self, recipients: str | list[str], subject: str,
             body_html: str, body_text: str = "") -> None: ...

    def is_configured(self) -> bool: ...


@runtime_checkable
class StorageBackend(Protocol):
    """Generic entity store with per-collection directory layout.

    ``YamlStore`` is the sole implementation today. An adapter that satisfies
    this protocol would allow Postgres, SQLite, or an object store to be
    plugged in without touching route handlers.
    """

    def list_items(self, collection: str) -> list[dict]: ...
    def get_item(self, collection: str, item_id: str) -> dict | None: ...
    def create_item(self, collection: str, data: dict) -> dict: ...
    def update_item(self, collection: str, item_id: str, data: dict) -> dict | None: ...
    def delete_item(self, collection: str, item_id: str) -> bool: ...
    def write_item(self, collection: str, item_id: str, data: dict) -> dict: ...
    def read_meta(self) -> dict: ...
    def write_meta(self, data: dict) -> None: ...


@runtime_checkable
class ImportFormat(Protocol):
    """An import format plug-in — ReqIF, SysML v2, CSV, etc."""

    def sniff(self, raw: bytes) -> bool: ...
    def parse_and_import(self, store: StorageBackend, raw: bytes,
                         mode: str = "merge") -> dict: ...


@runtime_checkable
class ExportFormat(Protocol):
    """An export format plug-in — HTML, PDF, LaTeX, Markdown, etc."""

    def build(self, store: StorageBackend) -> str: ...


@runtime_checkable
class AuthBackend(Protocol):
    """Authentication back-end — JWT cookie/bearer, OAuth, OIDC, etc."""

    def authenticate(self, credentials: dict) -> dict | None: ...
    def refresh(self, token: str) -> dict | None: ...
    def revoke(self, user_id: str) -> None: ...
