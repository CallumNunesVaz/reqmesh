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
