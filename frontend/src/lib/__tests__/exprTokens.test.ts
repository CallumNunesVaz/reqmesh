import { describe, it, expect } from 'vitest';
import { tokenizeExpr, type ExprToken } from '../exprTokens';

const tokens = (expr: string): ExprToken[] => tokenizeExpr(expr);
const kinds = (expr: string) => tokens(expr).map((t) => t.kind);
const text = (expr: string) => tokens(expr).map((t) => t.text);

describe('tokenizeExpr — round-trip', () => {
  // The property that matters most: a half-typed or malformed expression must
  // render in full, so the joined `text` has to reproduce the input exactly.
  const cases = [
    '',
    '-',
    "'unterminated",
    'GROS0001.',
    'mtow - empty_mass',
    "rollup('C172', 'mass')",
    '2e-3',
    'a <= b',
    'x ** y',
    'min(max(a, b), 2)',
    'foo ? bar',
  ];

  it('never drops or invents characters', () => {
    for (const expr of cases) {
      expect(text(expr).join(''), `round-trip ${JSON.stringify(expr)}`).toBe(expr);
    }
  });
});

describe('tokenizeExpr — classification', () => {
  it('reads a qualified reference as one ref token, not ident + punct + ident', () => {
    expect(tokens('GROS0001.empty_mass')).toEqual([
      { kind: 'ref', text: 'GROS0001.empty_mass' },
    ]);
  });

  it('reads a bare subtraction as ident, operator, ident', () => {
    expect(tokens('mtow - empty_mass')).toEqual([
      { kind: 'ident', text: 'mtow' },
      { kind: 'text', text: ' ' },
      { kind: 'operator', text: '-' },
      { kind: 'text', text: ' ' },
      { kind: 'ident', text: 'empty_mass' },
    ]);
  });

  it('reads rollup(...) as func, punct, string, punct, text, string, punct', () => {
    expect(kinds("rollup('C172', 'mass')")).toEqual([
      'func', 'punct', 'string', 'punct', 'text', 'string', 'punct',
    ]);
  });

  it('reads 2e-3 as a single number, not number + operator + number', () => {
    expect(tokens('2e-3')).toEqual([{ kind: 'number', text: '2e-3' }]);
  });

  it('reads <= as one operator, not < then =', () => {
    expect(tokens('a <= b')).toEqual([
      { kind: 'ident', text: 'a' },
      { kind: 'text', text: ' ' },
      { kind: 'operator', text: '<=' },
      { kind: 'text', text: ' ' },
      { kind: 'ident', text: 'b' },
    ]);
  });

  it('reads ** as one operator, not two *', () => {
    expect(tokens('**')).toEqual([{ kind: 'operator', text: '**' }]);
  });
});
