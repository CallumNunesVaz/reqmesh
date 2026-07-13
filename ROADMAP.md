# reqmesh Implementation Roadmap

This document proposes the next phases of reqmesh development. Each feature is
derived from a specific strength of a mature open-source requirements tool, with
detailed implementation instructions grounded in reqmesh's actual architecture.

**Status legend:** ✅ done · 🔨 proposed · ⚡ quick win (low effort / high value)

## Inspiration sources

The proposals below borrow deliberately from three git/text-native requirements
tools. Understanding their models is the basis for these features:

| Tool | Repo | Core idea reqmesh can learn from |
|------|------|----------------------------------|
| **OpenFastTrace (OFT)** | https://github.com/itsallcode/openfasttrace | Trace requirements into **source code & tests** via tags scanned from files; `Needs`/`Covers` coverage types; **shallow vs deep** coverage; revision-versioned links; rich link-status taxonomy |
| **Doorstop** | https://github.com/doorstop-dev/doorstop | **Fingerprint-based review** (content hash auto-invalidates review on change); `derived`/`normative`/heading item semantics; structured external `references` with SHA; CSV/TSV/XLSX interchange; per-document custom-attribute schema |
| **rmtoo** | https://github.com/florath/rmtoo | **Requirement-text quality heuristics** (weak words, ambiguity, testability); per-stakeholder priority; effort estimation → burndown; prioritized backlog; dependency-graph cycle validation |

## Where reqmesh stands today (Phases 1–5, ✅)

- YAML/git-native storage, one file per entity (`backend/app/services/yaml_store.py`).
- Requirements, specifications, verification cases, traces, change requests, risks,
  comments, decisions, baselines, field-level history.
- Traceability + verification, cascade propagation, workflow state machine
  (`app/services/workflow.py`), impact analysis.
- Git auto-commit, log, pre-commit hooks; baselines with freeze/diff.
- Analysis: metrics, coverage, gap-analysis, conflicts, compliance, integrity
  checks with **imperative** suspect-links (`app/services/integrity.py`).
- ReqIF 1.2 + SysML v2 import **and** export; publish to HTML/MD/LaTeX/PDF.
- Real-time collaboration (SSE change stream + presence).
- Auth (viewer/editor/admin), React UI, CLI (`create/validate/publish/export/import/serve`).

### Honest gaps these phases target

- Coverage is **single-level and binary** (`coverage_analysis`: covered = `VC>0 AND relations>0`).
- "Quality" metrics measure **completeness only** (has-description/rationale/…), not text quality.
- Review (`review_status`) and suspect-links are **manual/imperative** — no content fingerprint.
- **No link from requirements to actual source code or test files.**
- Interchange is limited to ReqIF/SysML (no spreadsheet round-trip).
- No effort/estimation, per-stakeholder priority, or planning artifacts.

---

## Phase 6 — Code & Test Traceability 🔨 *(flagship)*

**Inspiration:** OpenFastTrace's source-code coverage tags
(`// [impl->dsn~validate-request~1]`, recognised across Java/Python/C/JS/SQL/…)
and Doorstop's structured `references` (`{path, type, keyword}` with per-file
SHA). This is the biggest strategic gap and the most natural fit for reqmesh's
git-native identity: the links live where the code lives.

**Goal:** connect requirements to the source files and tests that implement/verify
them, and detect when a linked file changes.

### 6.1 Structured references on the requirement model

Extend `backend/app/models/requirement.py`:

```python
class Reference(BaseModel):
    path: str                      # repo-relative, e.g. "src/auth/login.py"
    keyword: Optional[str] = None  # optional anchor string to locate within file
    kind: str = "impl"             # impl | test | doc
    sha256: Optional[str] = None   # hash captured when linked (staleness detection)
    lines: Optional[str] = None    # optional "L20-L45"
```

Add `references: list[Reference] = Field(default_factory=list)` to `Requirement`,
`RequirementCreate`, `RequirementUpdate`. Persisted as YAML like:

