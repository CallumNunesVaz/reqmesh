const BASE = '/api';

interface RequestOptions {
  method?: string;
  body?: unknown;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body } = options;
  const headers: Record<string, string> = {};

  const token = (() => {
    try { return localStorage.getItem('rt-token'); } catch { return null; }
  })();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  if (body && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export interface Project {
  id: string;
  name: string;
  path: string;
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
  verification_method: string;
  attributes: { key: string; value: string }[];
  parameters: Parameter[];
  constraints: Constraint[];
  relations: { type: string; target: string; reviewed_fingerprint?: string | null }[];
  verification_cases: string[];
  verification_status: string;
  parent: string | null;
  cascade_from: string | null;
  rationale: string;
  source: string;
  allocated_to: string;
  baselines: string[];
  references: Reference[];
  reviewed: string | null;
  derived: boolean;
  normative: boolean;
  effort: number | null;
  priorities: Record<string, number>;
  needs: string[];
  requirement_kind: 'stakeholder_need' | 'system_requirement';
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

export interface ChangeRequest {
  id: string;
  title: string;
  description: string;
  affected_requirements: string[];
  status: string;
  submitted_by: string;
  reviewed_by: string;
  approved_by: string;
  created: string;
  modified: string;
}

export interface Risk {
  id: string;
  title: string;
  description: string;
  severity: string;
  probability: string;
  impact: string;
  mitigation: string;
  linked_requirements: string[];
  status: string;
  created: string;
  modified: string;
}

export interface Comment {
  id: string;
  requirement_id: string;
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
export interface EvaluationData {
  requirements: EvaluatedRequirement[];
  summary: Record<string, number>;
  measured_summary: { pass: number; fail: number; unmeasured: number };
  parameter_count: number;
  measurement_count: number;
}
export interface MetricsData {
  total: number;
  verification_cases: number;
  baselines: number;
  status_distribution: Record<string, number>;
  quality: Record<string, number>;
  quality_pct: Record<string, number>;
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
  type: 'str' | 'int' | 'bool' | 'list';
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
    request<{ username: string; role: string; token: string }>('/auth/login', { method: 'POST', body: { username, password } }),
  register: (username: string, password: string, role: string = 'editor') =>
    request<{ username: string; role: string; token: string }>('/auth/register', { method: 'POST', body: { username, password, role } }),
  loginAsGuest: () =>
    request<{ username: string; role: string }>('/auth/guest', { method: 'POST' }),
  whoami: () =>
    request<{ username: string; role: string }>('/auth/whoami'),

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

  // Projects
  listProjects: () => request<Project[]>('/projects'),
  createProject: (data: { id: string; name: string }) => request<Project>('/projects', { method: 'POST', body: data }),
  getProject: (id: string) => request<Project>(`/projects/${id}`),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: 'DELETE' }),
  updateProject: (id: string, data: { name?: string; naming?: Record<string, any>; quality?: Record<string, any>; workflow?: Record<string, any>; git?: Record<string, any>; baselines?: string[] }) =>
    request<any>(`/projects/${id}`, { method: 'PATCH', body: data }),
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
  deleteComponent: (projectId: string, componentId: string) =>
    request<{ ok: boolean; promoted_children: string[] }>(`/projects/${projectId}/components/${componentId}`, { method: 'DELETE' }),
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
  deleteRequirement: (projectId: string, reqId: string) =>
    request<void>(`/projects/${projectId}/requirements/${reqId}`, { method: 'DELETE' }),
  cascadeRequirement: (projectId: string, reqId: string) =>
    request<{ cascaded: boolean; created: string[]; source: string }>(`/projects/${projectId}/requirements/${reqId}/cascade`, { method: 'POST' }),
  breakCascade: (projectId: string, reqId: string, breakChildren?: boolean) =>
    request<{ broken: boolean; id: string }>(`/projects/${projectId}/requirements/${reqId}/break-cascade`, { method: 'POST', body: { break_children: breakChildren || false } }),

  // Baselines
  listBaselines: (projectId: string) =>
    request<{ name: string; requirements: string[]; count: number }[]>(`/projects/${projectId}/baselines`),
  createBaseline: (projectId: string, name: string, requirements: string[]) =>
    request<{ name: string; requirements_assigned: number }>(`/projects/${projectId}/baselines`, { method: 'POST', body: { name, requirements } }),
  renameBaseline: (projectId: string, oldName: string, newName: string) =>
    request<{ old_name: string; new_name: string; requirements_updated: number }>(`/projects/${projectId}/baselines/${encodeURIComponent(oldName)}`, { method: 'PATCH', body: { name: newName } }),
  deleteBaseline: (projectId: string, name: string) =>
    request<{ name: string; requirements_cleared: number }>(`/projects/${projectId}/baselines/${encodeURIComponent(name)}`, { method: 'DELETE' }),

  // Specifications
  listSpecifications: (projectId: string) => request<Specification[]>(`/projects/${projectId}/specifications`),
  createSpecification: (projectId: string, data: Partial<Specification>) =>
    request<Specification>(`/projects/${projectId}/specifications`, { method: 'POST', body: data }),
  updateSpecification: (projectId: string, specId: string, data: Partial<Specification>) =>
    request<Specification>(`/projects/${projectId}/specifications/${specId}`, { method: 'PUT', body: data }),
  deleteSpecification: (projectId: string, specId: string) =>
    request<void>(`/projects/${projectId}/specifications/${specId}`, { method: 'DELETE' }),

  // Verification Cases
  listVerificationCases: (projectId: string) => request<VerificationCase[]>(`/projects/${projectId}/verification`),
  createVerificationCase: (projectId: string, data: Partial<VerificationCase>) =>
    request<VerificationCase>(`/projects/${projectId}/verification`, { method: 'POST', body: data }),
  updateVerificationCase: (projectId: string, vcId: string, data: Partial<VerificationCase>) =>
    request<VerificationCase>(`/projects/${projectId}/verification/${vcId}`, { method: 'PUT', body: data }),
  deleteVerificationCase: (projectId: string, vcId: string) =>
    request<void>(`/projects/${projectId}/verification/${vcId}`, { method: 'DELETE' }),
  runVerification: (projectId: string, vcId: string, data: { status: string; notes?: string; step_results?: Record<string, string> }) =>
    request<VerificationCase>(`/projects/${projectId}/verification/${vcId}/run`, { method: 'POST', body: data }),

  // Traces
  getTraces: (projectId: string) => request<{ links: TraceLink[] }>(`/projects/${projectId}/traces`),
  updateTraces: (projectId: string, data: { links: TraceLink[] }) =>
    request<{ links: TraceLink[] }>(`/projects/${projectId}/traces`, { method: 'PUT', body: data }),

  // Change Requests
  listChangeRequests: (projectId: string) => request<ChangeRequest[]>(`/projects/${projectId}/change-requests`),
  createChangeRequest: (projectId: string, data: Partial<ChangeRequest>) =>
    request<ChangeRequest>(`/projects/${projectId}/change-requests`, { method: 'POST', body: data }),
  updateChangeRequest: (projectId: string, crId: string, data: Partial<ChangeRequest>) =>
    request<ChangeRequest>(`/projects/${projectId}/change-requests/${crId}`, { method: 'PUT', body: data }),
  deleteChangeRequest: (projectId: string, crId: string) =>
    request<void>(`/projects/${projectId}/change-requests/${crId}`, { method: 'DELETE' }),

  // Risks
  listRisks: (projectId: string) => request<Risk[]>(`/projects/${projectId}/risks`),
  createRisk: (projectId: string, data: Partial<Risk>) =>
    request<Risk>(`/projects/${projectId}/risks`, { method: 'POST', body: data }),
  updateRisk: (projectId: string, riskId: string, data: Partial<Risk>) =>
    request<Risk>(`/projects/${projectId}/risks/${riskId}`, { method: 'PUT', body: data }),
  deleteRisk: (projectId: string, riskId: string) =>
    request<void>(`/projects/${projectId}/risks/${riskId}`, { method: 'DELETE' }),

  // Comments
  listComments: (projectId: string, requirementId?: string) => {
    const qs = requirementId ? `?requirement_id=${encodeURIComponent(requirementId)}` : '';
    return request<Comment[]>(`/projects/${projectId}/comments${qs}`);
  },
  createComment: (projectId: string, data: { requirement_id: string; author: string; text: string }) =>
    request<Comment>(`/projects/${projectId}/comments`, { method: 'POST', body: data }),
  deleteComment: (projectId: string, commentId: string) =>
    request<void>(`/projects/${projectId}/comments/${commentId}`, { method: 'DELETE' }),

  // Decisions
  listDecisions: (projectId: string) => request<DecisionRecord[]>(`/projects/${projectId}/decisions`),
  createDecision: (projectId: string, data: Partial<DecisionRecord>) =>
    request<DecisionRecord>(`/projects/${projectId}/decisions`, { method: 'POST', body: data }),
  updateDecision: (projectId: string, decId: string, data: Partial<DecisionRecord>) =>
    request<DecisionRecord>(`/projects/${projectId}/decisions/${decId}`, { method: 'PUT', body: data }),
  deleteDecision: (projectId: string, decId: string) =>
    request<void>(`/projects/${projectId}/decisions/${decId}`, { method: 'DELETE' }),

  // Analysis
  getImpact: (projectId: string, reqId: string) =>
    request<ImpactResult>(`/projects/${projectId}/requirements/${reqId}/impact`),
  getGapAnalysis: (projectId: string) =>
    request<{ total: number; gaps: number; items: GapItem[] }>(`/projects/${projectId}/gap-analysis`),
  getCoverageAnalysis: (projectId: string) =>
    request<CoverageData>(`/projects/${projectId}/coverage`),
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

  // Metrics & Compliance
  getMetrics: (projectId: string) => request<MetricsData>(`/projects/${projectId}/metrics`),
  getCompliance: (projectId: string) =>
    request<{ standards: { name: string; count: number }[]; tracked_count: number; total_requirements: number }>(`/projects/${projectId}/compliance`),

  // Bulk — Requirements
  bulkUpdateRequirements: (projectId: string, ids: string[], updates: Record<string, any>) =>
    request<{ updated: number; ids: string[] }>(`/projects/${projectId}/requirements/bulk`, { method: 'POST', body: { ids, updates } }),
  bulkDeleteRequirements: (projectId: string, ids: string[]) =>
    request<{ deleted: number }>(`/projects/${projectId}/requirements/bulk-delete`, { method: 'POST', body: { ids } }),
  bulkReparentRequirements: (projectId: string, ids: string[], parent: string | null, rePrefix: boolean = false) =>
    request<{ updated: number; ids: string[] }>(`/projects/${projectId}/requirements/bulk-reparent`, { method: 'POST', body: { ids, parent, re_prefix: rePrefix } }),

  // Bulk — Components
  bulkUpdateComponents: (projectId: string, ids: string[], updates: Record<string, any>) =>
    request<{ updated: number }>(`/projects/${projectId}/components/bulk`, { method: 'POST', body: { ids, updates } }),
  bulkDeleteComponents: (projectId: string, ids: string[]) =>
    request<{ deleted: number }>(`/projects/${projectId}/components/bulk-delete`, { method: 'POST', body: { ids } }),
  bulkReparentComponents: (projectId: string, ids: string[], parent: string | null) =>
    request<{ updated: number }>(`/projects/${projectId}/components/bulk-reparent`, { method: 'POST', body: { ids, parent } }),

  // Bulk — Verification Cases
  bulkUpdateVerificationCases: (projectId: string, ids: string[], updates: Record<string, any>) =>
    request<{ updated: number }>(`/projects/${projectId}/verification/bulk`, { method: 'POST', body: { ids, updates } }),
  bulkDeleteVerificationCases: (projectId: string, ids: string[]) =>
    request<{ deleted: number }>(`/projects/${projectId}/verification/bulk-delete`, { method: 'POST', body: { ids } }),

  // Bulk — Specifications
  bulkUpdateSpecifications: (projectId: string, ids: string[], updates: Record<string, any>) =>
    request<{ updated: number }>(`/projects/${projectId}/specifications/bulk`, { method: 'POST', body: { ids, updates } }),
  bulkDeleteSpecifications: (projectId: string, ids: string[]) =>
    request<{ deleted: number }>(`/projects/${projectId}/specifications/bulk-delete`, { method: 'POST', body: { ids } }),

  // Bulk — Risks
  bulkUpdateRisks: (projectId: string, ids: string[], updates: Record<string, any>) =>
    request<{ updated: number }>(`/projects/${projectId}/risks/bulk`, { method: 'POST', body: { ids, updates } }),
  bulkDeleteRisks: (projectId: string, ids: string[]) =>
    request<{ deleted: number }>(`/projects/${projectId}/risks/bulk-delete`, { method: 'POST', body: { ids } }),

  // Bulk — Change Requests
  bulkUpdateChangeRequests: (projectId: string, ids: string[], updates: Record<string, any>) =>
    request<{ updated: number }>(`/projects/${projectId}/change-requests/bulk`, { method: 'POST', body: { ids, updates } }),
  bulkDeleteChangeRequests: (projectId: string, ids: string[]) =>
    request<{ deleted: number }>(`/projects/${projectId}/change-requests/bulk-delete`, { method: 'POST', body: { ids } }),

  // History
  getRequirementHistory: (projectId: string, reqId: string) =>
    request<any[]>(`/projects/${projectId}/requirements/${reqId}/history`),

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
    return request<{ items: { id: string; name: string; status: string; effort: number | null; priorities: Record<string, number>; combined_priority: number }[]; total_effort: number; completed_effort: number }>(`/projects/${projectId}/backlog${qs}`);
  },
};
