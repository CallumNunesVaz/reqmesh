import { describe, it, expect } from 'vitest';
import {
  componentsSatisfyingRequirement,
  requirementsSatisfiedByComponent,
} from '../src/lib/crossHighlight';

const components = [
  { id: 'C-001', satisfies: ['REQ-A', 'REQ-B'] },
  { id: 'C-002', satisfies: ['REQ-B'] },
  { id: 'C-003', satisfies: [] },
];

describe('componentsSatisfyingRequirement', () => {
  it('maps a requirement to every component that satisfies it', () => {
    expect(componentsSatisfyingRequirement('REQ-B', components)).toEqual(['C-001', 'C-002']);
  });

  it('returns an empty list when nothing satisfies the requirement', () => {
    expect(componentsSatisfyingRequirement('REQ-Z', components)).toEqual([]);
  });
});

describe('requirementsSatisfiedByComponent', () => {
  it('maps a component to the requirements it satisfies', () => {
    expect(requirementsSatisfiedByComponent('C-001', components)).toEqual(['REQ-A', 'REQ-B']);
  });

  it('returns an empty list for a component that satisfies nothing', () => {
    expect(requirementsSatisfiedByComponent('C-003', components)).toEqual([]);
  });

  it('returns an empty list for an unknown component', () => {
    expect(requirementsSatisfiedByComponent('C-999', components)).toEqual([]);
  });
});
