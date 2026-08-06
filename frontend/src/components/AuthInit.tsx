import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useAuthStore } from '../store/auth';
import LoadingSplash from './LoadingSplash';

export default function AuthInit({ children }: { children: React.ReactNode }) {
  const { csrfToken, setUser, login, loginGuest, logout } = useAuthStore();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    api.whoami().then((u) => {
      if (u.role === 'guest') {
        // No valid session cookie — try guest if server allows it
        api.loginAsGuest().then((g) => {
          loginGuest(g.csrf_token);
          setReady(true);
        }).catch(() => {
          // Guest disabled — stay logged out
          setReady(true);
        });
      } else {
        login(u.username, u.role, u.csrf_token || '', u.token, u.password_change_required);
        setReady(true);
      }
    }).catch(() => {
      // Network error or server unreachable
      setReady(true);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!ready) return <div className="h-screen"><LoadingSplash label="Starting reqmesh..." /></div>;

  return <>{children}</>;
}
