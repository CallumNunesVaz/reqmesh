export interface SplitCandidate {
  text: string;
  name: string;
}

const MIN_LENGTH = 15;
const MAX_NAME = 60;
/** A cut this early leaves too little to identify the clause by, so the next
 *  strategy is tried instead of accepting a two-word name. */
const MIN_CUT = 20;

/**
 * Turn one clause into a child's name.
 *
 * A name is not a sentence: it is what shows in the tree, on a canvas node, in
 * the trace matrix and in the exported document, all of which truncate. The
 * previous rule — the clause's first 60 characters — read as a considered title
 * while actually stopping mid-thought, and siblings from one requirement share
 * their opening ("The cabin heating system shall …"), so two children could end
 * up with the *same* name.
 *
 * So: drop the subject-and-modal opening that every sibling repeats, keep what
 * distinguishes this clause, and cut at a phrase boundary rather than wherever
 * the 60th character lands.
 */
export function deriveName(text: string): string {
  let s = text.trim().replace(/[.;,:]+$/, '');

  // "The cabin heating system shall provide …" → "provide …". Only when a
  // useful amount survives: a clause that is *mostly* its subject would be cut
  // down to nothing meaningful.
  const modal = s.match(/^.{0,60}?\b(?:shall|must|should|will|is required to|are required to)\b\s+/i);
  if (modal && s.length - modal[0].length >= MIN_CUT) s = s.slice(modal[0].length);

  s = s.charAt(0).toUpperCase() + s.slice(1);
  if (s.length <= MAX_NAME) return s;

  // Prefer the last clause boundary that leaves a usable name — cutting at a
  // comma reads as a deliberate short form rather than a sentence chopped off.
  const window = s.slice(0, MAX_NAME + 1);
  const boundary = Math.max(window.lastIndexOf(', '), window.lastIndexOf('; '), window.lastIndexOf(': '));
  if (boundary >= MIN_CUT) return s.slice(0, boundary);

  const lastSpace = window.slice(0, MAX_NAME).lastIndexOf(' ');
  return lastSpace > 0 ? s.slice(0, lastSpace) : s.slice(0, MAX_NAME);
}

export function splitDescription(html: string): SplitCandidate[] {
  const tagless = html.replace(/<[^>]+>/g, ' ');
  if (!tagless.trim()) return [];

  const clauses = tagless.split(/(?<=[.;])\s+|(?<=\n)\s*/);
  const candidates = clauses
    .map((c) => c.replace(/\s+/g, ' ').trim())
    .filter((c) => c.length >= MIN_LENGTH);

  if (candidates.length < 2) return [];

  return candidates.map((text) => ({ text, name: deriveName(text) }));
}
