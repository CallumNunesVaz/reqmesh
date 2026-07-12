import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { FolderOpen, Plus, Trash2, WifiOff, RotateCw } from 'lucide-react';
import { api, type Project } from '../api/client';
import { useStore } from '../store';
import { useAuthStore } from '../store/auth';

export default function ProjectsPage() {
  const navigate = useNavigate();
  const { projects, setProjects } = useStore();
  const editable = useAuthStore((s) => s.editMode && s.user !== null && s.user.role !== 'viewer');
  const [showCreate, setShowCreate] = useState(false);
  const [newId, setNewId] = useState('');
  const [newName, setNewName] = useState('');
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadProjects = () => {
    setLoadError(null);
    api.listProjects().then(setProjects).catch((err) => {
      console.error(err);
      setLoadError(err.message || 'Failed to load projects');
    });
  };

  useEffect(loadProjects, [setProjects]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newId.trim() || !editable) return;
    try {
      const project = await api.createProject({ id: newId.trim(), name: newName.trim() || newId.trim() });
      setProjects([...projects, project]);
      setShowCreate(false);
      setNewId('');
      setNewName('');
      navigate(`/project/${project.id}`);
    } catch {
      // silently no-op when permissions insufficient
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm(`Delete project "${id}" and all its data?`)) return;
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
        {editable && (
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
            <label className="label">Project ID</label>
            <input
              className="input"
              placeholder="my-aircraft-system"
              value={newId}
              onChange={(e) => setNewId(e.target.value)}
              autoFocus
            />
          </div>
          <div className="flex-1">
            <label className="label">Display Name (optional)</label>
            <input
              className="input"
              placeholder="My Aircraft System"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
          </div>
          <button type="submit" className="btn-primary">Create</button>
          <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary">Cancel</button>
        </motion.form>
      )}

      {loadError ? (
        <div className="card p-12 text-center">
          <WifiOff size={32} className="mx-auto mb-4 text-destructive" />
          <p className="text-foreground font-medium">Can't reach the backend</p>
          <p className="text-sm text-muted-foreground mt-1">
            Is the API running on port 8000? ({loadError})
          </p>
          <button onClick={loadProjects} className="btn-secondary mt-4 inline-flex items-center gap-2">
            <RotateCw size={14} />
            Retry
          </button>
        </div>
      ) : projects.length === 0 ? (
        <div className="card p-12 text-center">
          <img src="/reqmesh-logo.svg" alt="reqmesh" className="w-48 mx-auto mb-6 opacity-80" />
          <p className="text-foreground font-medium">No projects yet</p>
          <p className="text-sm text-muted-foreground mt-1">Create a new project to get started.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
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
                  className="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all"
                >
                  <Trash2 size={14} />
                </button>
                )}
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
