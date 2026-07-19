"""Components — the synthesised design.  Aligned with ISO/IEC 15288:2023.

A requirement says what the system must *do*; a component says what the system
*is* (ISO 15288 §4.48: system element). Components form their own hierarchy
(system → subsystem → assembly → part, plus software and interface types) and
map onto the functional side via:
- §6.4.3 Architecture Definition: the component tree with satisfies links
- §6.4.4 Design Definition: numeric parameters enabling budget rollups
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.models.requirement import AttributeValue, Parameter, Relation


class ComponentType(str, Enum):
    SYSTEM = "system"
    SUBSYSTEM = "subsystem"
    ASSEMBLY = "assembly"
    PART = "part"
    SOFTWARE = "software"
    INTERFACE = "interface"


class Component(BaseModel):
    id: str
    name: str = ""
    description: str = ""
    type: ComponentType = ComponentType.ASSEMBLY
    # Hierarchy: None means the component sits at the top of the design tree.
    parent: Optional[str] = None
    part_number: str = ""
    supplier: str = ""
    quantity: int = 1
    # The design→function mapping. Requirements this component realises, and
    # the verification cases that exercise it.
    satisfies: list[str] = Field(default_factory=list)
    verification_cases: list[str] = Field(default_factory=list)
    attributes: list[AttributeValue] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    # Numeric quantities (mass, power draw, cost…) that budget rollups sum
    # over the design tree.
    parameters: list[Parameter] = Field(default_factory=list)
    created: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    modified: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ComponentCreate(BaseModel):
    id: str
    name: str = ""
    description: str = ""
    type: ComponentType = ComponentType.ASSEMBLY
    parent: Optional[str] = None
    part_number: str = ""
    supplier: str = ""
    quantity: int = 1
    satisfies: list[str] = Field(default_factory=list)
    verification_cases: list[str] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    parameters: list[Parameter] = Field(default_factory=list)


class ComponentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[ComponentType] = None
    parent: Optional[str] = None
    part_number: Optional[str] = None
    supplier: Optional[str] = None
    quantity: Optional[int] = None
    satisfies: Optional[list[str]] = None
    verification_cases: Optional[list[str]] = None
    relations: Optional[list[Relation]] = None
    attributes: Optional[list[AttributeValue]] = None
    parameters: Optional[list[Parameter]] = None
