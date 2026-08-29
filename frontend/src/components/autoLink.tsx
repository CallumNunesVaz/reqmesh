import { Fragment, createElement, type ReactNode } from 'react';
import { useParams } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';
import { EntityLink, type EntityKind } from './entities';
import { resolveParam, useParameterValues, type ParameterValue } from './parameterIndex';

export type AutoLinkSegment = { text: string } | { id: string } | { param: string };

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

// A parameter reference written as a bracket token: [[ID.param]]. The dot
// separates the owner id from the parameter name, which is exactly how the
// rich-text editor distinguishes a parameter mention from an entity link (whose
// ids never match this pattern). Recognised even when the parameter no longer
// exists, so a deleted reference renders broken rather than as literal text.
const PARAM_BRACKET_RE = /\[\[([\w-]+\.[\w.-]+)\]\]/g;

/** Split a text run on param-shaped bracket tokens it still contains. */
function pushParamBrackets(parts: AutoLinkSegment[], text: string): void {
  if (!text) return;
  let last = 0;
  for (const m of text.matchAll(PARAM_BRACKET_RE)) {
    if (m.index! > last) parts.push({ text: text.slice(last, m.index) });
    parts.push({ param: m[1] });
    last = m.index! + m[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
}

/**
 * Split free text into plain segments, known-entity-id segments and parameter
 * segments.
 *
 * Ids only match on their own — "REQ" must not light up inside "REQ-042", so
 * the boundary treats `-` like a word character (plain \b would split there).
 * Longest tokens win when one is a prefix of another, and the parameter branch
 * is tried before the id branch, so a known `REQM0002.temp_max` matches whole
 * rather than the id `REQM0002` being split out of it. A full stop after an id
 * is ordinary sentence punctuation, so the id boundary must still link
 * `REQM0002.`.
 */
export function autoLinkParts(text: string, ids: Iterable<string>, params?: Iterable<string>): AutoLinkSegment[] {
  const idList = [...ids].filter(Boolean);
  const paramList = [...(params ?? [])].filter(Boolean);

  if (!text) return [];

  // One map so the bracket branch can name a token's kind; sorted longest
  // first so a parameter ref matches before the entity id that is its prefix.
  const kindByToken = new Map<string, 'id' | 'param'>();
  for (const id of idList) kindByToken.set(id, 'id');
  for (const p of paramList) kindByToken.set(p, 'param');
  const combined = [...kindByToken.entries()].sort((a, b) => b[0].length - a[0].length);

  if (combined.length === 0) {
    const parts: AutoLinkSegment[] = [];
    pushParamBrackets(parts, text);
    return parts;
  }

  const paramAlt = paramList.slice().sort((a, b) => b.length - a.length).map(escapeRe).join('|');
  const idAlt = idList.slice().sort((a, b) => b.length - a.length).map(escapeRe).join('|');
  const combinedAlt = combined.map(([t]) => escapeRe(t)).join('|');

  // Three forms, explicit first:
  //   [[ID]] / [[ID.param]] — written deliberately in the editor (the `@`
  //            picker inserts it). The server strips the editor's <span>
  //            wrapper, since `span` is not in its allowlist, so this bracket
  //            token is what actually persists — and the brackets must not
  //            survive into the render.
  //   ID.param — a bare parameter mention, linked opportunistically. A
  //            trailing sentence `.` is not part of the name, so the boundary
  //            only excludes word/hyphen characters.
  //   ID      — a bare entity id. Tried after the parameter branch, so it can
  //            only win where the parameter branch did not. A full stop is
  //            ordinary sentence punctuation, so the boundary still links an id
  //            before `.` — it only declines when the `.` is followed by a word
  //            or hyphen character (the shape of a `ID.param` suffix).
  // Every token is escapeRe'd and joined as a flat alternation of literals — no
  // nesting, so no catastrophic backtracking. The tokens are entity ids and
  // parameter refs from this project, not free user input.
  // nosemgrep: javascript.lang.security.audit.detect-non-literal-regexp.detect-non-literal-regexp
  const alternatives = `\\[\\[(?<bracket>${combinedAlt})\\]\\]` +
    (paramAlt ? `|(?<![\\w-])(?<param>${paramAlt})(?![\\w-])` : '') +
    (idAlt ? `|(?<![\\w-])(?<id>${idAlt})(?!\\.?[\\w-])` : '');
  const re = new RegExp(alternatives, 'g');

  const parts: AutoLinkSegment[] = [];
  let last = 0;
  for (const m of text.matchAll(re)) {
    const g = m.groups!;
    let token: string;
    let kind: 'id' | 'param';
    if (g.id !== undefined) { token = g.id; kind = 'id'; }
    else if (g.param !== undefined) { token = g.param; kind = 'param'; }
    else { token = g.bracket; kind = kindByToken.get(token)!; }
    if (m.index! > last) pushParamBrackets(parts, text.slice(last, m.index));
    parts.push(kind === 'param' ? { param: token } : { id: token });
    last = m.index! + m[0].length;
  }
  if (last < text.length) pushParamBrackets(parts, text.slice(last));
  return parts;
}

/** A parameter mention in read mode. Resolved value reads as prose; an
 *  unresolvable ref renders in place, obviously broken. */
function ParamMention({ paramRef, params }: { paramRef: string; params: Map<string, ParameterValue> }) {
  const r = resolveParam(paramRef, params);
  if (r.kind === 'value') return <>{r.text}</>;
  const reason = params.has(paramRef) ? `parameter ${paramRef} has no value` : `parameter ${paramRef} not found`;
  return (
    <span
      title={reason}
      className="inline-flex items-center gap-0.5 align-baseline rounded-md bg-cs-orange/10 px-1 text-cs-orange"
    >
      <AlertTriangle size={11} className="shrink-0" />
      <span className="font-mono text-[0.9em]">{paramRef}</span>
    </span>
  );
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

/** Plain text with every mention of a known entity id turned into a link and
 *  every parameter reference resolved to its value. */
export function AutoLinkText({ text, kinds, className, renderPlain }: AutoLinkTextProps) {
  const { projectId } = useParams<{ projectId: string }>();
  const params = useParameterValues(projectId);
  const parts = autoLinkParts(text, kinds.keys(), params.keys());
  return (
    <span className={className}>
      {parts.map((p, i) =>
        'param' in p
          ? <ParamMention key={i} paramRef={p.param} params={params} />
          : 'id' in p
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
  'h1', 'h2', 'h3', 'code', 'pre', 'blockquote', 'img',
]);

/** True when an `<img>` `src` may be rendered in the read-only view. Only
 *  `data:image/…` and same-origin relative paths pass; `javascript:`,
 *  `vbscript:`, protocol-relative `//host` and any absolute URL are rejected —
 *  a remote image would quietly reintroduce an outbound request into an
 *  air-gapped bundle (see frontend/scripts/check-selfcontained.mjs). */
function isSafeImgSrc(src: string): boolean {
  // Match how a browser actually resolves the URL before reading the scheme,
  // per the WHATWG URL parser: ASCII tab and newline are stripped from
  // anywhere in the string, and leading/trailing C0 controls *and space* are
  // trimmed. Stripping only tab/newline/CR left `" https://evil/x.png"` and
  // `"\u000bhttps://…"` looking scheme-less, so they passed as relative paths
  // and loaded a remote image — an outbound request from a bundle whose
  // self-containment is only checked at build time.
  // The C0 range is the point, not an accident: `.trim()` would miss a leading
  // U+0001, which a browser strips and which would otherwise hide a scheme.
  // eslint-disable-next-line no-control-regex
  const stripLead = /^[\u0000-\u0020]+/;
  // eslint-disable-next-line no-control-regex
  const stripTrail = /[\u0000-\u0020]+$/;
  const cleaned = src
    .replace(/[\t\n\r]/g, '')
    .replace(stripLead, '')
    .replace(stripTrail, '');
  if (/^data:image\//i.test(cleaned)) return true;
  if (cleaned.startsWith('//')) return false;
  return !/^[A-Za-z][A-Za-z0-9+.-]*:/.test(cleaned);
}

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
  if (tag === 'img') {
    const src = el.getAttribute('src') || '';
    if (!isSafeImgSrc(src)) return null;
    // Only `src` and `alt` survive; every other attribute (e.g. `onerror`) is
    // dropped, which is what keeps this renderer a sanitising rebuild.
    const alt = el.getAttribute('alt');
    const props: { key: number; src: string; alt?: string } = { key, src };
    if (alt !== null) props.alt = alt;
    return createElement('img', props);
  }
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
 * Read-only rendering of rich-text (TipTap) HTML with entity ids linked and
 * parameter references resolved. Used where the editor would otherwise render
 * a disabled copy of itself.
 */
export function AutoLinkHtml({ html, kinds, className, renderPlain }: AutoLinkHtmlProps) {
  const doc = new DOMParser().parseFromString(html || '', 'text/html');
  const nodes = Array.from(doc.body.childNodes).map((n, i) => nodeToReact(n, kinds, i, renderPlain));
  return <div className={className}>{nodes}</div>;
}
