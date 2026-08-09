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
  const alternation = sorted.map(escapeRe).join('|');
  // Two forms, explicit first:
  //   [[ID]] — written deliberately in the editor (the `@` picker inserts it).
  //            The server strips the editor's <span> wrapper, since `span` is
  //            not in its allowlist, so this bracket token is what actually
  //            persists — and the brackets must not survive into the render.
  //   ID     — a bare mention anywhere in prose, linked opportunistically.
  // Every id is escapeRe'd and joined as a flat alternation of literals — no
  // nesting, so no catastrophic backtracking. The ids are entity ids from this
  // project, not free user input.
  // nosemgrep: javascript.lang.security.audit.detect-non-literal-regexp.detect-non-literal-regexp
  const re = new RegExp(
    `\\[\\[(${alternation})\\]\\]|(?<![\\w-])(${alternation})(?![\\w-])`, 'g',
  );

  const parts: AutoLinkSegment[] = [];
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index! > last) parts.push({ text: text.slice(last, m.index) });
    parts.push({ id: m[1] ?? m[2] });
    last = m.index! + m[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts;
}

interface AutoLinkTextProps {
  text: string;
  /** Every known id in the project, mapped to its kind — see useEntityKinds. */
  kinds: Map<string, EntityKind>;
  className?: string;
  /** Optional decoration for the non-link segments — used to highlight modal
   *  keywords. Applied only to plain text, so an entity id is never re-styled
   *  as prose. Without this hook a caller has to re-implement this whole
   *  renderer to decorate text nodes. */
  renderPlain?: (text: string) => ReactNode;
}

/** Plain text with every mention of a known entity id turned into a link. */
export function AutoLinkText({ text, kinds, className, renderPlain }: AutoLinkTextProps) {
  const parts = autoLinkParts(text, kinds.keys());
  return (
    <span className={className}>
      {parts.map((p, i) =>
        'id' in p
          ? <EntityLink key={i} kind={kinds.get(p.id)!} id={p.id} className="text-inherit" />
          : <Fragment key={i}>{renderPlain ? renderPlain(p.text) : p.text}</Fragment>,
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

function nodeToReact(node: ChildNode, kinds: Map<string, EntityKind>, key: number,
                     renderPlain?: (text: string) => ReactNode): ReactNode {
  if (node.nodeType === Node.TEXT_NODE) {
    const text = node.textContent || '';
    if (!text) return null;
    return <AutoLinkText key={key} text={text} kinds={kinds} renderPlain={renderPlain} />;
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return null;
  const el = node as Element;

  // An explicit entity link written in the editor. Its text content is the
  // `[[ID]]` source form; rendering the children instead would leave the
  // brackets sitting either side of the link, which is what read mode used to
  // show. Rendered as a link directly so it carries the kind's icon like every
  // other reference in the app.
  const explicitId = el.getAttribute?.('data-entity-id');
  if (explicitId) {
    const kind = kinds.get(explicitId);
    return kind
      ? <EntityLink key={key} kind={kind} id={explicitId} className="text-inherit" />
      // Unknown id — the entity was deleted or renamed. Show the bare id
      // rather than a dead link or, worse, nothing at all.
      : <span key={key} className="font-mono text-muted-foreground">{explicitId}</span>;
  }

  const tag = el.tagName.toLowerCase();
  if (tag === 'br') return <br key={key} />;
  const children = Array.from(node.childNodes).map((c, i) => nodeToReact(c, kinds, i, renderPlain));
  if (!ALLOWED_TAGS.has(tag)) return <Fragment key={key}>{children}</Fragment>;
  return createElement(tag, { key }, children.length > 0 ? children : undefined);
}

interface AutoLinkHtmlProps {
  html: string;
  kinds: Map<string, EntityKind>;
  className?: string;
  /** See AutoLinkTextProps.renderPlain — threaded down to every text node. */
  renderPlain?: (text: string) => ReactNode;
}

/**
 * Read-only rendering of rich-text (TipTap) HTML with entity ids linked.
 * Used where the editor would otherwise render a disabled copy of itself.
 */
export function AutoLinkHtml({ html, kinds, className, renderPlain }: AutoLinkHtmlProps) {
  const doc = new DOMParser().parseFromString(html || '', 'text/html');
  const nodes = Array.from(doc.body.childNodes).map((n, i) => nodeToReact(n, kinds, i, renderPlain));
  return <div className={className}>{nodes}</div>;
}
