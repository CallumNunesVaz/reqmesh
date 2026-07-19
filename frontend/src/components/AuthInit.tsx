import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useAuthStore } from '../store/auth';
import LoadingSplash from './LoadingSplash';

export default function AuthInit({ children }: { children: React.ReactNode }) {
  const { token, setUser, logout, isGuest } = useAuthStore();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (token) {
      api.whoami().then((u) => {
        setUser({ username: u.username, role: u.role, token });
        setReady(true);
      }).catch(() => { logout(); setReady(true); });
    } else if (!isGuest) {
      api.loginAsGuest().then(() => {
        useAuthStore.getState().loginGuest();
        setReady(true);
      }).catch(() => setReady(true));
    } else {
      setReady(true);
    }
  }, []);

  if (!ready) return <div className="h-screen"><LoadingSplash label="Starting reqmesh…" /></div>;

  return <>{children}</>;
}
