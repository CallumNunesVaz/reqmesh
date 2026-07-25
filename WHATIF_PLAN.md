# Live Parametric What-If — Implementation Plan

**Feature:** enter a hypothetical parameter value, watch the recalculation propagate through
downstream requirements (animated, in the inspector) and light up the canvas live, then
**Confirm** the change or **Restore** the original — so data can be entered carefully without
silently breaking any requirement's thresholds.

---

## 1. Background: what already exists

### 1.1 The parametric model (backend)
- `Parameter` (`backend/app/models/requirement.py:92`): `name`, `value` (literal), `unit`,
  `expr` (derived value from other params, e.g. `GROS0001.mass - EMPT0001.mass`), `kind`
  (MOE/MOP/TPM), `calc_def` + `bindings` (reusable calc template).
- `Constraint` (`requirement.py:114`): `expr` is a boolean comparison (`"mass <= 12.5"`) — the
  threshold **and** operator live inside the string; `assume` (precondition), `constraint_def` +
  `bindings`. There is **no** separate operator/target/tolerance field.
- Requirements carry `parameters: list[Parameter]` and `constraints: list[Constraint]`;
  components carry `parameters` too (drives rollups).

### 1.2 The evaluator (backend) — the key asset
`backend/app/services/evaluation.py`:
- `Evaluator` (line 69) parses expressions with Python's `ast` against a strict whitelist
  (arithmetic, comparisons, and/or/not, param refs, `min/max/abs/sqrt/floor/ceil/round`, and
  `rollup('COMP','param')`). Nothing else executes — YAML can never run code.
- `resolve(ref)` (line 96) computes a parameter's value: honours **overrides**, then `calc_def`,
  then `expr` (recursive, with circular-derivation detection), then literal `value`.
- `rollup(comp, param)` (line 129) sums a parameter over a component subtree × each child's
  `quantity` — the mass/power-budget mechanism.
- `_constraint_verdict` (line 369) → `pass | fail | unknown | not_applicable | error`, plus a
  signed `margin` (headroom vs violation depth) from `_margin` (line 335) for single comparisons.
- **`evaluate_project(store, scope=None, extra_overrides=None)` (line 420)** — evaluates the whole
  project. **It already accepts `extra_overrides`** (a dict of `"ENTITY.param" -> float`
  hypothetical inputs) and recomputes all derived params, rollups, and verdicts. This is exactly
  the what-if solver; `run_analysis_case` (line 521) is a thin wrapper over it.

**Consequence:** the what-if *computation* needs no new solver — only an ad-hoc endpoint plus a
trace of the dependency order for the animation.

### 1.3 Frontend display / edit / graph (what we hook into)
- Types (`frontend/src/api/client.ts`): `Parameter`, `Constraint`, and the evaluated shapes
  `EvaluatedRequirement { parameters[], constraints[], verdict, measured_verdict? }`,
  `EvaluatedConstraint { status, margin?, detail, unit_warning }`, `EvaluationData`.
- `ParametricsCard` (`frontend/src/components/parametrics.tsx`) renders a requirement's params &
  constraints with `VerdictBadge` + `MarginTag`, colour-mapped by `VERDICT_META`. Edits go through
  `onSave({ parameters?, constraints? })`.
- Save flow (`frontend/src/pages/RequirementDetailPage.tsx:162`): `save()` calls
  `api.updateRequirement(projectId, reqId, updates)` (`PUT /projects/{id}/requirements/{id}`),
  pushes undo, then **re-fetches `api.getEvaluation(projectId)`** when params/constraints changed.
- The graph (`frontend/src/components/GraphPane.tsx`) loads `getEvaluation` into an `evaluated`
  map (~line 606) and already flows a per-node **`verdict`** into node `data` (~line 927).
  `BlockNode.tsx` / `RequirementNode.tsx` colour a verdict badge / constraint dots (via
  `constraintColors`) but do **not** yet recolour the node border by fail state — room for our
  highlight. Node dimming/selection runs through `GraphSelectionCtx` / `useGraphSelection`
  (`connectedIds`, `hasSelection`, `selectedReqId`).
