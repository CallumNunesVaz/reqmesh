import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import {
  listPathFor, readLastEntity, readScroll, saveLastEntity, saveScroll,
} from '../lib/listPosition';

/**
 * Restore scroll position and the last-opened row when returning to a list.
 *
 * Lives in `Layout` because the scroll container is Layout's `<main>`, not the
 * page — the pages render inside it and never see it. Driving it from here also
 * means no list page has to opt in: the behaviour arrives for every route, and
 * the "which row did I open" half is derived from the URL (see
 * `lib/listPosition`) rather than from per-page click handlers.
 *
 * Two things here are counter-intuitive, and both were measured rather than
 * reasoned about:
 *
 *  - **The offset cannot be read at navigation time.** `<main>` is not
 *    remounted across routes, so it looks safe to read `scrollTop` in an effect
 *    when the path changes. It is not: React removing the outgoing list's rows
 *    collapses `scrollHeight` during commit, and the browser clamps `scrollTop`
 *    to 0 right then — before any effect runs. Probed directly: scroll to 900,
 *    navigate, and the same element (proved identical by a marker attribute
 *    that survives the transition) already reads 0. So the offset is recorded
 *    *while scrolling*, and navigation only reads what is already stored.
 *
 *  - **Restoring cannot happen on the first frame either.** The list loads
 *    asynchronously, so the container is still short and assigning `scrollTop`
 *    is silently clamped to 0 again. The restore waits, in a bounded loop, for
 *    the content to grow tall enough to hold the offset.
 */

/** How long to keep waiting for the list to render before giving up. Lists load
 *  from one API call; well past that and the row genuinely is not there — it was
 *  filtered out, deleted, or is on another page of results. */
const SETTLE_WAIT_MS = 2000;

/** How long the returned-to row stays marked. Long enough to catch the eye on
 *  arrival, short enough that it does not read as a persistent selection.
 *  Matches the `.rt-last-visited` animation duration. */
const HIGHLIGHT_MS = 2000;

/**
 * The y below which content is actually visible: the bottom of any toolbar
 * pinned to the top of the scroll container, or the container's own top when
 * there is none. `.sticky` is Tailwind's class and the marker every list
 * header in this app uses, which keeps this a cheap indexed lookup rather than
 * a walk over thousands of rows.
 */
function stickyBottom(container: HTMLElement, viewTop: number): number {
  let bottom = viewTop;
  for (const node of container.querySelectorAll<HTMLElement>('.sticky')) {
    if (getComputedStyle(node).position !== 'sticky') continue;
    const box = node.getBoundingClientRect();
    // Only a header currently pinned at the top occludes the first rows; one
    // that has scrolled with the content does not.
    if (box.top <= viewTop + 1 && box.bottom > bottom) bottom = box.bottom;
  }
  return bottom;
}

