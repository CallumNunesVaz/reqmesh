"""Comment model — threaded comments on any entity.

Comments used to carry a required ``requirement_id``, so a risk, a decision or a
change request could not be discussed at all — surprising in a tool built around
review. They now carry ``entity_kind`` + ``entity_id``.

``requirement_id`` is still **accepted** on create for one release so existing
clients keep working, but it is not stored: it is coerced to
``entity_kind="requirements"``. Stored comments were rewritten by schema
migration 2.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, model_validator


def commentable_collections() -> frozenset[str]:
    """Collections a comment may attach to.

    Derived from the link registry rather than listed again here, so adding a
    commentable entity means adding a row there and nothing else. Imported
    lazily because this is a model and ``link_registry`` is a service — the
    dependency runs one way only.
    """
    from app.services.link_registry import LINKS

    return frozenset(ln.target for ln in LINKS if ln.holder == "comments")


class Comment(BaseModel):
    id: str
    #: The collection the comment is attached to, e.g. ``"risks"``.
    entity_kind: str
    #: The id of the record within that collection.
    entity_id: str
    author: str = ""
    text: str = ""
    resolved: bool = False
    created: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CommentCreate(BaseModel):
    entity_kind: str = ""
    entity_id: str = ""
    #: Deprecated. Accepted for one release; coerced to
    #: ``entity_kind="requirements"`` and never stored.
    requirement_id: str = ""
    author: str = ""
    text: str = ""

    @model_validator(mode="after")
    def _resolve_target(self) -> "CommentCreate":
        if self.requirement_id and not self.entity_id:
            self.entity_kind = "requirements"
            self.entity_id = self.requirement_id
        if not self.entity_id:
            raise ValueError("entity_id is required")
        if self.entity_kind not in commentable_collections():
            allowed = ", ".join(sorted(commentable_collections()))
            raise ValueError(f"entity_kind must be one of: {allowed}")
        return self