- **Layout (`frontend/src/components/Layout.tsx:250`)** mounts the canvas (`GraphPane`) and the
  inspector (`Outlet` → detail page) **side by side under one `SelectedReqCtx.Provider`** — so a
  sibling provider can drive both surfaces from one session.

---

## 2. Design decisions (confirmed)

| Decision | Choice |
|---|---|
| Which requirements count as "affected" | **Layered / both.** Ground truth = backend re-evaluation: any requirement whose verdict/margin genuinely changes. The canvas also emphasises edges among affected nodes; unaffected nodes dim. |
| How many values per session | **Stack multiple** overrides (trade-study); Confirm/Restore act on the whole set. |
| Availability | **Edit mode only** (`editMode` from `useAuthStore`). |
| Presentation | A **dialog over the inspector** animating the calculation through the affected equations in dependency order, **plus** the canvas updating live and in sync. |

---

## 3. Backend changes

### 3.1 Impact-trace builder — new `build_impact(store, overrides)` in `evaluation.py`
Returns `{ steps, affected, roots }`:

1. Build two evaluators over the same reqs/components/definitions: `base` (no overrides) and
   `over` (with the hypothetical overrides). Cheap; reuses `Evaluator` unchanged.
2. **Dependency extraction** — add `Evaluator.refs_in(text, owner, env) -> set[str]`, a walk that
   mirrors the existing `_eval` AST handling (`Name` → `owner.name` or `env` binding, `Attribute`
   → `ENTITY.attr`, `Call` → `rollup` subtree refs via the `children` map) but **collects**
   referenced `"ENTITY.param"` refs instead of evaluating. `calc_def`/`constraint_def` expand the
   definition's `expr` under `bindings`.
3. **Affected params** = every param ref whose `base.resolve` ≠ `over.resolve`, or that is a root,
   or that flips resolvable↔unresolvable. Each `resolve()` wrapped in try/except so a broken
   expression becomes a visible `unknown`/`error` step, never a 500.
4. **Ordering** = topological sort of affected params by `refs_in` edges, seeded from `roots`
   (Kahn). The evaluator already rejects real cycles; fall back to insertion order if one slips
   through. Each affected **constraint** is appended right after the last param it depends on.
5. **Step shapes:**
   ```jsonc
   { "kind": "param", "ref": "EMPT0001.mass", "owner": "EMPT0001", "name": "mass",
     "expr": "GROS0001.mass - fuel", "unit": "kg", "inputs": ["GROS0001.mass","EMPT0001.fuel"],
     "before": 743.0, "after": 761.0 }
   { "kind": "constraint", "owner": "EMPT0001", "expr": "mass <= 750",
     "before": { "status": "pass", "margin": {"value": 7.0, "pct": 0.93} },
     "after":  { "status": "fail", "margin": {"value": -11.0, "pct": -1.47} } }
   ```
6. `affected` = requirement ids whose **aggregate verdict** changed between `base` and `over`
   (compare per-req verdict from `evaluate_project`). `roots` echoes the override refs.

### 3.2 Endpoint — `backend/app/api/extra_routes.py`
Add beside `parametric_evaluation` (`extra_routes.py:987`):
```
POST /projects/{project_id}/evaluation/impact
body : { "overrides": { "REQ.param": <number>, ... } }
resp : { "evaluation": <EvaluationData with overrides>,  # for the canvas
         "steps": [ ...ordered... ], "affected": ["REQ", ...], "roots": ["REQ.param", ...] }
```
- `evaluation` = `evaluate_project(store, extra_overrides=overrides)`.
- `steps`/`affected`/`roots` = `build_impact(store, overrides)`.
- Override values coerced to `float`; malformed/unknown refs dropped. Same auth/project
  resolution as neighbouring routes. Never 500 on bad input.

### 3.3 Tests — `backend/tests/test_impact_preview.py`
- Overriding an input param that feeds a derived param + constraint → steps in dependency order,
  correct before/after, a `fail` appears.
