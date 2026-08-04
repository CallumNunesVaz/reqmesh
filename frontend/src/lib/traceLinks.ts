import type { TraceModelLink } from '../api/client';

/**
 * Remove one trace link from the full set.
 *
 * Deliberately identity-based rather than index-based. The matrix page renders
 * a *filtered* view of the links, so a row index from that view addresses a
 * different element of the full array whenever a search or type filter is
 * active — index-based removal silently deleted an unrelated link, and traces
 * have neither a history entry nor an undo entry to recover from it.
 *
 * Object identity is exact: the filtered view holds the same references, so a
 * duplicate source/target/type pair removes only the row that was clicked.
 * Returns the original array when the link isn't present, so callers can skip
 * a pointless write.
 */
export function removeTraceLink(links: TraceModelLink[], link: TraceModelLink): TraceModelLink[] {
  const next = links.filter((l) => l !== link);
  return next.length === links.length ? links : next;
}
