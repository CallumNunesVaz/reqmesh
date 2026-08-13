/**
 * Selection maths for list rows, kept pure so it can be tested without a DOM.
 *
 * These are checkbox lists, so a plain click keeps meaning "toggle this one".
 * The desktop convention where a plain click *replaces* the selection would be
 * wrong here — clicking a ticked checkbox to wipe every other selection is not
 * what a checkbox promises, and it would silently undo work already done.
 */

export interface SelectionModifiers {
  shiftKey?: boolean;
  ctrlKey?: boolean;
  metaKey?: boolean;
}

/**
 * The selection after clicking `id`.
 *
 * `orderedIds` must be the ids **in display order**, after filtering and
 * collapsing: a Shift range is only meaningful over rows the user can see, and
 * ranging through a collapsed branch would select records that never appeared.
 *
 * Shift extends from `anchor` to `id` inclusive, and the clicked row decides
 * the whole range's new state — so a Shift+click can sweep a mis-selected block
 * off as easily as it selects one. With no usable anchor (never clicked, or the
 * anchor has since been filtered away) it degrades to a plain toggle rather
 * than guessing at a range that no longer exists.
 *
 * Ctrl/Cmd is a toggle, identical to a plain click. It is handled explicitly so
 * the habit carried over from other list UIs behaves rather than doing nothing.
 */
export function nextSelection(
  orderedIds: readonly string[],
  selected: ReadonlySet<string>,
  id: string,
  anchor: string | null,
  modifiers: SelectionModifiers = {},
): Set<string> {
  const next = new Set(selected);

  if (modifiers.shiftKey && anchor !== null && anchor !== id) {
    const from = orderedIds.indexOf(anchor);
    const to = orderedIds.indexOf(id);
    if (from !== -1 && to !== -1) {
      const [lo, hi] = from < to ? [from, to] : [to, from];
      const turningOn = !selected.has(id);
      for (let i = lo; i <= hi; i += 1) {
        if (turningOn) next.add(orderedIds[i]);
        else next.delete(orderedIds[i]);
      }
      return next;
    }
  }

  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

/**
 * The anchor after clicking `id`: the last row clicked *without* Shift.
 * A Shift+click leaves it alone, so several ranges can be swept from one anchor.
 */
export function nextAnchor(
  id: string,
  anchor: string | null,
  modifiers: SelectionModifiers = {},
): string | null {
  return modifiers.shiftKey ? anchor : id;
}
