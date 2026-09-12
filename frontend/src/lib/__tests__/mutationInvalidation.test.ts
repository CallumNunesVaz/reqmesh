import { describe, it, expect } from 'vitest';
import { graphRelevant, GRAPH_KINDS } from '../mutationInvalidation';

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
