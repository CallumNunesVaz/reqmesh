from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from typing import Any

from pydantic import BaseModel, Field


class CRStatus(str, Enum):
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"
    CLOSED = "closed"


class CRUrgency(str, Enum):
    """How soon the change needs deciding.

    An enum rather than a per-project list, unlike the risk vocabularies: a
    change request's urgency is not an axis a project configures, and CRStatus
    above is already an enum, so this stays consistent with its own file.
    """
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EMERGENCY = "emergency"


class ChangeRequest(BaseModel):
    id: str
    title: str = ""
    description: str = ""
    affected_requirements: list[str] = Field(default_factory=list)
    #: A change often lands on the design, not only on the text: swapping a part
    #: is a change request against a component. Without this the CR could name
    #: the requirement it rewrites but not the thing being rebuilt.
    affected_components: list[str] = Field(default_factory=list)
    status: CRStatus = CRStatus.SUBMITTED
    urgency: CRUrgency = CRUrgency.NORMAL
    #: Why the change is needed, as opposed to `description`, which is what it
    #: is. Rich text, like a requirement's rationale.
    rationale: str = ""
    #: The proposed change itself: target id -> {field: new value}. Without this
    #: a change request names what it touches and never what it would do, which
    #: leaves nothing to redline and nothing to execute.
    changes: dict[str, dict[str, Any]] = Field(default_factory=dict)
    #: Ids in `changes` that this request proposes to *create* rather than modify.
    #: Without it a target that is absent is indistinguishable from one that was
    #: deleted, and the redline has to assume the pessimistic case.
    creates: list[str] = Field(default_factory=list)
    #: Target id -> `compute_fingerprint` of that requirement when the request
    #: was raised.
    #:
    #: The "before" side of the redline is read live rather than snapshotted,
    #: because a stored before goes stale the moment anyone edits the target and
    #: would then show a diff against a version that no longer exists. That makes
    #: the redline honest but leaves execute able to clobber newer edits, so the
    #: fingerprint is the guard: if it no longer matches, the target moved under
    #: the request and executing is refused rather than silently overwriting.
    base_fingerprints: dict[str, str] = Field(default_factory=dict)
    #: The requester. Not duplicated as a separate `requester` field — one person
    #: recorded twice is two facts free to disagree.
    submitted_by: str = ""
    reviewed_by: str = ""
    approved_by: str = ""
    created: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    modified: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ChangeRequestCreate(BaseModel):
    id: str
    title: str = ""
    description: str = ""
    rationale: str = ""
    urgency: CRUrgency = CRUrgency.NORMAL
    affected_requirements: list[str] = Field(default_factory=list)
    changes: dict[str, dict[str, Any]] = Field(default_factory=dict)
    creates: list[str] = Field(default_factory=list)


class ChangeRequestUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[CRStatus] = None
    urgency: Optional[CRUrgency] = None
    rationale: Optional[str] = None
    changes: Optional[dict[str, dict[str, Any]]] = None
    creates: Optional[list[str]] = None
    affected_requirements: Optional[list[str]] = None
    affected_components: Optional[list[str]] = None
    submitted_by: Optional[str] = None
    reviewed_by: Optional[str] = None
    approved_by: Optional[str] = None
