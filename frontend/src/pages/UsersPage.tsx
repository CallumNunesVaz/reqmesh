import { useEffect, useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Users, Plus, Trash2, ShieldCheck, User as UserIcon, KeyRound, X, Loader, Search, Filter, Pencil, Check, Clock, Ban, CircleCheck, Unlock, LogOut, UserPlus, Download, Upload, Copy, Lock } from 'lucide-react';
import { api, type ManagedUser } from '../api/client';
import { useAuthStore } from '../store/auth';

const ROLE_LABELS: Record<string, string> = { admin: 'Administrator', editor: 'Standard', viewer: 'Viewer' };
const ROLE_BADGE: Record<string, string> = {
  admin: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  editor: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  viewer: 'bg-muted text-muted-foreground border-border',
};

/** Compact account-status badge (disabled / locked / invited / active). */
function StatusBadge({ u }: { u: ManagedUser }) {
  if (u.disabled) return <span className="badge border text-[10px] bg-red-500/15 text-red-400 border-red-500/30 gap-1"><Ban size={9} /> Disabled</span>;
  if (u.locked) return <span className="badge border text-[10px] bg-amber-500/15 text-amber-400 border-amber-500/30 gap-1"><Lock size={9} /> Locked</span>;
  if (u.invited) return <span className="badge border text-[10px] bg-blue-500/15 text-blue-400 border-blue-500/30 gap-1"><UserPlus size={9} /> Invited</span>;
  return <span className="badge border text-[10px] bg-emerald-500/10 text-emerald-400 border-emerald-500/30">Active</span>;
}

