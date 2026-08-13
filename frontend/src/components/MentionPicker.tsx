import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { entityIconMeta } from './entities';
import { searchEntities, type IndexedEntity } from './entityIndex';

/**
 * The floating entity picker shown while an `@`-mention is being typed.
 *
 * Rendered in a portal and positioned from a caret rectangle, because both
 * callers sit inside scrollable, overflow-hidden containers — the rich-text
 * editor's rounded border box and the cards on the plain-text pages — where an
 * absolutely-positioned child would be clipped.
 *
 * Selection is driven from the parent: focus stays in the editor the whole
 * time, so the picker never takes it. It is a display surface with an index,
 * not a focusable listbox.
 */

/** Keeps the list short enough to scan without scrolling in the common case. */
const MAX_RESULTS = 8;
const PICKER_WIDTH = 340;
/** Gap between the caret line and the picker. */
const OFFSET = 4;

export interface MentionPickerProps {
  /** All linkable entities in the project. */
  entities: IndexedEntity[];
  /** Text typed after the `@`. */
  query: string;
  /** Caret rectangle in viewport coordinates. */
  anchor: DOMRect;
  /** Highlighted row, owned by the parent so keys work without focus. */
  activeIndex: number;
  onSelect: (entity: IndexedEntity) => void;
  /** Reports the current result list so the parent can bound its index. */
  onResults: (results: IndexedEntity[]) => void;
}

export default function MentionPicker({
  entities, query, anchor, activeIndex, onSelect, onResults,
}: MentionPickerProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 });

  const results = query
    ? searchEntities(entities, query, MAX_RESULTS)
    : entities.slice(0, MAX_RESULTS);

  // Report upward in an effect, not during render — calling a parent's setState
  // mid-render is what turns a picker into an infinite loop.
  useEffect(() => { onResults(results); },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [query, entities]);

  // Flip above the caret when there is no room below, and keep the picker
  // inside the viewport horizontally. Measured after layout so the real height
  // is known rather than assumed.
  useLayoutEffect(() => {
    const height = listRef.current?.offsetHeight ?? 0;
    const belowRoom = window.innerHeight - (anchor.bottom + OFFSET);
    const top = belowRoom >= height
      ? anchor.bottom + OFFSET
      : Math.max(OFFSET, anchor.top - height - OFFSET);
    const left = Math.min(
      Math.max(OFFSET, anchor.left),
      Math.max(OFFSET, window.innerWidth - PICKER_WIDTH - OFFSET),
    );
    setPos({ top, left });
  }, [anchor, results.length]);

  // Keep the highlighted row visible when arrowing past the fold.
  useEffect(() => {
    const el = listRef.current?.children[activeIndex] as HTMLElement | undefined;
    el?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  if (results.length === 0) {
    return createPortal(
      <div
        className="fixed z-[70] text-xs text-muted-foreground bg-popover border rounded-lg shadow-lg px-3 py-2"
        style={{ top: pos.top, left: pos.left, width: PICKER_WIDTH }}
      >
        No entity matches “{query}”
      </div>,
      document.body,
    );
  }

  return createPortal(
    // A combobox popup rendered at the caret; focus stays in the editor, so the
    // listbox/option roles are the ARIA 1.2 active-descendant pattern, not a
    // native select — there is no native element that stays unfocused here.
    /* oxlint-disable jsx-a11y/prefer-tag-over-role */
    <div
      ref={listRef}
      role="listbox"
      aria-label="Link an entity"
      className="fixed z-[70] max-h-64 overflow-y-auto bg-popover border rounded-lg shadow-lg py-1"
      style={{ top: pos.top, left: pos.left, width: PICKER_WIDTH }}
    >
      {results.map((entity, i) => {
        const meta = entityIconMeta(entity.kind, entity.subtype);
        const Icon = meta.icon;
        return (
          <div
            key={entity.id}
            role="option"
            // -1, not 0: the row is reachable programmatically and announced as
            // the active option, but must never enter the tab order — focus
            // stays in the editor so typing keeps filtering the list.
            tabIndex={-1}
            aria-selected={i === activeIndex}
            // The editor keeps focus, so this is a mousedown handler: a click
            // would fire after blur has already torn the mention down.
            onMouseDown={(e) => { e.preventDefault(); onSelect(entity); }}
            className={`flex items-center gap-2 px-2.5 py-1.5 cursor-pointer ${
              i === activeIndex ? 'bg-accent' : ''
            }`}
          >
            <Icon size={13} className={`shrink-0 ${meta.cls}`} />
            <span className="font-mono text-[11px] shrink-0">{entity.id}</span>
            <span className="text-xs text-muted-foreground truncate">{entity.name}</span>
          </div>
        );
      })}
    </div>,
    /* oxlint-enable jsx-a11y/prefer-tag-over-role */
    document.body,
  );
}
