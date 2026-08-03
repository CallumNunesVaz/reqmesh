import { Suspense } from 'react';
import { Outlet, useParams } from 'react-router-dom';
import { GuardedLink as Link } from './navGuard';
import LoadingSplash from './LoadingSplash';
import { PanelRight, PanelRightClose, PanelRightOpen, LogIn, LogOut, User, Pencil, Eye, FileDown, FileUp, Users, Search, HelpCircle, BookOpen, Server, SlidersHorizontal, Undo2, Redo2 } from 'lucide-react';
import { useState, useEffect, useCallback, useMemo, createContext, useContext, useRef } from 'react';
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
import { useUndoStore } from '../store/undo';
import { api, type PresenceUser } from '../api/client';
import { WhatIfProvider } from './WhatIfContext';
import WhatIfPanel from './WhatIfPanel';

const GraphPaneCtx = createContext({ graphOpen: false, toggleGraph: () => {} });
export function useGraphPane() { return useContext(GraphPaneCtx); }

/** Lets the canvas reveal the inspector. Double-clicking a node selects it and
 *  loads its detail, which is invisible while the pane is collapsed — the
 *  interaction appeared to do nothing at all. */
const ContextPaneCtx = createContext({ contextOpen: false, openContext: () => {} });
export function useContextPane() { return useContext(ContextPaneCtx); }

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
      className="hidden 2xl:inline text-[10px] font-mono text-muted-foreground/70 border rounded px-1 py-px"
      title="reqmesh version"
    >
      v{version}
    </span>
  );
}

interface SelectedReqCtxValue {
  selectedReqId: string | null;
  selectReq: (id: string | null) => void;
  /** Ask the canvas to trace everything feeding into a requirement. The nonce
   *  lets the same id be re-traced (the button is idempotent otherwise). */
  derivationReq: { id: string; nonce: number } | null;
  showDerivation: (id: string) => void;
}
const SelectedReqCtx = createContext<SelectedReqCtxValue>({
  selectedReqId: null, selectReq: () => {}, derivationReq: null, showDerivation: () => {},
});
export function useSelectedReq() { return useContext(SelectedReqCtx); }

const GRAPH_MIN = 320;    // px floor for the canvas column
const CONTEXT_MIN = 300;  // px floor for the inspector column (form-heavy, size-sensitive)
const NAV_MIN = 200;
const NAV_MAX = 480;
const NAV_RAIL = 40;

/**
 * The route chunks are lazy, so a first visit to any page suspends. This
 * boundary sits *inside* the layout, around the page area only.
 *
 * It used to live in App.tsx wrapping the whole <Routes> tree, including
 * <Layout /> — so the first click on each nav item unmounted the nav pane,
 * header and graph canvas, drew a fullscreen splash, then remounted all of it.
 * That was the "whole screen flashes once per page, and a refresh brings it
 * back" report: the second visit found the chunk already in the module
 * registry and never suspended.
 *
 * LoadingSplash fades in after a beat, so a cached chunk shows nothing at all.
 */
function PageArea({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<LoadingSplash label="Loading page…" />}>{children}</Suspense>;
}

