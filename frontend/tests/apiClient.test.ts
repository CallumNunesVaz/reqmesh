import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { api } from '../src/api/client';

/** Build a fetch stub that always answers with one canned response. */
function stubFetch(response: { status?: number; statusText?: string; json?: () => Promise<unknown> } = {}) {
  const res = {
    ok: (response.status ?? 200) < 400,
    status: response.status ?? 200,
    statusText: response.statusText ?? 'OK',
    json: response.json ?? (async () => ({})),
  };
  const fetchMock = vi.fn(async () => res as unknown as Response);
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

/** The single [url, init] pair a stub was called with. */
function callOf(fetchMock: ReturnType<typeof stubFetch>) {
  expect(fetchMock).toHaveBeenCalledOnce();
  const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
  return { url, init, headers: (init.headers ?? {}) as Record<string, string> };
}

beforeEach(() => {
  vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => {}, removeItem: () => {} });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('request', () => {
  it('prefixes /api and defaults to GET without a body', async () => {
    const f = stubFetch({ json: async () => [] });
    await api.listProjects();
    const { url, init } = callOf(f);
    expect(url).toBe('/api/projects');
    expect(init.method).toBe('GET');
    expect(init.body).toBeUndefined();
  });

  it('returns the parsed JSON body', async () => {
    stubFetch({ json: async () => [{ id: 'demo', name: 'Demo', path: '/tmp/demo' }] });
    await expect(api.listProjects()).resolves.toEqual([{ id: 'demo', name: 'Demo', path: '/tmp/demo' }]);
  });

  it('JSON-encodes a body and sets the content type', async () => {
    const f = stubFetch();
    await api.createProject({ id: 'demo', name: 'Demo' });
    const { url, init, headers } = callOf(f);
    expect(url).toBe('/api/projects');
    expect(init.method).toBe('POST');
    expect(headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(init.body as string)).toEqual({ id: 'demo', name: 'Demo' });
  });

  it('attaches X-CSRF-Token header on mutating requests when available', async () => {
    const { useAuthStore } = await import('../src/store/auth');
    useAuthStore.getState().login('alice', 'admin', 'csrf-tok-123');
    const f = stubFetch();
    await api.createProject({ id: 'demo', name: 'Demo' });
    expect(callOf(f).headers['X-CSRF-Token']).toBe('csrf-tok-123');
  });

  it('omits X-CSRF-Token on GET requests', async () => {
    const { useAuthStore } = await import('../src/store/auth');
    useAuthStore.getState().login('alice', 'admin', 'csrf-tok-123');
    const f = stubFetch({ json: async () => [] });
    await api.listProjects();
    expect(callOf(f).headers['X-CSRF-Token']).toBeUndefined();
  });

  it('still sends the request when localStorage is unavailable', async () => {
    vi.stubGlobal('localStorage', { getItem: () => { throw new Error('denied'); } });
    const f = stubFetch({ json: async () => [] });
    await expect(api.listProjects()).resolves.toEqual([]);
    expect(callOf(f).headers['Authorization']).toBeUndefined();
  });

  it('surfaces the backend detail message on an error status', async () => {
    stubFetch({ status: 403, json: async () => ({ detail: 'Edit permission required' }) });
    await expect(api.listProjects()).rejects.toThrow('Edit permission required');
  });

  it('falls back to the status text when the error body is not JSON', async () => {
    stubFetch({
      status: 500,
      statusText: 'Internal Server Error',
      json: async () => { throw new Error('not json'); },
    });
    await expect(api.listProjects()).rejects.toThrow('Internal Server Error');
  });

  it('returns undefined for 204 rather than parsing an empty body', async () => {
    stubFetch({ status: 204, json: async () => { throw new Error('no body to parse'); } });
    await expect(api.deleteProject('demo')).resolves.toBeUndefined();
  });
});

describe('session expiry (401 handling)', () => {
  it('calls logout and still rejects on a 401 from a normal endpoint', async () => {
    const { useAuthStore } = await import('../src/store/auth');
    useAuthStore.getState().login('alice', 'admin', 'csrf-tok');
    expect(useAuthStore.getState().user).not.toBeNull();

    stubFetch({ status: 401, json: async () => ({ detail: 'Session expired' }) });
    await expect(api.listProjects()).rejects.toThrow('Session expired');

    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().csrfToken).toBeNull();
  });

  it('does NOT call logout on a 401 from an auth endpoint', async () => {
    const { useAuthStore } = await import('../src/store/auth');
    useAuthStore.getState().login('alice', 'admin', 'csrf-tok');
    expect(useAuthStore.getState().user).not.toBeNull();

    stubFetch({ status: 401, json: async () => ({ detail: 'Invalid credentials' }) });
    await expect(api.login('alice', 'wrong')).rejects.toThrow('Invalid credentials');

    // Auth store must still have the previous user — logout must not fire.
    expect(useAuthStore.getState().user).not.toBeNull();
  });

  it('does not redirect a second time once already signed out', async () => {
    // The redirect must fire on *expiry*, not on every 401, or it loops: with
    // RT_REQUIRE_AUTH the projects list is itself 401 to an unauthenticated
    // caller, so redirecting to `/` lands on a page whose own listProjects()
    // 401s and redirects again — a reloading tab you cannot sign in from.
    //
    // Asserted through the store rather than through `window.location`, which
    // this environment does not have: the guard reads the user before clearing
    // it, so "already signed out" is the terminating condition.
    const { useAuthStore } = await import('../src/store/auth');
    useAuthStore.getState().logout();
    expect(useAuthStore.getState().user).toBeNull();

    stubFetch({ status: 401, json: async () => ({ detail: 'Not authenticated' }) });
    await expect(api.listProjects()).rejects.toThrow('Not authenticated');

    // Still signed out, and the call reported the error rather than bouncing.
    expect(useAuthStore.getState().user).toBeNull();
  });

  it('does not log the user out on a 403', async () => {
    const { useAuthStore } = await import('../src/store/auth');
    useAuthStore.getState().login('alice', 'admin', 'csrf-tok');
    expect(useAuthStore.getState().user).not.toBeNull();

    stubFetch({ status: 403, json: async () => ({ detail: 'Forbidden' }) });
    await expect(api.listProjects()).rejects.toThrow('Forbidden');

    expect(useAuthStore.getState().user).not.toBeNull();
  });
});

