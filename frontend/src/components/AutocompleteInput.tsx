import { useState, useRef, useEffect, useMemo, useCallback, useId } from 'react';

interface Suggestion {
  id: string;
  label: string;
}

interface AutocompleteInputProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  suggestions: Suggestion[];
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

export default function AutocompleteInput({
  id,
  value,
  onChange,
  suggestions,
  placeholder,
  className = '',
  disabled = false,
}: AutocompleteInputProps) {
  const [open, setOpen] = useState(false);
  const [highlightIdx, setHighlightIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();

  const filtered = useMemo(() => {
    if (!value) return suggestions;
    const q = value.toLowerCase();
    return suggestions.filter(
      (s) => s.id.toLowerCase().includes(q) || s.label.toLowerCase().includes(q)
    );
  }, [value, suggestions]);

  const handleSelect = useCallback(
    (id: string) => {
      onChange(id);
      setOpen(false);
      setHighlightIdx(0);
    },
    [onChange],
  );

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      setOpen(true);
      e.preventDefault();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlightIdx((prev) => Math.min(prev + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightIdx((prev) => Math.max(prev - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (open && filtered[highlightIdx]) {
        handleSelect(filtered[highlightIdx].id);
      }
    } else if (e.key === 'Escape') {
      setOpen(false);
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
