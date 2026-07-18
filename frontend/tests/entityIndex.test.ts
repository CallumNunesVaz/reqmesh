import { describe, it, expect } from 'vitest';
import { searchEntities, type IndexedEntity } from '../src/components/entityIndex';

const e = (kind: IndexedEntity['kind'], id: string, name: string, detail = ''): IndexedEntity =>
  ({ kind, id, name, detail });

const index: IndexedEntity[] = [
  e('requirement', 'AFRM0000', 'Roll authority', 'The aircraft shall roll'),
  e('requirement', 'AFRM0001', 'Pitch authority'),
  e('verification', 'VCAF0001', 'Roll rate test'),
  e('component', 'SPAR', 'Main spar', 'Carries the wing bending load'),
  e('specification', 'SRS-001', 'System spec'),
];

describe('searchEntities', () => {
  it('returns the head of the index for an empty query', () => {
    expect(searchEntities(index, '').length).toBe(index.length);
    expect(searchEntities(index, '', 2).length).toBe(2);
  });

  it('ranks id matches above name matches', () => {
    // "roll" appears in AFRM0000's name and VCAF0001's name, but nothing
    // id-matches — name hits only, original order kept.
    const byName = searchEntities(index, 'roll');
    expect(byName.map((r) => r.id)).toEqual(['AFRM0000', 'VCAF0001']);
    // "spar" id-matches SPAR; an id hit must come first even though the
    // detail of another row could match too.
    const r = searchEntities(index, 'spar');
    expect(r[0].id).toBe('SPAR');
  });

  it('ranks id prefix above id substring', () => {
    const idx = [e('requirement', 'XAF-1', 'a'), e('requirement', 'AF-2', 'b')];
    expect(searchEntities(idx, 'af').map((r) => r.id)).toEqual(['AF-2', 'XAF-1']);
  });

  it('matches case-insensitively and in descriptions', () => {
    expect(searchEntities(index, 'BENDING')[0].id).toBe('SPAR');
  });

  it('returns nothing when nothing matches', () => {
    expect(searchEntities(index, 'zzz')).toEqual([]);
  });
});
