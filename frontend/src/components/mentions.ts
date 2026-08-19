/**
 * Shared `@`-mention plumbing.
 *
 * Two editing surfaces need the same trigger behaviour: the TipTap rich-text
 * editor (requirement, component, risk and baseline descriptions) and the plain
 * `<textarea>` fields (decisions, specifications, change requests, verification).
 * Keeping the rule in one place is what stops `@` meaning subtly different
 * things depending on which field you are standing in.
 *
 * What the two surfaces insert differs, and deliberately so:
 *   - rich text stores an explicit `[[ID]]` entity-link node, which is the
 *     format the editor already round-trips;
 *   - plain text stores the **bare id**, because `AutoLinkText` already links
 *     bare ids on read and adding markup would put `[[…]]` in front of users of
 *     every other renderer, the YAML file and the exports.
 * Neither introduces a new storage format — `@` is an input affordance only.
 *
 * Parameters extend the same two rules rather than adding a third:
 *   - rich text stores `[[ID.param]]` — the same bracket token, with the owner
 *     id and parameter name separated by a dot;
 *   - plain text stores the bare `ID.param`.
 * A bare-name pick of the holder's own parameter is still persisted fully
 * qualified, because a description can be quoted elsewhere and `temp_max`
 * alone has no meaning outside its requirement.
 */

import type { IndexedEntity } from './entityIndex';
import type { ParameterRef } from './parameterIndex';

/** One selectable row in the `@` picker: an entity or a parameter. */
export interface ParamOption {
  type: 'param';
  ref: string;
  name: string;
  unit: string;
  value: number | null;
  own: boolean;
}

export type MentionOption = { type: 'entity'; entity: IndexedEntity } | ParamOption;

export interface MentionTrigger {
  /** Text typed after the `@`; empty right after typing the `@` itself. */
  query: string;
  /** Offset of the `@` character. */
  from: number;
  /** Offset just past the query — i.e. the caret. */
  to: number;
}

/**
 * A mention query is short. The cap stops a stray `@` early in a paragraph
 * from keeping the picker open across a whole sentence of subsequent typing.
 */
const MAX_QUERY_LENGTH = 40;

/** Ids may contain these; they must not terminate the query. */
const ID_PUNCTUATION = new Set(['-', '_', '.']);

function isQueryChar(ch: string): boolean {
  return /[\w]/.test(ch) || ID_PUNCTUATION.has(ch);
}

/**
 * Find an active mention immediately before `caret`.
 *
 * The `@` must start a word — preceded by nothing, whitespace, or an opening
 * bracket. Without that rule an email address turns the picker on halfway
 * through typing it, which is the single most common way this feature becomes
 * an irritation rather than a shortcut.
 */
export function findMentionTrigger(text: string, caret: number): MentionTrigger | null {
  if (caret < 1 || caret > text.length) return null;

  let i = caret - 1;
  while (i >= 0 && isQueryChar(text[i])) i -= 1;

  if (i < 0 || text[i] !== '@') return null;

  const from = i;
  const query = text.slice(from + 1, caret);
  if (query.length > MAX_QUERY_LENGTH) return null;

  const before = from > 0 ? text[from - 1] : '';
  if (before && !/[\s([{<]/.test(before)) return null;

  return { query, from, to: caret };
}

/**
 * Screen position of the caret inside a `<textarea>`.
 *
 * A textarea exposes no caret rectangle, so the text up to the caret is
 * re-rendered into an off-screen div that copies every property affecting
 * layout, and the position of a marker span is measured. The copied property
 * list matters: miss `padding` or `letterSpacing` and the picker drifts further
 * from the caret the longer the line gets.
 */
const MIRRORED_STYLES = [
  'boxSizing', 'width', 'borderTopWidth', 'borderRightWidth', 'borderBottomWidth',
  'borderLeftWidth', 'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
  'fontFamily', 'fontSize', 'fontWeight', 'fontStyle', 'letterSpacing',
  'lineHeight', 'textTransform', 'textIndent', 'whiteSpace', 'wordSpacing',
  'wordBreak', 'overflowWrap', 'tabSize',
] as const;

export function caretRect(textarea: HTMLTextAreaElement, caret: number): DOMRect {
  const mirror = document.createElement('div');
  const computed = window.getComputedStyle(textarea);

  for (const prop of MIRRORED_STYLES) {
    mirror.style[prop as never] = computed[prop as never];
  }
  mirror.style.position = 'absolute';
  mirror.style.visibility = 'hidden';
  mirror.style.whiteSpace = 'pre-wrap';
  mirror.style.overflowWrap = 'break-word';
  mirror.style.height = 'auto';
  mirror.style.top = '0';
  mirror.style.left = '-9999px';

  mirror.textContent = textarea.value.slice(0, caret);
  const marker = document.createElement('span');
  // A zero-width space gives the span a measurable box even at a line start.
  marker.textContent = '​';
  mirror.appendChild(marker);
  document.body.appendChild(mirror);

  const box = textarea.getBoundingClientRect();
  const top = box.top + marker.offsetTop - textarea.scrollTop;
  const left = box.left + marker.offsetLeft - textarea.scrollLeft;
  const height = parseFloat(computed.lineHeight) || marker.offsetHeight || 16;

  document.body.removeChild(mirror);

  return new DOMRect(left, top, 0, height);
}

/**
 * Rank the project's parameters against a mention query.
 *
 * The holder's own parameters are offered by bare name (and persist fully
 * qualified); everyone else's are offered as `ID.param`. An empty query returns
 * own parameters first, then the rest, so a user browsing the picker sees the
 * names they can type directly.
 */
export function searchParameters(
  parameters: ParameterRef[],
  holderId: string | undefined,
  query: string,
  limit = 8,
): ParamOption[] {
  const q = query.trim().toLowerCase();
  const scored: { option: ParamOption; score: number }[] = [];

  for (const p of parameters) {
    const own = holderId !== undefined && p.entityId === holderId;
    const label = own ? p.name : p.ref;
    // Match against both the display label and the qualified ref, so `@temp`
    // also finds a parameter whose owner is some other requirement.
    const targets = (own ? [p.name, p.ref] : [p.ref, p.name]).map((s) => s.toLowerCase());
    let score = -1;
    if (!q) {
      score = own ? 6200 : 5000;
    } else if (targets.includes(q)) {
      score = 6000;
    } else if (targets.some((t) => t.startsWith(q))) {
      score = 5700;
    } else if (targets.some((t) => t.includes(q))) {
      score = 5500;
    }
    if (score < 0) continue;
    if (own) score += 50;
    scored.push({
      option: { type: 'param', ref: p.ref, name: label, unit: p.unit, value: p.value, own },
      score,
    });
  }

  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, limit).map((s) => s.option);
}
