from __future__ import annotations

"""Requirements model — aligned with ISO/IEC 15288:2023 §6.4.2.3 (Stakeholder Needs and Requirements Definition).

A Requirement represents either a stakeholder requirement (expressing a need
or expectation) or a system requirement (derived from stakeholder requirements,
expressed in technical terms). The 'type' field distinguishes these:
functional, non_functional, interface, design, and constraint.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.services.sanitize import sanitize_html


class RequirementType(str, Enum):
    FUNCTIONAL = "functional"
    NON_FUNCTIONAL_PERFORMANCE = "non_functional_performance"
    NON_FUNCTIONAL_SECURITY = "non_functional_security"
    NON_FUNCTIONAL_USABILITY = "non_functional_usability"
    NON_FUNCTIONAL_MAINTAINABILITY = "non_functional_maintainability"
    NON_FUNCTIONAL_RELIABILITY = "non_functional_reliability"
    NON_FUNCTIONAL_SCALABILITY = "non_functional_scalability"
    NON_FUNCTIONAL_PORTABILITY = "non_functional_portability"
    INTERFACE = "interface"
    USER = "user"
    SYSTEM = "system"
    BUSINESS = "business"
    REGULATORY_COMPLIANCE = "regulatory_compliance"
    SAFETY = "safety"
    ENVIRONMENTAL = "environmental"
    VERIFICATION = "verification"


class RequirementStatus(str, Enum):
    PROPOSED = "proposed"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    IMPLEMENTED = "implemented"
    VERIFIED = "verified"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


class VerificationMethod(str, Enum):
    TEST = "test"
    ANALYSIS = "analysis"
    DEMONSTRATION = "demonstration"
    INSPECTION = "inspection"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MeasureKind(str, Enum):
    """OOSEM measure taxonomy: MOE (operational), MOP (system), TPM (component)."""
    MOE = "MOE"
    MOP = "MOP"
    TPM = "TPM"


class Relation(BaseModel):
    type: str
    target: str
    reviewed_fingerprint: Optional[str] = None


class Reference(BaseModel):
    path: str
    keyword: Optional[str] = None
    kind: str = "impl"
    sha256: Optional[str] = None
    lines: Optional[str] = None


class AttributeValue(BaseModel):
    key: str
    value: str


class Parameter(BaseModel):
    """A typed numeric quantity on a requirement or component.

    Either a literal `value`, or an `expr` deriving it from other parameters
    (`span * chord`, `GROS0001.mass - EMPT0001.mass`,
    `rollup('WING', 'mass')`). Unlike `attributes`, these participate in
    constraint evaluation.
    """

    name: str
    value: Optional[float] = None
    unit: str = ""
    expr: Optional[str] = None
    kind: Optional[MeasureKind] = None
    # Optional SysML v2 value-type name (e.g. "MassValue") for typed export.
    value_type: Optional[str] = None
    # Reusable calc-definition usage: reference a CalcDef and bind its formals
    # to actual parameter refs. Value derives from the definition's expression.
    calc_def: Optional[str] = None
    bindings: dict[str, str] = Field(default_factory=dict)


class Constraint(BaseModel):
    """A boolean expression over parameters that must hold.

    `assume` is an optional precondition: when present and not satisfied the
    constraint is out of scope rather than failed (SysML assume/require).
    """

    expr: str = ""
    assume: Optional[str] = None
    kind: Optional[MeasureKind] = None
    # Reusable constraint-definition usage: reference a ConstraintDef and bind
    # its formals to actual parameter refs. When set, ``expr`` is derived from
    # the definition and may be left blank.
    constraint_def: Optional[str] = None
    bindings: dict[str, str] = Field(default_factory=dict)


class Requirement(BaseModel):
    id: str
    type: RequirementType = RequirementType.FUNCTIONAL
    name: str = ""
    description: str = ""
    priority: Priority = Priority.MEDIUM
    status: RequirementStatus = RequirementStatus.PROPOSED
    verification_method: VerificationMethod = VerificationMethod.TEST
    attributes: list[AttributeValue] = Field(default_factory=list)
    parameters: list[Parameter] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    verification_cases: list[str] = Field(default_factory=list)
    verification_status: str = "pending"
    parent: Optional[str] = None
    cascade_from: Optional[str] = None
    rationale: str = ""
    source: str = ""
    allocated_to: str = ""
    baselines: list[str] = Field(default_factory=list)
    reviewed: Optional[str] = None
    derived: bool = False
    normative: bool = True
    priorities: dict[str, int] = Field(default_factory=dict)
    needs: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    system_states: list[str] = Field(default_factory=list)
    # SysML v2 requirement subject: the part/component this requirement constrains.
    subject: Optional[str] = None
    created: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    modified: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RequirementCreate(BaseModel):
    model_config = {"extra": "ignore"}
    id: str
    type: RequirementType = RequirementType.FUNCTIONAL
    name: str = ""
    description: str = ""

    # Descriptions are stored and published as HTML. The editor cleans content
    # client-side, but the API takes a plain str, so this is the only place a
    # direct API call can be stopped from persisting a script payload.
    @field_validator("description")
    @classmethod
    def _clean_description(cls, v: str) -> str:
        return sanitize_html(v)
    priority: Priority = Priority.MEDIUM
    status: RequirementStatus = RequirementStatus.PROPOSED
    verification_method: VerificationMethod = VerificationMethod.TEST
    attributes: list[AttributeValue] = Field(default_factory=list)
    parameters: list[Parameter] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    verification_cases: list[str] = Field(default_factory=list)
    parent: Optional[str] = None
    cascade_from: Optional[str] = None
    rationale: str = ""
    source: str = ""
    allocated_to: str = ""
    baselines: list[str] = Field(default_factory=list)
    reviewed: Optional[str] = None
    derived: bool = False
    normative: bool = True
    priorities: dict[str, int] = Field(default_factory=dict)
    needs: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    system_states: list[str] = Field(default_factory=list)
    subject: Optional[str] = None


class RequirementUpdate(BaseModel):
    type: Optional[RequirementType] = None
    name: Optional[str] = None
    description: Optional[str] = None

    @field_validator("description")
    @classmethod
    def _clean_description(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else sanitize_html(v)
    priority: Optional[Priority] = None
    status: Optional[RequirementStatus] = None
    verification_method: Optional[VerificationMethod] = None
    attributes: Optional[list[AttributeValue]] = None
    parameters: Optional[list[Parameter]] = None
    constraints: Optional[list[Constraint]] = None
    relations: Optional[list[Relation]] = None
    verification_cases: Optional[list[str]] = None
    verification_status: Optional[str] = None
    parent: Optional[str] = None
    cascade_from: Optional[str] = None
    rationale: Optional[str] = None
    source: Optional[str] = None
    allocated_to: Optional[str] = None
    baselines: Optional[list[str]] = None
    reviewed: Optional[str] = None
    derived: Optional[bool] = None
    normative: Optional[bool] = None
    priorities: Optional[dict[str, int]] = None
    needs: Optional[list[str]] = None
    references: Optional[list[Reference]] = None
    system_states: Optional[list[str]] = None
    subject: Optional[str] = None


class RequirementTreeNode(BaseModel):
    id: str
    name: str
    type: str
    status: str
    priority: str
    children: list["RequirementTreeNode"] = Field(default_factory=list)


# ── Validate-on-load: structural integrity for any dict coming off disk ───────
# YAML on disk is unstructured — a manual git edit, a merge conflict or a
# migration bug can leave a field with the wrong type. This is the
# requirement-specific half of the read-side guard; see
# `app/services/load_guard.py` for the id/HTML checks common to every
# collection and for where this runs.
#
# Two things this deliberately does NOT do, both learned the hard way:
#
# * **It does not fill in missing fields.** `compute_fingerprint` canonicalises
#   over the normative fields, so injecting `type: functional` into a file that
#   omitted it changes that requirement's fingerprint and flips it to
#   "unreviewed". Load-time defaults would silently invalidate the review state
#   of every existing project — the exact false-assurance failure the store
#   exists to prevent. Consumers already read these with `.get(field, default)`.
#
# * **It does not coerce unrecognised enum values.** The vocabularies are open
#   in practice: `type: design` is not in `RequirementType`, but the coverage
#   model matches a requirement's `type` against a downstream `needs` entry, so
#   rewriting it to `functional` silently breaks the trace. The write path
#   validates against the enums via Pydantic; the read path must not
#   second-guess data a human put there on purpose.
#
# What is left is the narrow case worth acting on: a field whose *type* is
# wrong (so consumers would raise), and entity references that can't be valid.

# Fields naming another entity. A hostile value here can't reach the filesystem
# (ids are re-validated before becoming a path) but it does produce dangling
# graph edges and confusing traceability output, so drop it at the boundary.
_ID_LIST_FIELDS = ("verification_cases", "needs")

_LIST_FIELDS = ("attributes", "parameters", "constraints", "relations",
                "verification_cases", "baselines", "needs", "references",
                "system_states")


def normalise_requirement_on_load(req: dict) -> dict:
    """Return *req* with structurally impossible values repaired.

    Mutates and returns the same dict — no copy is made. Only keys that are
    *present and the wrong shape* are touched; absent keys stay absent.
    """
    from app.services.load_guard import is_safe_id

    # A scalar where a list belongs raises in every consumer that iterates it.
    for field in _LIST_FIELDS:
        if field in req and not isinstance(req[field], list):
            req[field] = []
    if "priorities" in req and not isinstance(req["priorities"], dict):
        req["priorities"] = {}

    # Entity references: a parent or relation target that isn't a usable id
    # renders as a broken link and confuses the tree builder.
    if req.get("parent") is not None and not is_safe_id(req["parent"]):
        req["parent"] = None
    if req.get("relations"):
        req["relations"] = [
            rel for rel in req["relations"]
            if isinstance(rel, dict) and is_safe_id(rel.get("target"))
        ]
    for field in _ID_LIST_FIELDS:
        if req.get(field):
            req[field] = [v for v in req[field] if is_safe_id(v)]

    return req
