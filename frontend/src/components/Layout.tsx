import { Outlet, Link, useParams } from 'react-router-dom';
import { PanelRight, PanelRightClose, PanelRightOpen, LogIn, LogOut, User, Pencil, Eye, FileDown, FileUp, Users, Search, HelpCircle, BookOpen, Server, SlidersHorizontal } from 'lucide-react';
import { useState, useEffect, useCallback, createContext, useContext, useRef } from 'react';
import { ThemeToggle } from './ThemeToggle';
import RequirementNav from './RequirementNav';
import GraphPane from './GraphPane';
import CommandPalette, { OPEN_PALETTE_EVENT } from './CommandPalette';
import ShortcutHelp from './ShortcutHelp';
import DocumentationPanel from './DocumentationPanel';
import { useKeyboardShortcuts } from './useKeyboardShortcuts';
import LoginModal from './LoginModal';
import ExportDialog from './ExportDialog';
import ImportDialog from './ImportDialog';
import PresenceBar from './PresenceBar';
import { useAuthStore } from '../store/auth';
import { useStore } from '../store';
import { api, type PresenceUser } from '../api/client';

const GraphPaneCtx = createContext({ graphOpen: false, toggleGraph: () => {} });
export function useGraphPane() { return useContext(GraphPaneCtx); }

// Fetched once per page load; the version rarely changes within a session.
let _versionCache: string | null = null;
let _instanceNameCache: string | null = null;

/** Instance name from public config, falling back to "reqmesh". */
function InstanceName() {
  const [name, setName] = useState<string | null>(_instanceNameCache);
  useEffect(() => {
    if (_instanceNameCache) return;
    let alive = true;
    api.getPublicConfig()
      .then((c) => { _instanceNameCache = c.instance_name || 'reqmesh'; if (alive) setName(_instanceNameCache); })
      .catch(() => {});
    return () => { alive = false; };
  }, []);
  return <span className="font-semibold text-sm tracking-tight text-foreground hidden sm:inline">{name || 'reqmesh'}</span>;
}

function VersionBadge() {
  const [version, setVersion] = useState<string | null>(_versionCache);
  useEffect(() => {
    if (_versionCache) return;
    let alive = true;
    api.getVersion()
      .then((info) => { _versionCache = info.version; if (alive) setVersion(info.version); })
      .catch(() => {});
    return () => { alive = false; };
  }, []);
  if (!version) return null;
  return (
    <span
      className="hidden md:inline text-[10px] font-mono text-muted-foreground/70 border rounded px-1 py-px"
      title="reqmesh version"
    >
      v{version}
    </span>
  );
}

interface SelectedReqCtxValue {
  selectedReqId: string | null;
  selectReq: (id: string | null) => void;
}
const SelectedReqCtx = createContext<SelectedReqCtxValue>({ selectedReqId: null, selectReq: () => {} });
export function useSelectedReq() { return useContext(SelectedReqCtx); }

const GRAPH_MIN = 320;
const NAV_MIN = 200;
const NAV_MAX = 480;
const NAV_RAIL = 40;
const graphMax = () => Math.round(window.innerWidth * 0.65);

