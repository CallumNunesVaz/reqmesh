import { useId, useState } from 'react';
import { X, User, Lock, Eye, EyeOff, LogIn, UserPlus } from 'lucide-react';
import { api } from '../api/client';
import { useAuthStore } from '../store/auth';
import Modal from './Modal';

interface LoginModalProps {
  open: boolean;
  onClose: () => void;
}

export default function LoginModal({ open, onClose }: LoginModalProps) {
  const { login, loginGuest } = useAuthStore();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const usernameId = useId();
  const passwordId = useId();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      let result;
      if (mode === 'login') {
        result = await api.login(username, password);
      } else {
        result = await api.register(username, password);
      }
      login(result.username, result.role, result.csrf_token, undefined, result.password_change_required);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  const handleGuest = async () => {
    try {
      const result = await api.loginAsGuest();
      loginGuest(result.csrf_token);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Guest access is not available');
    }
  };

  return (
    <Modal open={open} onClose={onClose} panelClassName="w-full max-w-sm p-6">
      <button onClick={onClose} className="absolute right-4 top-4 text-muted-foreground hover:text-foreground">
        <X size={18} />
      </button>

      <img src="/reqmesh-logo.svg" alt="reqmesh" className="w-32 mx-auto mb-4" />

      <h2 className="text-lg font-bold text-foreground mb-6">
        {mode === 'login' ? 'Sign In' : 'Create Account'}
      </h2>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="label" htmlFor={usernameId}>Username</label>
                <div className="relative">
                  <User size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <input id={usernameId} className="input pl-9" placeholder="username" value={username} onChange={e => setUsername(e.target.value)} required minLength={3} />
                </div>
              </div>
              <div>
                <label className="label" htmlFor={passwordId}>Password</label>
                <div className="relative">
                  <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <input id={passwordId} type={showPw ? 'text' : 'password'} className="input pl-9 pr-9" placeholder="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={mode === 'register' ? 12 : 1} />
                  <button type="button" onClick={() => setShowPw(!showPw)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                    {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>

              {error && <p className="text-xs text-destructive">{error}</p>}

              <button type="submit" disabled={loading} className="btn-primary w-full justify-center">
                {loading ? (
                  <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                ) : mode === 'login' ? (
                  <><LogIn size={14} /> Sign In</>
                ) : (
                  <><UserPlus size={14} /> Create Account</>
                )}
              </button>
            </form>

            <div className="mt-4 pt-4 border-t space-y-2">
              <button onClick={handleGuest} className="btn-secondary w-full justify-center text-xs">
                Continue as Guest
              </button>
              <button
                onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }}
                className="w-full text-center text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                {mode === 'login' ? "Don't have an account? Register" : 'Already have an account? Sign in'}
              </button>
            </div>
    </Modal>
  );
}
