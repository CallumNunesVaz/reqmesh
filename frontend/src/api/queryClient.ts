import { QueryClient } from '@tanstack/react-query';

/**
 * The app's server-state cache.
 *
 * Data is refreshed by an entity-scoped invalidation signal: the SSE listener
 * bumps `entityVersions[kind]`, and the bridge in `Layout` turns that into
 * `invalidateQueries({ queryKey: [kind] })`. Local mutations bump the global
 * `dataVersion`, which invalidates everything. This replaces the hand-rolled
 * "reload on a global counter" pattern with per-collection cache entries.
 *
 * `staleTime` is short because the invalidation signal is the real freshness
 * mechanism; the window only avoids a refetch on every remount.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});
