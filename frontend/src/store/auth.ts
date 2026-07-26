import { create } from 'zustand';

interface AuthUser {
  username: string;
  role: string;
}

interface AuthState {
  user: AuthUser | null;
  csrfToken: string | null;
  wsToken: string | null;
  editMode: boolean;
  isGuest: boolean;
  passwordChangeRequired: boolean;
  setUser: (user: AuthUser | null) => void;
  setCsrfToken: (token: string | null) => void;
  setWsToken: (token: string | null) => void;
  setEditMode: (on: boolean) => void;
  login: (username: string, role: string, csrfToken: string, wsToken?: string, passwordChangeRequired?: boolean) => void;
  loginGuest: (csrfToken: string) => void;
  logout: () => void;
  isLoggedIn: () => boolean;
  canEdit: () => boolean;
  canPropose: () => boolean;
  canToggleEdit: () => boolean;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  csrfToken: null,
  wsToken: null,
  editMode: false,
  isGuest: false,
  passwordChangeRequired: false,

  setUser: (user) => set({ user }),
  setCsrfToken: (token) => set({ csrfToken: token }),
  setWsToken: (token) => set({ wsToken: token }),
  setEditMode: (on) => set({ editMode: on }),

  login: (username, role, csrfToken, wsToken, passwordChangeRequired) => {
    set({
      user: { username, role },
      csrfToken,
      wsToken: wsToken ?? null,
      isGuest: false,
      editMode: false,
      passwordChangeRequired: passwordChangeRequired ?? false,
    });
  },

  loginGuest: (csrfToken) => {
    set({
      user: { username: 'guest', role: 'guest' },
      csrfToken,
      wsToken: null,
      isGuest: true,
      editMode: false,
      passwordChangeRequired: false,
    });
  },

  logout: () => {
    set({
      user: null,
      csrfToken: null,
      wsToken: null,
      isGuest: false,
      editMode: false,
      passwordChangeRequired: false,
    });
  },

  isLoggedIn: () => {
    const s = get();
    return s.user !== null && s.user.role !== 'guest';
  },
  canEdit: () => {
    const s = get();
    return s.user !== null && (s.user.role === 'maintainer' || s.user.role === 'admin') && s.editMode;
  },
  canPropose: () => {
    const s = get();
    return s.user !== null && ['contributor', 'maintainer', 'admin'].includes(s.user.role);
  },
  canToggleEdit: () => {
    const s = get();
    return s.user !== null && (s.user.role === 'maintainer' || s.user.role === 'admin');
  },
}));
