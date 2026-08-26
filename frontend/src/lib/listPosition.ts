/**
 * Remembering where you were in a list.
 *
 * Scroll down the requirements list, open one, come back — the list used to
 * reopen at the top, having thrown away both your scroll position and any trace
 * of which row you had been looking at.
 *
 * Two facts are remembered per route, and they are deliberately separate:
 *
 *   - the scroll offset, which restores the *view*;
 *   - the id of the row you opened from that list, which restores your *place*
 *     even when the offset no longer means what it did (a filter changed, an
 *     item was added above, the window was resized between visits).
 *
 * The second is derived from navigation rather than from a click handler: a
 * detail route *is* "the row that was opened", so `listPathFor` maps
 * `/project/p/requirements/REQM0001` back to `/project/p/requirements` and
 * yields the id. That keeps every list page free of bookkeeping — nothing to
 * remember to wire up on the next list that gets a detail route.
 *
 * Storage is `sessionStorage`: per tab, cleared when the tab closes. A scroll
 * offset is a within-session convenience, not a preference worth surviving to
 * the next visit, and per-tab means two tabs on the same list do not fight.
 * Every access is guarded — Safari private mode throws on write, and the app
 * must not fail to render a list because it could not remember a scroll offset.
 */

const SCROLL_PREFIX = 'reqmesh.listScroll.';
const ENTITY_PREFIX = 'reqmesh.listEntity.';

/** Detail routes whose parent list should remember the opened row. The segment
 *  is the list path's last element; anything deeper is treated as an id. */
const DETAIL_PARENTS = new Set(['requirements', 'components', 'risks']);

function read(key: string): string | null {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    /* private mode, or the quota is full — remembering is not worth throwing */
  }
}

/**
 * The list a detail path belongs to, plus the id being shown, or null when the
 * path is not a detail route.
 *
 * Matches `<list>/<id>` where `<list>` is a known detail parent, so
 * `/project/p/requirements/REQM0001` resolves but `/project/p/requirements`
 * and `/project/p/settings/git` do not.
 */
export function listPathFor(pathname: string): { listPath: string; id: string } | null {
  const parts = pathname.replace(/\/+$/, '').split('/');
  if (parts.length < 2) return null;
  const id = parts[parts.length - 1];
  const parent = parts[parts.length - 2];
  if (!DETAIL_PARENTS.has(parent) || !id) return null;
  return { listPath: parts.slice(0, -1).join('/'), id };
}

export function saveScroll(path: string, top: number): void {
  // 0 is worth storing: it is the difference between "was at the top" and
  // "never visited", and only the latter should fall through to a row scroll.
  write(SCROLL_PREFIX + path, String(Math.round(top)));
}

export function readScroll(path: string): number | null {
  const raw = read(SCROLL_PREFIX + path);
  if (raw === null) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

export function saveLastEntity(listPath: string, id: string): void {
  write(ENTITY_PREFIX + listPath, id);
}

export function readLastEntity(listPath: string): string | null {
  return read(ENTITY_PREFIX + listPath);
}