- No-op override → empty `affected`, empty/near-empty `steps`.
- `rollup` and `calc_def` dependencies are traced.
- Unknown / malformed ref → ignored, 200.
- Endpoint auth + response shape.

---

## 4. Frontend changes

### 4.1 API client + types — `frontend/src/api/client.ts`
- `getEvaluationImpact(projectId, overrides): Promise<ImpactResult>` → `POST …/evaluation/impact`
  (reuse the `request<T>` wrapper).
- New types: `ImpactStepParam`, `ImpactStepConstraint`, `ImpactStep` (union),
  `ImpactResult { evaluation: EvaluationData; steps: ImpactStep[]; affected: string[]; roots: string[] }`.

### 4.2 Session provider — `frontend/src/components/WhatIfContext.tsx` (new), wired into `Layout.tsx`
Rendered inside `SelectedReqCtx.Provider`, wrapping the workspace `<div>` so both `GraphPane` and
the `Outlet` inspector consume it via `useWhatIf()`. State:
```ts
overrides: Record<string, number>;      // "REQ.param" -> hypothetical value
base:      Record<string, number|null>; // original values (diff + Restore label)
impact:    ImpactResult | null;
pending:   boolean;  error: string | null;
stepIndex: number;                       // animation cursor -> dialog + canvas pulse
playing:   boolean;
```
Actions: `setOverride(ref, value, original)`, `removeOverride(ref)`, `clear()` (Restore),
`confirm()`, `setStepIndex`, `setPlaying`.
- On any override change: **debounced ~250 ms** call to `getEvaluationImpact`; on result reset
  `stepIndex=0` and auto-play.
- `confirm()`: group overrides by requirement, `api.updateRequirement(projectId, reqId,
  { parameters })` writing the new literal `value`s, then `bumpGraphVersion()` +
  `bumpDataVersion()` and `clear()`.
- The entire provider no-ops unless `editMode` is on.

### 4.3 Trigger — `frontend/src/components/parametrics.tsx` (`ParametricsCard`)
For each **literal** parameter row (`value` present, no `expr`) in edit mode, add a small beaker
"what-if" toggle that reveals an inline number input seeded with the current value; typing calls
`setOverride("<reqId>.<name>", n, currentValue)`. An active override marks the row with a dashed
ring + `was X → Y`. Derived params get no affordance (they are computed downstream).

### 4.4 Propagation dialog — `frontend/src/components/WhatIfPanel.tsx` (new)
A panel **overlaying the inspector pane only** (absolutely positioned inside `<main>`, whose
`@container` is already the containing block — no full-screen portal, so the canvas stays
visible):
- **Header:** `N requirements affected · M now failing · K now passing`, plus the roots
  (`REQ.param: was X → Y`).
- **Animated cascade:** `impact.steps` as an ordered list; playback reveals them one at a time
  (`stepIndex` advances on a ~600 ms timer; prev / next / play-pause controls; click a step to
  jump). Each step card shows the equation with its `inputs` values substituting in → `before →
  after`; constraint steps show before/after `VerdictBadge` + `MarginTag`. Newly-broken steps
  flash red, newly-fixed green.
- **Footer:** **Confirm** (writes; disabled while `pending` or no overrides) and **Restore**
  (`clear()`).
- Reuses `VerdictBadge` / `MarginTag` / `VERDICT_META` from `parametrics.tsx`.

