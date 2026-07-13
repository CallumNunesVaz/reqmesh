import { Outlet, Link, useParams } from 'react-router-dom';
import { PanelRight, PanelRightClose, LogIn, LogOut, User, Pencil, Eye, FileDown, FileUp, Users } from 'lucide-react';
import { useState, useEffect, useCallback, createContext, useContext, useRef } from 'react';
import { ThemeToggle } from './ThemeToggle';
import RequirementNav from './RequirementNav';
import GraphPane from './GraphPane';
import LoginModal from './LoginModal';
import ExportDialog from './ExportDialog';
import ImportDialog from './ImportDialog';
import PresenceBar from './PresenceBar';
import { useAuthStore } from '../store/auth';
import { useStore } from '../store';
import { api, type PresenceUser } from '../api/client';

const GraphPaneCtx = createContext({ graphOpen: false, toggleGraph: () => {} });
export function useGraphPane() { return useContext(GraphPaneCtx); }

interface SelectedReqCtxValue {
  selectedReqId: string | null;
  selectReq: (id: string | null) => void;
}
const SelectedReqCtx = createContext<SelectedReqCtxValue>({ selectedReqId: null, selectReq: () => {} });
export function useSelectedReq() { return useContext(SelectedReqCtx); }

const GRAPH_MIN = 320;
const NAV_MIN = 200;
const NAV_MAX = 480;
const graphMax = () => Math.round(window.innerWidth * 0.65);

