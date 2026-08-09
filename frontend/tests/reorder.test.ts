import { describe, it, expect } from 'vitest';
import { moveInSequence, moveToIndex } from '../src/lib/reorder';

const BASELINES = ['SRR', 'PDR', 'CDR', 'FCA'];

describe('moveInSequence', () => {
  it('moves a name up in the middle of the list', () => {
    expect(moveInSequence(BASELINES, 'PDR', 'up')).toEqual(['PDR', 'SRR', 'CDR', 'FCA']);
  });

  it('moves a name down in the middle of the list', () => {
    expect(moveInSequence(BASELINES, 'PDR', 'down')).toEqual(['SRR', 'CDR', 'PDR', 'FCA']);
  });

  it('returns null when moving the first item up', () => {
    expect(moveInSequence(BASELINES, 'SRR', 'up')).toBeNull();
  });

  it('returns null when moving the last item down', () => {
    expect(moveInSequence(BASELINES, 'FCA', 'down')).toBeNull();
  });

  it('returns null for an unknown name', () => {
    expect(moveInSequence(BASELINES, 'NOPE', 'up')).toBeNull();
    expect(moveInSequence(BASELINES, 'NOPE', 'down')).toBeNull();
  });

  it('does not mutate the input array', () => {
    const input = [...BASELINES];
    moveInSequence(BASELINES, 'PDR', 'up');
    expect(input).toEqual(BASELINES);
  });

  it('handles a single-element list', () => {
    expect(moveInSequence(['X'], 'X', 'up')).toBeNull();
    expect(moveInSequence(['X'], 'X', 'down')).toBeNull();
  });

  it('handles an empty list', () => {
    expect(moveInSequence([], 'X', 'up')).toBeNull();
  });
});

describe('moveToIndex', () => {
  it('moves an item forwards', () => {
    expect(moveToIndex(BASELINES, 1, 3)).toEqual(['SRR', 'CDR', 'FCA', 'PDR']);
  });

  it('moves an item backwards', () => {
    expect(moveToIndex(BASELINES, 3, 1)).toEqual(['SRR', 'FCA', 'PDR', 'CDR']);
  });

  it('moves the first item to the end', () => {
    expect(moveToIndex(BASELINES, 0, 3)).toEqual(['PDR', 'CDR', 'FCA', 'SRR']);
  });

  it('moves the last item to the beginning', () => {
    expect(moveToIndex(BASELINES, 3, 0)).toEqual(['FCA', 'SRR', 'PDR', 'CDR']);
  });

  it('returns same-length array with same members (permutation)', () => {
    const result = moveToIndex(BASELINES, 2, 0);
    expect(result).toHaveLength(BASELINES.length);
    expect([...result].sort()).toEqual([...BASELINES].sort());
  });

  it('does not mutate the input array', () => {
    const input = [...BASELINES];
    moveToIndex(BASELINES, 1, 2);
    expect(input).toEqual(BASELINES);
  });

  it('returns an equal array when from === to', () => {
    expect(moveToIndex(BASELINES, 1, 1)).toEqual(BASELINES);
  });

  it('handles single-element array', () => {
    expect(moveToIndex(['X'], 0, 0)).toEqual(['X']);
  });
});
