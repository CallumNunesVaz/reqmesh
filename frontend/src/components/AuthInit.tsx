import { useEffect } from 'react';
import { api } from '../api/client';
import { useAuthStore } from '../store/auth';

export default function AuthInit({ children }: { children: React.ReactNode }) {
  const { token, setUser, logout, isGuest } = useAuthStore();

  useEffect(() => {
    if (token) {
      api.whoami().then((u) => {
        setUser({ username: u.username, role: u.role, token });
      }).catch(() => logout());
    } else if (!isGuest) {
      api.loginAsGuest().then(() => {
        useAuthStore.getState().loginGuest();
      }).catch(() => {});
    }
  }, []);

  return <>{children}</>;
}