export default function UsersPage() {
  const currentUser = useAuthStore((s) => s.user);
  const isAdmin = currentUser?.role === 'admin';
  const username = currentUser?.username ?? '';
  const isAuthenticated = username !== '' && username !== 'guest';

  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [sortBy, setSortBy] = useState<'username' | 'full_name' | 'role' | 'last_active' | 'joined'>('username');
  const [sortAsc, setSortAsc] = useState(true);

  // ── Profile editing (self-service, available to all authenticated users) ──
  const [editingSelf, setEditingSelf] = useState(false);
  const [selfForm, setSelfForm] = useState({ full_name: '', email: '', password: '' });
  const [savingSelf, setSavingSelf] = useState(false);

  // ── Admin: create new user ──────────────────────────────────────────────
  const [showCreate, setShowCreate] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState('editor');
  const [newFullName, setNewFullName] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [creating, setCreating] = useState(false);

  // ── Admin: password reset ───────────────────────────────────────────────
  const [resetFor, setResetFor] = useState<string | null>(null);
  const [resetPassword, setResetPassword] = useState('');
  const [resetting, setResetting] = useState(false);

  // ── Admin: inline editing ───────────────────────────────────────────────
  const [editingRow, setEditingRow] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ full_name: '', email: '' });

  // ── Admin: status filter, bulk selection, invite, CSV ────────────────────
  const [statusFilter, setStatusFilter] = useState('all');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showInvite, setShowInvite] = useState(false);
  const [invite, setInvite] = useState({ username: '', email: '', full_name: '', role: 'editor' });
  const [inviting, setInviting] = useState(false);
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const [importText, setImportText] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<{ created: string[]; skipped: string[]; invites: { username: string; invite_link: string }[] } | null>(null);

  const load = () => {
    setLoadError(null);
    api.listUsers().then((u) => {
      setUsers(u);
      const me = u.find((x) => x.username === username);
      if (me) setSelfForm({ full_name: me.full_name || '', email: me.email || '', password: '' });
    }).catch((err) => setLoadError(err.message || 'Failed to load users'));
  };

  useEffect(() => { if (isAdmin || isAuthenticated) load(); }, [isAdmin, isAuthenticated]);

  const toggleSort = (col: typeof sortBy) => {
    if (sortBy === col) setSortAsc(!sortAsc);
    else { setSortBy(col); setSortAsc(true); }
  };

  const filtered = useMemo(() => {
    let result = [...users];
    const q = search.toLowerCase();
    if (q) result = result.filter((u) =>
      u.username.toLowerCase().includes(q) || (u.full_name || '').toLowerCase().includes(q) || (u.email || '').toLowerCase().includes(q));
    if (roleFilter !== 'all') result = result.filter((u) => u.role === roleFilter);
    if (statusFilter !== 'all') result = result.filter((u) =>
      statusFilter === 'disabled' ? u.disabled
        : statusFilter === 'locked' ? u.locked
        : statusFilter === 'invited' ? u.invited
        : !u.disabled && !u.locked && !u.invited);
    result.sort((a, b) => {
      const av = (a[sortBy] || '').toString().toLowerCase();
      const bv = (b[sortBy] || '').toString().toLowerCase();
      return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
    });
    return result;
  }, [users, search, roleFilter, statusFilter, sortBy, sortAsc]);

  const allSelected = filtered.length > 0 && filtered.every((u) => selected.has(u.username));
  const toggleSelect = (uname: string) => setSelected((s) => {
    const n = new Set(s); n.has(uname) ? n.delete(uname) : n.add(uname); return n;
  });
  const toggleSelectAll = () => setSelected(allSelected ? new Set() : new Set(filtered.map((u) => u.username)));

  // ── Actions ─────────────────────────────────────────────────────────────

  const saveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSavingSelf(true);
    try {
      await api.updateProfile({ full_name: selfForm.full_name || undefined, email: selfForm.email || undefined, password: selfForm.password || undefined });
      setEditingSelf(false);
      setSelfForm((f) => ({ ...f, password: '' }));
      load();
    } catch (err: any) { setError(err.message); }
    finally { setSavingSelf(false); }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(''); setCreating(true);
    try {
      await api.createUser({ username: newUsername.trim(), password: newPassword, role: newRole, full_name: newFullName.trim(), email: newEmail.trim() });
      setShowCreate(false);
      setNewUsername(''); setNewPassword(''); setNewRole('editor'); setNewFullName(''); setNewEmail('');
      load();
    } catch (err: any) { setError(err.message); }
    finally { setCreating(false); }
  };

  const handleRoleChange = async (uname: string, role: string) => {
    setError('');
    try { await api.updateUser(uname, { role }); load(); }
    catch (err: any) { setError(err.message); }
  };

  const handleDelete = async (uname: string) => {
    if (!confirm(`Delete user "${uname}"? This cannot be undone.`)) return;
    setError('');
    try { await api.deleteUser(uname); load(); }
    catch (err: any) { setError(err.message); }
  };

  const handleDisable = async (uname: string, disabled: boolean) => {
    setError('');
    try { await api.setUserDisabled(uname, disabled); load(); }
    catch (err: any) { setError(err.message); }
  };
  const handleUnlock = async (uname: string) => {
    setError('');
    try { await api.unlockUser(uname); load(); }
    catch (err: any) { setError(err.message); }
  };
  const handleForceLogout = async (uname: string) => {
    if (!confirm(`Sign ${uname} out of all sessions?`)) return;
    setError('');
    try { await api.forceLogout(uname); }
    catch (err: any) { setError(err.message); }
  };

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(''); setInviting(true); setInviteLink(null);
    try {
      const res = await api.inviteUser({ username: invite.username.trim(), email: invite.email.trim(), role: invite.role, full_name: invite.full_name.trim() });
      if (res.invite_link) setInviteLink(res.invite_link);
      else { setShowInvite(false); }
      setInvite({ username: '', email: '', full_name: '', role: 'editor' });
      load();
    } catch (err: any) { setError(err.message); }
    finally { setInviting(false); }
  };

  const handleBulk = async (action: 'disable' | 'enable' | 'delete' | 'set_role', role?: string) => {
    if (selected.size === 0) return;
    if (action === 'delete' && !confirm(`Delete ${selected.size} user(s)? This cannot be undone.`)) return;
    setError('');
    try {
      const res = await api.bulkUsers([...selected], action, role);
      if (res.skipped.length) setError(`Skipped (protected): ${res.skipped.join(', ')}`);
      setSelected(new Set());
      load();
    } catch (err: any) { setError(err.message); }
  };

  const handleImport = async () => {
    if (!importText?.trim()) return;
    setError('');
    try {
      const res = await api.importUsersCsv(importText);
      setImportResult(res);
      load();
    } catch (err: any) { setError(err.message); }
  };

  const exportCsv = async () => {
    try {
      const token = localStorage.getItem('rt-token');
      const res = await fetch(api.exportUsersCsvUrl, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'reqmesh-users.csv'; a.click();
      URL.revokeObjectURL(url);
    } catch (err: any) { setError(err.message); }
  };

  const signOutEverywhere = async () => {
    if (!confirm('Sign out of all your sessions on every device?')) return;
    try { await api.logoutEverywhere(); }
    catch (err: any) { setError(err.message); }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resetFor) return;
    setError(''); setResetting(true);
    try { await api.updateUser(resetFor, { password: resetPassword }); setResetFor(null); setResetPassword(''); }
    catch (err: any) { setError(err.message); }
    finally { setResetting(false); }
  };

  const startEditRow = (u: ManagedUser) => {
    setEditingRow(u.username);
    setEditForm({ full_name: u.full_name || '', email: u.email || '' });
  };
  const saveEditRow = async (uname: string) => {
    setError('');
    try { await api.updateUser(uname, editForm); setEditingRow(null); load(); }
    catch (err: any) { setError(err.message); }
  };

  const fmtDate = (d: string) => d ? d.slice(0, 10) : '—';
  const fmtLast = (d: string) => d ? new Date(d).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'never';

  const SortHead = ({ col, label }: { col: typeof sortBy; label: string }) => (
    <button onClick={() => toggleSort(col)} className={`text-[10px] font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground flex items-center gap-0.5 ${sortBy === col ? 'text-foreground' : ''}`}>
      {label}{sortBy === col ? (sortAsc ? ' ↑' : ' ↓') : ''}
    </button>
  );

  return (
    <div className="max-w-6xl mx-auto p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <Users size={22} /> Users
          </h1>
          <p className="text-sm text-muted-foreground mt-1">Manage accounts, roles, and profiles</p>
        </div>
        {isAdmin && (
          <div className="flex items-center gap-2">
            <button onClick={exportCsv} className="btn-secondary text-xs" title="Export users as CSV"><Download size={14} /> Export</button>
            <button onClick={() => { setImportText(''); setImportResult(null); setError(''); }} className="btn-secondary text-xs" title="Import users from CSV"><Upload size={14} /> Import</button>
            <button onClick={() => { setShowInvite(true); setInviteLink(null); setError(''); }} className="btn-secondary text-xs"><UserPlus size={14} /> Invite</button>
            <button onClick={() => { setShowCreate((s) => !s); setError(''); }} className="btn-primary">
              <Plus size={16} /> New User
            </button>
          </div>
        )}
      </div>

      {/* ── Self-service profile (visible to everyone) ───────────────────── */}
      {isAuthenticated && (
        <div className="card p-4 mb-6">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold text-card-foreground flex items-center gap-2"><UserIcon size={14} /> Your Profile</h2>
            {!editingSelf && (
              <div className="flex items-center gap-2">
                <button onClick={signOutEverywhere} className="btn-ghost text-xs text-muted-foreground" title="Invalidate all your sessions on every device">
                  <LogOut size={13} /> Sign out everywhere
                </button>
                <button onClick={() => { setEditingSelf(true); setError(''); }} className="btn-secondary text-xs">
                  <Pencil size={13} /> Edit
                </button>
              </div>
            )}
          </div>

          {editingSelf ? (
            <form onSubmit={saveProfile} className="flex flex-wrap items-end gap-3">
              <div>
                <label className="label text-[10px]">Full name</label>
                <input className="input text-sm" value={selfForm.full_name} onChange={(e) => setSelfForm({ ...selfForm, full_name: e.target.value })} placeholder="Your name" autoFocus />
              </div>
              <div>
                <label className="label text-[10px]">Email</label>
                <input className="input text-sm" value={selfForm.email} onChange={(e) => setSelfForm({ ...selfForm, email: e.target.value })} placeholder="you@example.com" />
              </div>
              <div>
                <label className="label text-[10px]">New password (optional)</label>
                <input className="input text-sm" type="password" value={selfForm.password} onChange={(e) => setSelfForm({ ...selfForm, password: e.target.value })} placeholder="Leave blank to keep" />
              </div>
              <button type="submit" className="btn-primary" disabled={savingSelf}>
                {savingSelf ? <><Loader size={14} className="animate-spin" /> Saving</> : <><Check size={14} /> Save</>}
              </button>
              <button type="button" onClick={() => { setEditingSelf(false); setSelfForm((f) => ({ ...f, password: '' })); }} className="btn-secondary">Cancel</button>
            </form>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div><span className="text-muted-foreground">Username</span><div className="font-mono text-card-foreground">{username}</div></div>
              <div><span className="text-muted-foreground">Name</span><div className="text-card-foreground">{selfForm.full_name || <span className="italic text-muted-foreground/50">not set</span>}</div></div>
              <div><span className="text-muted-foreground">Email</span><div className="text-card-foreground">{selfForm.email || <span className="italic text-muted-foreground/50">not set</span>}</div></div>
              <div><span className="text-muted-foreground">Role</span><div><span className={`badge border text-[10px] ${ROLE_BADGE[currentUser?.role || 'viewer']}`}>{ROLE_LABELS[currentUser?.role || 'viewer']}</span></div></div>
            </div>
          )}
        </div>
      )}

      {/* ── Admin section ─────────────────────────────────────────────────── */}
      {!isAdmin && (
        <div className="text-center text-muted-foreground text-sm py-4">User management is available to administrators.</div>
      )}

      {isAdmin && (
        <>
          {/* Create form */}
          <AnimatePresence>
            {showCreate && (
              <motion.form
                initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
                onSubmit={handleCreate}
                className="card p-4 mb-6 flex items-end gap-3 flex-wrap"
              >
                <div className="min-w-[140px]">
                  <label className="label text-[10px]">Username *</label>
                  <input className="input text-sm" placeholder="jdoe" value={newUsername} onChange={(e) => setNewUsername(e.target.value)} autoFocus />
                </div>
                <div className="min-w-[140px]">
                  <label className="label text-[10px]">Full name</label>
                  <input className="input text-sm" placeholder="Jane Doe" value={newFullName} onChange={(e) => setNewFullName(e.target.value)} />
                </div>
                <div className="min-w-[180px]">
                  <label className="label text-[10px]">Email</label>
                  <input className="input text-sm" placeholder="jane@example.com" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} />
                </div>
                <div className="min-w-[140px]">
                  <label className="label text-[10px]">Password *</label>
                  <input className="input text-sm" type="password" placeholder="min 12 chars" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
                </div>
                <div className="min-w-[130px]">
                  <label className="label text-[10px]">Role</label>
                  <select className="input text-sm" value={newRole} onChange={(e) => setNewRole(e.target.value)}>
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

          {/* Filters */}
          <div className="flex items-center gap-3 mb-4">
            <div className="relative flex-1 max-w-sm">
              <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input className="input text-sm pl-7" placeholder="Search by username, name, or email…" value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
            <div className="flex items-center gap-1.5">
              <Filter size={12} className="text-muted-foreground" />
              <select className="input text-xs !w-auto !py-1.5" value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
                <option value="all">All roles</option>
                <option value="admin">Administrator</option>
                <option value="editor">Standard</option>
                <option value="viewer">Viewer</option>
              </select>
              <select className="input text-xs !w-auto !py-1.5" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="all">All statuses</option>
                <option value="active">Active</option>
                <option value="disabled">Disabled</option>
                <option value="locked">Locked</option>
                <option value="invited">Invited</option>
              </select>
            </div>
            <span className="text-[10px] text-muted-foreground">{filtered.length} of {users.length} users</span>
          </div>

          {/* Bulk action bar */}
          <AnimatePresence>
            {selected.size > 0 && (
              <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
                className="flex items-center gap-2 mb-4 px-3 py-2 rounded-lg border bg-primary/5 border-primary/30 text-xs">
                <span className="font-medium">{selected.size} selected</span>
                <div className="flex-1" />
                <button onClick={() => handleBulk('disable')} className="btn-ghost text-xs"><Ban size={13} /> Disable</button>
                <button onClick={() => handleBulk('enable')} className="btn-ghost text-xs"><CircleCheck size={13} /> Enable</button>
                <select className="input text-xs !w-auto !py-1" defaultValue="" onChange={(e) => { if (e.target.value) { handleBulk('set_role', e.target.value); e.target.value = ''; } }}>
                  <option value="">Set role…</option>
                  <option value="editor">Standard</option>
                  <option value="admin">Administrator</option>
                  <option value="viewer">Viewer</option>
                </select>
                <button onClick={() => handleBulk('delete')} className="btn-ghost text-xs text-destructive"><Trash2 size={13} /> Delete</button>
                <button onClick={() => setSelected(new Set())} className="btn-ghost text-xs"><X size={13} /></button>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Table */}
          {loadError ? (
            <div className="card p-12 text-center">
              <p className="text-foreground font-medium">Couldn't load users</p>
              <p className="text-sm text-muted-foreground mt-1">{loadError}</p>
            </div>
          ) : (
            <div className="card overflow-hidden">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b bg-muted/30">
                    <th className="px-3 py-2.5 w-0">
                      <input type="checkbox" checked={allSelected} onChange={toggleSelectAll} className="w-3.5 h-3.5 rounded border-muted-foreground/30" aria-label="Select all" />
                    </th>
                    <th className="px-4 py-2.5"><SortHead col="username" label="Username" /></th>
                    <th className="px-4 py-2.5"><SortHead col="full_name" label="Name" /></th>
                    <th className="px-4 py-2.5 hidden md:table-cell"><span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Email</span></th>
                    <th className="px-4 py-2.5"><SortHead col="role" label="Role" /></th>
                    <th className="px-4 py-2.5"><span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Status</span></th>
                    <th className="px-4 py-2.5 hidden lg:table-cell"><SortHead col="last_active" label="Last active" /></th>
                    <th className="px-4 py-2.5 hidden lg:table-cell"><SortHead col="joined" label="Joined" /></th>
                    <th className="px-4 py-2.5 w-0" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filtered.map((u) => {
                    const isSelf = u.username === username;
                    const isEditing = editingRow === u.username;
                    return (
                      <tr key={u.username} className={`hover:bg-accent/30 transition-colors ${isSelf ? 'bg-primary/[0.02]' : ''} ${u.disabled ? 'opacity-60' : ''}`}>
                        <td className="px-3 py-2.5">
                          <input type="checkbox" checked={selected.has(u.username)} onChange={() => toggleSelect(u.username)} className="w-3.5 h-3.5 rounded border-muted-foreground/30" aria-label={`Select ${u.username}`} />
                        </td>
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-2">
                            <div className={`w-7 h-7 rounded-md flex items-center justify-center shrink-0 ${u.role === 'admin' ? 'bg-amber-500/10 text-amber-400' : 'bg-muted text-muted-foreground'}`}>
                              {u.role === 'admin' ? <ShieldCheck size={14} /> : <UserIcon size={14} />}
                            </div>
                            <div>
                              <span className="font-mono text-xs text-card-foreground font-medium">{u.username}</span>
                              {isSelf && <span className="text-[9px] text-muted-foreground ml-1">(you)</span>}
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-2.5 text-xs text-card-foreground">
                          {isEditing ? (
                            <input className="input text-xs !py-1 w-full" value={editForm.full_name} onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })} autoFocus />
                          ) : (u.full_name || <span className="text-muted-foreground/40 italic">—</span>)}
                        </td>
                        <td className="px-4 py-2.5 text-xs text-card-foreground hidden md:table-cell">
                          {isEditing ? (
                            <input className="input text-xs !py-1 w-full" value={editForm.email} onChange={(e) => setEditForm({ ...editForm, email: e.target.value })} />
                          ) : (u.email || <span className="text-muted-foreground/40 italic">—</span>)}
                          {u.email_verified && u.email && <span className="text-[9px] text-emerald-400 ml-1">✓</span>}
                        </td>
                        <td className="px-4 py-2.5">
                          <select
                            className="input !w-auto !py-1 text-[11px]"
                            value={u.role}
                            onChange={(e) => handleRoleChange(u.username, e.target.value)}
                            disabled={isSelf && u.role === 'admin'}
                          >
                            <option value="editor">Standard</option>
                            <option value="admin">Administrator</option>
                            <option value="viewer">Viewer (read-only)</option>
                          </select>
                        </td>
                        <td className="px-4 py-2.5"><StatusBadge u={u} /></td>
                        <td className="px-4 py-2.5 text-[11px] text-muted-foreground hidden lg:table-cell">
                          {u.last_active ? <span className="flex items-center gap-1"><Clock size={10} />{fmtLast(u.last_active)}</span> : <span className="text-muted-foreground/40 italic">—</span>}
                        </td>
                        <td className="px-4 py-2.5 text-[11px] text-muted-foreground hidden lg:table-cell">{fmtDate(u.joined)}</td>
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-0.5">
                            {isEditing ? (
                              <>
                                <button onClick={() => saveEditRow(u.username)} className="p-1 rounded-md text-emerald-400 hover:bg-emerald-500/10" title="Save"><Check size={13} /></button>
                                <button onClick={() => setEditingRow(null)} className="p-1 rounded-md text-muted-foreground hover:text-foreground" title="Cancel"><X size={13} /></button>
                              </>
                            ) : (
                              <button onClick={() => startEditRow(u)} className="p-1 rounded-md text-muted-foreground hover:text-foreground" title="Edit name & email"><Pencil size={13} /></button>
                            )}
                            <button onClick={() => { setResetFor(u.username); setResetPassword(''); setError(''); }} className="p-1 rounded-md text-muted-foreground hover:text-foreground" title="Reset password"><KeyRound size={13} /></button>
                            {u.locked && (
                              <button onClick={() => handleUnlock(u.username)} className="p-1 rounded-md text-amber-400 hover:bg-amber-500/10" title="Unlock account"><Unlock size={13} /></button>
                            )}
                            <button onClick={() => handleDisable(u.username, !u.disabled)} disabled={isSelf} className="p-1 rounded-md text-muted-foreground hover:text-foreground disabled:opacity-30" title={isSelf ? "Can't disable yourself" : u.disabled ? 'Enable account' : 'Disable account'}>
                              {u.disabled ? <CircleCheck size={13} /> : <Ban size={13} />}
                            </button>
                            <button onClick={() => handleForceLogout(u.username)} className="p-1 rounded-md text-muted-foreground hover:text-foreground" title="Force sign-out (revoke sessions)"><LogOut size={13} /></button>
                            <button onClick={() => handleDelete(u.username)} disabled={isSelf} className="p-1 rounded-md text-muted-foreground hover:text-destructive disabled:opacity-30" title={isSelf ? "Can't delete yourself" : 'Delete'}><Trash2 size={13} /></button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  {filtered.length === 0 && (
                    <tr><td colSpan={9} className="px-4 py-8 text-center text-sm text-muted-foreground">No users match your filters.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Invite modal */}
      <AnimatePresence>
        {showInvite && (
          <div className="fixed inset-0 z-50 flex items-center justify-center">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 bg-background/80 backdrop-blur-sm" onClick={() => setShowInvite(false)} />
            <motion.form initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 10 }} onSubmit={handleInvite} className="relative bg-card border rounded-xl shadow-2xl w-full max-w-md p-6 mx-4">
              <button type="button" onClick={() => setShowInvite(false)} className="absolute right-4 top-4 text-muted-foreground hover:text-foreground"><X size={18} /></button>
              <h2 className="text-lg font-bold text-foreground mb-1 flex items-center gap-2"><UserPlus size={18} /> Invite a user</h2>
              <p className="text-xs text-muted-foreground mb-4">Creates an account and emails a set-password link (shown here if email isn't configured).</p>
              {inviteLink ? (
                <div className="space-y-3">
                  <p className="text-xs text-emerald-500 flex items-center gap-1"><Check size={13} /> Account created. Share this set-password link:</p>
                  <div className="flex gap-1">
                    <input readOnly className="input text-xs font-mono flex-1" value={inviteLink} onFocus={(e) => e.target.select()} />
                    <button type="button" onClick={() => navigator.clipboard?.writeText(inviteLink)} className="btn-secondary shrink-0 p-2" title="Copy"><Copy size={13} /></button>
                  </div>
                  <button type="button" onClick={() => { setShowInvite(false); setInviteLink(null); }} className="btn-primary w-full justify-center">Done</button>
                </div>
              ) : (
                <div className="space-y-3">
                  <div><label className="label text-[10px]">Username *</label><input className="input text-sm" value={invite.username} onChange={(e) => setInvite({ ...invite, username: e.target.value })} placeholder="jdoe" autoFocus /></div>
                  <div><label className="label text-[10px]">Email</label><input className="input text-sm" value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} placeholder="jane@example.com" /></div>
                  <div><label className="label text-[10px]">Full name</label><input className="input text-sm" value={invite.full_name} onChange={(e) => setInvite({ ...invite, full_name: e.target.value })} placeholder="Jane Doe" /></div>
                  <div><label className="label text-[10px]">Role</label>
                    <select className="input text-sm" value={invite.role} onChange={(e) => setInvite({ ...invite, role: e.target.value })}>
                      <option value="editor">Standard</option><option value="admin">Administrator</option><option value="viewer">Viewer</option>
                    </select>
                  </div>
                  <button type="submit" className="btn-primary w-full justify-center" disabled={inviting || !invite.username.trim()}>
                    {inviting ? <><Loader size={14} className="animate-spin" /> Inviting</> : 'Send invite'}
                  </button>
                </div>
              )}
            </motion.form>
          </div>
        )}
      </AnimatePresence>

      {/* CSV import modal */}
      <AnimatePresence>
        {importText !== null && (
          <div className="fixed inset-0 z-50 flex items-center justify-center">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 bg-background/80 backdrop-blur-sm" onClick={() => setImportText(null)} />
            <motion.div initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 10 }} className="relative bg-card border rounded-xl shadow-2xl w-full max-w-lg p-6 mx-4">
              <button type="button" onClick={() => setImportText(null)} className="absolute right-4 top-4 text-muted-foreground hover:text-foreground"><X size={18} /></button>
              <h2 className="text-lg font-bold text-foreground mb-1 flex items-center gap-2"><Upload size={18} /> Import users (CSV)</h2>
              <p className="text-xs text-muted-foreground mb-3">Columns: <code className="bg-muted px-1 rounded">username,full_name,email,role</code>. Each new user is invited to set a password.</p>
              {importResult ? (
                <div className="space-y-2 text-xs">
                  <p className="text-emerald-500">Created {importResult.created.length}: {importResult.created.join(', ') || '—'}</p>
                  {importResult.skipped.length > 0 && <p className="text-amber-500">Skipped: {importResult.skipped.join(', ')}</p>}
                  {importResult.invites.length > 0 && (
                    <div className="max-h-40 overflow-auto border rounded p-2 bg-muted/30 font-mono">
                      {importResult.invites.map((iv) => <div key={iv.username} className="truncate">{iv.username}: {iv.invite_link}</div>)}
                    </div>
                  )}
                  <button onClick={() => setImportText(null)} className="btn-primary w-full justify-center mt-2">Done</button>
                </div>
              ) : (
                <>
                  <textarea className="input font-mono text-xs h-40 resize-none w-full" placeholder={'username,full_name,email,role\njdoe,Jane Doe,jane@example.com,editor'} value={importText} onChange={(e) => setImportText(e.target.value)} autoFocus />
                  <div className="flex gap-2 mt-3">
                    <button onClick={handleImport} className="btn-primary flex-1 justify-center" disabled={!importText.trim()}>Import</button>
                    <button onClick={() => setImportText(null)} className="btn-secondary">Cancel</button>
                  </div>
                </>
              )}
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Reset password modal */}
      <AnimatePresence>
        {resetFor && (
          <div className="fixed inset-0 z-50 flex items-center justify-center">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 bg-background/80 backdrop-blur-sm" onClick={() => setResetFor(null)} />
            <motion.form initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 10 }} onSubmit={handleResetPassword} className="relative bg-card border rounded-xl shadow-2xl w-full max-w-sm p-6 mx-4">
              <button type="button" onClick={() => setResetFor(null)} className="absolute right-4 top-4 text-muted-foreground hover:text-foreground"><X size={18} /></button>
              <h2 className="text-lg font-bold text-foreground mb-1 flex items-center gap-2"><KeyRound size={18} /> Reset password</h2>
              <p className="text-xs text-muted-foreground mb-4">Set a new password for <b>{resetFor}</b></p>
              <input className="input mb-4" type="password" placeholder="New password (min 12 chars)" value={resetPassword} onChange={(e) => setResetPassword(e.target.value)} autoFocus />
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