describe('listRequirements', () => {
  // The list endpoint is paginated; the unwrapping wrapper asks for the
  // server's max page so "list the project" callers see a plain array.
  const page = (items: unknown[] = []) =>
    ({ json: async () => ({ items, total: items.length, offset: 0, limit: 2000 }) });

  it('appends filters after the max-page limit', async () => {
    const f = stubFetch(page());
    await api.listRequirements('demo', { search: 'stall', type: 'functional' });
    expect(callOf(f).url).toBe('/api/projects/demo/requirements?limit=2000&search=stall&type=functional');
  });

  it('requests the max page when no filters are given, and unwraps items', async () => {
    const f = stubFetch(page([{ id: 'R1' }]));
    const result = await api.listRequirements('demo');
    expect(callOf(f).url).toBe('/api/projects/demo/requirements?limit=2000');
    expect(result).toEqual([{ id: 'R1' }]);
  });

  it('lets an explicit limit override the default', async () => {
    const f = stubFetch(page());
    await api.listRequirements('demo', { limit: '50' });
    expect(callOf(f).url).toBe('/api/projects/demo/requirements?limit=50');
  });

  it('url-encodes filter values', async () => {
    const f = stubFetch(page());
    await api.listRequirements('demo', { search: 'fuel & air' });
    expect(callOf(f).url).toBe('/api/projects/demo/requirements?limit=2000&search=fuel+%26+air');
  });

  it('exposes the raw envelope through the paged variant', async () => {
    const f = stubFetch(page([{ id: 'R1' }]));
    const result = await api.listRequirementsPaged('demo', { offset: '10' });
    expect(callOf(f).url).toBe('/api/projects/demo/requirements?offset=10');
    expect(result.total).toBe(1);
  });
});

describe('components', () => {
  it('fetches the design tree from its own endpoint', async () => {
    const f = stubFetch({ json: async () => [] });
    await api.getComponentTree('demo');
    expect(callOf(f).url).toBe('/api/projects/demo/components/tree');
  });

  it('filters components by the requirement they satisfy, unwrapping the page', async () => {
    const f = stubFetch({ json: async () => ({ items: [{ id: 'C-001' }], total: 1, offset: 0, limit: 2000 }) });
    const result = await api.listComponents('demo', { satisfies: 'REQ-001' });
    expect(callOf(f).url).toBe('/api/projects/demo/components?limit=2000&satisfies=REQ-001');
    expect(result).toEqual([{ id: 'C-001' }]);
  });

  it('creates a component with its parent link', async () => {
    const f = stubFetch();
    await api.createComponent('demo', { id: 'C-002', name: 'Pump', parent: 'C-001' });
    const { url, init } = callOf(f);
    expect(url).toBe('/api/projects/demo/components');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({ id: 'C-002', name: 'Pump', parent: 'C-001' });
  });

  it('sends a null parent when promoting to the top level', async () => {
    const f = stubFetch();
    await api.updateComponent('demo', 'C-002', { parent: null });
    expect(JSON.parse(callOf(f).init.body as string)).toEqual({ parent: null });
  });

  it('reads the components allocated to a requirement', async () => {
    const f = stubFetch({ json: async () => [] });
    await api.getComponentsForRequirement('demo', 'REQ-001');
    expect(callOf(f).url).toBe('/api/projects/demo/requirements/REQ-001/components');
  });
});

describe('importProject', () => {
  it('posts multipart form data without forcing a content type', async () => {
    const f = stubFetch();
    const file = new File(['<REQ-IF/>'], 'model.reqif');
    await api.importProject('demo', file, 'auto', 'merge');
    const { url, init, headers } = callOf(f);

    expect(url).toBe('/api/projects/demo/import');
    expect(init.method).toBe('POST');
    // The browser must set the multipart boundary itself.
    expect(headers['Content-Type']).toBeUndefined();

    const fd = init.body as FormData;
    expect(fd).toBeInstanceOf(FormData);
    expect(fd.get('file')).toBe(file);
    expect(fd.get('format')).toBe('auto');
    expect(fd.get('mode')).toBe('merge');
  });
});

describe('user management', () => {
  it('patches only the fields being changed', async () => {
    const f = stubFetch();
    await api.updateUser('bob', { role: 'admin' });
    const { url, init } = callOf(f);
    expect(url).toBe('/api/auth/users/bob');
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(init.body as string)).toEqual({ role: 'admin' });
  });

  it('encodes the username into the path', async () => {
    const f = stubFetch();
    await api.deleteUser('bob smith');
    const { url, init } = callOf(f);
    expect(url).toBe('/api/auth/users/bob%20smith');
    expect(init.method).toBe('DELETE');
  });
});
