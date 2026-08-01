import { describe, it, expect, beforeEach, vi } from 'vitest';

/**
 * The auth store no longer uses localStorage — tokens are in HttpOnly cookies.
 * Each test imports a fresh module to avoid shared state.
 */

async function freshStore() {
  vi.resetModules();
  return (await import('../src/store/auth')).useAuthStore;
}

describe('useAuthStore init', () => {
  it('starts with no user or token', async () => {
    const s = (await freshStore()).getState();
    expect(s.user).toBeNull();
    expect(s.csrfToken).toBeNull();
    expect(s.isGuest).toBe(false);
    expect(s.passwordChangeRequired).toBe(false);
  });
});

describe('login', () => {
  it('sets user, csrfToken, and clears guest mode', async () => {
    const useAuthStore = await freshStore();
    useAuthStore.getState().login('alice', 'admin', 'csrf123');

    const s = useAuthStore.getState();
    expect(s.user).toEqual({ username: 'alice', role: 'admin' });
    expect(s.csrfToken).toBe('csrf123');
    expect(s.isGuest).toBe(false);
    expect(s.editMode).toBe(false);
  });

  it('supports wsToken and passwordChangeRequired', async () => {
    const useAuthStore = await freshStore();
    useAuthStore.getState().login('alice', 'admin', 'csrf123', 'ws456', true);

    const s = useAuthStore.getState();
    expect(s.wsToken).toBe('ws456');
    expect(s.passwordChangeRequired).toBe(true);
  });
});

describe('loginGuest', () => {
  it('marks the session as a viewer guest with csrf token', async () => {
    const useAuthStore = await freshStore();
    useAuthStore.getState().loginGuest('guestCsrf123');

    const s = useAuthStore.getState();
    expect(s.user).toEqual({ username: 'guest', role: 'guest' });
    expect(s.csrfToken).toBe('guestCsrf123');
    expect(s.isGuest).toBe(true);
  });
});

describe('logout', () => {
  it('clears all state', async () => {
    const useAuthStore = await freshStore();
    useAuthStore.getState().login('alice', 'admin', 'csrf123');
    useAuthStore.getState().logout();

    const s = useAuthStore.getState();
    expect(s.user).toBeNull();
    expect(s.csrfToken).toBeNull();
    expect(s.wsToken).toBeNull();
    expect(s.isGuest).toBe(false);
    expect(s.passwordChangeRequired).toBe(false);
  });
});

describe('canEdit', () => {
  it('requires maintainer or admin with edit mode switched on', async () => {
    const useAuthStore = await freshStore();
    const { login, setEditMode, loginGuest } = useAuthStore.getState();

    expect(useAuthStore.getState().canEdit()).toBe(false);

    login('bob', 'maintainer', 't');
    expect(useAuthStore.getState().canEdit()).toBe(false);
    setEditMode(true);
    expect(useAuthStore.getState().canEdit()).toBe(true);

    login('alice', 'admin', 't');
    setEditMode(true);
    expect(useAuthStore.getState().canEdit()).toBe(true);

    loginGuest('t');
    setEditMode(true);
    expect(useAuthStore.getState().canEdit()).toBe(false);

    login('charlie', 'contributor', 't');
    setEditMode(true);
    expect(useAuthStore.getState().canEdit()).toBe(false);
  });
});

describe('canPropose', () => {
  // Previously asserted "independent of edit mode", which is what let risks
  // and change requests be created and deleted while the header said VIEWING.
  it('allows contributor, maintainer, and admin — but only while editing', async () => {
    const useAuthStore = await freshStore();
    const { login, loginGuest, setEditMode } = useAuthStore.getState();

    expect(useAuthStore.getState().canPropose()).toBe(false);

    loginGuest('t');
    setEditMode(true);
    expect(useAuthStore.getState().canPropose()).toBe(false);

    for (const role of ['contributor', 'maintainer', 'admin']) {
      login('bob', role, 't');
      expect(useAuthStore.getState().canPropose()).toBe(false);   // login resets to viewing
      useAuthStore.getState().setEditMode(true);
      expect(useAuthStore.getState().canPropose()).toBe(true);
    }

    login('old', 'editor', 't');
    useAuthStore.getState().setEditMode(true);
    expect(useAuthStore.getState().canPropose()).toBe(false);     // legacy role
  });
});

describe('isLoggedIn', () => {
  it('checks user role is not guest', async () => {
    const useAuthStore = await freshStore();
    expect(useAuthStore.getState().isLoggedIn()).toBe(false);
    useAuthStore.getState().loginGuest('t');
    expect(useAuthStore.getState().isLoggedIn()).toBe(false);
    useAuthStore.getState().login('bob', 'contributor', 't');
    expect(useAuthStore.getState().isLoggedIn()).toBe(true);
  });
});

/**
 * Edit mode is the guard against changing data you only meant to read. It has
 * to bind every tier that writes.
 *
 * canPropose ignored it entirely, so risks, change requests and comments were
 * fully editable — and deletable — while the header said VIEWING.
 */
describe('viewing mode blocks every write tier', () => {
  const ROLES = ['contributor', 'maintainer', 'admin'] as const;

  it.each(ROLES)('%s cannot propose while viewing', async (role) => {
    const useAuthStore = await freshStore();
    useAuthStore.getState().login('u', role, 'csrf');
    expect(useAuthStore.getState().editMode).toBe(false);
    expect(useAuthStore.getState().canPropose()).toBe(false);
    expect(useAuthStore.getState().canEdit()).toBe(false);
  });

  it.each(ROLES)('%s can propose once editing is on', async (role) => {
    const useAuthStore = await freshStore();
    useAuthStore.getState().login('u', role, 'csrf');
    useAuthStore.getState().setEditMode(true);
    expect(useAuthStore.getState().canPropose()).toBe(true);
  });

  it('a guest can never propose, edit, or turn edit mode on', async () => {
    const useAuthStore = await freshStore();
    useAuthStore.getState().loginGuest('csrf');
    useAuthStore.getState().setEditMode(true);
    expect(useAuthStore.getState().canPropose()).toBe(false);
    expect(useAuthStore.getState().canEdit()).toBe(false);
    expect(useAuthStore.getState().canToggleEdit()).toBe(false);
  });

  it('a contributor can reach edit mode, or making canPropose respect it would lock them out entirely', async () => {
    const useAuthStore = await freshStore();
    useAuthStore.getState().login('c', 'contributor', 'csrf');
    expect(useAuthStore.getState().canToggleEdit()).toBe(true);
  });

  it('editing does not promote a contributor to the maintainer tier', async () => {
    const useAuthStore = await freshStore();
    useAuthStore.getState().login('c', 'contributor', 'csrf');
    useAuthStore.getState().setEditMode(true);
    expect(useAuthStore.getState().canPropose()).toBe(true);
    expect(useAuthStore.getState().canEdit()).toBe(false);
  });

  it('logging in lands in viewing mode', async () => {
    const useAuthStore = await freshStore();
    useAuthStore.getState().login('m', 'maintainer', 'csrf');
    useAuthStore.getState().setEditMode(true);
    useAuthStore.getState().login('m', 'maintainer', 'csrf');
    expect(useAuthStore.getState().editMode).toBe(false);
  });
});
