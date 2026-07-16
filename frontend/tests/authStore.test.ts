import { describe, it, expect, beforeEach, vi } from 'vitest';

/**
 * The auth store reads localStorage at module-init time (to rehydrate a token
 * across reloads), so each test installs a fresh stub and re-imports the module
 * rather than sharing one instance.
 */
function installStorage(seed: Record<string, string> = {}) {
  const data = new Map(Object.entries(seed));
  const store = {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
    clear: () => data.clear(),
    key: (i: number) => [...data.keys()][i] ?? null,
    get length() { return data.size; },
  };
  vi.stubGlobal('localStorage', store);
  return data;
}

async function freshStore() {
  vi.resetModules();
  return (await import('../src/store/auth')).useAuthStore;
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe('useAuthStore init', () => {
  it('rehydrates a persisted token and the guest flag', async () => {
    installStorage({ 'rt-token': 'abc', 'rt-guest': 'true' });
    const s = (await freshStore()).getState();
    expect(s.token).toBe('abc');
    expect(s.isGuest).toBe(true);
  });

  it('starts empty when nothing is persisted', async () => {
    installStorage();
    const s = (await freshStore()).getState();
    expect(s.token).toBeNull();
    expect(s.isGuest).toBe(false);
  });

  it('survives localStorage being unavailable', async () => {
    vi.stubGlobal('localStorage', {
      getItem: () => { throw new Error('denied'); },
      setItem: () => { throw new Error('denied'); },
      removeItem: () => { throw new Error('denied'); },
    });
    const useAuthStore = await freshStore();
    expect(useAuthStore.getState().token).toBeNull();
    // Writes must not throw either — the store is the app's boot path.
    expect(() => useAuthStore.getState().login('bob', 't', 'editor')).not.toThrow();
    expect(useAuthStore.getState().user?.username).toBe('bob');
  });
});

describe('login', () => {
  it('persists the token, clears guest mode and starts in view mode', async () => {
    const data = installStorage({ 'rt-guest': 'true' });
    const useAuthStore = await freshStore();
    useAuthStore.getState().login('alice', 'tok123', 'admin');

    const s = useAuthStore.getState();
    expect(s.user).toEqual({ username: 'alice', role: 'admin', token: 'tok123' });
    expect(s.token).toBe('tok123');
    expect(s.isGuest).toBe(false);
    expect(s.editMode).toBe(false);
    expect(data.get('rt-token')).toBe('tok123');
    expect(data.get('rt-guest')).toBe('false');
  });
});

describe('loginGuest', () => {
  it('drops any token and marks the session as a viewer guest', async () => {
    const data = installStorage({ 'rt-token': 'stale' });
    const useAuthStore = await freshStore();
    useAuthStore.getState().loginGuest();

    const s = useAuthStore.getState();
    expect(s.user).toEqual({ username: 'guest', role: 'viewer' });
    expect(s.token).toBeNull();
    expect(s.isGuest).toBe(true);
    expect(data.has('rt-token')).toBe(false);
    expect(data.get('rt-guest')).toBe('true');
  });
});

describe('logout', () => {
  it('clears both state and storage', async () => {
    const data = installStorage();
    const useAuthStore = await freshStore();
    useAuthStore.getState().login('alice', 'tok123', 'admin');
    useAuthStore.getState().logout();

    const s = useAuthStore.getState();
    expect(s.user).toBeNull();
    expect(s.token).toBeNull();
    expect(s.isGuest).toBe(false);
    expect(data.size).toBe(0);
  });
});

describe('setToken', () => {
  it('removes the persisted token when set to null', async () => {
    const data = installStorage({ 'rt-token': 'abc' });
    const useAuthStore = await freshStore();
    useAuthStore.getState().setToken(null);
    expect(useAuthStore.getState().token).toBeNull();
    expect(data.has('rt-token')).toBe(false);
  });
});

describe('canEdit', () => {
  it('requires a non-viewer user with edit mode switched on', async () => {
    installStorage();
    const useAuthStore = await freshStore();
    const { login, setEditMode, loginGuest } = useAuthStore.getState();

    expect(useAuthStore.getState().canEdit()).toBe(false); // logged out

    login('bob', 't', 'editor');
    expect(useAuthStore.getState().canEdit()).toBe(false); // edit mode off
    setEditMode(true);
    expect(useAuthStore.getState().canEdit()).toBe(true);

    // A viewer can never edit, even with the toggle forced on.
    loginGuest();
    setEditMode(true);
    expect(useAuthStore.getState().canEdit()).toBe(false);
  });
});

describe('isLoggedIn', () => {
  it('tracks the token, not the guest user object', async () => {
    installStorage();
    const useAuthStore = await freshStore();
    expect(useAuthStore.getState().isLoggedIn()).toBe(false);
    useAuthStore.getState().loginGuest();
    expect(useAuthStore.getState().isLoggedIn()).toBe(false);
    useAuthStore.getState().login('bob', 't', 'editor');
    expect(useAuthStore.getState().isLoggedIn()).toBe(true);
  });
});