```yaml
references:
  - path: backend/app/core/auth.py
    keyword: "def authenticate"
    kind: impl
    sha256: "9f2c…"
```

### 6.2 Source-tag scanner service

New `backend/app/services/code_scan.py`:

- `scan_tree(code_root: Path, patterns: dict) -> list[dict]` walks the tree
  (respecting `.gitignore` via `git ls-files` when available, else `os.walk`
  with a skip-list), reads text files, and extracts coverage tags from comments.
- Default tag grammar (OFT-style, configurable): `[<kind>-><REQ-ID>]` and a
  looser `@covers <REQ-ID>` / `@satisfies <REQ-ID>`. Regex:
  `r"\[(?P<kind>[a-z]+)\s*->\s*(?P<id>[A-Za-z0-9._-]+)\]"`.
- Returns hits `{req_id, kind, path, line, sha256}`.
- `compute_sha(path)` uses `hashlib.sha256` on file bytes.

Config in `app/core/config.py`: `code_root: str = ""` (env `RT_CODE_ROOT`) and
`scan_extensions` / `scan_tag_patterns` overridable per project via `_meta.yaml`.

### 6.3 Staleness detection

New `app/services/references.py`:
`check_reference_freshness(store, code_root)` compares each requirement's stored
`references[].sha256` with the current file hash → returns
`{req_id, path, status: ok|changed|missing}`. Reuse the existing suspect-link
surface so a changed impl file flags the requirement.

### 6.4 API

Add to `app/api/extra_routes.py`:

- `POST /projects/{id}/scan` (require_edit) — run `scan_tree` against `code_root`,
  merge discovered links into requirement `references` (dedupe by path+kind),
  return a summary `{created, updated, files_scanned, requirements_touched}`.
- `GET /projects/{id}/references/freshness` — the staleness report.

### 6.5 CLI

New command in `app/cli.py`:

```
oft-style:  python -m app.cli scan <project-path> --code <code-dir> [--dry-run]
```

Print a table of discovered links; `--dry-run` reports without writing.

### 6.6 Frontend

- `client.ts`: `scanProject(id, opts)`, `getReferenceFreshness(id)`.
- Requirement detail page (`pages/RequirementDetailPage.tsx`): a **References**
  panel listing files (path, kind badge, fresh/stale indicator, line anchor).
- A "Scan code" action in the Layout header (editors only), reusing the
  `ImportDialog` pattern; show the scan summary toast.
- Feed stale references into the existing coverage view.

### 6.7 Tests & acceptance

- `tests/test_code_scan.py`: fixture tree with tagged files → assert links found,
  SHA captured, `.gitignore`/binary files skipped, dedupe on re-scan.
- Acceptance: tagging a source file and running `scan` produces a reference on
  the requirement; editing that file flips its freshness to `changed`.

**Effort:** L (largest phase). Ship 6.1–6.4 first; 6.5/6.6 incrementally.

---

## Phase 7 — Coverage Completeness & Deep Tracing 🔨

**Inspiration:** OFT's `Needs:` (which artifact types must cover an item), its
distinction between **shallow** coverage (each needed type has ≥1 coverer) and
**deep** coverage (coverers are themselves fully covered → end-to-end chains),
and its link-status taxonomy (orphaned / unwanted / outdated / predated).

**Goal:** move reqmesh from binary coverage to a per-artifact-type, transitive
model with a CI-friendly report.

### 7.1 Data model

Add `needs: list[str]` to the requirement (artifact types that must cover it,
e.g. `["design", "test"]`; empty = terminating). Reuse existing `type` values
plus references `kind` from Phase 6 as coverage providers.

### 7.2 Coverage engine

New `backend/app/services/tracing.py` (extract/expand the logic currently inline
in `extra_routes.coverage_analysis`):

- Build a directed graph of requirements (via `relations`, `parent`,
  `verification_cases`, and Phase-6 `references`).
- `shallow_status(req)` → for each entry in `needs`, is there ≥1 covering item of
  that type? Return per-type `covered/uncovered`, plus `+unexpected` / `-missing`.
