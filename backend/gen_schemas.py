#!/usr/bin/env python3
"""Generate JSON Schemas for the project YAML formats from the pydantic models.

Run from backend/:  python gen_schemas.py
Output goes to ../schemas/ so editors and CI can validate project YAML files.
"""

import json
from pathlib import Path

from app.models.requirement import Requirement
from app.models.specification import Specification
from app.models.verification import VerificationCase
from app.models.trace import TraceMatrix
from app.models.risk import Risk, Comment, DecisionRecord
from app.models.change_request import ChangeRequest
from app.models.component import Component
from app.models.baseline import Baseline

OUT = Path(__file__).resolve().parent.parent / "schemas"

MODELS = {
    "requirement": Requirement,
    "specification": Specification,
    "verification_case": VerificationCase,
    "traces": TraceMatrix,
    "risk": Risk,
    "comment": Comment,
    "decision": DecisionRecord,
    "change_request": ChangeRequest,
    "component": Component,
    "baseline": Baseline,
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, model in MODELS.items():
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["title"] = f"reqmesh {name}"
        path = OUT / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2) + "\n")
        print(f"  wrote {path}")


if __name__ == "__main__":
    main()
