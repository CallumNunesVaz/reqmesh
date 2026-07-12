import { create } from 'zustand';

interface AuthUser {
  username: string;
  role: string;
  token?: string;
}

interface AuthState {
  user: AuthUser | null;
  token: string | null;
  editMode: boolean;
  isGuest: boolean;
  setUser: (user: AuthUser | null) => void;
  setToken: (token: string | null) => void;
  setEditMode: (on: boolean) => void;
  login: (username: string, token: string, role: string) => void;
  loginGuest: () => void;
  logout: () => void;
  isLoggedIn: () => boolean;
  canEdit: () => boolean;
}

const storage = {
  get: (key: string) => { try { return localStorage.getItem(key); } catch { return null; } },
  set: (key: string, val: string) => { try { localStorage.setItem(key, val); } catch {} },
  remove: (key: string) => { try { localStorage.removeItem(key); } catch {} },
};

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: storage.get('rt-token'),
  editMode: false,
  isGuest: storage.get('rt-guest') === 'true',

  setUser: (user) => set({ user }),
  setToken: (token) => {
    if (token) storage.set('rt-token', token);
    else storage.remove('rt-token');
    set({ token });
  },
  setEditMode: (on) => set({ editMode: on }),

  login: (username, token, role) => {
    storage.set('rt-token', token);
    storage.set('rt-guest', 'false');
    set({ user: { username, role, token }, token, isGuest: false, editMode: false });
  },

  loginGuest: () => {
    storage.remove('rt-token');
    storage.set('rt-guest', 'true');
    set({ user: { username: 'guest', role: 'viewer' }, token: null, isGuest: true, editMode: false });
  },

  logout: () => {
    storage.remove('rt-token');
    storage.remove('rt-guest');
    set({ user: null, token: null, isGuest: false, editMode: false });
  },

  isLoggedIn: () => get().token !== null,
  canEdit: () => {
    const s = get();
    return s.user !== null && s.user.role !== 'viewer' && s.editMode;
  },
}));
