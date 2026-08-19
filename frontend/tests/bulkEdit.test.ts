import { describe, it, expect } from 'vitest';
import { buildBulkUpdates, hasBulkEditChanges, bulkEditFieldCount, INITIAL_BULK_EDIT } from '../src/lib/bulkEdit';

describe('buildBulkUpdates', () => {
  it('includes priorities only for the stakeholders the user touched', () => {
    const updates = buildBulkUpdates({
      ...INITIAL_BULK_EDIT,
      priorities: { safety: 5 },
    });
    // Untouched stakeholders (development, customers, maintenance) are absent,
    // not zero — a zero would silently overwrite their existing scores.
    expect(updates.priorities).toEqual({ safety: 5 });
  });

  it('omits priorities entirely when no stakeholder was touched', () => {
    const updates = buildBulkUpdates({ ...INITIAL_BULK_EDIT });
    expect('priorities' in updates).toBe(false);
  });

  it('treats null priorities as "no change", never as zeroed stakeholders', () => {
    const updates = buildBulkUpdates({ ...INITIAL_BULK_EDIT, priorities: null });
    expect('priorities' in updates).toBe(false);
  });

  it('sends list-valued fields verbatim under replace semantics', () => {
    const updates = buildBulkUpdates({
      ...INITIAL_BULK_EDIT,
      system_states: ['Cruise', 'Landing'],
      needs: ['design'],
    });
    expect(updates.system_states).toEqual(['Cruise', 'Landing']);
    expect(updates.needs).toEqual(['design']);
  });

  it('leaves scalar fields alone when they are empty strings', () => {
    const updates = buildBulkUpdates({ ...INITIAL_BULK_EDIT, source: '' });
    expect('source' in updates).toBe(false);
  });
});

describe('hasBulkEditChanges / bulkEditFieldCount', () => {
  it('counts a touched stakeholder as a change', () => {
    const form = { ...INITIAL_BULK_EDIT, priorities: { safety: 4 } };
    expect(hasBulkEditChanges(form)).toBe(true);
    expect(bulkEditFieldCount(form)).toBe(1);
  });

  it('treats a null list field as unchanged', () => {
    const form = { ...INITIAL_BULK_EDIT, system_states: null, needs: null };
    expect(hasBulkEditChanges(form)).toBe(false);
    expect(bulkEditFieldCount(form)).toBe(0);
  });

  it('treats an empty (cleared) list field as a change', () => {
    const form = { ...INITIAL_BULK_EDIT, system_states: [] };
    expect(hasBulkEditChanges(form)).toBe(true);
    expect(bulkEditFieldCount(form)).toBe(1);
  });
});