export default function Layout() {
  const { projectId } = useParams();
  const isInProject = !!projectId;
  const [graphOpen, setGraphOpen] = useState(true);
  const [contextOpen, setContextOpen] = useState(true);
  const [loginOpen, setLoginOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [docsOpen, setDocsOpen] = useState(false);
  const [presence, setPresence] = useState<PresenceUser[]>([]);
  // The canvas/inspector split is stored as the canvas's *fraction* of the
  // space the two share (not an absolute width), so on a window resize both
  // panes keep their proportions via flex-grow. Because the canvas holds the
  // larger share it absorbs more of the delta in pixels, leaving the
  // size-sensitive inspector comparatively stable.
  const [graphFrac, setGraphFrac] = useState(() => {
    const saved = parseFloat(localStorage.getItem('rt-graph-frac') || '');
    return saved >= 0.15 && saved <= 0.85 ? saved : 0.52;
  });
  const [navWidth, setNavWidth] = useState(() => {
    const saved = parseInt(localStorage.getItem('rt-nav-width') || '', 10);
    return Math.min(Math.max(isNaN(saved) ? 300 : saved, NAV_MIN), NAV_MAX);
  });
  const [resizing, setResizing] = useState<'graph' | 'nav' | false>(false);
  const [selectedReqId, setSelectedReqId] = useState<string | null>(null);
  const [navCollapsed, setNavCollapsed] = useState(() => localStorage.getItem('rt-nav-collapsed') === '1');

  const toggleNavCollapsed = useCallback(() => {
    setNavCollapsed((c) => {
      localStorage.setItem('rt-nav-collapsed', c ? '0' : '1');
      return !c;
    });
  }, []);

  // Collapsing the nav hands its freed width to the canvas, not the page.
  const canvasBonus = navCollapsed ? navWidth + 4 - NAV_RAIL : 0;

  const selectReq = useCallback((id: string | null) => {
    setSelectedReqId(id);
  }, []);

  // Idempotent: revealing an already-open pane must not toggle it shut, so this
  // is deliberately not the existing toggle.
  const openContext = useCallback(() => setContextOpen(true), []);
  const contextPaneValue = useMemo(() => ({ contextOpen, openContext }), [contextOpen, openContext]);

  const [derivationReq, setDerivationReq] = useState<{ id: string; nonce: number } | null>(null);
  const showDerivation = useCallback((id: string) => {
    setSelectedReqId(id);
    setDerivationReq((prev) => ({ id, nonce: (prev?.nonce ?? 0) + 1 }));
  }, []);

  // The divider sits between the canvas and the inspector. Dragging it sets the
  // canvas fraction of the pool the two share (everything right of the nav and
  // its bonus, minus the divider). Clamped so neither pane drops below its px
  // floor, keeping the maths resolution-independent so the split survives a
  // window resize.
  const startGraphResize = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    setResizing('graph');
    const left = (navCollapsed ? NAV_RAIL : navWidth + 4) + canvasBonus;
    const fracAt = (clientX: number) => {
      const pool = Math.max(1, window.innerWidth - left - 4 /* divider */);
      const minFrac = Math.min(0.85, GRAPH_MIN / pool);
      const maxFrac = Math.max(0.15, 1 - CONTEXT_MIN / pool);
      return Math.min(Math.max((clientX - left) / pool, minFrac), maxFrac);
    };
    const onMove = (ev: PointerEvent) => setGraphFrac(fracAt(ev.clientX));
    const onUp = (ev: PointerEvent) => {
      const f = fracAt(ev.clientX);
      setGraphFrac(f);
      localStorage.setItem('rt-graph-frac', String(f));
      setResizing(false);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [navWidth, navCollapsed, canvasBonus]);

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

  const { user, editMode, isGuest, setEditMode, logout } = useAuthStore();

  // Clear undo stack when switching projects
  const clearUndo = useUndoStore((s) => s.clear);
  useEffect(() => { clearUndo(); }, [projectId]);

  // Reset component/baseline visibility when the open project changes.
  const resetVisibility = useStore((s) => s.resetVisibility);
  const prevProjectRef = useRef(projectId);
  useEffect(() => {
    if (prevProjectRef.current !== projectId) {
      resetVisibility();
      prevProjectRef.current = projectId;
    }
  }, [projectId, resetVisibility]);

  // Session restoration lives in <AuthInit>, which resolves whoami() from the
  // HttpOnly cookie before the app renders. The old effect here keyed off a
  // localStorage token that no longer exists.

  // Signing out must reach the server: the session cookie is HttpOnly, so
  // clearing client state alone leaves a valid session that whoami() would
  // silently restore on the next load.
  const signOut = useCallback(async () => {
    try { await api.logout(); } catch { /* clear locally regardless */ }
    logout();
  }, [logout]);

  // SSE listener for real-time collaboration: live data refresh + presence.
  const bumpGraphVersion = useStore((s) => s.bumpGraphVersion);
  const bumpDataVersion = useStore((s) => s.bumpDataVersion);
  const helpersEnabled = useStore((s) => s.helpersEnabled);
  const toggleHelpers = useStore((s) => s.toggleHelpers);
  const { undo, redo, canUndo, canRedo } = useUndoStore();
  const undoRef = useRef(undo);
  const redoRef = useRef(redo);
  useEffect(() => { undoRef.current = undo; redoRef.current = redo; }, [undo, redo]);
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
    onUndo: () => { if (editMode) undoRef.current(); },
    onRedo: () => { if (editMode) redoRef.current(); },
    // Escape/save/delete on detail pages belong to the page's own
    // useKeyboardShortcuts instance — a second handler here would fire twice.
  });

  const canToggleEdit = useAuthStore((s) => s.canToggleEdit());

  return (
    <GraphPaneCtx.Provider value={{ graphOpen, toggleGraph }}>
    <ContextPaneCtx.Provider value={contextPaneValue}>
    <SelectedReqCtx.Provider value={{ selectedReqId, selectReq, derivationReq, showDerivation }}>
      <div className="h-screen flex flex-col bg-background">
        {/* overflow-x-auto: at very narrow windows the icon row degrades to a
            horizontal scroll instead of buttons overlapping each other. */}
        <header className="h-14 border-b bg-card flex items-center px-3 gap-2 shrink-0 z-40 overflow-x-auto overflow-y-hidden whitespace-nowrap">
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
              <kbd className="hidden 2xl:inline text-[9px] border rounded px-1 py-px">Ctrl K</kbd>
            </button>
          )}

          {isInProject && (
            <button
              onClick={() => setDocsOpen(true)}
              className="btn-ghost p-2 rounded-lg gap-1.5 text-xs text-muted-foreground hover:text-foreground"
              title="Documentation (F1)"
            >
              <BookOpen size={15} />
              <span className="hidden 2xl:inline text-[10px]">Docs</span>
            </button>
          )}

          {isInProject && (
            <button
              onClick={toggleHelpers}
              className={`btn-ghost p-2 rounded-lg gap-1.5 text-xs transition-all ${helpersEnabled ? 'bg-violet-500/15 text-violet-400 border border-violet-500/30' : 'text-muted-foreground'}`}
              title={helpersEnabled ? 'Helpers ON — click to hide guidance' : 'Helpers OFF — click to show guidance'}
            >
              <HelpCircle size={15} />
              <span className="hidden 2xl:inline text-[10px]">{helpersEnabled ? 'GUIDED ON' : 'GUIDED OFF'}</span>
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
              <span className="hidden 2xl:inline">Export</span>
            </button>
          )}

          {isInProject && canToggleEdit && (
            <button
              onClick={() => setImportOpen(true)}
              className="btn-ghost p-2 rounded-lg gap-1.5 text-xs text-muted-foreground hover:text-foreground"
              title="Import ReqIF / SysML"
            >
              <FileUp size={15} />
              <span className="hidden 2xl:inline">Import</span>
            </button>
          )}

          {isInProject && editMode && (
            <>
              <button
                onClick={() => undo()}
                disabled={!canUndo()}
                className="btn-ghost p-2 rounded-lg text-xs text-muted-foreground hover:text-foreground disabled:opacity-30"
                title="Undo (Ctrl+Z)"
              >
                <Undo2 size={15} />
              </button>
              <button
                onClick={() => redo()}
                disabled={!canRedo()}
                className="btn-ghost p-2 rounded-lg text-xs text-muted-foreground hover:text-foreground disabled:opacity-30"
                title="Redo (Ctrl+Y / Ctrl+Shift+Z)"
              >
                <Redo2 size={15} />
              </button>
            </>
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
              <span className="hidden 2xl:inline">Users</span>
            </Link>
          )}

          {user?.role === 'admin' && (
            <Link
              to="/settings"
              className="btn-ghost p-2 rounded-lg gap-1.5 text-xs text-muted-foreground hover:text-foreground"
              title="Application settings"
            >
              <SlidersHorizontal size={15} />
              <span className="hidden 2xl:inline">Settings</span>
            </Link>
          )}

          {user?.role === 'admin' && (
            <Link
              to="/system"
              className="btn-ghost p-2 rounded-lg gap-1.5 text-xs text-muted-foreground hover:text-foreground"
              title="System & updates"
            >
              <Server size={15} />
              <span className="hidden 2xl:inline">System</span>
            </Link>
          )}

          {user ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground hidden sm:inline">
                <User size={12} className="inline mr-1" />
                <span className="hidden 2xl:inline">{user.username}</span>
                {editMode && <span className="ml-1 text-amber-400 text-[10px]">edit</span>}
              </span>
              <button onClick={signOut} className="btn-ghost p-2 rounded-lg text-muted-foreground hover:text-destructive" title="Sign out">
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
                  <button onClick={() => { void signOut().then(() => setLoginOpen(true)); }} className="btn-ghost p-2 rounded-lg text-muted-foreground" title="Sign in">
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
        {isInProject ? (
          <WhatIfProvider projectId={projectId!}>
            <div className="flex flex-1 min-h-0 overflow-hidden">
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
              {isInProject && graphOpen && (
                <>
                  <div
                    className="overflow-hidden bg-background"
                    style={{
                      flex: contextOpen ? `${graphFrac} 1 ${canvasBonus}px` : '1 1 0%',
                      minWidth: 0,
                      transition: resizing ? 'none' : 'flex-grow 0.3s ease',
                    }}
                  >
                    <GraphPane projectId={projectId!} />
                  </div>
                  {contextOpen && (
                    <div
                      onPointerDown={startGraphResize}
                      className={`w-1 shrink-0 cursor-col-resize transition-colors ${resizing === 'graph' ? 'bg-primary/60' : 'bg-border/60 hover:bg-primary/40'}`}
                      title="Drag to resize the canvas"
                    />
                  )}
                </>
              )}
              {(!isInProject || contextOpen) && (
                <main
                  className="overflow-auto @container relative"
                  style={{
                    // `1 - graphFrac` only makes sense while the canvas is
                    // actually rendered and taking the other share. With the
                    // canvas closed this is the row's only flex item, and a
                    // flex-grow below 1 against a 0 basis leaves the remainder
                    // of the row simply empty — the page drew at ~48% width with
                    // blank space beside it. Worst on wide grids like the
                    // allocation matrix, which then scrolled inside half a
                    // window for no reason.
                    flex: isInProject && graphOpen ? `${1 - graphFrac} 1 0%` : '1 1 0%',
                    minWidth: 0,
                    transition: resizing ? 'none' : 'flex-grow 0.3s ease',
                  }}
                >
                  <PageArea><Outlet /></PageArea>
                  {isInProject && <WhatIfPanel />}
                </main>
              )}
            </div>
          </WhatIfProvider>
        ) : (
          <div className="flex flex-1 min-h-0 overflow-hidden">
            {(!isInProject || contextOpen) && (
              <main
                className="overflow-auto @container relative"
                style={{ flex: '1 1 0%', minWidth: 0 }}
              >
                <PageArea><Outlet /></PageArea>
              </main>
            )}
          </div>
        )}
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
    </ContextPaneCtx.Provider>
    </GraphPaneCtx.Provider>
  );
}