export default function Layout() {
  const { projectId } = useParams();
  const isInProject = !!projectId;
  const [graphOpen, setGraphOpen] = useState(true);
  const [loginOpen, setLoginOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [presence, setPresence] = useState<PresenceUser[]>([]);
  const [graphWidth, setGraphWidth] = useState(() => {
    const saved = parseInt(localStorage.getItem('rt-graph-width') || '', 10);
    const fallback = Math.round(window.innerWidth * 0.38);
    return Math.min(Math.max(isNaN(saved) ? fallback : saved, GRAPH_MIN), graphMax());
  });
  const [navWidth, setNavWidth] = useState(() => {
    const saved = parseInt(localStorage.getItem('rt-nav-width') || '', 10);
    return Math.min(Math.max(isNaN(saved) ? 300 : saved, NAV_MIN), NAV_MAX);
  });
  const [resizing, setResizing] = useState<'graph' | 'nav' | false>(false);
  const [selectedReqId, setSelectedReqId] = useState<string | null>(null);

  const selectReq = useCallback((id: string | null) => {
    setSelectedReqId(id);
  }, []);

  const startGraphResize = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    setResizing('graph');
    const onMove = (ev: PointerEvent) => {
      const w = Math.min(Math.max(window.innerWidth - ev.clientX, GRAPH_MIN), graphMax());
      setGraphWidth(w);
    };
    const onUp = (ev: PointerEvent) => {
      const w = Math.min(Math.max(window.innerWidth - ev.clientX, GRAPH_MIN), graphMax());
      localStorage.setItem('rt-graph-width', String(w));
      setResizing(false);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, []);

  const startNavResize = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    setResizing('nav');
    const onMove = (ev: PointerEvent) => {
      const w = Math.min(Math.max(ev.clientX, NAV_MIN), NAV_MAX);
      setNavWidth(w);
    };
    const onUp = (ev: PointerEvent) => {
      const w = Math.min(Math.max(ev.clientX, NAV_MIN), NAV_MAX);
      localStorage.setItem('rt-nav-width', String(w));
      setResizing(false);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, []);

  const { user, token, editMode, isGuest, setUser, setEditMode, logout } = useAuthStore();

  useEffect(() => {
    if (token) {
      api.whoami().then(u => setUser(u)).catch(() => logout());
    }
  }, []);

  // SSE listener for real-time collaboration: live data refresh + presence.
  const bumpGraphVersion = useStore((s) => s.bumpGraphVersion);
  const bumpDataVersion = useStore((s) => s.bumpDataVersion);
  const username = user?.username;
  useEffect(() => {
    if (!isInProject || !projectId) return;
    const params = new URLSearchParams();
    if (username) params.set('user', username);
    if (user?.role) params.set('role', user.role);
    const url = `/api/projects/${projectId}/events?${params.toString()}`;
    let es: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    const connect = () => {
      es = new EventSource(url);
      es.addEventListener('change', () => {
        bumpGraphVersion();
        bumpDataVersion();
      });
      es.addEventListener('presence', (e) => {
        try {
          const data = JSON.parse((e as MessageEvent).data);
          setPresence(data.users || []);
        } catch { /* ignore malformed presence frames */ }
      });
      es.onerror = () => {
        es?.close();
        reconnectTimer = setTimeout(connect, 3000);
      };
    };
    connect();

    return () => {
      clearTimeout(reconnectTimer);
      es?.close();
    };
  }, [isInProject, projectId, username, user?.role, bumpGraphVersion, bumpDataVersion]);

  const toggleGraph = () => setGraphOpen((o) => !o);
  const toggleEdit = () => setEditMode(!editMode);

  const canToggleEdit = user && user.role !== 'viewer';

  return (
    <GraphPaneCtx.Provider value={{ graphOpen, toggleGraph }}>
    <SelectedReqCtx.Provider value={{ selectedReqId, selectReq }}>
      <div className="h-screen flex flex-col bg-background">
        <header className="h-14 border-b bg-card flex items-center px-3 gap-2 shrink-0 z-40">
          <Link to="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity shrink-0">
            <img src="/reqmesh-mark.png" alt="reqmesh" className="w-7 h-7" />
            <span className="font-semibold text-sm tracking-tight text-foreground hidden sm:inline">reqmesh</span>
          </Link>

          {isInProject && (
            <div className="flex items-center gap-1 min-w-0">
              <span className="text-muted-foreground text-sm hidden sm:inline">/</span>
              <Link to={`/project/${projectId}`} className="text-sm text-muted-foreground hover:text-foreground transition-colors font-mono truncate">{projectId}</Link>
            </div>
          )}

          <div className="flex-1" />

          {isInProject && (
            <button onClick={toggleGraph} className={`btn-ghost p-2 rounded-lg gap-1.5 text-xs ${graphOpen ? 'bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground' : 'text-muted-foreground'}`}>
              {graphOpen ? <PanelRightClose size={15} /> : <PanelRight size={15} />}
              <span className="hidden sm:inline">Graph</span>
            </button>
          )}

          {isInProject && (
            <button
              onClick={() => setExportOpen(true)}
              className="btn-ghost p-2 rounded-lg gap-1.5 text-xs text-muted-foreground hover:text-foreground"
              title="Export document"
            >
              <FileDown size={15} />
              <span className="hidden sm:inline">Export</span>
            </button>
          )}

          {isInProject && canToggleEdit && (
            <button
              onClick={() => setImportOpen(true)}
              className="btn-ghost p-2 rounded-lg gap-1.5 text-xs text-muted-foreground hover:text-foreground"
              title="Import ReqIF / SysML"
            >
              <FileUp size={15} />
              <span className="hidden sm:inline">Import</span>
            </button>
          )}

          {isInProject && <PresenceBar users={presence} self={username} />}

          {canToggleEdit && (
            <button
              onClick={toggleEdit}
              className={`btn-ghost p-2 rounded-lg gap-1.5 text-xs transition-all ${
                editMode ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30' : 'text-muted-foreground'
              }`}
              title={editMode ? 'Editing mode ON - click to disable' : 'Click to enable editing'}
            >
              {editMode ? <Pencil size={15} /> : <Eye size={15} />}
              <span className="hidden sm:inline text-[10px]">{editMode ? 'EDITING' : 'VIEWING'}</span>
            </button>
          )}

          {user?.role === 'admin' && (
            <Link
              to="/users"
              className="btn-ghost p-2 rounded-lg gap-1.5 text-xs text-muted-foreground hover:text-foreground"
              title="Manage users"
            >
              <Users size={15} />
              <span className="hidden sm:inline">Users</span>
            </Link>
          )}

          {user ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground hidden sm:inline">
                <User size={12} className="inline mr-1" />
                {user.username}
                {editMode && <span className="ml-1 text-amber-400 text-[10px]">edit</span>}
              </span>
              <button onClick={logout} className="btn-ghost p-2 rounded-lg text-muted-foreground hover:text-destructive" title="Sign out">
                <LogOut size={15} />
              </button>
            </div>
          ) : (
            <>
              {isGuest ? (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground hidden sm:inline">
                    <Eye size={12} className="inline mr-1" /> Guest
                  </span>
                  <button onClick={() => { logout(); setLoginOpen(true); }} className="btn-ghost p-2 rounded-lg text-muted-foreground" title="Sign in">
                    <LogIn size={15} />
                  </button>
                </div>
              ) : (
                <button onClick={() => setLoginOpen(true)} className="btn-ghost p-2 rounded-lg text-muted-foreground" title="Sign in">
                  <LogIn size={15} />
                </button>
              )}
            </>
          )}

          <ThemeToggle />
        </header>

        <div className="flex flex-1 min-h-0 overflow-hidden">
          {isInProject && (
            <>
              <div className="shrink-0 overflow-hidden bg-sidebar" style={{ width: navWidth }}>
                <RequirementNav width={navWidth} />
              </div>
              <div
                onPointerDown={startNavResize}
                className={`w-1 shrink-0 cursor-col-resize transition-colors ${resizing === 'nav' ? 'bg-primary/60' : 'bg-border/60 hover:bg-primary/40'}`}
                title="Drag to resize"
              />
            </>
          )}
          <main className="flex-1 overflow-auto">
            <Outlet />
          </main>
          {isInProject && graphOpen && (
            <>
              <div
                onPointerDown={startGraphResize}
                className={`w-1 shrink-0 cursor-col-resize transition-colors ${resizing === 'graph' ? 'bg-primary/60' : 'bg-border/60 hover:bg-primary/40'}`}
                title="Drag to resize"
              />
              <div className="border-l shrink-0 overflow-hidden bg-background" style={{ width: graphWidth }}>
                <GraphPane projectId={projectId!} />
              </div>
            </>
          )}
        </div>
        {/* Capture pointer events over the canvas while resizing */}
        {resizing && <div className="fixed inset-0 z-50 cursor-col-resize" />}
      </div>

      <LoginModal open={loginOpen} onClose={() => setLoginOpen(false)} />
      {isInProject && <ExportDialog open={exportOpen} onClose={() => setExportOpen(false)} projectId={projectId!} />}
      {isInProject && <ImportDialog open={importOpen} onClose={() => setImportOpen(false)} projectId={projectId!} />}
    </SelectedReqCtx.Provider>
    </GraphPaneCtx.Provider>
  );
}