### 4.5 Live canvas highlight — `GraphPane.tsx` + `BlockNode.tsx` + `RequirementNode.tsx`
- `GraphPane` consumes `useWhatIf()`. When `impact` is present, overlay onto node `data` in the
  build (~lines 831-931, where `verdict` is set at ~927):
  - `previewVerdict` — the node's verdict from `impact.evaluation`.
  - `previewDelta: 'broke' | 'fixed' | 'changed' | null` — base verdict vs preview verdict.
  - `isOverrideRoot` — owns one of `impact.roots`.
  - `pulseActive` — `owner === impact.steps[stepIndex].owner` (syncs the canvas pulse to the
    dialog's current step).
- Drive dimming through the existing machinery: when a session is active, set `hasSelection` and
  `connectedIds = rootOwners ∪ impact.affected` in `GraphSelectionCtx`, so unaffected nodes dim
  and the affected chain (and the edges among affected nodes) stays lit.
- `BlockNode` / `RequirementNode`: when `previewDelta` is set, recolour the node **border/ring**
  (broke = red pulse, fixed = emerald, changed = amber; root = blue "editing" ring) and swap the
  footer verdict badge to `previewVerdict`; brief pulse when `pulseActive`. Reuse
  `constraintColors` (BlockNode) and `glow()` (`graphColors.ts`).

---

## 5. Build order / phasing

Recommended **phased** landing to de-risk (each phase independently verifiable):

- **Phase A — engine + live canvas (safest first):** §3 (endpoint, trace, tests) → §4.1 (client) →
  §4.2 (context) → §4.3 (trigger) → §4.5 (canvas highlight, static end-state; no animation yet) →
  Confirm/Restore. At this point the whole loop works: enter a value, canvas lights up, confirm or
  restore.
- **Phase B — the animation:** §4.4 dialog with playback + `stepIndex`, and wire `pulseActive` in
  §4.5 so canvas pulses sync to the dialog steps.

(If you'd rather ship it all at once, the same order applies without the phase gate.)

---

## 6. Risks & mitigations
- **Debounce vs. keystrokes:** every override edit hits the backend; 250 ms debounce + cancel of
  in-flight requests (ignore stale responses by sequence token) keeps it smooth.
- **Topological order with a bad cycle:** evaluator already detects circular derivation; builder
  falls back to insertion order and marks the offending step `error` rather than looping.
- **Panel containment:** the inspector `<main>` already has `@container` (⇒ `contain: layout`), so
  an absolutely-positioned panel is correctly clipped to the inspector and the canvas stays
  interactive — verified against the responsive work already in the codebase.
- **Confirm writing derived params:** only **literal** params get a what-if input, so Confirm only
  ever writes real input values — never a computed `expr` result.

---

## 7. Verification
1. `cd backend && .venv/bin/pytest tests/test_impact_preview.py` then the full suite;
   `cd frontend && npm run typecheck && npm run test && npm run build`.
2. Drive the real app (run-app skill; rebuild `dist` first), edit mode on, cessna-172 project:
   - Enter a what-if value that **breaks** a downstream threshold → dialog animates the cascade in
     dependency order, ending on the failing constraint; canvas dims unaffected nodes, rings the
     broken one red, and the active step pulses its node in sync. Numbers match a manual calc.
   - **Restore** → canvas + dialog clear; re-fetch confirms the original value was never written.
   - **Confirm** → value persists; evaluation re-fetches; highlight clears; committed verdict updates.
   - **Stack** two overrides across two requirements → combined downstream effect shown; Confirm
     writes both.
   - No-op override → "0 affected", empty cascade.
   - View mode → what-if affordance absent.
   - Both themes; narrow inspector (panel overlays inspector only; canvas stays visible; no
     horizontal overflow).

---

## 8. Files touched (summary)

**Backend**
- `backend/app/services/evaluation.py` — `build_impact()`, `Evaluator.refs_in()`.
- `backend/app/api/extra_routes.py` — `POST …/evaluation/impact`.
- `backend/tests/test_impact_preview.py` — new.

**Frontend**
- `frontend/src/api/client.ts` — `getEvaluationImpact`, impact types.
- `frontend/src/components/WhatIfContext.tsx` — new (session state).
- `frontend/src/components/WhatIfPanel.tsx` — new (animated dialog).
- `frontend/src/components/Layout.tsx` — provider wiring.
- `frontend/src/components/parametrics.tsx` — what-if trigger on literal param rows.
- `frontend/src/components/GraphPane.tsx` — preview overlay + dimming.
- `frontend/src/components/BlockNode.tsx`, `frontend/src/components/RequirementNode.tsx` — preview ring/badge/pulse.
