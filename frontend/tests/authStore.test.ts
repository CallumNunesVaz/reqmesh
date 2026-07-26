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
  it('allows contributor, maintainer, and admin — independent of edit mode', async () => {
    const useAuthStore = await freshStore();
    const { login, loginGuest } = useAuthStore.getState();

    expect(useAuthStore.getState().canPropose()).toBe(false);

    loginGuest('t');
    expect(useAuthStore.getState().canPropose()).toBe(false);

    login('bob', 'contributor', 't');
    expect(useAuthStore.getState().canPropose()).toBe(true);

    login('mo', 'maintainer', 't');
    expect(useAuthStore.getState().canPropose()).toBe(true);

    login('old', 'editor', 't');
    expect(useAuthStore.getState().canPropose()).toBe(false);
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
