/**
 * Which collections force the graph canvas to re-run its layout.
 *
 * The SSE mutation event names the collection that changed; the canvas is only
 * re-fetched and re-laid-out for the ones whose data it actually renders, so a
 * risk or comment edit no longer re-solves and re-lays-out the whole graph on
 * every connected client.
 */
export const GRAPH_KINDS: ReadonlySet<string> = new Set([
  'requirements',
  'components',
  'traces',
  'verification',
  'definitions',
  'baselines',
]);

export function graphRelevant(collection: string | null | undefined): boolean {
  return !!collection && GRAPH_KINDS.has(collection);
}

/**
 * Query keys that are *derived* from a collection and go stale with it, even
 * though they are not a collection themselves: the parametric evaluation is
 * solved from requirements, components, definitions and verification, and the
 * project record carries the baseline and system-state definitions.
 */
export const DERIVED_QUERY_KEYS: Readonly<Record<string, readonly string[]>> = {
  requirements: ['evaluation'],
  components: ['evaluation'],
  definitions: ['evaluation'],
  verification: ['evaluation'],
  baselines: ['project'],
  'system-states': ['project'],
};

/** Every top-level query key to invalidate when `collection` changes. */
export function queryKeysFor(collection: string): string[] {
  return [collection, ...(DERIVED_QUERY_KEYS[collection] ?? [])];
}

/**
 * The collections a mutation event asks the client to refresh.
 *
 * The server sends `collections` (the keyed collection plus the ones the write
 * also rewrote, e.g. a requirement edit mirrors verification-case ownership);
 * an older server sends only `collection`. Empty means the change could not be
 * attributed and the client must refresh everything.
 */
export function mutationCollections(data: unknown): string[] {
  if (!data || typeof data !== 'object') return [];
  const d = data as { collection?: unknown; collections?: unknown };
  if (Array.isArray(d.collections)) {
    const kinds = d.collections.filter((k): k is string => typeof k === 'string' && k.length > 0);
    if (kinds.length) return kinds;
  }
  return typeof d.collection === 'string' && d.collection ? [d.collection] : [];
}