- `deep_status(req)` → memoised DFS: covered AND every coverer deep-covered;
  detect and break cycles (see 7.4).
- Emit a `CoverageItem` with `shallow`, `deep`, `uncovered_types`, `broken_chain`.

### 7.3 Link-status taxonomy in the integrity checker

Extend `IntegrityChecker` (`app/services/integrity.py`) with OFT-style statuses:

- `orphaned` — relation target doesn't exist (already partly covered by
  `_check_dangling_links`; rename/extend).
- `unwanted` — an item covers a target whose `needs` didn't ask for that type.
- `outdated`/`predated` — once Phase 8 adds fingerprints/revisions, compare.

### 7.4 Dependency cycle detection *(also from rmtoo)*

Add `_check_relation_cycles()` to `IntegrityChecker`: Tarjan/DFS over the
`relations` graph (today only `_check_circular_parents` exists). Report SCCs of
size > 1 as errors — mirrors rmtoo's "NoDirectedCircles" rule.

### 7.5 API & CLI

- `GET /projects/{id}/coverage` — extend response with `shallow`/`deep`/`needs`.
- `GET /projects/{id}/trace` — full tracing report (JSON).
- CLI `python -m app.cli trace <project>` prints an OFT-style plaintext report
  and **exits non-zero** when deep coverage is incomplete (CI gate). Model the
  output on OFT: `not ok [ in: 1/2 | out: 0/1 ] REQ-001 (-test)`.

### 7.6 Frontend

- Coverage page: per-type coverage chips, a deep-vs-shallow toggle, and a
  "broken chains" list.

### 7.7 Tests

- `tests/test_tracing.py`: chains that are shallow-but-not-deep, unwanted
  coverage, cycles, terminating items.

**Effort:** M. Depends conceptually on Phase 6 references but can ship with just
reqs+VCs first.

---

## Phase 8 — Review & Change Control 🔨

**Inspiration:** Doorstop's fingerprint model — each item has a SHA256 of its
normative content; the `reviewed` field stores the fingerprint at last review,
and links store the parent's fingerprint. When content or a parent changes, the
fingerprint diverges and the item/link is automatically flagged as needing
re-review. `doorstop review` re-baselines. Also Doorstop's `derived` (needs no
parent link) and `normative`/heading semantics.

**Goal:** replace reqmesh's imperative suspect-links with an automatic,
content-hash-driven review workflow — the compliance-grade differentiator.

### 8.1 Fingerprints

New `backend/app/services/fingerprint.py`:

- `compute(req) -> str`: SHA256 over a canonical subset of normative fields
  (`type,name,description,rationale,priority,verification_method`, plus link
  target IDs) — mirror Doorstop's rule that only the UID of a link contributes,
  not its stored parent-hash. URL-safe base64, matching Doorstop's format.
- Store `reviewed: <fingerprint>|null` on the requirement (null = never reviewed).
- On each link in `relations`, optionally store the target's fingerprint at review
  time: `{type, target, reviewed_fingerprint}`.

### 8.2 Automatic staleness

Replace/augment `mark_links_suspect` in `integrity.py`:

- An item is **unreviewed** when `compute(req) != req["reviewed"]`.
- A link is **suspect** when the target's current fingerprint ≠ the link's stored
  `reviewed_fingerprint` (i.e. the parent changed after the child last reviewed it).
- This is computed on read (in `IntegrityChecker`), so no imperative bookkeeping
  and no `_suspect.yaml` drift.

### 8.3 Review action

Rework `POST /projects/{id}/requirements/{rid}/review` (already exists) to:
- set `reviewed = compute(req)` and stamp each `relations[].reviewed_fingerprint`
  with the current target fingerprint;
- keep the existing `reviewers` / `review_comments` audit fields;
- record a `review` history entry.

Add `POST /projects/{id}/review-all` and CLI `python -m app.cli review <project>
[--item ID]` to re-baseline (Doorstop parity).

### 8.4 Item semantics

