import { describe, it, expect } from 'vitest';
import { graphRelevant, GRAPH_KINDS, mutationCollections, queryKeysFor } from '../mutationInvalidation';

describe('graphRelevant', () => {
  it('is true only for collections the canvas renders', () => {
    for (const kind of GRAPH_KINDS) expect(graphRelevant(kind)).toBe(true);
    expect(graphRelevant('requirements')).toBe(true);
    expect(graphRelevant('traces')).toBe(true);
  });

  it('is false for unrelated collections and unattributed changes', () => {
    expect(graphRelevant('risks')).toBe(false);
    expect(graphRelevant('comments')).toBe(false);
    expect(graphRelevant('change-requests')).toBe(false);
    expect(graphRelevant(null)).toBe(false);
    expect(graphRelevant(undefined)).toBe(false);
  });
});

describe('mutationCollections', () => {
  it('prefers the server-side list, which carries side-effect collections', () => {
    expect(mutationCollections({ collection: 'requirements', collections: ['requirements', 'verification'] }))
      .toEqual(['requirements', 'verification']);
  });

  it('falls back to the single collection from an older server', () => {
    expect(mutationCollections({ collection: 'risks' })).toEqual(['risks']);
    expect(mutationCollections({ collection: 'risks', collections: [] })).toEqual(['risks']);
  });

  it('is empty for an unattributed change or a malformed frame', () => {
    expect(mutationCollections({ collection: null, collections: [] })).toEqual([]);
    expect(mutationCollections({})).toEqual([]);
    expect(mutationCollections(null)).toEqual([]);
    expect(mutationCollections('requirements')).toEqual([]);
  });
});

describe('queryKeysFor', () => {
  it('adds the queries derived from a collection', () => {
    expect(queryKeysFor('requirements')).toEqual(['requirements', 'evaluation']);
    expect(queryKeysFor('definitions')).toEqual(['definitions', 'evaluation']);
    expect(queryKeysFor('baselines')).toEqual(['baselines', 'project']);
    expect(queryKeysFor('system-states')).toEqual(['system-states', 'project']);
  });

  it('is just the collection when nothing is derived from it', () => {
    expect(queryKeysFor('risks')).toEqual(['risks']);
  });
});
