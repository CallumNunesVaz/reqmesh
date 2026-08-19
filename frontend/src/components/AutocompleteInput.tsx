import { useState, useRef, useEffect, useMemo, useCallback, useId } from 'react';

export interface Suggestion {
  id: string;
  label: string;
}

/**
 * Substring match on id and label, case-insensitive — the single filter rule
 * shared by every combobox in the app. Kept here, exported, so a second widget
 * (LinkEditor) reuses the exact same rule rather than drifting a copy.
 */
export function filterSuggestions(query: string, suggestions: Suggestion[]): Suggestion[] {
  if (!query) return suggestions;
  const q = query.toLowerCase();
  return suggestions.filter(
    (s) => s.id.toLowerCase().includes(q) || s.label.toLowerCase().includes(q)
  );
}

export interface ComboboxState {
  open: boolean;
  highlight: number;
}

export interface ComboboxKeyResult {
  open: boolean;
  highlight: number;
  /** The id to commit when the key selected the highlighted row. */
  selectId?: string;
}

/**
 * The keyboard contract of a suggestion popup, expressed as a pure function so
 * the arrow/Enter/Escape behaviour is unit-testable and cannot drift between
 * AutocompleteInput and anything that embeds it. `filtered` is the list that is
 * currently visible; Enter returns `selectId` and the caller commits it — the
 * popup never commits on its own.
 */
export function comboboxKeyDown(
  state: ComboboxState,
  key: string,
  filtered: Suggestion[],
): ComboboxKeyResult {
  const count = filtered.length;
  if (!state.open && (key === 'ArrowDown' || key === 'ArrowUp')) {
    return { open: true, highlight: state.highlight };
  }
  if (key === 'ArrowDown') {
    return { open: state.open, highlight: Math.min(state.highlight + 1, count - 1) };
  }
  if (key === 'ArrowUp') {
    return { open: state.open, highlight: Math.max(state.highlight - 1, 0) };
  }
  if (key === 'Enter') {
    if (state.open) {
      const item = filtered[state.highlight];
      if (item) return { open: false, highlight: 0, selectId: item.id };
    }
    return { open: state.open, highlight: state.highlight };
  }
  if (key === 'Escape') {
    return { open: false, highlight: state.highlight };
  }
  return { open: state.open, highlight: state.highlight };
}

interface AutocompleteInputProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  suggestions: Suggestion[];
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  /**
   * Called with the chosen id when a suggestion is committed (click or Enter).
   * When omitted, `onChange` receives the id instead, preserving the original
   * value-as-id behaviour for callers that treat the field's value as the id.
   */
  onSelect?: (id: string) => void;
}

export default function AutocompleteInput({
  id,
  value,
  onChange,
  suggestions,
  placeholder,
  className = '',
  disabled = false,
  onSelect,
}: AutocompleteInputProps) {
  const [open, setOpen] = useState(false);
  const [highlightIdx, setHighlightIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();

  const filtered = useMemo(
    () => filterSuggestions(value, suggestions),
    [value, suggestions],
  );

  const handleSelect = useCallback(
    (id: string) => {
      if (onSelect) onSelect(id);
      else onChange(id);
      setOpen(false);
      setHighlightIdx(0);
    },
    [onChange, onSelect],
  );

  const handleKeyDown = (e: React.KeyboardEvent) => {
    const key = e.key;
    if (key !== 'ArrowDown' && key !== 'ArrowUp' && key !== 'Enter' && key !== 'Escape') {
      return;
    }
    e.preventDefault();
    const next = comboboxKeyDown({ open, highlight: highlightIdx }, key, filtered);
    if (next.selectId) {
      handleSelect(next.selectId);
    } else {
      setOpen(next.open);
      setHighlightIdx(next.highlight);
    }
  };

  // Scroll highlighted item into view.
  useEffect(() => {
    const el = listRef.current?.children[highlightIdx] as HTMLElement | undefined;
    el?.scrollIntoView({ block: 'nearest' });
  }, [highlightIdx]);

  // Close on click outside.
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  return (
    <div ref={containerRef} className="relative">
      <input
        ref={inputRef}
        id={id}
        className={className}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setHighlightIdx(0);
        }}
        onFocus={() => { if (value && filtered.length > 0) setOpen(true); }}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        autoComplete="off"
        disabled={disabled}
        role="combobox"
        aria-expanded={open && filtered.length > 0}
        aria-controls={listboxId}
        aria-activedescendant={
          open && filtered.length > 0 ? `${listboxId}-${highlightIdx}` : undefined
        }
        aria-autocomplete="list"
      />
      {open && filtered.length > 0 && (
        /* oxlint-disable jsx-a11y/prefer-tag-over-role -- a combobox popup: there
           is no native element that reproduces a filterable suggestion list. */
        <div
          ref={listRef}
          id={listboxId}
          role="listbox"
          className="absolute z-50 left-0 min-w-full mt-1 max-h-52 overflow-y-auto rounded-lg border bg-popover shadow-lg"
        >
          {filtered.map((s, i) => (
            <div
              key={s.id}
              id={`${listboxId}-${i}`}
              role="option"
              aria-selected={i === highlightIdx}
              tabIndex={-1}
              onMouseDown={(e) => {
                e.preventDefault();
                handleSelect(s.id);
              }}
              onMouseEnter={() => setHighlightIdx(i)}
              className={`flex items-center gap-2 px-3 py-1.5 text-xs cursor-pointer transition-colors ${
                i === highlightIdx
                  ? 'bg-primary/10 text-primary'
                  : 'text-popover-foreground hover:bg-accent'
              }`}
            >
              <span className="font-mono text-[10px] opacity-50 shrink-0">{s.id}</span>
              <span className="whitespace-nowrap">{s.label}</span>
            </div>
          ))}
        </div>
        /* oxlint-enable jsx-a11y/prefer-tag-over-role */
      )}
    </div>
  );
}
