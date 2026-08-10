import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useGuardedNavigate } from './navGuard';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Search } from 'lucide-react';
import { ENTITY_META } from './entities';
import { loadEntityIndex, searchEntities, recordEntityVisit, type IndexedEntity } from './entityIndex';
import { useStore } from '../store';
import { api, type SearchResult } from '../api/client';

function highlightMatch(text: string, query: string): React.ReactNode {
  if (!query.trim()) return text;
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  // `escaped` has already had every regex metacharacter escaped, so the query
  // cannot introduce alternation, nesting or backtracking — it can only ever
  // match itself literally.
  // nosemgrep: javascript.lang.security.audit.detect-non-literal-regexp.detect-non-literal-regexp
  const parts = text.split(new RegExp(`(${escaped})`, 'gi'));
  return parts.map((part, i) =>
    part.toLowerCase() === query.toLowerCase() ? <mark key={i}>{part}</mark> : part
  );
}

/** Header button and other far-away UI can open the palette with this. */
export const OPEN_PALETTE_EVENT = 'rt-open-palette';

/**
 * Ctrl/Cmd+K jump-to-anything. Searches every entity in the project by id,
 * name and description, and navigates to the pick — the fastest traversal
 * path between any two things in the app.
 */
export default function CommandPalette({ projectId }: { projectId: string }) {
  const navigate = useGuardedNavigate();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [entities, setEntities] = useState<IndexedEntity[]>([]);
  const [cursor, setCursor] = useState(0);
  const [backendResults, setBackendResults] = useState<SearchResult[]>([]);
  const [backendLoading, setBackendLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const dataVersion = useStore((s) => s.dataVersion);
  const searchSeqRef = useRef(0);

  // Fetch backend project-wide search when query is 3+ chars.
  //
  // Debounced: the search scans every collection in the project, and firing on
  // each keystroke meant a 12-character query cost ten full scans — enough to
  // exhaust the endpoint's rate limit mid-word, after which the catch below
  // would quietly blank the results and the palette would look empty rather
  // than throttled. The sequence guard still handles out-of-order responses.
  useEffect(() => {
    if (!open || query.trim().length < 3) {
      setBackendResults([]);
      return;
    }
    const timer = setTimeout(() => {
      const seq = ++searchSeqRef.current;
      setBackendLoading(true);
      api.searchProject(projectId, query.trim()).then((res) => {
        if (seq !== searchSeqRef.current) return;
        setBackendResults(res.results);
      }).catch(() => {
        if (seq === searchSeqRef.current) setBackendResults([]);
      }).finally(() => {
        if (seq === searchSeqRef.current) setBackendLoading(false);
      });
    }, 200);
    return () => clearTimeout(timer);
  }, [open, query, projectId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    const onOpen = () => setOpen(true);
    window.addEventListener('keydown', onKey);
    window.addEventListener(OPEN_PALETTE_EVENT, onOpen);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener(OPEN_PALETTE_EVENT, onOpen);
    };
  }, []);

  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
      setQuery('');
      setCursor(0);
      loadEntityIndex(projectId).then(setEntities);
      requestAnimationFrame(() => inputRef.current?.focus());
    } else {
      document.body.style.overflow = '';
    }
  }, [open, projectId, dataVersion]);

  const localResults = searchEntities(entities, query);
  const showBackend = query.trim().length >= 3;

  // Merge results: local entity-index results first, then deduplicated backend results
  const localIds = useMemo(() => new Set(localResults.map(e => e.id)), [localResults]);
  const mergedBackend = useMemo(() =>
    showBackend ? backendResults.filter(r => !localIds.has(r.id)) : [],
    [showBackend, backendResults, localIds],
  );

  const combinedResults = useMemo(() => {
    const combined: Array<IndexedEntity | SearchResult> = [...localResults];
    if (showBackend && mergedBackend.length > 0) {
      combined.push(...mergedBackend);
    }
    return combined;
  }, [localResults, showBackend, mergedBackend]);

  const trimmed = query.trim();
  const showCreateAction = trimmed === '' ||
    ['new', 'create', 'requirement', 'add'].includes(trimmed.toLowerCase());

  const pickCreate = useCallback(() => {
    setOpen(false);
    navigate(`/project/${projectId}/requirements?new=1`);
  }, [navigate, projectId]);

  // Fix cursor bounds when results change
  useEffect(() => {
    if (cursor >= combinedResults.length && combinedResults.length > 0) {
      setCursor(0);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [combinedResults.length]);

  // Recent items — shown at top when query is empty
  const [recentIds, setRecentIds] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem(`rt-recent-${projectId}`) || '[]'); }
    catch { return []; }
  });
  const recentEntities = !query.trim() ? recentIds.map(id => entities.find(e => e.id === id)).filter(Boolean) as IndexedEntity[] : [];

  const pick = useCallback((entity: IndexedEntity | SearchResult) => {
    setOpen(false);
    if ('kind_icon' in entity) {
      // Backend search result — navigate to the entity
      const meta = ENTITY_META[entity.kind as keyof typeof ENTITY_META];
      if (meta) {
        navigate(meta.path(projectId, entity.id));
        return;
      }
      // Fallback for entity kinds without dedicated pages (comments, decisions, baselines)
      if (entity.kind === 'baseline') {
        navigate(`/project/${projectId}/baselines`);
      } else {
        // Navigate to the project overview as fallback
        navigate(`/project/${projectId}`);
      }
      return;
    }
    // Local entity index result
    const newRecent = [entity.id, ...recentIds.filter(id => id !== entity.id)].slice(0, 8);
    setRecentIds(newRecent);
    try { localStorage.setItem(`rt-recent-${projectId}`, JSON.stringify(newRecent)); } catch {}
    recordEntityVisit(entity.id);
    navigate(ENTITY_META[entity.kind].path(projectId, entity.id));
  }, [navigate, projectId, recentIds]);

  const onInputKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { setOpen(false); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor((c) => Math.min(c + 1, Math.max(showCreateAction ? combinedResults.length : combinedResults.length - 1, 0))); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setCursor((c) => Math.max(c - 1, 0)); }
    else if (e.key === 'Enter') {
      e.preventDefault();
      if (showCreateAction && cursor === 0) { pickCreate(); return; }
      const idx = showCreateAction ? cursor - 1 : cursor;
      if (combinedResults[idx]) pick(combinedResults[idx]);
    }
    else return;
    requestAnimationFrame(() => {
      listRef.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest' });
    });
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }}
          className="fixed inset-0 z-[90] bg-black/40 backdrop-blur-[2px] flex items-start justify-center pt-[14vh]"
          onMouseDown={(e) => { if (e.target === e.currentTarget) setOpen(false); }}
        >
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }} transition={{ duration: 0.12 }}
            className="card w-full max-w-xl shadow-2xl overflow-hidden"
          >
            <div className="flex items-center gap-2 px-3 border-b">
              <Search size={15} className="text-muted-foreground shrink-0" />
              <input
                ref={inputRef}
                className="flex-1 bg-transparent py-3 text-sm text-foreground outline-none placeholder:text-muted-foreground"
                placeholder="Jump to a requirement, verification, component…"
                value={query}
                onChange={(e) => { setQuery(e.target.value); setCursor(0); }}
                onKeyDown={onInputKey}
              />
              <kbd className="text-[10px] text-muted-foreground border rounded px-1.5 py-0.5 shrink-0">esc</kbd>
            </div>

            <div ref={listRef} className="max-h-[50vh] overflow-y-auto p-1.5">
              {recentEntities.length > 0 && !query.trim() && (
                <>
                  <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider px-2 py-1">Recent</p>
                  {recentEntities.map((e) => {
                    const meta = ENTITY_META[e.kind];
                    const Icon = meta.icon;
                    return (
                      <button key={`recent-${e.kind}-${e.id}`} onClick={() => pick(e)}
                        className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left hover:bg-accent/50 transition-colors">
                        <Icon size={14} className={`${meta.cls} shrink-0`} />
                        <span className="font-mono text-xs text-muted-foreground shrink-0">{highlightMatch(e.id, query)}</span>
                        <span className="text-sm text-card-foreground truncate">{highlightMatch(e.name || 'Untitled', query)}</span>
                        <span className="ml-auto text-[10px] text-muted-foreground">{meta.label}</span>
                      </button>
                    );
                  })}
                  <div className="border-t my-1 mx-1" />
                </>
              )}
              {showCreateAction && (
                <>
                  <button
                    key="action-create"
                    data-active={cursor === 0 ? 'true' : undefined}
                    onClick={pickCreate}
                    onMouseMove={() => setCursor(0)}
                    className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left transition-colors ${
                      cursor === 0 ? 'bg-accent' : ''
                    }`}
                  >
                    <Plus size={14} className="text-muted-foreground shrink-0" />
                    <span className="text-sm text-card-foreground">New requirement</span>
                    <span className="ml-auto text-[10px] text-muted-foreground shrink-0">Action</span>
                  </button>
                  <div className="border-t my-1 mx-1" />
                </>
              )}
              {combinedResults.length === 0 && !showCreateAction ? (
                <p className="text-sm text-muted-foreground text-center py-8">
                  {backendLoading ? 'Searching…' : 'No matches.'}
                </p>
              ) : (
                combinedResults.map((e, i) => {
                  const isBackend = 'kind_icon' in e;
                  if (isBackend) {
                    const sr = e as SearchResult;
                    const meta = ENTITY_META[sr.kind as keyof typeof ENTITY_META];
                    const Icon = meta?.icon ?? Search;
                    return (
                      <button
                        key={`b-${sr.kind}-${sr.id}`}
                        data-active={i + (showCreateAction ? 1 : 0) === cursor}
                        onClick={() => pick(sr)}
                        onMouseMove={() => setCursor(i + (showCreateAction ? 1 : 0))}
                        className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left transition-colors ${
                          i + (showCreateAction ? 1 : 0) === cursor ? 'bg-accent' : ''
                        }`}
                      >
                        <Icon size={14} className={`${meta?.cls ?? 'text-muted-foreground'} shrink-0`} />
                        <span className="font-mono text-xs text-muted-foreground shrink-0">{highlightMatch(sr.id, query)}</span>
                        <span className="text-sm text-card-foreground truncate">{highlightMatch(sr.name || sr.id, query)}</span>
                        {sr.snippet && (
                          <span className="text-[11px] text-muted-foreground/60 truncate hidden sm:inline max-w-[200px]">{sr.snippet}</span>
                        )}
                        <span className="ml-auto text-[10px] text-muted-foreground shrink-0 hidden sm:inline">{sr.kind_label}</span>
                      </button>
                    );
                  }
                  const entity = e as IndexedEntity;
                  const meta = ENTITY_META[entity.kind];
                  const Icon = meta.icon;
                  return (
                    <button
                      key={`${entity.kind}-${entity.id}`}
                      data-active={i + (showCreateAction ? 1 : 0) === cursor}
                      onClick={() => pick(entity)}
                      onMouseMove={() => setCursor(i + (showCreateAction ? 1 : 0))}
                      className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left transition-colors ${
                        i + (showCreateAction ? 1 : 0) === cursor ? 'bg-accent' : ''
                      }`}
                    >
                      <Icon size={14} className={`${meta.cls} shrink-0`} />
                      <span className="font-mono text-xs text-muted-foreground shrink-0">{highlightMatch(entity.id, query)}</span>
                      <span className="text-sm text-card-foreground truncate">{highlightMatch(entity.name || 'Untitled', query)}</span>
                      <span className="ml-auto text-[10px] text-muted-foreground shrink-0 hidden sm:inline">{meta.label}</span>
                    </button>
                  );
                })
              )}
            </div>

            <div className="flex items-center gap-3 px-3 py-2 border-t text-[10px] text-muted-foreground">
              <span><kbd className="border rounded px-1">↑</kbd> <kbd className="border rounded px-1">↓</kbd> navigate</span>
              <span><kbd className="border rounded px-1">↵</kbd> open</span>
              <span className="ml-auto">{entities.length} entities indexed</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
