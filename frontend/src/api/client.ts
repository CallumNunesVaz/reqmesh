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

export interface Requirement {
  id: string;
  type: string;
  name: string;
  description: string;
  priority: string;
  status: string;
  verification_method: string;
  attributes: { key: string; value: string }[];
  relations: { type: string; target: string }[];
  verification_cases: string[];
  verification_status: string;
  parent: string | null;
  cascade_from: string | null;
  rationale: string;
  source: string;
  allocated_to: string;
  baseline: string | null;
  created: string;
  modified: string;
}

export interface RequirementTreeNode {
  id: string;
  name: string;
  type: string;
  status: string;
  priority: string;
  children: RequirementTreeNode[];
}

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
export interface CoverageItem { id: string; name: string; verification_cases: number; relations: number; covered: boolean }
export interface ConflictItem { ids?: string[]; a?: string; b?: string; type: string; name?: string }
export interface MetricsData {
  total: number;
  verification_cases: number;
  baselines: number;
  status_distribution: Record<string, number>;
  quality: Record<string, number>;
  quality_pct: Record<string, number>;
}

export const api = {
  // Auth
  login: (username: string, password: string) =>
    request<{ username: string; role: string; token: string }>('/auth/login', { method: 'POST', body: { username, password } }),
  register: (username: string, password: string, role: string = 'editor') =>
    request<{ username: string; role: string; token: string }>('/auth/register', { method: 'POST', body: { username, password, role } }),
  loginAsGuest: () =>
    request<{ username: string; role: string }>('/auth/guest', { method: 'POST' }),
  whoami: () =>
    request<{ username: string; role: string }>('/auth/whoami'),

  // Projects
  listProjects: () => request<Project[]>('/projects'),
  createProject: (data: { id: string; name: string }) => request<Project>('/projects', { method: 'POST', body: data }),
  getProject: (id: string) => request<Project>(`/projects/${id}`),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: 'DELETE' }),
  getWorkflow: (projectId: string) =>
    request<{ states: string[]; transitions: Record<string, string[]>; default: string }>(`/projects/${projectId}/workflow`),

  // Requirements
  listRequirements: (projectId: string, params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return request<Requirement[]>(`/projects/${projectId}/requirements${qs}`);
  },
  getRequirementTree: (projectId: string) =>
    request<RequirementTreeNode[]>(`/projects/${projectId}/requirements/tree`),
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
    request<{ total: number; covered: number; coverage_pct: number; items: CoverageItem[] }>(`/projects/${projectId}/coverage`),
  getConflicts: (projectId: string) =>
    request<{ count: number; conflicts: ConflictItem[] }>(`/projects/${projectId}/conflicts`),

  // Metrics & Compliance
  getMetrics: (projectId: string) => request<MetricsData>(`/projects/${projectId}/metrics`),
  getCompliance: (projectId: string) =>
    request<{ standards: { name: string; count: number }[]; tracked_count: number; total_requirements: number }>(`/projects/${projectId}/compliance`),

  // Bulk
  bulkUpdateRequirements: (projectId: string, ids: string[], updates: Record<string, any>) =>
    request<{ updated: number; ids: string[] }>(`/projects/${projectId}/requirements/bulk`, { method: 'POST', body: { ids, updates } }),
  bulkDeleteRequirements: (projectId: string, ids: string[]) =>
    request<{ deleted: number }>(`/projects/${projectId}/requirements/bulk-delete`, { method: 'POST', body: { ids } }),

  // History
  getRequirementHistory: (projectId: string, reqId: string) =>
    request<any[]>(`/projects/${projectId}/requirements/${reqId}/history`),

  // UID
  getNextUid: (projectId: string, parent?: string) => {
    const qs = parent ? `?parent=${encodeURIComponent(parent)}` : '';
    return request<{ prefix: string; next_id: string }>(`/projects/${projectId}/requirements/next-uid${qs}`);
  },
};
