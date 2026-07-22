# Parametrics → SysML v2 Alignment Plan

> **Status: IMPLEMENTED (2026-07-21).** All four slices, the GUI data-entry
> updates, the Cessna demo examples, and documentation are in place and verified
> (backend + frontend suites, typecheck, build, e2e). See per-slice notes below.

## Context

reqmesh's parametric modelling today is **SysML v2-inspired but not conformant**:
a bespoke, accessible engine (`backend/app/services/evaluation.py`) evaluates
free-text expressions over a flat `ENTITY.param` namespace and produces rich
verdicts (pass/fail/unknown/not_applicable/error), margins, rollups, and
verification-measured verdicts. The value lives in the **evaluator**, which
SysML v2 (a modelling *language*, not a solver) does not define.

The chosen direction is **"keep the engine, SysML-ify the representation."**
This is deliberately **additive**: no computed capability is removed. We adopt
SysML v2 *structure and notation* on top of the existing solver, gaining
dimensional unit checking, reusable constraint/calc definitions, analysis
cases, and — critically — a parametrics-complete SysML interchange (the export
currently drops parameters and constraints entirely).

**Explicit "nothing is lost" guarantees baked into the design:**
- Unknown/free-text units skip checking → today's permissiveness is preserved.
- Inline `expr` constraints remain valid alongside new definition-based ones.
- `MeasureKind` (MOE/MOP/TPM) is preserved, re-expressed as SysML `metadata`.
- `rollup()`, cross-entity refs, verdict taxonomy, and measured verdicts are untouched.
- All new model fields are `Optional` with defaults → existing YAML loads unchanged; no data migration required.

Reference specs (SysML v2 / KerML) are cited in [docs/REFERENCES.md](docs/REFERENCES.md);
they are not redistributed here — obtain them from the OMG specification catalog.

---

## Slice 1 — Round-trip parametrics in the SysML v2 interchange

**Why:** `sysml_export.py::render_req` emits requirement defs, status, priority,
relations, and verification — but **no parameters or constraints**. Import
(`sysml_import.py`) only reads `requirement def` blocks. This is the highest
value-for-risk slice: purely additive, delivers real interoperability.

**Export (`backend/app/services/sysml_export.py`):**
- In `render_req`, after the existing metadata lines, emit per parameter:
  - literal: `attribute <name> = <value> [<unit>];`
  - derived: `attribute <name> = <expr>;` (the reqmesh expr grammar is a subset of SysML expressions; `A.b` refs are valid feature paths)
- Emit per constraint: `require constraint { <expr> }`, preceded by
  `assume constraint { <assume> }` when `assume` is set (SysML v2 assume/require).
- Emit `MeasureKind` as `metadata reqmesh_measure { :>> kind = "MOE"; }`.
- **New:** render components as `part def` blocks with their `attribute`s and
  `satisfy requirement` lines, so `rollup()` targets round-trip faithfully.

**Import (`backend/app/services/sysml_import.py`):**
- Add line regexes for `attribute <name> = <rest>;` → parse into `parameters`
  (split trailing `[unit]`; value vs expr by numeric test), and
  `require constraint { … }` / `assume constraint { … }` → `constraints`.
- Parse `part def` blocks into components; parse `metadata reqmesh_measure`.

**Tests (`backend/tests/test_parametrics_sysml.py`):** export → import into a fresh
store → assert parameters, constraints, assume, units, and rollup targets are
byte-equivalent; re-run `evaluate_project` on both and assert identical verdicts.

---

## Slice 2 — Value types + units with dimensional checking

**Why:** `unit` is free text today (no `grep` hit for any unit system). SysML v2
uses typed value types over ISQ/SI quantities. Adding dimensional checking is a
pure gain; unknown units degrade gracefully to "unchecked."

**New `backend/app/services/units.py`:**
- Unit registry: symbol → (7-dim SI vector [m,kg,s,A,K,mol,cd], factor to base).
  Seed SI base + common units (mm, cm, km, in, ft; g, lb; min, h; mA; and derived
  N, Pa, W, V, Hz…). Dimensionless and unknown units → `None` dimension.
- Helpers: `dimension_of(unit)`, `compatible(u1, u2)`, `combine(dimA, op, dimB)`
  for `+ - * /`, `to_base(value, unit)`.

**Model (`backend/app/models/requirement.py::Parameter`):**
- Add `value_type: Optional[str] = None` (e.g. `"MassValue"`) — optional, used for
  richer SysML export typing. `unit` continues to drive dimensional checking.

**Evaluator (`backend/app/services/evaluation.py`):**
- Add a **separate, non-fatal dimension pass** (a `DimensionEvaluator` mirroring
  `_eval`, returning dimensions instead of numbers) so the numeric path is
  untouched. In `evaluate_project`, for each derived parameter and each
  comparison constraint, infer dimensions and attach `unit_warning` when
  inconsistent (e.g. `kg + m`, comparing `m` to `s`) and the inferred unit of
  derived params. Warnings are informational — **verdicts are unchanged**.

