import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { FolderOpen, Plus, Trash2, WifiOff, LogIn } from 'lucide-react';
import { api } from '../api/client';
import { useStore } from '../store';
import { useAuthStore } from '../store/auth';
import { useToasts } from '../components/Toast';
import { useConfirm } from '../components/ConfirmDialog';
import EmptyState from '../components/EmptyState';

export default function ProjectsPage() {
  const navigate = useNavigate();
  const { projects, setProjects } = useStore();
  const editable = useAuthStore((s) => s.canEdit());
  // Creating a project is a maintainer/admin action gated on the server by
  // require_maintain_global — it does NOT require the per-project edit-mode
  // toggle (that governs editing entities *inside* a project). Keying the create
  // affordances on permission, not edit mode, is what makes them discoverable
  // without first flipping to EDITING (UX-6), while still hiding them from users
  // who cannot create a project at all.
  const canCreate = useAuthStore((s) => s.user !== null && (s.user.role === 'maintainer' || s.user.role === 'admin'));
  const { addToast } = useToasts();
  const showConfirm = useConfirm();
  const [showCreate, setShowCreate] = useState(false);
  const [newId, setNewId] = useState('');
  const [newName, setNewName] = useState('');
  const [loadError, setLoadError] = useState<string | null>(null);
  const [needsAuth, setNeedsAuth] = useState(false);
  // Re-running the fetch when the signed-in user changes is the whole point:
  // on a deployment with RT_REQUIRE_AUTH the first load 401s, and without this
  // the page kept its error state after a successful sign-in. The projects
  // only appeared after a manual browser reload, which reads as "login didn't
  // work" rather than "the list is stale".
  const username = useAuthStore((s) => s.user?.username ?? null);

  const loadProjects = () => {
    setLoadError(null);
    setNeedsAuth(false);
    api.listProjects().then(setProjects).catch((err) => {
      // 401 is not a connectivity problem, and telling someone to check
      // whether the API is running on port 8000 sends them to inspect a
      // healthy server. Say what actually happened.
      if (err?.status === 401 || /authentication required/i.test(err?.message || '')) {
        setNeedsAuth(true);
        return;
      }
      console.error(err);
      setLoadError(err.message || 'Failed to load projects');
    });
  };

  useEffect(loadProjects, [setProjects, username]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newId.trim() || !canCreate) return;
    try {
      const project = await api.createProject({ id: newId.trim(), name: newName.trim() || newId.trim() });
      setProjects([...projects, project]);
      setShowCreate(false);
      setNewId('');
      setNewName('');
      navigate(`/project/${project.id}`);
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Failed to create project');
    }
  };

  const handleDelete = async (id: string) => {
    const ok = await showConfirm(`Delete project "${id}" and all its data?`, 'Delete Project', { resultLabel: 'Delete', destructive: true });
    if (!ok) return;
    await api.deleteProject(id);
    setProjects(projects.filter((p) => p.id !== id));
  };

  return (
    <div className="max-w-4xl mx-auto p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Projects</h1>
          <p className="text-sm text-muted-foreground mt-1">Select or create a requirements project</p>
        </div>
        {canCreate && (
          <button onClick={() => setShowCreate(!showCreate)} className="btn-primary">
            <Plus size={16} />
            New Project
          </button>
        )}
      </div>

      {showCreate && (
        <motion.form
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          onSubmit={handleCreate}
          className="card p-4 mb-6 flex items-end gap-3"
        >
          <div className="flex-1">
            <label className="label">Project ID
              <input
                className="input"
                placeholder="my-aircraft-system"
                value={newId}
                onChange={(e) => setNewId(e.target.value)}
              />
            </label>
          </div>
          <div className="flex-1">
            <label className="label">Display Name (optional)
              <input
                className="input"
                placeholder="My Aircraft System"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
              />
            </label>
          </div>
          <button type="submit" className="btn-primary">Create</button>
          <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary">Cancel</button>
        </motion.form>
      )}

      {needsAuth ? (
        <EmptyState icon={LogIn} title="Sign in to see your projects" hint="This instance requires an account. Use the sign-in button in the header." />
      ) : loadError ? (
        <EmptyState
          icon={WifiOff}
          title="Can't reach the backend"
          hint={`Is the API running on port 8000? (${loadError})`}
          action={{ label: 'Retry', onClick: loadProjects }}
        />
      ) : projects.length === 0 ? (
        <EmptyState
          title="No projects yet"
          hint={canCreate ? 'Create your first project to start managing requirements.' : 'Ask an administrator to create one.'}
          action={canCreate ? { label: 'New Project', onClick: () => setShowCreate(true) } : undefined}
        />
      ) : (
        <div className="grid grid-cols-1 @2xl:grid-cols-2 @4xl:grid-cols-3 gap-4">
          {projects.map((project, i) => (
            <motion.div
              key={project.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="card p-5 hover:shadow-md transition-shadow cursor-pointer group"
              onClick={() => navigate(`/project/${project.id}`)}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-muted rounded-lg flex items-center justify-center group-hover:bg-accent transition-colors">
                    <FolderOpen size={20} className="text-muted-foreground" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="font-semibold text-sm truncate text-card-foreground">{project.name}</h3>
                    <p className="text-xs text-muted-foreground mt-0.5 font-mono">{project.id}</p>
                  </div>
                </div>
                {editable && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(project.id);
                  }}
                  className="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-[color,background-color,opacity]"
                  title="Delete"
                >
                  <Trash2 size={14} />
                </button>
                )}
              </div>
            </motion.div>
          ))}
          {canCreate && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: projects.length * 0.05 }}
              className="card p-5 border-dashed border-2 border-muted-foreground/25 hover:border-primary/40 hover:shadow-md transition-[border-color,box-shadow] cursor-pointer group flex items-center justify-center min-h-[140px]"
              onClick={() => setShowCreate(true)}
            >
              <div className="text-center">
                <div className="w-10 h-10 mx-auto bg-muted rounded-lg flex items-center justify-center group-hover:bg-primary/10 transition-colors">
                  <Plus size={20} className="text-muted-foreground group-hover:text-primary" />
                </div>
                <p className="text-sm text-muted-foreground mt-2 group-hover:text-primary font-medium">New Project</p>
              </div>
            </motion.div>
          )}
        </div>
      )}
    </div>
  );
}
