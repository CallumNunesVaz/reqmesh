import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Sigma } from 'lucide-react';
import { entityIconMeta } from './entities';
import { searchEntities, type IndexedEntity } from './entityIndex';
import { searchParameters, type MentionOption } from './mentions';
import { formatParamValue, type ParameterRef } from './parameterIndex';

/**
 * The floating mention picker shown while an `@`-mention is being typed.
 *
 * Rendered in a portal and positioned from a caret rectangle, because both
 * callers sit inside scrollable, overflow-hidden containers — the rich-text
 * editor's rounded border box and the cards on the plain-text pages — where an
 * absolutely-positioned child would be clipped.
 *
 * Offers entities and, additionally, parameters: the holder's own by bare name,
 * everyone else's as `ID.param`.
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
  /** All parameters in the project. */
  parameters: ParameterRef[];
  /** The entity whose parameters are "own" (offered by bare name). */
  holderId?: string;
  /** Text typed after the `@`. */
  query: string;
  /** Caret rectangle in viewport coordinates. */
  anchor: DOMRect;
  /** Highlighted row, owned by the parent so keys work without focus. */
  activeIndex: number;
  onSelect: (option: MentionOption) => void;
  /** Reports the current result list so the parent can bound its index. */
  onResults: (results: MentionOption[]) => void;
}

export default function MentionPicker({
  entities, parameters, holderId, query, anchor, activeIndex, onSelect, onResults,
}: MentionPickerProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 });

  const entityOptions: MentionOption[] = (query
    ? searchEntities(entities, query, MAX_RESULTS)
    : entities.slice(0, MAX_RESULTS)
  ).map((entity) => ({ type: 'entity', entity }));
  const paramOptions = searchParameters(parameters, holderId, query, MAX_RESULTS);
  // With a query the picker is narrowing in on a specific reference, so
  // parameters (the more specific match) lead; while browsing, keep the
  // existing head-of-index entity order and append parameters below.
  const results = (query
    ? [...paramOptions, ...entityOptions]
    : [...entityOptions, ...paramOptions]
  ).slice(0, MAX_RESULTS);

  // Report upward in an effect, not during render — calling a parent's setState
  // mid-render is what turns a picker into an infinite loop.
  useEffect(() => { onResults(results); },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [query, entities, parameters, holderId]);

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
        No entity or parameter matches “{query}”
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
      aria-label="Link an entity or parameter"
      className="fixed z-[70] max-h-64 overflow-y-auto bg-popover border rounded-lg shadow-lg py-1"
      style={{ top: pos.top, left: pos.left, width: PICKER_WIDTH }}
    >
      {results.map((result, i) => {
        if (result.type === 'param') {
          return (
            <div
              key={result.ref}
              role="option"
              tabIndex={-1}
              aria-selected={i === activeIndex}
              onMouseDown={(e) => { e.preventDefault(); onSelect(result); }}
              className={`flex items-center gap-2 px-2.5 py-1.5 cursor-pointer ${
                i === activeIndex ? 'bg-accent' : ''
              }`}
            >
              <Sigma size={13} className="shrink-0 text-cs-teal" />
              <span className="font-mono text-2xs shrink-0">{result.name}</span>
              <span className="text-xs text-muted-foreground truncate">
                {result.value != null ? paramDisplay(result.value, result.unit) : result.unit || ''}
              </span>
            </div>
          );
        }
        const entity = result.entity;
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
            onMouseDown={(e) => { e.preventDefault(); onSelect(result); }}
            className={`flex items-center gap-2 px-2.5 py-1.5 cursor-pointer ${
              i === activeIndex ? 'bg-accent' : ''
            }`}
          >
            <Icon size={13} className={`shrink-0 ${meta.cls}`} />
            <span className="font-mono text-2xs shrink-0">{entity.id}</span>
            <span className="text-xs text-muted-foreground truncate">{entity.name}</span>
          </div>
        );
      })}
    </div>,
    /* oxlint-enable jsx-a11y/prefer-tag-over-role */
    document.body,
  );
}

/** `value unit`, using the same number formatter as read-mode resolution. */
function paramDisplay(value: number, unit: string): string {
  return unit ? `${formatParamValue(value)} ${unit}` : formatParamValue(value);
}
