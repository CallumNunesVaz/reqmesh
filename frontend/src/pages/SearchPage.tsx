import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { Search, X, SlidersHorizontal } from 'lucide-react';
import { api, type SearchResult } from '../api/client';
import { ENTITY_META, EntityLink, type EntityKind } from '../components/entities';
import { BACKEND_KIND_TO_ENTITY, SEARCHABLE_KINDS } from '../lib/searchKinds';
import { useStore } from '../store';

const TRUNCATION_LIMIT = 50;

function toEntityKind(backendKind: string): EntityKind | null {
  return BACKEND_KIND_TO_ENTITY[backendKind] ?? null;
}

// The backend's kind names are not all EntityKind values (change_request vs
// change), so the search filter must use the backend names rather than
// ENTITY_META keys. The filter list is explicit instead of derived so it does
// not accidentally include subtypes like COMPONENT_TYPE_META entries.

const KIND_LABELS: Record<string, string> = {
  change_request: 'Change Request',
  comment: 'Comment',
};

const FILTER_KINDS: { value: string; label: string }[] = [
  { value: '', label: 'All kinds' },
  ...SEARCHABLE_KINDS.map((key) => ({
    value: key,
    label: KIND_LABELS[key]
      ?? ENTITY_META[key as EntityKind]?.label
      ?? key.charAt(0).toUpperCase() + key.slice(1),
  })),
];

export default function SearchPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const dataVersion = useStore((s) => s.dataVersion);

  const q = searchParams.get('q') || '';
  const kind = searchParams.get('kind') || '';

  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [localQuery, setLocalQuery] = useState(q);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const seqRef = useRef(0);

  const updateSearchParams = useCallback((newQ: string, newKind: string) => {
    const params = new URLSearchParams();
    if (newQ) params.set('q', newQ);
    if (newKind) params.set('kind', newKind);
    setSearchParams(params, { replace: true });
  }, [setSearchParams]);

  // Debounce local input to URL params
  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      if (localQuery !== q) {
        updateSearchParams(localQuery, kind);
      }
    }, 300);
    return () => clearTimeout(debounceRef.current);
  }, [localQuery]);  // eslint-disable-line react-hooks/exhaustive-deps

  // Sync local input when URL changes externally
  useEffect(() => {
    setLocalQuery(q);
  }, [q]);

  // Fetch when URL params change
  useEffect(() => {
    if (!projectId) return;
    if (!q.trim()) {
      setResults([]);
      setError('');
      return;
    }
    const seq = ++seqRef.current;
    setLoading(true);
    setError('');
    api.searchProject(projectId, q.trim(), kind || undefined).then((res) => {
      if (seq !== seqRef.current) return;
      setResults(res.results);
    }).catch((e) => {
      if (seq !== seqRef.current) return;
      setError(e.message || 'Search failed');
    }).finally(() => {
      if (seq === seqRef.current) setLoading(false);
    });
  }, [projectId, q, kind, dataVersion]);

  const showingTruncation = results.length === TRUNCATION_LIMIT;

  const handleKindChange = (newKind: string) => {
    updateSearchParams(localQuery, newKind);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-4 border-b space-y-3">
        <h1 className="text-lg font-semibold text-card-foreground">Search</h1>
        <div className="flex items-center gap-2">
          <div className="relative flex-1 max-w-xl">
            <Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="search"
              className="w-full pl-8 pr-8 py-2 text-sm bg-muted/40 border rounded-lg outline-none focus:border-primary/60 text-foreground placeholder:text-muted-foreground"
              placeholder="Search entities…"
              value={localQuery}
              onChange={(e) => setLocalQuery(e.target.value)}
            />
            {localQuery && (
              <button
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                onClick={() => { setLocalQuery(''); updateSearchParams('', kind); }}
                aria-label="Clear search"
              >
                <X size={14} />
              </button>
            )}
          </div>
          <div className="relative">
            <SlidersHorizontal size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
            <select
              className="select pl-7"
              value={kind}
              onChange={(e) => handleKindChange(e.target.value)}
            >
              {FILTER_KINDS.map((k) => (
                <option key={k.value} value={k.value}>{k.label}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {error && (
          <div className="mb-4 text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</div>
        )}

        {!q.trim() ? (
          <div className="text-center py-16">
            <Search size={48} className="mx-auto text-muted-foreground/40 mb-4" />
            <p className="text-card-foreground font-medium">Search across all entities</p>
            <p className="text-sm text-muted-foreground mt-1">
              Type a query above to search requirements, components, risks, and more.
            </p>
          </div>
        ) : loading ? (
          <div className="text-center py-16 text-sm text-muted-foreground">Searching…</div>
        ) : results.length === 0 ? (
          <div className="text-center py-16">
            <Search size={48} className="mx-auto text-muted-foreground/40 mb-4" />
            <p className="text-card-foreground font-medium">No results for &ldquo;{q.trim()}&rdquo;</p>
            <p className="text-sm text-muted-foreground mt-1">Try a different query or adjust the kind filter.</p>
          </div>
        ) : (
          <>
            {showingTruncation && (
              <div className="mb-4 text-sm bg-muted/40 rounded-lg px-3 py-2 text-muted-foreground">
                Showing the first {TRUNCATION_LIMIT} matches — narrow your search to see more specific results.
              </div>
            )}
            <div className="card p-2">
              {results.map((r) => {
                const ek = toEntityKind(r.kind);
                return (
                  <div
                    key={`${r.kind}-${r.id}`}
                    className="flex items-center gap-3 px-3 py-2.5 hover:bg-accent/50 rounded-lg transition-colors"
                  >
                    {ek ? (
                      <EntityLink kind={ek} id={r.id} name={r.name} showIcon className="min-w-0 flex-1" />
                    ) : (
                      <span className="font-mono text-xs text-muted-foreground shrink-0">{r.id}</span>
                    )}
                    {r.snippet && (
                      <span className="text-xs text-muted-foreground/70 truncate max-w-xs hidden sm:inline">
                        {r.snippet}
                      </span>
                    )}
                    <span className="ml-auto text-3xs text-muted-foreground shrink-0 hidden sm:inline">
                      {r.kind_label}
                    </span>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