Add to the model:
- `derived: bool = False` — when true, `_check_orphan_requirements` no longer
  flags a missing parent (Doorstop's derived rule).
- `normative: bool = True` — non-normative items are excluded from coverage and
  gap analysis; a non-normative item can act as a section **heading** in publish
  output (`publisher.py`).

### 8.5 Frontend

- A "Needs re-review" badge on items whose fingerprint diverged; a one-click
  **Review** button that re-baselines.
- Toggles for `derived`/`normative` in the requirement editor.

### 8.6 Tests

- `tests/test_fingerprint.py`: editing a normative field flips `unreviewed`;
  editing a non-fingerprinted field (e.g. `allocated_to`) does not; parent edit
  makes child link suspect; `review` clears both.

**Effort:** M. High compliance value; self-contained.

---

## Phase 9 — Requirement Quality Linting ⚡ *(quick win)*

**Inspiration:** rmtoo's quality heuristics — it scores requirement text and
flags low-quality wording (weak words, ambiguity, count-words). reqmesh's current
"quality" is only completeness, so this is net-new and immediately useful.

**Goal:** lint the natural-language quality of requirements and expose scores in
the editor, a report, and CI.

### 9.1 Linter service

New `backend/app/services/quality.py`:

- Operate on plain text (strip the XHTML from `description` — reuse the
  `stripHtml` idea already in the frontend, mirror it server-side).
- Rules (each returns findings with severity + span):
  - **weak/ambiguous words**: "should, may, might, could, appropriate, adequate,
    as needed, etc., and/or, user-friendly, fast, robust".
  - **vague quantifiers**: "some, several, many, minimal, maximal" without a number.
  - **passive voice** (heuristic: `be`-verb + past participle).
  - **placeholders**: "TBD, TODO, ???, FIXME".
  - **non-atomic**: multiple " and "/" or " joining clauses (possible split).
  - **untestable**: no measurable term and `verification_method == test`.
  - **length**: word count outside `[min,max]` (configurable).
- `score(req) -> {score: 0..100, findings: [...]}` — weighted deduction.
- Config/thresholds in `_meta.yaml` under `quality:` (rule toggles + weights).

### 9.2 API & CLI

- `GET /projects/{id}/quality` — per-requirement scores + findings + project
  average (sits beside `gap-analysis`).
- CLI: fold into `python -m app.cli validate --quality` and fail CI when the
  project average or any requirement drops below a configurable floor.

### 9.3 Frontend

- Inline in `RichTextEditor.tsx`: underline weak words as the user types
  (client-side mirror of the rule list); a quality meter in the detail panel.
- A "Quality" tab on the metrics page with the worst offenders.

### 9.4 Tests

- `tests/test_quality.py`: known-bad sentences trigger the right rule; clean
  sentence scores 100; thresholds gate the CLI exit code.

**Effort:** S. No data-model change. Strong candidate to ship first.

---

## Phase 10 — Planning & Estimation 🔨

**Inspiration:** rmtoo's per-stakeholder priority (`development:5 customers:5`),
effort estimation (story points), burndown/statistics, and prioritized backlog
artifacts.

**Goal:** add lightweight project-planning signals on top of requirements.

### 10.1 Data model

- `effort: Optional[int] = None` — story points.
- `priorities: dict[str, int] = {}` — per-stakeholder scores, keeping the existing
  `priority` enum as a derived/overall value for backward compatibility.

### 10.2 Services & artifacts

- Extend `project_metrics` (`extra_routes.py`) with total/remaining effort by
  status → a **burndown** series (bucketed by the `modified`/history timeline).
- New `GET /projects/{id}/backlog` — requirements ordered by a configurable
  priority function (weighted per-stakeholder × effort), like rmtoo's prioritized
  backlog.
- Optional: a GanttProject/CSV planning export in `publisher.py`.

### 10.3 Frontend

- Metrics page: burndown chart (recharts is already a dependency) and a sortable
  backlog table with effort + per-stakeholder priority columns.

### 10.4 Tests

- `tests/test_planning.py`: backlog ordering, effort rollups, empty-project guards.

**Effort:** M.

---

## Phase 11 — Interchange & Attribute Schema ⚡ *(CSV half is a quick win)*

**Inspiration:** Doorstop's CSV/TSV/XLSX import & export and its configurable
per-document attribute schema (`attributes.defaults` / `.publish` / `.reviewed`).

**Goal:** stakeholder-friendly spreadsheet round-trip and a real custom-attribute
schema.

### 11.1 CSV/TSV/XLSX

- New `backend/app/services/table_io.py`:
  - `export_table(store, fmt)` flattens requirements to rows (stable column
    order: id, type, name, description-as-text, status, priority, parent,
    relations-joined, verification_cases-joined, plus custom attributes).
  - `import_table(store, content, fmt, mode)` mirrors the existing
    `importer.parse_and_import` contract (merge/replace, id validation via
    `core/ids.safe_id`). Use `openpyxl` for XLSX (add to `requirements.txt`),
    stdlib `csv` for CSV/TSV.
- Wire into the existing endpoints: extend `POST /projects/{id}/import` format
  enum and `publish/download` format map (both already dispatch on `format`).
- Add `csv`/`xlsx` to the `ImportDialog`/`ExportDialog` format lists in the UI.

### 11.2 Custom-attribute schema

- Per-project `attributes:` block in `_meta.yaml`:
  `{defaults: {...}, publish: [...], reviewed: [...]}` mirroring Doorstop.
- Apply `defaults` on create; include `publish` attributes in `publisher.py`
  output; add `reviewed` attributes into the Phase-8 fingerprint input.

### 11.3 Tests

- `tests/test_table_io.py`: round-trip CSV and XLSX; custom columns preserved;
  malformed rows rejected with a clear error.

**Effort:** CSV/TSV = S (quick win); XLSX + schema = M.

---

## Suggested sequencing

1. **Phase 9 (quality linting)** ⚡ — smallest, no schema change, immediate value.
2. **Phase 11 CSV/TSV export+import** ⚡ — self-contained, high stakeholder value.
3. **Phase 8 (fingerprint review)** — compliance-grade, self-contained.
4. **Phase 6 (code traceability)** — the strategic differentiator (largest build).
5. **Phase 7 (deep coverage)** — builds naturally on Phase 6.
6. **Phase 10 (planning)** and **Phase 11 XLSX/schema** — round out.

## Cross-cutting conventions

- Keep every new field **optional** with a sensible default so existing YAML and
  the ReqIF/SysML round-trips (`reqif_import`/`sysml_import`/`importer`) stay valid.
- Every new analysis service gets a CLI surface that returns a **CI exit code**
  (reqmesh already does this for `validate`).
- Add fields to the frontend `Requirement` interface in `client.ts` in lockstep
  so imported records stay shape-consistent (as done for the import/presence work).
- Regenerate JSON schemas (`python backend/gen_schemas.py`) after model changes.

## Appendix — feature → inspiration map

| Phase | Feature | Inspired by | Their mechanism |
|-------|---------|-------------|-----------------|
| 6 | Code/test traceability | OFT tags + Doorstop `references` | `[impl->id]` comment tags; `{path,keyword,sha}` |
| 7 | `needs` + shallow/deep coverage | OFT | required coverage types; transitive coverage |
| 7 | Link-status taxonomy | OFT | orphaned/unwanted/outdated/predated |
| 7 | Relation cycle detection | rmtoo | "NoDirectedCircles" DAG rule |
| 8 | Fingerprint review | Doorstop | SHA256 of normative fields; `reviewed` baseline |
| 8 | `derived`/`normative`/heading | Doorstop | derived needs no parent; non-normative excluded |
| 9 | Requirement quality linting | rmtoo | weak-word / count-words heuristics |
| 10 | Per-stakeholder priority | rmtoo | `development:5 customers:5` |
| 10 | Effort → burndown, backlog | rmtoo | story points, prioritized backlog artifact |
| 11 | CSV/TSV/XLSX interchange | Doorstop | spreadsheet import/export |
| 11 | Custom-attribute schema | Doorstop | `attributes.defaults/publish/reviewed` |
