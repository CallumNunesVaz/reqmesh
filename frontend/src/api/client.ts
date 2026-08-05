const BASE = '/api';

/** An error carrying the server's structured `detail`, when it sent one. */
export class ApiError extends Error {
  status: number;
  data?: unknown;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export interface Referrer {
  holder: string;
  id: string;
  name: string;
  field: string;
  label: string;
}

/** 409 body from the delete guard. */
export interface ReferencedError {
  error: 'referenced';
  message: string;
  id: string;
  collection: string;
  referrers: Referrer[];
}

export interface Backlinks {
  id: string;
  collection: string;
  total: number;
  groups: { collection: string; label: string; items: Referrer[] }[];
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  raw?: boolean;
}

function getCsrfToken(): string {
  try { return useAuthStore.getState().csrfToken || ''; } catch { return ''; }
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body } = options;
  const headers: Record<string, string> = {};

  if (method !== 'GET' && method !== 'HEAD') {
    const csrf = getCsrfToken();
    if (csrf) {
      headers['X-CSRF-Token'] = csrf;
    }
  }

  if (body && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    credentials: 'include',
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail;
    // A structured detail (the delete guard's 409 carries the referrer list)
    // used to be interpolated into a string as "[object Object]", losing the
    // very information the caller needs to offer a sensible next step.
    if (detail && typeof detail === 'object') {
      const e = new ApiError(detail.message || `Request failed: ${res.status}`, res.status);
      e.data = detail;
      throw e;
    }
    const e = new ApiError(detail || `Request failed: ${res.status}`, res.status);
    throw e;
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

import { useAuthStore } from '../store/auth';

export interface Project {
  id: string;
  name: string;
  path: string;
  /** Only present on `getProject`; `listProjects` omits it. Baselines used to
   *  be bare name strings and hand-edited `_meta.yaml` may still hold those,
   *  so both shapes are accepted — use `baselineNames` to read them. */
  baselines?: (string | BaselineDef)[];
  /** Only present on `getProject`. Normalized server-side, so always objects. */
  stakeholders?: StakeholderDef[];
  /** Only present on `getProject`. Normalized server-side. */
  system_states?: SystemStateDef[];
  risk_matrix?: RiskMatrix;
}

export interface BaselineDef {
  name: string;
  symbol: string;
  description: string;
  /** `YYYY-MM-DD`, or "" when the baseline has no deadline. */
  due_date: string;
  /** 1-based position in the sequence. Derived server-side from the order the
   *  definitions are stored in — never sent back on a write. Reorder with
   *  `reorderBaselines`. */
  order: number;
}

/** Baseline *names* from either storage shape.
 *
 *  `requirement.baselines` is an array of names, so anything comparing against
 *  it (filters, toggles, `<option value>`) needs names rather than the
 *  definition objects `getProject` now returns. */
export const baselineNames = (baselines?: (string | BaselineDef)[]): string[] =>
  (baselines || []).map((b) => (typeof b === 'string' ? b : b.name));

export interface BaselineInfo extends BaselineDef {
  requirements: string[];
  count: number;
  frozen: boolean;
  frozen_at: string;
  frozen_count: number;
}

export interface BaselineDiff {
  baseline: string;
  symbol: string;
  description: string;
  frozen_at: string;
  changes: Array<{
    id: string;
    type: 'added' | 'modified' | 'removed';
    diffs?: Record<string, { before: string; after: string }>;
  }>;
  changed_count: number;
}

export interface SearchResult {
  kind: string;
  kind_label: string;
  kind_icon: string;
  id: string;
  name: string;
  snippet: string;
  score: number;
  status: string;
}

/** A project-level system state. `requirement.system_states` holds these by
 *  name, so defining them is what lets the editor offer a list rather than a
 *  free-text box where a typo makes a state nobody can find again. */
export interface SystemStateDef {
  name: string;
  description: string;
  /** 1-based position, derived from storage order server-side. Never sent back. */
  order: number;
}

/** Envelope returned by GET /system-states. */
export interface SystemStatesResponse {
  states: SystemStateDef[];
  /** Names used by some requirement but defined nowhere — surfaced so the
   *  user can define them rather than wondering where they went. */
  orphans: string[];
}

export interface StakeholderDef { name: string; weight: number }

/** Scores run 0-5. Bounded server-side on write only, so a project written
 *  before the rescale can still hold a larger number until it is next edited. */
export const PRIORITY_MIN = 0;
export const PRIORITY_MAX = 5;

/** One requirement's column in the Pugh matrix. */
export interface PughColumn {
  id: string;
  name: string;
  value: number;
  rank: number;
  /** Keyed by stakeholder name. `sign` is the comparison against the datum;
   *  `null` when either side is unscored, which is not the same as parity. */
  cells: Record<string, { score: number | null; sign: number | null }>;
  plus: number;
  minus: number;
  /** Sum of weight x sign over the comparable stakeholders. */
  weighted: number;
}

/** Stakeholders are the criteria, requirements the alternatives, and every
 *  column is scored relative to `datum` — whose own column is all zeroes by
 *  definition. `null` datum means nothing is scored yet. */
export interface PughMatrix {
  datum: string | null;
  limit: number;
  /** Scored requirements before `limit` was applied. */
  total_candidates: number;
  stakeholders: StakeholderDef[];
  columns: PughColumn[];
}

export interface RequirementValue {
  id: string;
  /** null when no defined stakeholder has scored it — not the same as 0. */
  value: number | null;
  rank: number | null;
  ranked_total: number;
  scored_count: number;
  stakeholder_count: number;
  contributions: { name: string; weight: number; score: number | null; contribution: number | null }[];
  /** Scores whose stakeholder is no longer defined on the project. */
  unknown_stakeholders: string[];
}

/** Which relationship a matrix shows.
 *
 *  `components`, `verification` and `risks` are links declared in the backend's
 *  link registry whose target is `requirements` — the column entity holds the
 *  link, keyed by requirement id.
 *
 *  `baselines` is the exception: its columns are project-metadata definitions
 *  rather than records, and membership lives on `requirement.baselines` as
 *  baseline *names*. Column `id` is therefore the baseline name. */
export type MatrixAxis = 'components' | 'verification' | 'risks' | 'baselines';

export interface AllocationMatrixData {
  axis: MatrixAxis;
  /** Reads as "<requirement> <verb> <column>", e.g. "is verified by". */
  verb: string;
  column_label: string;
  rows: Array<{
    req_id: string;
    req_name: string;
    req_status: string;
    req_type: string;
    allocated_to: string;
    cells: Record<string, boolean>;
  }>;
  columns: Array<{
    /** The column entity's id — except on the `baselines` axis, where it is
     *  the baseline *name*, because that is what `requirement.baselines`
     *  stores. */
    id: string;
    name: string;
    /** The column entity's secondary label: component type, verification
     *  method, risk severity, or a baseline's symbol. */
    kind: string;
    /** `baselines` axis only: `YYYY-MM-DD` or "". */
    due_date?: string;
    /** `baselines` axis only: 1-based position in the sequence. Columns are
     *  returned in this order, so a requirement's progress reads left to
     *  right. */
    order?: number;
  }>;
  total_requirements: number;
  total_columns: number;
  allocated: number;
  unallocated: number;
  allocation_pct: number;
}

export interface TestResultImportDetail {
  vc_id?: string;
  test_name: string;
  test_class?: string;
  status: string;
  detail: string;
}

export interface TestResultImportSummary {
  format: string;
  dry_run: boolean;
  parsed: number;
  matched: number;
  updated: number;
  unmatched: number;
  errors: string[];
  details: TestResultImportDetail[];
}

/** Envelope returned by paginated list endpoints. */
export interface Paged<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

/** A typed numeric quantity; `expr` derives it, or a `calc_def` usage does. */
export interface Parameter {
  name: string;
  value?: number | null;
  unit?: string;
  expr?: string | null;
  kind?: 'MOE' | 'MOP' | 'TPM' | null;
  value_type?: string | null;
  calc_def?: string | null;
  bindings?: Record<string, string>;
}

/** A boolean constraint: an inline `expr`, or a `constraint_def` usage bound to refs. */
export interface Constraint {
  expr?: string;
  assume?: string | null;
  kind?: 'MOE' | 'MOP' | 'TPM' | null;
  constraint_def?: string | null;
  bindings?: Record<string, string>;
}

/** A reusable SysML v2-style constraint/calc definition over formal parameters. */
export interface Definition {
  id: string;
  type: 'constraint' | 'calc';
  name?: string;
  parameters: string[];
  expr: string;
  unit?: string;
  doc?: string;
}

/** A scoped, parameterised evaluation (what-if analysis) over the model. */
export interface AnalysisCase {
  id: string;
  name?: string;
  doc?: string;
  scope: string[];
  overrides: Record<string, number>;
}

/** Registered units offered for autocomplete when entering a parameter. */
export const KNOWN_UNITS = [
  'kg', 'g', 'lb', 't', 'm', 'mm', 'cm', 'km', 'in', 'ft', 'm2', 'm3', 'L',
  's', 'min', 'h', 'A', 'mA', 'K', 'N', 'kN', 'Pa', 'kPa', 'MPa', 'bar', 'psi',
  'J', 'W', 'kW', 'hp', 'V', 'Hz', 'm/s', 'km/h', 'kt', '%', 'each', 'deg',
] as const;

/** A measured value recorded against a fully-qualified parameter ref. */
export interface Measurement {
  parameter: string;
  value: number;
  unit?: string;
}

export interface Requirement {
  id: string;
  type: string;
  name: string;
  description: string;
  priority: string;
  status: string;
  /** Derived from the verifying cases — read-only. Sending it on create or
   *  update is ignored by the API; link a verification case instead. */
  verification_method: string;
  /** Every distinct method among the verifying cases; `verification_method` is
   *  the first of these. Empty when nothing verifies this requirement. */
  verification_methods: string[];
  attributes: { key: string; value: string }[];
  parameters: Parameter[];
  constraints: Constraint[];
  relations: { type: string; target: string; reviewed_fingerprint?: string | null }[];
  /** Derived from `verification_case.verified_requirements` — read-only. */
  verification_cases: string[];
  /** Derived: the worst status among the verifying cases. Read-only. */
  verification_status: string;
  parent: string | null;
  cascade_from: string | null;
  rationale: string;
  source: string;
  allocated_to: string;
  baselines: string[];
  references: Reference[];
  reviewed: string | null;
  normative: boolean;
  priorities: Record<string, number>;
  needs: string[];
  system_states: string[];
  subject?: string | null;
  created: string;
  modified: string;
}

export interface Reference {
  path: string;
  keyword?: string | null;
  kind: string;
  sha256?: string | null;
  lines?: string | null;
}

export interface RequirementTreeNode {
  id: string;
  name: string;
  type: string;
  status: string;
  priority: string;
  children: RequirementTreeNode[];
}

/** A piece of the synthesised design, as opposed to a functional requirement. */
export interface Component {
  id: string;
  name: string;
  description: string;
  type: string;
  parent: string | null;
  part_number: string;
  supplier: string;
  quantity: number;
  satisfies: string[];
  verification_cases: string[];
  relations: { type: string; target: string }[];
  attributes: { key: string; value: string }[];
  parameters: Parameter[];
  created: string;
  modified: string;
}

export interface ComponentTreeNode {
  id: string;
  name: string;
  type: string;
  quantity: number;
  satisfies: string[];
  children: ComponentTreeNode[];
}

export const COMPONENT_TYPES = ['system', 'subsystem', 'assembly', 'part', 'software', 'interface'] as const;

export interface Specification {
  id: string;
  name: string;
  description: string;
  /** Link to the authoritative source document. May be empty. Rendered as an
   *  anchor, so pass it through `isSafeExternalUrl` before building an href —
   *  the backend blanks unsafe values on load, but the check is cheap and a
   *  `javascript:` href is stored XSS against every viewer. */
  url: string;
  requirements: string[];
  children: string[];
  created: string;
  modified: string;
}

export interface VerificationCase {
  id: string;
  name: string;
  description: string;
  method: string;
  status: string;
  result: string | null;
  verified_requirements: string[];
  test_procedure: string;
  steps: { action: string; expected_result: string; actual_result?: string | null }[];
  execution_history: { timestamp: string; status: string; notes: string; executed_by: string }[];
  measurements: Measurement[];
  case_type: 'verification' | 'validation';
  environment: string;
  decision_gate: string | null;
  created: string;
  modified: string;
}

export interface TraceLink {
  source: string;
  target: string;
  type: string;
}

/** A trace-model link returned by GET /trace-model.  Extends TraceLink with
 *  origin metadata so the UI can distinguish derived edges from hand-authored
 *  ones. */
export interface TraceModelLink extends TraceLink {
  holder: string;
  target_collection: string;
  /** False for registry-derived edges; true for hand-authored traces. */
  stored: boolean;
}

/** Offered in the UI. Unlike the risk vocabularies this is not per-project. */
export const CR_URGENCIES = ['low', 'normal', 'high', 'emergency'] as const;

/** One field's redline. `before` is read live from the target, not stored, so
 *  the diff always shows what would actually change now. */
export interface CRFieldDiff { before: unknown; after: unknown }

/** The redline for one change request, computed server-side. */
export interface CRRedline {
  id: string;
  targets: Array<{
    id: string;
    name: string;
    /** Field -> {before, after}. Empty when the proposal matches the target
     *  already — a request that would change nothing. */
    diffs: Record<string, CRFieldDiff>;
    /** True when the target has moved since the request was raised, so
     *  executing would overwrite edits the requester never saw. */
    stale: boolean;
  }>;
  /** True when any target is stale; execute is refused while this holds. */
  blocked: boolean;
}

export interface ChangeRequest {
  id: string;
  title: string;
  description: string;
  /** Why the change is needed, as opposed to `description` — what it is. */
  rationale: string;
  urgency: string;
  affected_requirements: string[];
  /** Target id -> {field: proposed value}. */
  changes: Record<string, Record<string, unknown>>;
  /** Target id -> fingerprint when raised; the staleness guard for execute. */
  base_fingerprints: Record<string, string>;
  status: string;
  /** The requester. There is deliberately no separate `requester` field. */
  submitted_by: string;
  reviewed_by: string;
  approved_by: string;
  created: string;
  modified: string;
}

export interface RiskBand {
  key: string;
  label: string;
  color: string;
}

export interface RiskMatrix {
  severities: string[];
  likelihoods: string[];
  /** Detection vocabulary. Travels with the matrix but does not address a
   *  cell — `cells` stays severity x likelihood. */
  detections: string[];
  bands: RiskBand[];
  /** cells[severityIndex][likelihoodIndex] -> band key */
  cells: string[][];
}

/** Offered in the UI; not enforced, so a project that renames a state keeps
 *  its stored risks valid. */
export const RISK_STATUSES = ['open', 'mitigating', 'monitoring', 'accepted', 'closed'] as const;

/** Counts per severity x likelihood cell — the "bingo card" summary. */
export interface RiskBingo {
  severities: string[];
  likelihoods: string[];
  /** `cells[severityIndex][likelihoodIndex]` -> how many risks land there. */
  counts: number[][];
  /** `bands[severityIndex][likelihoodIndex]` -> the band key that cell rates as,
   *  so the grid can be coloured the same way the register is. */
  bands: string[][];
  /** Risks whose severity or likelihood is not a level in the matrix, so they
   *  address no cell and would otherwise vanish from a summary that claims to
   *  cover the register. */
  unrated: number;
  total: number;
}

/** Derived server-side from the project matrix; never stored on the risk. */
export interface RiskRating {
  band: string | null;
  label: string | null;
  color: string | null;
  severity: string | null;
  likelihood: string | null;
  unrated_reason: string | null;
}

export interface Risk {
  id: string;
  title: string;
  description: string;
  severity: string;
  likelihood: string;
  /** Superseded by likelihood; still read for risks written before the matrix. */
  probability: string;
  rating?: RiskRating;
  impact: string;
  mitigation: string;
  /** How likely the risk is to be noticed before it bites. Stored and shown,
   *  but deliberately not part of the rating — the project matrix is 2D, and
   *  folding a third axis in would re-rate every existing risk. */
  detection: string;
  /** Requirements this risk endangers — "Threatens". */
  linked_requirements: string[];
  /** Requirements that control this risk — "Mitigated By". The opposite
   *  direction to `linked_requirements`; a requirement may appear in both. */
  mitigating_requirements: string[];
  status: string;
  created: string;
  modified: string;
}

export interface Comment {
  id: string;
  entity_kind: string;
  entity_id: string;
  author: string;
  text: string;
  resolved: boolean;
  created: string;
}

export interface DecisionRecord {
  id: string;
  title: string;
  context: string;
  decision: string;
  rationale: string;
  consequences: string;
  linked_requirements: string[];
  status: string;
  decided_by: string;
  created: string;
  modified: string;
}

export interface ImpactResult {
  requirement: string;
  dependents: { id: string; name: string; relation: string }[];
  cascade_children: string[];
  count: number;
}

export interface GapItem { id: string; name: string; issues: string[] }
export interface CoverageItem {
  id: string;
  name: string;
  needs: string[];
  covered_types: string[];
  uncovered_types: string[];
  unwanted_coverage: string[];
  shallow: boolean;
  deep: boolean;
  broken_chain: boolean;
}
export interface CoverageData {
  total: number;
  shallow_covered: number;
  deep_covered: number;
  coverage_pct: number;
  deep_pct: number;
  items: CoverageItem[];
}
export interface ConflictItem { ids?: string[]; a?: string; b?: string; type: string; name?: string }
export interface QualityFinding { rule: string; severity: string; message: string; start: number; end: number }
export interface QualityItem { id: string; name: string; score: number; findings: QualityFinding[] }
export interface QualityData { average: number; per_requirement: QualityItem[]; total: number; config: { min_words: number; max_words: number } }

export type ConstraintStatus = 'pass' | 'fail' | 'unknown' | 'error' | 'not_applicable';
export type EvalVerdict = 'pass' | 'fail' | 'unknown' | 'error' | 'none';
export interface EvaluatedParameter {
  name: string;
  unit: string;
  expr?: string | null;
  derived: boolean;
  value: number | null;
  detail?: string;
  error?: string;
  measured?: number;
  measured_by?: string;
  unit_warning?: string;
}
export interface EvaluatedConstraint {
  expr: string;
  assume?: string | null;
  status: ConstraintStatus;
  detail?: string;
  margin?: { value: number; pct?: number };
  unit_warning?: string;
}
export interface EvaluatedRequirement {
  id: string;
  name: string;
  parameters: EvaluatedParameter[];
  constraints: EvaluatedConstraint[];
  verdict: EvalVerdict;
  measured_constraints?: EvaluatedConstraint[];
  measured_verdict?: EvalVerdict;
}
/** A value on disk the evaluator could not use, reported instead of crashing.
 *  Requirement data is hand-editable YAML, so a measurement of `n/a` is a
 *  thing a user can legitimately write — it must degrade, not 500. */
export type DataIssueKind = 'non_numeric_measurement' | 'non_numeric_override';
export interface EvaluationDataIssue {
  kind: DataIssueKind;
  /** Parameter ref the bad value was written against, e.g. `R-001.mass`. */
  ref: string;
  /** Entity that supplied it — a verification case or analysis case id. */
  source: string;
  /** The offending value, stringified. */
  value: string;
  message: string;
}
export interface EvaluationData {
  requirements: EvaluatedRequirement[];
  summary: Record<string, number>;
  measured_summary: { pass: number; fail: number; unmeasured: number };
  parameter_count: number;
  measurement_count: number;
  data_issues: EvaluationDataIssue[];
}
export interface RiskBand {
  key: string;
  label: string;
  color: string;
}

export interface TopRisk {
  id: string;
  title: string;
  band: string;
  label: string;
  color: string;
  severity: string;
  likelihood: string;
  mitigated: boolean;
}

export interface RiskMetrics {
  total: number;
  open: number;
  unrated: number;
  severe_open: number;
  severe_bands: string[];
  /** Bands come from the project's own matrix — do not hardcode a palette. */
  bands: RiskBand[];
  by_band: Record<string, number>;
  open_by_band: Record<string, number>;
  by_status: Record<string, number>;
  with_mitigation: number;
  with_requirements: number;
  mitigation_pct: number;
  linked_pct: number;
  top_open: TopRisk[];
}

export interface MetricsData {
  total: number;
  verification_cases: number;
  baselines: number;
  status_distribution: Record<string, number>;
  quality: Record<string, number>;
  quality_pct: Record<string, number>;
  risks: RiskMetrics;
}

export interface ImportSummary {
  created: number;
  updated: number;
  skipped: number;
  traces_added: number;
  verification_cases: number;
  format: string;
}

export interface PresenceUser {
  username: string;
  role: string;
  since: string;
}

export interface ManagedUser {
  username: string;
  role: string;
  full_name: string;
  email: string;
  email_verified: boolean;
  last_active: string;
  joined: string;
  created: string;
  disabled: boolean;
  locked: boolean;
  locked_until: number;
  invited: boolean;
}

/** One admin-editable runtime setting, as returned by GET /system/settings. */
export interface AppSetting {
  key: string;
  value: string | number | boolean | string[];
  type: 'str' | 'int' | 'bool' | 'list' | 'color';
  category: string;
  label: string;
  help: string;
  secret: boolean;
  env_locked: boolean;
  has_value: boolean | null;
}

/** Non-sensitive instance info available without auth. */
export interface PublicConfig {
  instance_name: string;
  support_email: string;
  allow_self_registration: boolean;
  require_email_verification: boolean;
}

export interface BuildInfo {
  name: string;
  version: string;
  git_sha: string;
  built_at: string;
  channel: string;
}

export interface SystemInfo {
  version: string;
  docker: boolean;
  offline: boolean;
  self_update_enabled: boolean;
  control_dir_writable: boolean;
  self_update_supported: boolean;
  file_update_supported: boolean;
  bundle_update_supported: boolean;
  can_restart: boolean;
  latex_engine: string | null;
  github_repo: string;
  hostname: string;
  fqdn: string;
  internal_ips: string[];
  os: { system: string; release: string; version: string; machine: string; python: string };
  process_uptime_seconds: number;
  working_directory: string;
  running_user: string;
}

export interface UpdateCheck {
  current: string;
  latest: string | null;
  update_available: boolean;
  offline: boolean;
  checked_at: string;
  error: string | null;
  notes: string;
  html_url: string;
  published_at: string;
}

export interface UpdateStatus {
  state: 'idle' | 'preparing' | 'requested' | 'in_progress' | 'staged' | 'completed' | 'failed' | 'unsupported';
  current?: string;
  target_version: string | null;
  message: string;
  updated_at: string;
  backup?: { tag: string; projects: string[]; created_at?: string };
}

export interface ImpactStepParam {
  kind: 'param';
  ref: string;
  owner: string;
  name: string;
  expr: string;
  unit: string;
  inputs: string[];
  before: number | null;
  after: number | null;
}

export interface ImpactStepConstraint {
  kind: 'constraint';
  owner: string;
  expr: string;
  before: { status: ConstraintStatus; margin?: { value: number; pct?: number } };
  after: { status: ConstraintStatus; margin?: { value: number; pct?: number } };
}

export type ImpactStep = ImpactStepParam | ImpactStepConstraint;

export interface ImpactResultData {
  evaluation: EvaluationData;
  steps: ImpactStep[];
  affected: string[];
  roots: string[];
}

export interface HistoryEntry {
  timestamp: string;
  action: string;
  user: string;
  changes: Record<string, { before: unknown; after: unknown }>;
}

export const api = {
  // Build metadata (version, git sha, build time)
  getVersion: () => request<BuildInfo>('/version'),

  // System / self-update (admin only)
  systemInfo: () => request<SystemInfo>('/system/info'),
  checkUpdate: (force = false) =>
    request<UpdateCheck>(`/system/update/check${force ? '?force=true' : ''}`),
  updateStatus: () => request<UpdateStatus>('/system/update/status'),
  startUpdate: (targetVersion?: string) =>
    request<{ state: string; target_version: string; backup: { tag: string; projects: string[] } }>(
      '/system/update', { method: 'POST', body: { target_version: targetVersion ?? null } }),
  uploadUpdate: (file: File, targetVersion?: string) => {
    const fd = new FormData();
    fd.append('file', file);
    if (targetVersion) fd.append('target_version', targetVersion);
    return request<{ state: string; target_version: string; backup: { tag: string; projects: string[] }; archive_bytes: number }>(
      '/system/update/upload', { method: 'POST', body: fd });
  },
  uploadBundle: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return request<{ state: string; target_version: string; backup: { tag: string; projects: string[] }; archive_bytes: number }>(
      '/system/update/bundle', { method: 'POST', body: fd });
  },
  restartApp: () => request<{ ok: boolean; restarting: boolean }>('/system/restart', { method: 'POST' }),
  dismissUpdate: () => request<{ ok: boolean }>('/system/update/dismiss', { method: 'POST' }),

  // Auth
  login: (username: string, password: string) =>
    request<{ username: string; role: string; csrf_token: string; password_change_required?: boolean }>('/auth/login', { method: 'POST', body: { username, password } }),
  register: (username: string, password: string, role: string = 'contributor') =>
    request<{ username: string; role: string; csrf_token: string; password_change_required?: boolean }>('/auth/register', { method: 'POST', body: { username, password, role } }),
  loginAsGuest: () =>
    request<{ username: string; role: string; csrf_token: string }>('/auth/guest', { method: 'POST' }),
  whoami: () =>
    request<{ username: string; role: string; token?: string; csrf_token?: string; password_change_required?: boolean }>('/auth/whoami'),
  logout: () =>
    request<{ ok: boolean }>('/auth/logout', { method: 'POST' }),

  // User management (admin only)
  listUsers: () => request<ManagedUser[]>('/auth/users'),
  createUser: (data: { username: string; password: string; role: string; email?: string; full_name?: string }) =>
    request<ManagedUser>('/auth/users', { method: 'POST', body: data }),
  updateUser: (username: string, data: { role?: string; password?: string; email?: string; full_name?: string }) =>
    request<ManagedUser>(`/auth/users/${encodeURIComponent(username)}`, { method: 'PATCH', body: data }),
  deleteUser: (username: string) =>
    request<void>(`/auth/users/${encodeURIComponent(username)}`, { method: 'DELETE' }),
  updateProfile: (data: { full_name?: string; email?: string; password?: string }) =>
    request<{ ok: boolean }>('/auth/profile', { method: 'PATCH', body: data }),
  // Account status & lifecycle
  setUserDisabled: (username: string, disabled: boolean) =>
    request<{ ok: boolean; disabled: boolean }>(`/auth/users/${encodeURIComponent(username)}/disable`, { method: 'POST', body: { disabled } }),
  unlockUser: (username: string) =>
    request<{ ok: boolean }>(`/auth/users/${encodeURIComponent(username)}/unlock`, { method: 'POST' }),
  forceLogout: (username: string) =>
    request<{ ok: boolean }>(`/auth/users/${encodeURIComponent(username)}/logout`, { method: 'POST' }),
  inviteUser: (data: { username: string; email?: string; role?: string; full_name?: string }) =>
    request<{ username: string; role: string; emailed: boolean; invite_link: string | null }>('/auth/users/invite', { method: 'POST', body: data }),
  bulkUsers: (usernames: string[], action: 'disable' | 'enable' | 'delete' | 'set_role', role?: string) =>
    request<{ applied: string[]; skipped: string[] }>('/auth/users/bulk', { method: 'POST', body: { usernames, action, role } }),
  importUsersCsv: (csv: string) =>
    request<{ created: string[]; skipped: string[]; invites: { username: string; invite_link: string }[] }>('/auth/users/import', { method: 'POST', body: { csv } }),
  exportUsersCsvUrl: '/api/auth/users/export',
  logoutEverywhere: () => request<{ ok: boolean }>('/auth/logout-everywhere', { method: 'POST' }),

  // Application settings (admin) + public instance config
  getSettings: () => request<{ settings: AppSetting[] }>('/system/settings'),
  patchSettings: (patch: Record<string, string | number | boolean | string[]>) =>
    request<{ settings: AppSetting[] }>('/system/settings', { method: 'PATCH', body: patch }),
  testEmail: (to: string) =>
    request<{ ok: boolean; error?: string }>('/system/settings/test-email', { method: 'POST', body: { to } }),
  getPublicConfig: () => request<PublicConfig>('/system/public-config'),
  getLatexStatus: () => request<{ available: boolean; engine: string | null }>('/system/latex-status'),
  listDependencies: () => request<Array<{ id: string; label: string; category: string; status: string; detail: string; has_e2e: boolean; install_guide: string }>>('/system/dependencies'),
  testDependency: (depId: string) => request<{ ok: boolean; error?: string; detail?: string }>(`/system/dependencies/${depId}/test`, { method: 'POST' }),

  // Projects
  listProjects: () => request<Project[]>('/projects'),
  createProject: (data: { id: string; name: string }) => request<Project>('/projects', { method: 'POST', body: data }),
  getProject: (id: string) => request<Project>(`/projects/${id}`),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: 'DELETE' }),
  updateProject: (id: string, data: { name?: string; naming?: Record<string, unknown>; quality?: Record<string, unknown>; workflow?: Record<string, unknown>; git?: Record<string, unknown>; baselines?: (string | BaselineDef)[]; stakeholders?: StakeholderDef[]; risk_matrix?: RiskMatrix }) =>
    request<Project>(`/projects/${id}`, { method: 'PATCH', body: data }),
  getWorkflow: (projectId: string) =>
    request<{ states: string[]; transitions: Record<string, string[]>; default: string }>(`/projects/${projectId}/workflow`),

  // Requirements
  //
  // The list endpoint is paginated ({items, total, offset, limit}).
  // listRequirements unwraps it at the server's maximum page size so every
  // existing "give me the project" caller keeps working; use the Paged
  // variant to actually page.
  listRequirements: async (projectId: string, params?: Record<string, string>) => {
    const qs = '?' + new URLSearchParams({ limit: '2000', ...params }).toString();
    const page = await request<Paged<Requirement>>(`/projects/${projectId}/requirements${qs}`);
    return page.items;
  },
  listRequirementsPaged: (projectId: string, params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return request<Paged<Requirement>>(`/projects/${projectId}/requirements${qs}`);
  },
  getRequirementTree: (projectId: string) =>
    request<RequirementTreeNode[]>(`/projects/${projectId}/requirements/tree`),

  // Components (the synthesised design)
  // Paginated like requirements — see listRequirements.
  listComponents: async (projectId: string, params?: Record<string, string>) => {
    const qs = '?' + new URLSearchParams({ limit: '2000', ...params }).toString();
    const page = await request<Paged<Component>>(`/projects/${projectId}/components${qs}`);
    return page.items;
  },
  listComponentsPaged: (projectId: string, params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return request<Paged<Component>>(`/projects/${projectId}/components${qs}`);
  },
  getComponentTree: (projectId: string) =>
    request<ComponentTreeNode[]>(`/projects/${projectId}/components/tree`),
  getComponent: (projectId: string, componentId: string) =>
    request<Component>(`/projects/${projectId}/components/${componentId}`),
  createComponent: (projectId: string, data: Partial<Component>) =>
    request<Component>(`/projects/${projectId}/components`, { method: 'POST', body: data }),
  updateComponent: (projectId: string, componentId: string, data: Partial<Component>) =>
    request<Component>(`/projects/${projectId}/components/${componentId}`, { method: 'PUT', body: data }),
  deleteComponent: (projectId: string, componentId: string, force = false) =>
    request<{ok?: true} | undefined>(`/projects/${projectId}/components/${componentId}${force ? '?force=true' : ''}`, { method: 'DELETE' }),
  getComponentsForRequirement: (projectId: string, reqId: string) =>
    request<Component[]>(`/projects/${projectId}/requirements/${reqId}/components`),
  getComponentsForVerificationCase: (projectId: string, vcId: string) =>
    request<Component[]>(`/projects/${projectId}/verification/${vcId}/components`),
  getRequirement: (projectId: string, reqId: string) =>
    request<Requirement>(`/projects/${projectId}/requirements/${reqId}`),
  createRequirement: (projectId: string, data: Partial<Requirement>) =>
    request<Requirement>(`/projects/${projectId}/requirements`, { method: 'POST', body: data }),
  updateRequirement: (projectId: string, reqId: string, data: Partial<Requirement>) =>
    request<Requirement>(`/projects/${projectId}/requirements/${reqId}`, { method: 'PUT', body: data }),
  deleteRequirement: (projectId: string, reqId: string, force = false) =>
    request<{ok?: true} | undefined>(`/projects/${projectId}/requirements/${reqId}${force ? '?force=true' : ''}`, { method: 'DELETE' }),
  cascadeRequirement: (projectId: string, reqId: string) =>
    request<{ cascaded: boolean; created: string[]; source: string }>(`/projects/${projectId}/requirements/${reqId}/cascade`, { method: 'POST' }),
  breakCascade: (projectId: string, reqId: string, breakChildren?: boolean) =>
    request<{ broken: boolean; id: string }>(`/projects/${projectId}/requirements/${reqId}/break-cascade`, { method: 'POST', body: { break_children: breakChildren || false } }),

  // Baselines
  listBaselines: (projectId: string) =>
    request<BaselineInfo[]>(`/projects/${projectId}/baselines`),
  createBaseline: (projectId: string, name: string, symbol?: string, description?: string, requirements?: string[], dueDate?: string) =>
    request<{ name: string; symbol: string; description: string; due_date: string; requirements_assigned: number }>(
      `/projects/${projectId}/baselines`,
      { method: 'POST', body: { name, symbol: symbol ?? '', description: description ?? '', requirements: requirements ?? [], due_date: dueDate ?? '' } }),
  /** `dueDate` follows `symbol`/`description`: omit to leave alone, `''` to clear. */
  renameBaseline: (projectId: string, oldName: string, newName: string, symbol?: string, description?: string, dueDate?: string) =>
    request<{ old_name: string; new_name: string; requirements_updated: number }>(
      `/projects/${projectId}/baselines/${encodeURIComponent(oldName)}`,
      { method: 'PATCH', body: { name: newName, symbol, description, due_date: dueDate } }),
  /** Rewrite the whole sequence. `names` must be a permutation of every defined
   *  baseline — a partial list is rejected rather than appended to, so a stale
   *  client cannot silently reorder around baselines it does not know about. */
  reorderBaselines: (projectId: string, names: string[]) =>
    request<{ baselines: BaselineDef[] }>(
      `/projects/${projectId}/baselines/order`,
      { method: 'PUT', body: { names } }),
  deleteBaseline: (projectId: string, name: string) =>
    request<{ name: string; requirements_cleared: number }>(`/projects/${projectId}/baselines/${encodeURIComponent(name)}`, { method: 'DELETE' }),

  // System States
  listSystemStates: (projectId: string) =>
    request<SystemStatesResponse>(`/projects/${projectId}/system-states`),
  createSystemState: (projectId: string, data: { name: string; description: string }) =>
    request<SystemStateDef>(`/projects/${projectId}/system-states`, { method: 'POST', body: data }),
  updateSystemState: (projectId: string, name: string, data: { name?: string; description?: string }) =>
    request<SystemStateDef>(`/projects/${projectId}/system-states/${encodeURIComponent(name)}`, { method: 'PATCH', body: data }),
  deleteSystemState: (projectId: string, name: string) =>
    request<{ name: string; requirements_affected: number }>(`/projects/${projectId}/system-states/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  freezeBaseline: (projectId: string, name: string) =>
    request<{ name: string; symbol: string; description: string; requirements: number }>(
      `/projects/${projectId}/baselines/${encodeURIComponent(name)}/freeze`,
      { method: 'POST' }),
  diffBaseline: (projectId: string, name: string) =>
    request<BaselineDiff>(`/projects/${projectId}/baselines/${encodeURIComponent(name)}/diff`),

  // Specifications
  listSpecifications: (projectId: string) => request<Specification[]>(`/projects/${projectId}/specifications`),
  createSpecification: (projectId: string, data: Partial<Specification>) =>
    request<Specification>(`/projects/${projectId}/specifications`, { method: 'POST', body: data }),
  updateSpecification: (projectId: string, specId: string, data: Partial<Specification>) =>
    request<Specification>(`/projects/${projectId}/specifications/${specId}`, { method: 'PUT', body: data }),
  deleteSpecification: (projectId: string, specId: string, force = false) =>
    request<{ok?: true} | undefined>(`/projects/${projectId}/specifications/${specId}${force ? '?force=true' : ''}`, { method: 'DELETE' }),

  // Verification Cases
  listVerificationCases: (projectId: string) => request<VerificationCase[]>(`/projects/${projectId}/verification`),
  createVerificationCase: (projectId: string, data: Partial<VerificationCase>) =>
    request<VerificationCase>(`/projects/${projectId}/verification`, { method: 'POST', body: data }),
  updateVerificationCase: (projectId: string, vcId: string, data: Partial<VerificationCase>) =>
    request<VerificationCase>(`/projects/${projectId}/verification/${vcId}`, { method: 'PUT', body: data }),
  deleteVerificationCase: (projectId: string, vcId: string, force = false) =>
    request<{ok?: true} | undefined>(`/projects/${projectId}/verification/${vcId}${force ? '?force=true' : ''}`, { method: 'DELETE' }),
  runVerification: (projectId: string, vcId: string, data: { status: string; notes?: string; step_results?: Record<string, string> }) =>
    request<VerificationCase>(`/projects/${projectId}/verification/${vcId}/run`, { method: 'POST', body: data }),

  // Traces
  getTraces: (projectId: string) => request<{ links: TraceLink[] }>(`/projects/${projectId}/traces`),
  updateTraces: (projectId: string, data: { links: TraceLink[] }) =>
    request<{ links: TraceLink[] }>(`/projects/${projectId}/traces`, { method: 'PUT', body: data }),
  /** Every relationship: registry-derived edges + hand-authored traces. */
  getTraceModel: (projectId: string) =>
    request<{ links: TraceModelLink[]; total: number }>(`/projects/${projectId}/trace-model`),

  // Change Requests
  listChangeRequests: (projectId: string) => request<ChangeRequest[]>(`/projects/${projectId}/change-requests`),
  createChangeRequest: (projectId: string, data: Partial<ChangeRequest>) =>
    request<ChangeRequest>(`/projects/${projectId}/change-requests`, { method: 'POST', body: data }),
  updateChangeRequest: (projectId: string, crId: string, data: Partial<ChangeRequest>) =>
    request<ChangeRequest>(`/projects/${projectId}/change-requests/${crId}`, { method: 'PUT', body: data }),
  deleteChangeRequest: (projectId: string, crId: string, force = false) =>
    request<{ok?: true} | undefined>(`/projects/${projectId}/change-requests/${crId}${force ? '?force=true' : ''}`, { method: 'DELETE' }),
  getCRRedline: (projectId: string, crId: string) =>
    request<CRRedline>(`/projects/${projectId}/change-requests/${crId}/redline`),
  executeChangeRequest: (projectId: string, crId: string) =>
    request<{ id: string; status: string; updated: number }>(`/projects/${projectId}/change-requests/${crId}/execute`, { method: 'POST' }),
  rejectChangeRequest: (projectId: string, crId: string) =>
    request<{ id: string; status: string }>(`/projects/${projectId}/change-requests/${crId}/reject`, { method: 'POST' }),
  getRequirementFingerprint: (projectId: string, reqId: string) =>
    request<{ id: string; fingerprint: string }>(`/projects/${projectId}/requirements/${reqId}/fingerprint`),

  // Risks
  getBacklinks: (projectId: string, entityId: string) =>
    request<Backlinks>(`/projects/${projectId}/entities/${entityId}/backlinks`),
  listRisks: (projectId: string) => request<Risk[]>(`/projects/${projectId}/risks`),
  getRiskMatrix: (projectId: string) => request<RiskMatrix>(`/projects/${projectId}/risk-matrix`),
  getRiskBingo: (projectId: string) => request<RiskBingo>(`/projects/${projectId}/risk-bingo`),
  createRisk: (projectId: string, data: Partial<Risk>) =>
    request<Risk>(`/projects/${projectId}/risks`, { method: 'POST', body: data }),
  updateRisk: (projectId: string, riskId: string, data: Partial<Risk>) =>
    request<Risk>(`/projects/${projectId}/risks/${riskId}`, { method: 'PUT', body: data }),
  deleteRisk: (projectId: string, riskId: string, force = false) =>
    request<{ok?: true} | undefined>(`/projects/${projectId}/risks/${riskId}${force ? '?force=true' : ''}`, { method: 'DELETE' }),

  // Comments
  listComments: (projectId: string, entityKind: string, entityId: string) => {
    const qs = `?entity_kind=${encodeURIComponent(entityKind)}&entity_id=${encodeURIComponent(entityId)}`;
    return request<Comment[]>(`/projects/${projectId}/comments${qs}`);
  },
  createComment: (projectId: string, data: { entity_kind: string; entity_id: string; text: string }) =>
    request<Comment>(`/projects/${projectId}/comments`, { method: 'POST', body: data }),
  deleteComment: (projectId: string, commentId: string) =>
    request<void>(`/projects/${projectId}/comments/${commentId}`, { method: 'DELETE' }),
  updateComment: (projectId: string, commentId: string, data: { resolved?: boolean; text?: string }) =>
    request<Comment>(`/projects/${projectId}/comments/${commentId}`, { method: 'PATCH', body: data }),

  // Decisions
  listDecisions: (projectId: string) => request<DecisionRecord[]>(`/projects/${projectId}/decisions`),
  createDecision: (projectId: string, data: Partial<DecisionRecord>) =>
    request<DecisionRecord>(`/projects/${projectId}/decisions`, { method: 'POST', body: data }),
  updateDecision: (projectId: string, decId: string, data: Partial<DecisionRecord>) =>
    request<DecisionRecord>(`/projects/${projectId}/decisions/${decId}`, { method: 'PUT', body: data }),
  deleteDecision: (projectId: string, decId: string, force = false) =>
    request<{ok?: true} | undefined>(`/projects/${projectId}/decisions/${decId}${force ? '?force=true' : ''}`, { method: 'DELETE' }),

  // Analysis
  getImpact: (projectId: string, reqId: string) =>
    request<ImpactResult>(`/projects/${projectId}/requirements/${reqId}/impact`),
  getGapAnalysis: (projectId: string) =>
    request<{ total: number; gaps: number; items: GapItem[] }>(`/projects/${projectId}/gap-analysis`),
  getCoverageAnalysis: (projectId: string) =>
    request<CoverageData>(`/projects/${projectId}/coverage`),
  /** The obligation kinds a requirement may declare in `needs`. Served rather
   *  than hardcoded so the picker cannot drift from what tracing.py satisfies. */
  getCoverageNeeds: () =>
    request<{ items: { value: string; label: string }[] }>(`/coverage-needs`),
  /** Weighted stakeholder value of one requirement, plus its rank in the project. */
  getRequirementValue: (projectId: string, reqId: string) =>
    request<RequirementValue>(`/projects/${projectId}/requirements/${reqId}/value`),
  getConflicts: (projectId: string) =>
    request<{ count: number; conflicts: ConflictItem[] }>(`/projects/${projectId}/conflicts`),
  getQuality: (projectId: string) =>
    request<QualityData>(`/projects/${projectId}/quality`),
  getEvaluation: (projectId: string) =>
    request<EvaluationData>(`/projects/${projectId}/evaluation`),

  // Reusable parametric definitions (constraint def / calc def)
  listDefinitions: (projectId: string) =>
    request<Definition[]>(`/projects/${projectId}/definitions`),
  createDefinition: (projectId: string, data: Definition) =>
    request<Definition>(`/projects/${projectId}/definitions`, { method: 'POST', body: data }),
  updateDefinition: (projectId: string, defId: string, data: Partial<Definition>) =>
    request<Definition>(`/projects/${projectId}/definitions/${encodeURIComponent(defId)}`, { method: 'PUT', body: data }),
  deleteDefinition: (projectId: string, defId: string) =>
    request<{ ok: boolean }>(`/projects/${projectId}/definitions/${encodeURIComponent(defId)}`, { method: 'DELETE' }),

  // Analysis cases (scoped, parameterised what-if evaluation)
  listAnalysisCases: (projectId: string) =>
    request<AnalysisCase[]>(`/projects/${projectId}/analysis`),
  createAnalysisCase: (projectId: string, data: AnalysisCase) =>
    request<AnalysisCase>(`/projects/${projectId}/analysis`, { method: 'POST', body: data }),
  updateAnalysisCase: (projectId: string, caseId: string, data: Partial<AnalysisCase>) =>
    request<AnalysisCase>(`/projects/${projectId}/analysis/${encodeURIComponent(caseId)}`, { method: 'PUT', body: data }),
  deleteAnalysisCase: (projectId: string, caseId: string) =>
    request<{ ok: boolean }>(`/projects/${projectId}/analysis/${encodeURIComponent(caseId)}`, { method: 'DELETE' }),
  runAnalysisCase: (projectId: string, caseId: string) =>
    request<EvaluationData & { case: AnalysisCase }>(`/projects/${projectId}/analysis/${encodeURIComponent(caseId)}/run`),

  // Pugh matrix
  getPugh: (projectId: string, datum?: string, limit: number = 8) => {
    const qs = new URLSearchParams();
    if (datum) qs.set('datum', datum);
    qs.set('limit', String(limit));
    return request<PughMatrix>(`/projects/${projectId}/pugh?${qs.toString()}`);
  },

  // Bundled example project (admin)
  getDemoProject: () =>
    request<{ exists: boolean; id: string; name: string; requirements: number }>('/system/demo-project'),
  /** Re-seeds the bundled example. `force` is required once it exists — the
   *  server 409s without it rather than silently discarding work in it. */
  reseedDemoProject: (force: boolean) =>
    request<{ id: string; replaced: boolean; seeded: boolean }>(
      '/system/demo-project/reseed', { method: 'POST', body: { force } }),

  // Metrics & Compliance
  getMetrics: (projectId: string) => request<MetricsData>(`/projects/${projectId}/metrics`),
  getCompliance: (projectId: string) =>
    request<{ standards: { name: string; count: number }[]; tracked_count: number; total_requirements: number }>(`/projects/${projectId}/compliance`),

  // Bulk — Requirements
  bulkUpdateRequirements: (projectId: string, ids: string[], updates: Record<string, unknown>) =>
    request<{ updated: number; ids: string[] }>(`/projects/${projectId}/requirements/bulk`, { method: 'POST', body: { ids, updates } }),
  bulkDeleteRequirements: (projectId: string, ids: string[]) =>
    request<{ deleted: number }>(`/projects/${projectId}/requirements/bulk-delete`, { method: 'POST', body: { ids } }),
  bulkReparentRequirements: (projectId: string, ids: string[], parent: string | null, rePrefix: boolean = false) =>
    request<{ updated: number; ids: string[] }>(`/projects/${projectId}/requirements/bulk-reparent`, { method: 'POST', body: { ids, parent, re_prefix: rePrefix } }),

  // Bulk — Components
  bulkUpdateComponents: (projectId: string, ids: string[], updates: Record<string, unknown>) =>
    request<{ updated: number }>(`/projects/${projectId}/components/bulk`, { method: 'POST', body: { ids, updates } }),
  bulkDeleteComponents: (projectId: string, ids: string[]) =>
    request<{ deleted: number }>(`/projects/${projectId}/components/bulk-delete`, { method: 'POST', body: { ids } }),
  bulkReparentComponents: (projectId: string, ids: string[], parent: string | null) =>
    request<{ updated: number }>(`/projects/${projectId}/components/bulk-reparent`, { method: 'POST', body: { ids, parent } }),

  // Bulk — Verification Cases
  bulkUpdateVerificationCases: (projectId: string, ids: string[], updates: Record<string, unknown>) =>
    request<{ updated: number }>(`/projects/${projectId}/verification/bulk`, { method: 'POST', body: { ids, updates } }),
  bulkDeleteVerificationCases: (projectId: string, ids: string[]) =>
    request<{ deleted: number }>(`/projects/${projectId}/verification/bulk-delete`, { method: 'POST', body: { ids } }),

  // Bulk — Specifications
  bulkUpdateSpecifications: (projectId: string, ids: string[], updates: Record<string, unknown>) =>
    request<{ updated: number }>(`/projects/${projectId}/specifications/bulk`, { method: 'POST', body: { ids, updates } }),
  bulkDeleteSpecifications: (projectId: string, ids: string[]) =>
    request<{ deleted: number }>(`/projects/${projectId}/specifications/bulk-delete`, { method: 'POST', body: { ids } }),

  // Bulk — Risks
  bulkUpdateRisks: (projectId: string, ids: string[], updates: Record<string, unknown>) =>
    request<{ updated: number }>(`/projects/${projectId}/risks/bulk`, { method: 'POST', body: { ids, updates } }),
  bulkDeleteRisks: (projectId: string, ids: string[]) =>
    request<{ deleted: number }>(`/projects/${projectId}/risks/bulk-delete`, { method: 'POST', body: { ids } }),

  // Bulk — Change Requests
  bulkUpdateChangeRequests: (projectId: string, ids: string[], updates: Record<string, unknown>) =>
    request<{ updated: number }>(`/projects/${projectId}/change-requests/bulk`, { method: 'POST', body: { ids, updates } }),
  bulkDeleteChangeRequests: (projectId: string, ids: string[]) =>
    request<{ deleted: number }>(`/projects/${projectId}/change-requests/bulk-delete`, { method: 'POST', body: { ids } }),

  // History
  getRequirementHistory: (projectId: string, reqId: string) =>
    request<unknown[]>(`/projects/${projectId}/requirements/${reqId}/history`),

  getItemHistory: (projectId: string, itemId: string) =>
    request<HistoryEntry[]>(`/projects/${projectId}/history/${itemId}`),

  // Git
  gitLog: (projectId: string, limit: number = 50) =>
    request<{ is_repo: boolean; commits: Array<{ hash: string; author: string; date: string; message: string }> }>(`/projects/${projectId}/git/log?limit=${limit}`),

  gitRestore: (projectId: string, hash: string) =>
    request<{ status: string; message: string }>(`/projects/${projectId}/git/restore`, { method: 'POST', body: { hash } }),

  gitTestRemote: (projectId: string, remoteUrl: string) =>
    request<{ ok: boolean; error?: string; branches?: string[]; branch_count?: number }>(`/projects/${projectId}/git/test-remote`, { method: 'POST', body: { remote_url: remoteUrl } }),

  // Import (ReqIF / SysML)
  importProject: (projectId: string, file: File, format: string, mode: string) => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('format', format);
    fd.append('mode', mode);
    return request<ImportSummary>(`/projects/${projectId}/import`, { method: 'POST', body: fd });
  },

  // Presence (real-time collaboration)
  getPresence: (projectId: string) =>
    request<{ users: PresenceUser[]; count: number }>(`/projects/${projectId}/presence`),

  // UID
  getNextUid: (projectId: string, parent?: string) => {
    const qs = parent ? `?parent=${encodeURIComponent(parent)}` : '';
    return request<{ prefix: string; next_id: string }>(`/projects/${projectId}/requirements/next-uid${qs}`);
  },

  // Review
  reviewRequirement: (projectId: string, reqId: string, comment?: string) =>
    request<Requirement>(`/projects/${projectId}/requirements/${reqId}/review`, { method: 'POST', body: { comment } }),
  reviewAll: (projectId: string) =>
    request<{ reviewed: number; total: number }>(`/projects/${projectId}/review-all`, { method: 'POST' }),
  getUnreviewed: (projectId: string) =>
    request<{ items: { id: string; name: string; reviewed: string | null; current_fingerprint: string }[] }>(`/projects/${projectId}/unreviewed`),

  // Code scan
  scanProject: (projectId: string, codeRoot: string) => {
    const fd = new FormData();
    fd.append('code_root', codeRoot);
    return request<{ created: number; updated: number; files_scanned: number; requirements_touched: number }>(
      `/projects/${projectId}/scan`, { method: 'POST', body: fd }
    );
  },
  getReferenceFreshness: (projectId: string) =>
    request<{ req_id: string; path: string; status: string }[]>(`/projects/${projectId}/references/freshness`),

  // Backlog
  getBacklog: (projectId: string, sort?: string) => {
    const qs = sort ? `?sort=${sort}` : '';
    return request<{ items: { id: string; name: string; status: string; priorities: Record<string, number>; combined_priority: number }[] }>(`/projects/${projectId}/backlog${qs}`);
  },

  // What-if impact preview
  getEvaluationImpact: (projectId: string, overrides: Record<string, number>) =>
    request<ImpactResultData>(`/projects/${projectId}/evaluation/impact`, { method: 'POST', body: { overrides } }),

  // Project-wide full-text search
  searchProject: (projectId: string, query: string, kind?: string) =>
    request<{ query: string; results: SearchResult[]; total: number }>(
      `/projects/${projectId}/search?q=${encodeURIComponent(query)}${kind ? '&kind=' + encodeURIComponent(kind) : ''}`
    ),

  // Allocation matrix
  getAllocationMatrix: (projectId: string, axis: MatrixAxis = 'components',
                        search?: string, filterType?: string) => {
    const qs = new URLSearchParams();
    if (axis) qs.set('axis', axis);
    if (search) qs.set('search', search);
    if (filterType) qs.set('filter_type', filterType);
    const qsStr = qs.toString();
    return request<AllocationMatrixData>(`/projects/${projectId}/allocation-matrix${qsStr ? '?' + qsStr : ''}`);
  },
  setAllocation: (projectId: string, reqId: string, targetId: string, allocated: boolean,
                  axis: MatrixAxis = 'components') =>
    request<{ req_id: string; axis: MatrixAxis; target_id: string; allocated: boolean; allocated_to: string }>(
      `/projects/${projectId}/allocation`,
      { method: 'POST', body: { req_id: reqId, target_id: targetId, axis, allocated } }),

  // CI test-result import
  importTestResults: (projectId: string, file: File, format: string, dryRun: boolean) => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('format', format);
    fd.append('dry_run', String(dryRun));
    return request<TestResultImportSummary>(`/projects/${projectId}/test-results/import`, { method: 'POST', body: fd });
  },
  getTestResultSample: (projectId: string) =>
    request<string>(`/projects/${projectId}/test-results/sample`, { raw: true }),
};
