import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Users, Plus, Trash2, ShieldCheck, User as UserIcon, KeyRound, X, Loader } from 'lucide-react';
import { api, type ManagedUser } from '../api/client';
import { useAuthStore } from '../store/auth';

const ROLE_LABELS: Record<string, string> = { admin: 'Administrator', editor: 'Standard', viewer: 'Viewer' };
const ROLE_BADGE: Record<string, string> = {
  admin: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  editor: 'bg-cs-blue/15 text-cs-blue border-cs-blue/30',
  viewer: 'bg-muted text-muted-foreground border-border',
};

export default function UsersPage() {
  const currentUser = useAuthStore((s) => s.user);
  const isAdmin = currentUser?.role === 'admin';

  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState('');

  const [showCreate, setShowCreate] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState('editor');
  const [creating, setCreating] = useState(false);

  const [resetFor, setResetFor] = useState<string | null>(null);
  const [resetPassword, setResetPassword] = useState('');
  const [resetting, setResetting] = useState(false);

  const load = () => {
    setLoadError(null);
    api.listUsers().then(setUsers).catch((err) => setLoadError(err.message || 'Failed to load users'));
  };

  useEffect(() => { if (isAdmin) load(); }, [isAdmin]);

  if (!isAdmin) {
    return (
      <div className="max-w-4xl mx-auto p-8">
        <div className="card p-12 text-center">
          <ShieldCheck size={32} className="mx-auto mb-4 text-muted-foreground" />
          <p className="text-foreground font-medium">Administrators only</p>
          <p className="text-sm text-muted-foreground mt-1">
            You need an administrator account to manage users.
          </p>
        </div>
      </div>
    );
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setCreating(true);
    try {
      await api.createUser({ username: newUsername.trim(), password: newPassword, role: newRole });
      setShowCreate(false);
      setNewUsername(''); setNewPassword(''); setNewRole('editor');
      load();
    } catch (err: any) {
      setError(err.message || 'Failed to create user');
    } finally {
      setCreating(false);
    }
  };

  const handleRoleChange = async (username: string, role: string) => {
    setError('');
    try {
      await api.updateUser(username, { role });
      load();
    } catch (err: any) {
      setError(err.message || 'Failed to change role');
    }
  };

  const handleDelete = async (username: string) => {
    if (!confirm(`Delete user "${username}"? This cannot be undone.`)) return;
    setError('');
    try {
      await api.deleteUser(username);
      load();
    } catch (err: any) {
      setError(err.message || 'Failed to delete user');
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resetFor) return;
    setError('');
    setResetting(true);
    try {
      await api.updateUser(resetFor, { password: resetPassword });
      setResetFor(null); setResetPassword('');
    } catch (err: any) {
      setError(err.message || 'Failed to reset password');
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <Users size={22} /> Users
          </h1>
          <p className="text-sm text-muted-foreground mt-1">Manage accounts and administrator access</p>
        </div>
        <button onClick={() => { setShowCreate((s) => !s); setError(''); }} className="btn-primary">
          <Plus size={16} /> New User
        </button>
      </div>

      <AnimatePresence>
        {showCreate && (
          <motion.form
            initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
            onSubmit={handleCreate}
            className="card p-4 mb-6 flex items-end gap-3 flex-wrap"
          >
            <div className="flex-1 min-w-[160px]">
              <label className="label">Username</label>
              <input className="input" placeholder="jdoe" value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)} autoFocus />
            </div>
            <div className="flex-1 min-w-[160px]">
              <label className="label">Password</label>
              <input className="input" type="password" placeholder="min 8 characters" value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)} />
            </div>
            <div className="min-w-[150px]">
              <label className="label">Role</label>
              <select className="input" value={newRole} onChange={(e) => setNewRole(e.target.value)}>
                <option value="editor">Standard</option>
                <option value="admin">Administrator</option>
              </select>
            </div>
            <button type="submit" className="btn-primary" disabled={creating}>
              {creating ? <><Loader size={14} className="animate-spin" /> Creating</> : 'Create'}
            </button>
            <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary">Cancel</button>
          </motion.form>
        )}
      </AnimatePresence>

      {error && <div className="mb-4 text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</div>}

      {loadError ? (
        <div className="card p-12 text-center">
          <p className="text-foreground font-medium">Couldn't load users</p>
          <p className="text-sm text-muted-foreground mt-1">{loadError}</p>
        </div>
      ) : (
        <div className="card divide-y divide-border overflow-hidden">
          {users.map((u) => {
            const isSelf = u.username === currentUser?.username;
            return (
              <div key={u.username} className="flex items-center gap-3 px-4 py-3">
                <div className="w-9 h-9 rounded-lg bg-muted flex items-center justify-center shrink-0">
                  {u.role === 'admin' ? <ShieldCheck size={17} className="text-amber-400" /> : <UserIcon size={17} className="text-muted-foreground" />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="font-medium text-sm text-card-foreground truncate">
                    {u.username}
                    {isSelf && <span className="ml-2 text-[10px] text-muted-foreground">(you)</span>}
                  </div>
                  {u.created && (
                    <div className="text-xs text-muted-foreground">Created {u.created.slice(0, 10)}</div>
                  )}
                </div>

                <span className={`hidden sm:inline-flex px-2 py-0.5 rounded-full text-[10px] font-medium border ${ROLE_BADGE[u.role] || ROLE_BADGE.viewer}`}>
                  {ROLE_LABELS[u.role] || u.role}
                </span>

                <select
                  className="input !w-auto !py-1 text-xs"
                  value={u.role === 'admin' ? 'admin' : 'editor'}
                  onChange={(e) => handleRoleChange(u.username, e.target.value)}
                  title="Change role"
                >
                  <option value="editor">Standard</option>
                  <option value="admin">Administrator</option>
                </select>

                <button
                  onClick={() => { setResetFor(u.username); setResetPassword(''); setError(''); }}
                  className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                  title="Reset password"
                >
                  <KeyRound size={15} />
                </button>

                <button
                  onClick={() => handleDelete(u.username)}
                  disabled={isSelf}
                  className="p-1.5 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-muted-foreground"
                  title={isSelf ? "You can't delete your own account" : 'Delete user'}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* Reset password modal */}
      <AnimatePresence>
        {resetFor && (
          <div className="fixed inset-0 z-50 flex items-center justify-center">
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="absolute inset-0 bg-background/80 backdrop-blur-sm" onClick={() => setResetFor(null)}
            />
            <motion.form
              initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 10 }}
              onSubmit={handleResetPassword}
              className="relative bg-card border rounded-xl shadow-2xl w-full max-w-sm p-6 mx-4"
            >
              <button type="button" onClick={() => setResetFor(null)} className="absolute right-4 top-4 text-muted-foreground hover:text-foreground">
                <X size={18} />
              </button>
              <h2 className="text-lg font-bold text-foreground mb-1 flex items-center gap-2">
                <KeyRound size={18} /> Reset password
              </h2>
              <p className="text-xs text-muted-foreground mb-4">Set a new password for <b>{resetFor}</b></p>
              <input
                className="input mb-4" type="password" placeholder="New password (min 8 characters)"
                value={resetPassword} onChange={(e) => setResetPassword(e.target.value)} autoFocus
              />
              <div className="flex gap-2">
                <button type="submit" className="btn-primary flex-1 justify-center" disabled={resetting}>
                  {resetting ? <><Loader size={14} className="animate-spin" /> Saving</> : 'Set password'}
                </button>
                <button type="button" onClick={() => setResetFor(null)} className="btn-secondary">Cancel</button>
              </div>
            </motion.form>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
