import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Search } from 'lucide-react';
import { ENTITY_META } from './entities';
import { loadEntityIndex, searchEntities, type IndexedEntity } from './entityIndex';
import { useStore } from '../store';

/** Header button and other far-away UI can open the palette with this. */
export const OPEN_PALETTE_EVENT = 'rt-open-palette';

/**
 * Ctrl/Cmd+K jump-to-anything. Searches every entity in the project by id,
 * name and description, and navigates to the pick — the fastest traversal
 * path between any two things in the app.
 */
export default function CommandPalette({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [entities, setEntities] = useState<IndexedEntity[]>([]);
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const dataVersion = useStore((s) => s.dataVersion);

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

  const results = searchEntities(entities, query);

  const pick = useCallback((entity: IndexedEntity) => {
    setOpen(false);
    navigate(ENTITY_META[entity.kind].path(projectId, entity.id));
  }, [navigate, projectId]);

  const onInputKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { setOpen(false); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor((c) => Math.min(c + 1, results.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setCursor((c) => Math.max(c - 1, 0)); }
    else if (e.key === 'Enter' && results[cursor]) { e.preventDefault(); pick(results[cursor]); }
    else return;
    // Keep the highlighted row in view while arrowing through.
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
              {results.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-8">No matches.</p>
              ) : (
                results.map((e, i) => {
                  const meta = ENTITY_META[e.kind];
                  const Icon = meta.icon;
                  return (
                    <button
                      key={`${e.kind}-${e.id}`}
                      data-active={i === cursor}
                      onClick={() => pick(e)}
                      onMouseMove={() => setCursor(i)}
                      className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left transition-colors ${
                        i === cursor ? 'bg-accent' : ''
                      }`}
                    >
                      <Icon size={14} className={`${meta.cls} shrink-0`} />
                      <span className="font-mono text-xs text-muted-foreground shrink-0">{e.id}</span>
                      <span className="text-sm text-card-foreground truncate">{e.name || 'Untitled'}</span>
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
