/**
 * A tiny hand-written tokeniser for parametric expressions, used only by the
 * read-only expression display. It splits an expression into coloured spans so
 * the structure of a long derived value is legible at a glance.
 *
 * Two invariants matter more than any specific classification:
 *
 * 1. **Round-trip.** The concatenation of every token's `text` equals the input
 *    exactly. A half-typed or malformed expression must still render in full —
 *    just less colourfully — so the tokeniser must never drop or invent
 *    characters.
 * 2. **Classify by shape, not by whitelist.** `func` means "identifier followed
 *    by `(`", not "one of the allowed function names", so an unknown call still
 *    reads as a call and the frontend never silently drifts from the evaluator's
 *    whitelist in `backend/app/services/evaluation.py`.
 */

export type ExprTokenKind =
  | 'number' | 'string' | 'ref' | 'ident' | 'func' | 'operator' | 'punct' | 'text';

export interface ExprToken {
  kind: ExprTokenKind;
  text: string;
}

const IDENT_START = /[A-Za-z_]/;
const IDENT_CHAR = /[A-Za-z0-9_]/;
const DIGIT = /[0-9]/;

/** Multi-character operators, matched before their single-character prefixes. */
const TWO_CHAR_OPERATORS: string[] = ['**', '<=', '>=', '==', '!='];
const ONE_CHAR_OPERATORS: string[] = ['+', '-', '*', '/', '%', '<', '>'];

function isDigit(c: string): boolean {
  return DIGIT.test(c);
}

function isIdentStart(c: string): boolean {
  return IDENT_START.test(c);
}

function isIdentChar(c: string): boolean {
  return IDENT_CHAR.test(c);
}

function isWhitespace(c: string): boolean {
  return /\s/.test(c);
}

/** End index of the numeric literal starting at `start` — integers, decimals,
 *  and an optional exponent (`1`, `1.5`, `2e-3`, `.5`). A bare trailing `e` is
 *  left for the identifier scanner so it still round-trips. */
function numberEnd(expr: string, start: number): number {
  const n = expr.length;
  let i = start;
  if (expr[i] === '.') {
    i += 1;
    while (i < n && isDigit(expr[i])) i += 1;
  } else {
    while (i < n && isDigit(expr[i])) i += 1;
    if (i < n && expr[i] === '.') {
      i += 1;
      while (i < n && isDigit(expr[i])) i += 1;
    }
  }
  if (i < n && (expr[i] === 'e' || expr[i] === 'E')) {
    let j = i + 1;
    if (j < n && (expr[j] === '+' || expr[j] === '-')) j += 1;
    if (j < n && isDigit(expr[j])) {
      j += 1;
      while (j < n && isDigit(expr[j])) j += 1;
      i = j;
    }
  }
  return i;
}

/** End index of the quoted literal starting at `start` (the opening quote).
 *  Backslash escapes are skipped; an unterminated literal runs to the end. */
function stringEnd(expr: string, start: number, quote: string): number {
  const n = expr.length;
  let i = start + 1;
  while (i < n) {
    if (expr[i] === '\\') {
      i += 2;
      continue;
    }
    if (expr[i] === quote) return i + 1;
    i += 1;
  }
  return n;
}

/** Split an expression into coloured spans. Never throws and never drops
 *  characters: the concatenation of all `text` equals the input exactly. */
export function tokenizeExpr(expr: string): ExprToken[] {
  const tokens: ExprToken[] = [];
  const n = expr.length;
  let i = 0;

  while (i < n) {
    const c = expr[i];

    if (isWhitespace(c)) {
      let j = i;
      while (j < n && isWhitespace(expr[j])) j += 1;
      tokens.push({ kind: 'text', text: expr.slice(i, j) });
      i = j;
      continue;
    }

    if (isIdentStart(c)) {
      let j = i + 1;
      while (j < n && isIdentChar(expr[j])) j += 1;
      // A qualified reference (`GROS0001.empty_mass`) is one token; a bare
      // identifier is a function call when followed by `(`, else a local name.
      if (expr[j] === '.' && j + 1 < n && isIdentStart(expr[j + 1])) {
        let k = j + 2;
        while (k < n && isIdentChar(expr[k])) k += 1;
        tokens.push({ kind: 'ref', text: expr.slice(i, k) });
        i = k;
      } else {
        tokens.push({ kind: expr[j] === '(' ? 'func' : 'ident', text: expr.slice(i, j) });
        i = j;
      }
      continue;
    }

    if (isDigit(c) || (c === '.' && i + 1 < n && isDigit(expr[i + 1]))) {
      const end = numberEnd(expr, i);
      tokens.push({ kind: 'number', text: expr.slice(i, end) });
      i = end;
      continue;
    }

    if (c === "'" || c === '"') {
      const end = stringEnd(expr, i, c);
      tokens.push({ kind: 'string', text: expr.slice(i, end) });
      i = end;
      continue;
    }

    const two = expr.slice(i, i + 2);
    if (TWO_CHAR_OPERATORS.includes(two)) {
      tokens.push({ kind: 'operator', text: two });
      i += 2;
      continue;
    }

    if (ONE_CHAR_OPERATORS.includes(c)) {
      tokens.push({ kind: 'operator', text: c });
      i += 1;
      continue;
    }

    if (c === '(' || c === ')' || c === ',') {
      tokens.push({ kind: 'punct', text: c });
      i += 1;
      continue;
    }

    tokens.push({ kind: 'text', text: c });
    i += 1;
  }

  return tokens;
}
