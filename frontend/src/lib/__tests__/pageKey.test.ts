import { describe, it, expect } from 'vitest';
import { pageKeyFor } from '../pageKey';

describe('pageKeyFor', () => {
  it('keys detail routes by their section, not the record id', () => {
    expect(pageKeyFor('/project/x/requirements/REQ-001')).toBe('requirements');
    expect(pageKeyFor('/project/x/requirements/REQ-002')).toBe('requirements');
    expect(pageKeyFor('/project/x/requirements')).toBe('requirements');
    expect(pageKeyFor('/project/x/components/C1')).toBe('components');
  });

  it('keys the project overview and top-level routes sensibly', () => {
    expect(pageKeyFor('/project/x')).toBe('overview');
    expect(pageKeyFor('/project/x/settings')).toBe('settings');
    expect(pageKeyFor('/users')).toBe('users');
    expect(pageKeyFor('/')).toBe('overview');
  });
});
