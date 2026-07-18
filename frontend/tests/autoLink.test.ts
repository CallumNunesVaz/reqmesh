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
});
