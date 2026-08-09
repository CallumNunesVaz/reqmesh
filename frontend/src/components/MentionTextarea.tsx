import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { loadEntityIndex, type IndexedEntity } from './entityIndex';
import { caretRect, findMentionTrigger } from './mentions';
import MentionPicker from './MentionPicker';

/**
 * A `<textarea>` with the same `@`-mention picker as the rich-text editor.
 *
 * Drop-in for the plain-text fields that already cross-link on read — decision
 * records, specifications, change requests, verification steps. Those store
 * plain text, so the picker inserts the **bare id**: `AutoLinkText` already
 * turns a bare id into a link with its kind's icon, and wrapping it in `[[…]]`
 * would only put punctuation into the YAML, the exports and every other
 * renderer for no gain.
 *
 * The icon therefore appears on read, not while typing — a textarea can only
 * hold text. The rich-text editor is the surface that shows a live chip.
 */

export interface MentionTextareaProps
  extends Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, 'onChange' | 'value'> {
  value: string;
  onChange: (value: string) => void;
}

export default function MentionTextarea({ value, onChange, ...rest }: MentionTextareaProps) {
  const { projectId } = useParams<{ projectId: string }>();
  const ref = useRef<HTMLTextAreaElement>(null);

  const [entities, setEntities] = useState<IndexedEntity[]>([]);
  const [mention, setMention] = useState<{ query: string; from: number; to: number; rect: DOMRect } | null>(null);
  const [index, setIndex] = useState(0);
  const results = useRef<IndexedEntity[]>([]);

  useEffect(() => {
    if (!projectId || rest.disabled) return;
    let live = true;
    loadEntityIndex(projectId).then((list) => { if (live) setEntities(list); });
    return () => { live = false; };
  }, [projectId, rest.disabled]);

  const refresh = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const caret = el.selectionStart ?? 0;
    // A selection is not a caret; picking into one would replace text the user
    // deliberately highlighted.
    if (el.selectionStart !== el.selectionEnd) { setMention(null); return; }
    const trigger = findMentionTrigger(el.value, caret);
    if (!trigger) { setMention(null); return; }
    setMention({ ...trigger, rect: caretRect(el, caret) });
    setIndex(0);
  }, []);

  const select = useCallback((entity: IndexedEntity) => {
    const el = ref.current;
    if (!el || !mention) return;
    // Trailing space so the next word does not run into the id — and so the
    // bare-id link boundary in AutoLinkText still matches.
    const next = `${value.slice(0, mention.from)}${entity.id} ${value.slice(mention.to)}`;
    onChange(next);
    setMention(null);
    const caret = mention.from + entity.id.length + 1;
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(caret, caret); });
  }, [mention, onChange, value]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (!mention) return;
    const count = results.current.length;
    if (e.key === 'Escape') { e.preventDefault(); setMention(null); return; }
    if (count === 0) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setIndex((i) => (i + 1) % count); return; }
    if (e.key === 'ArrowUp') { e.preventDefault(); setIndex((i) => (i - 1 + count) % count); return; }
    if (e.key === 'Enter' || e.key === 'Tab') {
      const picked = results.current[index];
      if (picked) { e.preventDefault(); select(picked); }
    }
  };

  return (
    <>
      <textarea
        {...rest}
        ref={ref}
        value={value}
        onChange={(e) => { onChange(e.target.value); requestAnimationFrame(refresh); }}
        onKeyUp={refresh}
        onClick={refresh}
        onKeyDown={onKeyDown}
        // The picker selects on mousedown, which lands before blur, so closing
        // here cannot swallow the click.
        onBlur={(e) => { setMention(null); rest.onBlur?.(e); }}
      />
      {mention && !rest.disabled && (
        <MentionPicker
          entities={entities}
          query={mention.query}
          anchor={mention.rect}
          activeIndex={index}
          onSelect={select}
          onResults={(r) => { results.current = r; }}
        />
      )}
    </>
  );
}
