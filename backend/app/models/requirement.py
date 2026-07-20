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

from pydantic import BaseModel, Field


class RequirementType(str, Enum):
    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"
    INTERFACE = "interface"
    DESIGN = "design"
    CONSTRAINT = "constraint"


class RequirementStatus(str, Enum):
    PROPOSED = "proposed"
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


class RequirementKind(str, Enum):
    """OOSEM / ISO 15288 distinction: stakeholder need vs system requirement."""
    STAKEHOLDER_NEED = "stakeholder_need"
    SYSTEM_REQUIREMENT = "system_requirement"


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
    baseline: Optional[str] = None
    reviewed: Optional[str] = None
    derived: bool = False
    normative: bool = True
    effort: Optional[int] = None
    priorities: dict[str, int] = Field(default_factory=dict)
    needs: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    requirement_kind: RequirementKind = RequirementKind.SYSTEM_REQUIREMENT
    system_states: list[str] = Field(default_factory=list)
    # SysML v2 requirement subject: the part/component this requirement constrains.
    subject: Optional[str] = None
    created: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    modified: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RequirementCreate(BaseModel):
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
    parent: Optional[str] = None
    cascade_from: Optional[str] = None
    rationale: str = ""
    source: str = ""
    allocated_to: str = ""
    baseline: Optional[str] = None
    reviewed: Optional[str] = None
    derived: bool = False
    normative: bool = True
    effort: Optional[int] = None
    priorities: dict[str, int] = Field(default_factory=dict)
    needs: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    requirement_kind: RequirementKind = RequirementKind.SYSTEM_REQUIREMENT
    system_states: list[str] = Field(default_factory=list)
    subject: Optional[str] = None


class RequirementUpdate(BaseModel):
    type: Optional[RequirementType] = None
    name: Optional[str] = None
    description: Optional[str] = None
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
    baseline: Optional[str] = None
    reviewed: Optional[str] = None
    derived: Optional[bool] = None
    normative: Optional[bool] = None
    effort: Optional[int] = None
    priorities: Optional[dict[str, int]] = None
    needs: Optional[list[str]] = None
    references: Optional[list[Reference]] = None
    requirement_kind: Optional[RequirementKind] = None
    system_states: Optional[list[str]] = None
    subject: Optional[str] = None


class RequirementTreeNode(BaseModel):
    id: str
    name: str
    type: str
    status: str
    priority: str
    children: list["RequirementTreeNode"] = Field(default_factory=list)