**Frontend (`frontend/src/components/parametrics.tsx`, `ParametricsGuide.tsx`):**
- Surface `unit_warning` on parameter/constraint rows; unit input gains
  autocomplete of known units (still free-text). Document units in the guide.

**Tests (`backend/tests/test_units.py`):** dimension algebra, compatibility,
`combine` for each op, and `evaluate_project` emitting `unit_warning` on a
`kg + m` derivation while a same-dimension expr stays clean.

---

## Slice 3 — Reusable constraint def / calc def (with binding)

**Why:** SysML v2's core parametric construct is the reusable `constraint def` /
`calc def` with typed parameters, *bound* to model features at each usage. Today
every constraint is an inline one-off expr.

**New model `backend/app/models/definition.py`:**
- `ConstraintDef{ id, name, parameters: list[str], expr, doc }` — boolean template
  over named formals.
- `CalcDef{ id, name, parameters: list[str], expr, unit, doc }` — value-returning.
- Extend `Constraint` with optional `def: Optional[str]` + `bindings: dict[str,str]`
  (formal → actual `ENTITY.param` ref); inline `expr` stays as the alternative.
  Same optional `calc` + `bindings` on `Parameter`.

**Storage:** new `definitions` collection via the existing generic item API
(`YamlStore.list_items/get_item/write_item/delete_item`, as baselines use).

**API:** CRUD under `/projects/{id}/definitions` in `backend/app/api/router.py`
(mirror the baseline endpoints; admin/edit-gated via `require_edit`).

**Evaluator:** when a constraint/parameter carries `def`/`calc` + `bindings`,
resolve by evaluating the def's `expr` in an environment where each formal maps
to its bound actual ref (reuse `Evaluator.resolve`); reuse existing cycle
protection (`stack`).

**Frontend:** a small Definitions manager (section on the metrics/parametrics
surface) + "add constraint from definition" with a binding picker in
`ParametricsCard`.

**Tests (`backend/tests/test_definitions.py`):** define once, bind on two
requirements, assert both evaluate; binding to a missing ref → `unknown`;
circular def → guarded error.

---

## Slice 4 — Analysis cases + assume/require formalization

**Why:** SysML v2 expresses evaluation via `analysis def` cases and requirements
via `subject` + assume/require constraints. `evaluate_project` is already a
global analysis; this exposes named, scoped, parameterised runs.

- **`subject`**: add `subject: Optional[str]` to `Requirement` (the part/component
  the requirement constrains); export as `subject <ref>;`, import back.
- **Analysis cases:** new `AnalysisCase{ id, name, scope: list[str], overrides:
  dict[str,float], doc }`. Evaluate by reusing `Evaluator(overrides=…)` and the
  existing verdict machinery, scoped to `scope`. Expose
  `GET /projects/{id}/analysis/{caseId}`; store in a `analysis_cases` collection.
  Export as `analysis def`.
- **Frontend:** an analysis-case runner showing scoped verdicts and margins,
  reusing `VerdictBadge`/`MarginTag` from `parametrics.tsx`.

**Tests (`backend/tests/test_analysis.py`):** a case with overrides flips a verdict
as expected; scoping limits the evaluated set; `subject` round-trips through SysML.

---

## Cross-cutting: migration & compatibility

- Every new field is `Optional`/defaulted → existing project YAML loads unchanged.
- Evaluator changes are additive (warnings + new resolution paths); existing
  parametric tests must continue to pass unchanged.
- No data migration needed. Optionally bump `migrations.CURRENT_SCHEMA_VERSION`
  to 2 with a **no-op** migration purely to record the format's evolution.
- Extend `demo_seed.py` (Cessna) with a couple of typed-unit parameters, one
  shared `ConstraintDef` (e.g. a reusable mass-budget), and one analysis case, so
  the features have living examples and the e2e has something to exercise.

## Verification (end-to-end)

1. **Backend:** `backend/.venv/bin/python -m pytest -q` — new suites per slice
   (`test_parametrics_sysml.py`, `test_units.py`, `test_definitions.py`,
   `test_analysis.py`) plus unchanged existing parametric/evaluation tests.
2. **Round-trip:** seed → SysML export → import into a fresh project →
   assert parameters/constraints/verdicts identical.
3. **Frontend:** `npx tsc --noEmit`, `npx vitest run`, `npm run build` (from `frontend/`).
4. **E2E (run-app skill):** rebuild `dist`, drive the app — open a requirement's
   Parametrics card and confirm unit warnings render, add a constraint from a
   definition, run an analysis case; capture screenshots in both themes.

## Sequencing

Ship in order **1 → 2 → 3 → 4**, each independently verifiable and shippable.
Slices 1–2 deliver most of the "SysML v2 feel" for the least disruption; 3 is the
largest structural addition; 4 is the most advanced and optional.
