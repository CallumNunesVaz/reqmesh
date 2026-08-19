import { describe, it, expect } from 'vitest';
import { autoLinkParts } from '../src/components/autoLink';

const ids = ['AFRM0000', 'VC-001', 'REQ'];

describe('autoLinkParts', () => {
  it('links a known id in the middle of a sentence', () => {
    expect(autoLinkParts('See AFRM0000 for detail.', ids)).toEqual([
      { text: 'See ' },
      { id: 'AFRM0000' },
      { text: ' for detail.' },
    ]);
  });

  it('links ids at the start and end of the text', () => {
    expect(autoLinkParts('VC-001 verifies AFRM0000', ids)).toEqual([
      { id: 'VC-001' },
      { text: ' verifies ' },
      { id: 'AFRM0000' },
    ]);
  });

  it('does not match an id inside a longer token', () => {
    // "REQ" is a known id, but "REQ-042" is not — a plain \b would split at
    // the hyphen and wrongly link the prefix.
    expect(autoLinkParts('REQ-042 is unrelated', ids)).toEqual([
      { text: 'REQ-042 is unrelated' },
    ]);
    expect(autoLinkParts('VC-0011 is a different case', ids)).toEqual([
      { text: 'VC-0011 is a different case' },
    ]);
  });

  it('prefers the longest id when one is a prefix of another', () => {
    expect(autoLinkParts('VC-001', ['VC', 'VC-001'])).toEqual([{ id: 'VC-001' }]);
  });

  it('escapes regex metacharacters in ids', () => {
    expect(autoLinkParts('see R(1) here', ['R(1)'])).toEqual([
      { text: 'see ' },
      { id: 'R(1)' },
      { text: ' here' },
    ]);
  });

  it('returns plain text untouched when there are no ids', () => {
    expect(autoLinkParts('nothing to link', [])).toEqual([{ text: 'nothing to link' }]);
    expect(autoLinkParts('', ids)).toEqual([]);
  });

  // The `@` picker inserts an entity as `[[ID]]`. The server strips the
  // editor's <span> wrapper (span is not in its allowlist), so this bracket
  // token is the form that actually persists — and the brackets must not leak
  // into the rendered output, which is what read mode used to show.
  it('links the [[ID]] form and consumes the brackets', () => {
    expect(autoLinkParts('see [[AFRM0000]] now', ids)).toEqual([
      { text: 'see ' },
      { id: 'AFRM0000' },
      { text: ' now' },
    ]);
  });

  it('links a bracketed id at the very start and end', () => {
    expect(autoLinkParts('[[VC-001]]', ids)).toEqual([{ id: 'VC-001' }]);
  });

  it('still links bare ids alongside bracketed ones', () => {
    expect(autoLinkParts('[[VC-001]] and AFRM0000', ids)).toEqual([
      { id: 'VC-001' },
      { text: ' and ' },
      { id: 'AFRM0000' },
    ]);
  });

  it('leaves brackets around an unknown id alone', () => {
    expect(autoLinkParts('[[NOPE-9]] here', ids)).toEqual([{ text: '[[NOPE-9]] here' }]);
  });

  // ── Parameter references (ID.param) ─────────────────────────────────────

  const params = ['REQM0002.temp_max'];

  it('splits a bracketed [[ID.param]] into a parameter segment', () => {
    expect(autoLinkParts('Limit is [[REQM0002.temp_max]].', ['REQM0002'], params)).toEqual([
      { text: 'Limit is ' },
      { param: 'REQM0002.temp_max' },
      { text: '.' },
    ]);
  });

  it('splits a bare ID.param into a parameter segment', () => {
    expect(autoLinkParts('Limit is REQM0002.temp_max.', ['REQM0002'], params)).toEqual([
      { text: 'Limit is ' },
      { param: 'REQM0002.temp_max' },
      { text: '.' },
    ]);
  });

  it('does not falsely match a trailing ID. as a parameter', () => {
    // "REQM0002." has a trailing dot and no parameter name, so it must not
    // become a {param} segment — but the id still links before the full stop.
    expect(autoLinkParts('REQM0002.', ['REQM0002'], params)).toEqual([
      { id: 'REQM0002' },
      { text: '.' },
    ]);
  });

  it('keeps a bare id with no dot as an entity, not a parameter', () => {
    expect(autoLinkParts('REQM0002', ['REQM0002'], params)).toEqual([{ id: 'REQM0002' }]);
  });

  it('still emits a param segment for a bracketed ID.param that no longer exists', () => {
    // The parameter was deleted; the token must resolve to the broken state
    // rather than being swallowed by the bare-id branch or vanishing.
    expect(autoLinkParts('[[REQM0002.temp_max]]', ['REQM0002'], [])).toEqual([
      { param: 'REQM0002.temp_max' },
    ]);
  });

  it('still resolves a bare ID.param that names a known parameter', () => {
    // The id branch must not split REQM0002 out of the ref: the parameter
    // branch is tried first and wins.
    expect(autoLinkParts('REQM0002.temp_max', ['REQM0002'], params)).toEqual([
      { param: 'REQM0002.temp_max' },
    ]);
  });

  it('degrades a bare ID.param naming a deleted parameter to unlinked text', () => {
    // The parameter no longer exists, so the parameter branch cannot match and
    // the id branch declines (the `.` is followed by a word char). The whole
    // ref stays visible as plain prose — no broken chip, no half-link.
    expect(autoLinkParts('REQM0002.temp_max', ['REQM0002'], [])).toEqual([
      { text: 'REQM0002.temp_max' },
    ]);
  });

  // ── Id boundary — sentence punctuation must not stop a link ─────────────

  it('links an id followed by a full stop', () => {
    expect(autoLinkParts('This refines REQM0002.', ['REQM0002'])).toEqual([
      { text: 'This refines ' },
      { id: 'REQM0002' },
      { text: '.' },
    ]);
  });

  it('links an id followed by a comma, a closing paren, and end-of-string', () => {
    expect(autoLinkParts('REQM0002, then', ['REQM0002'])).toEqual([
      { id: 'REQM0002' },
      { text: ', then' },
    ]);
    expect(autoLinkParts('(see REQM0002)', ['REQM0002'])).toEqual([
      { text: '(see ' },
      { id: 'REQM0002' },
      { text: ')' },
    ]);
    expect(autoLinkParts('see REQM0002', ['REQM0002'])).toEqual([
      { text: 'see ' },
      { id: 'REQM0002' },
    ]);
  });

  it('does not link an id inside a longer alphanumeric token', () => {
    expect(autoLinkParts('REQM0002X', ['REQM0002'])).toEqual([{ text: 'REQM0002X' }]);
  });
});