export default function Layout() {
  const { projectId } = useParams();
  const isInProject = !!projectId;
  const [graphOpen, setGraphOpen] = useState(true);
  const [contextOpen, setContextOpen] = useState(true);
  const [contextWidth, setContextWidth] = useState(() => {
    const saved = localStorage.getItem('rt-context-width');
    return saved ? Number(saved) : Math.round(window.innerWidth * 0.35);
  });
  const CONTEXT_MIN = 200;
  const [loginOpen, setLoginOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [docsOpen, setDocsOpen] = useState(false);
  const [presence, setPresence] = useState<PresenceUser[]>([]);
  const [graphWidth, setGraphWidth] = useState(() => {
    const saved = parseInt(localStorage.getItem('rt-graph-width') || '', 10);
    const fallback = Math.round(window.innerWidth * 0.44);
    return Math.min(Math.max(isNaN(saved) ? fallback : saved, GRAPH_MIN), graphMax());
  });
  const [navWidth, setNavWidth] = useState(() => {
    const saved = parseInt(localStorage.getItem('rt-nav-width') || '', 10);
    return Math.min(Math.max(isNaN(saved) ? 300 : saved, NAV_MIN), NAV_MAX);
  });
  const [resizing, setResizing] = useState<'graph' | 'nav' | 'context' | false>(false);
  const [selectedReqId, setSelectedReqId] = useState<string | null>(null);
  const [navCollapsed, setNavCollapsed] = useState(() => localStorage.getItem('rt-nav-collapsed') === '1');

  const toggleNavCollapsed = useCallback(() => {
    setNavCollapsed((c) => {
      localStorage.setItem('rt-nav-collapsed', c ? '0' : '1');
      return !c;
    });
  }, []);

  // Collapsing the nav hands its freed width to the canvas, not the page.
  const canvasBonus = (navCollapsed ? navWidth + 4 - NAV_RAIL : 0) + (!contextOpen ? contextWidth : 0);

  const selectReq = useCallback((id: string | null) => {
    setSelectedReqId(id);
  }, []);

  // The canvas sits between the nav and the page content, so its width is
  // measured from the nav's right edge. While the nav is collapsed the canvas
  // renders with a width bonus, so dragging adjusts the stored base width.
  const startGraphResize = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    setResizing('graph');
    const left = navCollapsed ? NAV_RAIL : navWidth + 4;
    const bonus = navCollapsed ? navWidth + 4 - NAV_RAIL : 0;
    const baseWidth = (clientX: number) =>
      Math.min(Math.max(clientX - left - bonus, GRAPH_MIN), graphMax());
    const onMove = (ev: PointerEvent) => setGraphWidth(baseWidth(ev.clientX));
    const onUp = (ev: PointerEvent) => {
      const w = baseWidth(ev.clientX);
      setGraphWidth(w);
      localStorage.setItem('rt-graph-width', String(w));
      setResizing(false);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [navWidth, navCollapsed]);

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

  const startContextResize = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    setResizing('context');
    const onMove = (ev: PointerEvent) => {
      const w = Math.min(Math.max(window.innerWidth - ev.clientX, CONTEXT_MIN), window.innerWidth - NAV_RAIL);
      setContextWidth(w);
    };
    const onUp = (ev: PointerEvent) => {
      const w = Math.min(Math.max(window.innerWidth - ev.clientX, CONTEXT_MIN), window.innerWidth - NAV_RAIL);
      setContextWidth(w);
      localStorage.setItem('rt-context-width', String(w));
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
  const helpersEnabled = useStore((s) => s.helpersEnabled);
  const toggleHelpers = useStore((s) => s.toggleHelpers);
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

  useKeyboardShortcuts(projectId, {
    onEditToggle: () => { if (canToggleEdit) toggleEdit(); },
    onGraphToggle: toggleGraph,
    onHelperToggle: toggleHelpers,
    onHelpToggle: () => setHelpOpen(o => !o),
    onDocsOpen: () => setDocsOpen(o => !o),
    // Escape/save/delete on detail pages belong to the page's own
    // useKeyboardShortcuts instance — a second handler here would fire twice.
  });

  const canToggleEdit = user && user.role !== 'viewer';

  return (
    <GraphPaneCtx.Provider value={{ graphOpen, toggleGraph }}>
    <SelectedReqCtx.Provider value={{ selectedReqId, selectReq }}>
      <div className="h-screen flex flex-col bg-background">
        <header className="h-14 border-b bg-card flex items-center px-3 gap-2 shrink-0 z-40">
          <Link to="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity shrink-0">
            <img src="/reqmesh-mark.png" alt="reqmesh" className="w-7 h-7" />
            <InstanceName />
          </Link>
          <VersionBadge />

          {isInProject && (
            <div className="flex items-center gap-1 min-w-0">
              <span className="text-muted-foreground text-sm hidden sm:inline">/</span>
              <Link to={`/project/${projectId}`} className="text-sm text-muted-foreground hover:text-foreground transition-colors font-mono truncate">{projectId}</Link>
            </div>
          )}

          <div className="flex-1" />

          {isInProject && (
            <button
              onClick={() => window.dispatchEvent(new Event(OPEN_PALETTE_EVENT))}
              className="btn-ghost p-2 rounded-lg gap-1.5 text-xs text-muted-foreground hover:text-foreground"
              title="Jump to anything (Ctrl+K)" aria-label="Open command palette"
            >
              <Search size={15} />
              <kbd className="hidden sm:inline text-[9px] border rounded px-1 py-px">Ctrl K</kbd>
            </button>
          )}

          {isInProject && (
            <button
              onClick={() => setDocsOpen(true)}
              className="btn-ghost p-2 rounded-lg gap-1.5 text-xs text-muted-foreground hover:text-foreground"
              title="Documentation (F1)"
            >
              <BookOpen size={15} />
              <span className="hidden sm:inline text-[10px]">Docs</span>
            </button>
          )}

          {isInProject && (
            <button
              onClick={toggleHelpers}
              className={`btn-ghost p-2 rounded-lg gap-1.5 text-xs transition-all ${helpersEnabled ? 'bg-violet-500/15 text-violet-400 border border-violet-500/30' : 'text-muted-foreground'}`}
              title={helpersEnabled ? 'Helpers ON — click to hide guidance' : 'Helpers OFF — click to show guidance'}
            >
              <HelpCircle size={15} />
              <span className="hidden sm:inline text-[10px]">{helpersEnabled ? 'GUIDED ON' : 'GUIDED OFF'}</span>
            </button>
          )}

          {isInProject && (
            <button onClick={toggleGraph} className={`btn-ghost p-2 rounded-lg gap-1.5 text-xs ${graphOpen ? 'bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground' : 'text-muted-foreground'}`}>
              {graphOpen ? <PanelRightClose size={15} /> : <PanelRight size={15} />}
              <span className="hidden sm:inline">Canvas</span>
            </button>
          )}

          {isInProject && (
            <button onClick={() => setContextOpen(o => !o)} className={`btn-ghost p-2 rounded-lg gap-1.5 text-xs ${contextOpen ? 'bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground' : 'text-muted-foreground'}`}>
              {contextOpen ? <PanelRightClose size={15} /> : <PanelRightOpen size={15} />}
              <span className="hidden sm:inline">Inspector</span>
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

          {user?.role === 'admin' && (
            <Link
              to="/settings"
              className="btn-ghost p-2 rounded-lg gap-1.5 text-xs text-muted-foreground hover:text-foreground"
              title="Application settings"
            >
              <SlidersHorizontal size={15} />
              <span className="hidden sm:inline">Settings</span>
            </Link>
          )}

          {user?.role === 'admin' && (
            <Link
              to="/system"
              className="btn-ghost p-2 rounded-lg gap-1.5 text-xs text-muted-foreground hover:text-foreground"
              title="System & updates"
            >
              <Server size={15} />
              <span className="hidden sm:inline">System</span>
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

        {/* Workspace order follows the MBSE anatomy: model browser (left),
            diagram canvas (centre), page content as the inspector surface. */}
        <div className="flex flex-1 min-h-0 overflow-hidden">
          {isInProject && (
            <>
              <div
                className="shrink-0 overflow-hidden bg-sidebar"
                style={{
                  width: navCollapsed ? NAV_RAIL : navWidth,
                  transition: resizing ? 'none' : 'width 0.3s ease',
                }}
              >
                <RequirementNav width={navWidth} collapsed={navCollapsed} onToggleCollapse={toggleNavCollapsed} />
              </div>
              {!navCollapsed && (
                <div
                  onPointerDown={startNavResize}
                  className={`w-1 shrink-0 cursor-col-resize transition-colors ${resizing === 'nav' ? 'bg-primary/60' : 'bg-border/60 hover:bg-primary/40'}`}
                  title="Drag to resize"
                />
              )}
            </>
          )}
          {isInProject && graphOpen && (
            <>
              <div
                className="shrink-0 overflow-hidden bg-background"
                style={{
                  width: graphWidth + canvasBonus,
                  transition: resizing ? 'none' : 'width 0.3s ease',
                }}
              >
                <GraphPane projectId={projectId!} />
              </div>
              <div
                onPointerDown={startGraphResize}
                className={`w-1 shrink-0 cursor-col-resize transition-colors ${resizing === 'graph' ? 'bg-primary/60' : 'bg-border/60 hover:bg-primary/40'}`}
                title="Drag to resize"
              />
            </>
          )}
          {isInProject && contextOpen && (
            <div
              onPointerDown={startContextResize}
              className={`w-1 shrink-0 cursor-col-resize transition-colors ${resizing === 'context' ? 'bg-primary/60' : 'bg-border/60 hover:bg-primary/40'}`}
              title="Drag to resize"
            />
          )}
          {isInProject && contextOpen ? (
            <main
              className="overflow-auto"
              style={{
                width: graphOpen ? contextWidth : undefined,
                flex: graphOpen ? undefined : '1 1 0%',
                transition: resizing ? 'none' : 'width 0.3s ease',
              }}
            >
              <Outlet />
            </main>
          ) : !isInProject ? (
            <main className="flex-1 overflow-auto">
              <Outlet />
            </main>
          ) : null}
        </div>
        {/* Capture pointer events over the canvas while resizing */}
        {resizing && <div className="fixed inset-0 z-50 cursor-col-resize" />}
      </div>

      <LoginModal open={loginOpen} onClose={() => setLoginOpen(false)} />
      {isInProject && <CommandPalette projectId={projectId!} />}
      {isInProject && <ExportDialog open={exportOpen} onClose={() => setExportOpen(false)} projectId={projectId!} />}
      {isInProject && <ImportDialog open={importOpen} onClose={() => setImportOpen(false)} projectId={projectId!} />}
      <ShortcutHelp open={helpOpen} onClose={() => setHelpOpen(false)} />
      <DocumentationPanel open={docsOpen} onClose={() => setDocsOpen(false)} />
    </SelectedReqCtx.Provider>
    </GraphPaneCtx.Provider>
  );
}
