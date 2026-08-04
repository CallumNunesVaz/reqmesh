import { describe, it, expect } from 'vitest';
import { DOC_SECTION_IDS } from '../src/components/DocumentationPanel';

describe('documentation sections', () => {
  it('includes baselines, risks and change-requests', () => {
    expect(DOC_SECTION_IDS).toContain('baselines');
    expect(DOC_SECTION_IDS).toContain('risks');
    expect(DOC_SECTION_IDS).toContain('change-requests');
  });

  it('has no duplicate section ids — a duplicate makes a section unreachable', () => {
    const seen = new Set<string>();
    const dupes: string[] = [];
    for (const id of DOC_SECTION_IDS) {
      if (seen.has(id)) {
        dupes.push(id);
      }
      seen.add(id);
    }
    expect(dupes, `Duplicate section ids: ${dupes.join(', ')}`).toHaveLength(0);
  });
});
