import { Fragment, createElement, type ReactNode } from 'react';
import { EntityLink, type EntityKind } from './entities';

export type AutoLinkSegment = { text: string } | { id: string };

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * Split free text into plain segments and known-entity-id segments.
 *
 * Ids only match on their own — "REQ" must not light up inside "REQ-042", so
 * the boundary treats `-` like a word character (plain \b would split there).
 * Longest ids win when one id is a prefix of another.
 */
export function autoLinkParts(text: string, ids: Iterable<string>): AutoLinkSegment[] {
  const sorted = [...ids].filter(Boolean).sort((a, b) => b.length - a.length);
  if (!text || sorted.length === 0) return text ? [{ text }] : [];
  const re = new RegExp(`(?<![\\w-])(${sorted.map(escapeRe).join('|')})(?![\\w-])`, 'g');

  const parts: AutoLinkSegment[] = [];
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index! > last) parts.push({ text: text.slice(last, m.index) });
    parts.push({ id: m[1] });
    last = m.index! + m[1].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts;
}

interface AutoLinkTextProps {
  text: string;
  /** Every known id in the project, mapped to its kind — see useEntityKinds. */
  kinds: Map<string, EntityKind>;
  className?: string;
}

/** Plain text with every mention of a known entity id turned into a link. */
export function AutoLinkText({ text, kinds, className }: AutoLinkTextProps) {
  const parts = autoLinkParts(text, kinds.keys());
  return (
    <span className={className}>
      {parts.map((p, i) =>
        'id' in p
          ? <EntityLink key={i} kind={kinds.get(p.id)!} id={p.id} className="text-inherit" />
          : <Fragment key={i}>{p.text}</Fragment>,
      )}
    </span>
  );
}

// The read-only rendering of rich text keeps only structural tags; anything
// else (and every attribute) is dropped, which doubles as sanitisation.
const ALLOWED_TAGS = new Set([
  'p', 'strong', 'em', 'b', 'i', 'u', 's', 'ul', 'ol', 'li',
  'h1', 'h2', 'h3', 'code', 'pre', 'blockquote',
]);

function nodeToReact(node: ChildNode, kinds: Map<string, EntityKind>, key: number): ReactNode {
  if (node.nodeType === Node.TEXT_NODE) {
    const text = node.textContent || '';
    if (!text) return null;
    return <AutoLinkText key={key} text={text} kinds={kinds} />;
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return null;
  const tag = (node as Element).tagName.toLowerCase();
  if (tag === 'br') return <br key={key} />;
  const children = Array.from(node.childNodes).map((c, i) => nodeToReact(c, kinds, i));
  if (!ALLOWED_TAGS.has(tag)) return <Fragment key={key}>{children}</Fragment>;
  return createElement(tag, { key }, children.length > 0 ? children : undefined);
}

interface AutoLinkHtmlProps {
  html: string;
  kinds: Map<string, EntityKind>;
  className?: string;
}

/**
 * Read-only rendering of rich-text (TipTap) HTML with entity ids linked.
 * Used where the editor would otherwise render a disabled copy of itself.
 */
export function AutoLinkHtml({ html, kinds, className }: AutoLinkHtmlProps) {
  const doc = new DOMParser().parseFromString(html || '', 'text/html');
  const nodes = Array.from(doc.body.childNodes).map((n, i) => nodeToReact(n, kinds, i));
  return <div className={className}>{nodes}</div>;
}
