from __future__ import annotations

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


class Requirement(BaseModel):
    id: str
    type: RequirementType = RequirementType.FUNCTIONAL
    name: str = ""
    description: str = ""
    priority: Priority = Priority.MEDIUM
    status: RequirementStatus = RequirementStatus.PROPOSED
    verification_method: VerificationMethod = VerificationMethod.TEST
    attributes: list[AttributeValue] = Field(default_factory=list)
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


class RequirementUpdate(BaseModel):
    type: Optional[RequirementType] = None
    name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[Priority] = None
    status: Optional[RequirementStatus] = None
    verification_method: Optional[VerificationMethod] = None
    attributes: Optional[list[AttributeValue]] = None
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


class RequirementTreeNode(BaseModel):
    id: str
    name: str
    type: str
    status: str
    priority: str
    children: list["RequirementTreeNode"] = Field(default_factory=list)