export function useListPosition(containerRef: React.RefObject<HTMLElement | null>) {
  const location = useLocation();
  const path = location.pathname;
  const prevPath = useRef<string | null>(null);

  // Record the offset as it changes, not when we leave. See the note above.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    let raf = 0;
    const onScroll = () => {
      if (raf) return;                       // coalesce a burst into one write
      raf = requestAnimationFrame(() => {
        raf = 0;
        // A container that cannot scroll is not reporting anyone's position.
        // This is the guard that matters during navigation: as the outgoing
        // list's rows are removed the container briefly becomes unscrollable
        // and fires a scroll event at 0, which would otherwise erase the very
        // offset being kept.
        if (el.scrollHeight - el.clientHeight <= 0) return;
        saveScroll(path, el.scrollTop);
      });
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      el.removeEventListener('scroll', onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [path, containerRef]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) { prevPath.current = path; return; }

    // Opening a detail route records the row it was opened from, so returning
    // to the list can point at it.
    if (prevPath.current !== null && prevPath.current !== path) {
      const detail = listPathFor(path);
      if (detail && detail.listPath === prevPath.current) {
        saveLastEntity(detail.listPath, detail.id);
      }
    }
    prevPath.current = path;

    const stored = readScroll(path);
    const wantedId = readLastEntity(path);
    if (stored === null && !wantedId) return;

    let raf = 0;
    let cancelled = false;
    let offsetApplied = stored === null || stored === 0;
    const deadline = performance.now() + SETTLE_WAIT_MS;
    let marked: HTMLElement | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let lastHeight = -1;

    // Chrome's scroll anchoring keeps content visually steady by adjusting
    // scrollTop when things above the viewport change size — which is exactly
    // what it does to a restored offset as the list finishes laying out. Traced
    // with scrollIntoView and focus both patched to log: nothing in JS moved
    // the container, yet an assignment that read back as 700 was 724 on the
    // next frame, and because the scroll listener records that, the error
    // compounded across visits (700 -> 724 -> 750). Anchoring is suppressed for
    // the restore only, then handed back.
    const priorAnchor = el.style.overflowAnchor;
    el.style.overflowAnchor = 'none';
    let releaseTimer: ReturnType<typeof setTimeout> | undefined;
    const releaseAnchor = () => {
      if (releaseTimer) { clearTimeout(releaseTimer); releaseTimer = undefined; }
      el.style.overflowAnchor = priorAnchor;
    };
    /** Long enough to cover the layout passes that follow a list render, short
     *  enough that normal scrolling gets anchoring back almost immediately. */
    const scheduleRelease = () => {
      if (releaseTimer) return;
      releaseTimer = setTimeout(releaseAnchor, 500);
    };

    const settle = () => {
      if (cancelled) return;
      const expired = performance.now() >= deadline;

      if (!offsetApplied) {
        const height = el.scrollHeight;
        // Wait for the content to be tall enough *and* to have stopped growing.
        // Restoring into a list that is still rendering rows lets Chrome's
        // scroll anchoring nudge the offset afterwards to keep the content
        // steady, and because the scroll listener then records that nudged
        // value the error compounds on every visit — measured drifting
        // 700 -> 724 -> 750 over three round trips before this check.
        const settled = height === lastHeight;
        lastHeight = height;
        if (settled && height - el.clientHeight >= stored!) {
          el.scrollTop = stored!;
          offsetApplied = true;
        } else if (!expired) {
          raf = requestAnimationFrame(settle);
          return;
        }
      }

      if (wantedId) {
        const row = document.getElementById(`entity-${wantedId}`);
        if (!row) {
          if (!expired) raf = requestAnimationFrame(settle);
          return;
        }
        // Scrolling a row the restored offset already put on screen is a
        // visible jolt for no gain — but "on screen" has to mean *seen*, not
        // merely inside the container's rect. Every list page pins its search
        // and filter bar with `sticky top-0`, and a row tucked under it passes
        // a naive rect test while being completely hidden. Measured: the
        // restored row sat at y=86 in a container starting at y=56, behind a
        // header reaching y~150.
        const rowBox = row.getBoundingClientRect();
        const viewBox = el.getBoundingClientRect();
        const visible = rowBox.top >= stickyBottom(el, viewBox.top)
          && rowBox.bottom <= viewBox.bottom;
        if (!visible) row.scrollIntoView({ block: 'center' });

        row.classList.add('rt-last-visited');
        marked = row;
        timer = setTimeout(() => row.classList.remove('rt-last-visited'), HIGHLIGHT_MS);
      }
      // Hand anchoring back only after the layout that provoked it has
      // settled. Releasing in this same tick is useless: the compensation
      // lands on the *next* frame, so the suppression has to outlive it.
      scheduleRelease();
    };
    raf = requestAnimationFrame(settle);

    return () => {
      cancelled = true;
      releaseAnchor();
      cancelAnimationFrame(raf);
      if (timer) clearTimeout(timer);
      // Leaving mid-highlight must not strand the class on a row that React
      // may reuse for a different entity.
      marked?.classList.remove('rt-last-visited');
    };
  }, [path, containerRef]);
}
