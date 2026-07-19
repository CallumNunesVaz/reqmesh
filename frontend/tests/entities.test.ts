import { describe, it, expect } from 'vitest';
import { ENTITY_META, COMPONENT_TYPE_META } from '../src/components/entities';
import { COMPONENT_TYPES } from '../src/api/client';

describe('entity routes', () => {
  it('sends requirements to their detail page', () => {
    expect(ENTITY_META.requirement.path('demo', 'REQ-001')).toBe('/project/demo/requirements/REQ-001');
  });

  it('sends components to their detail page', () => {
    expect(ENTITY_META.component.path('demo', 'SPAR')).toBe('/project/demo/components/SPAR');
  });

  it('deep-links the entity kinds that have no detail page', () => {
    // These only have list pages, so a reference focuses the row.
    expect(ENTITY_META.verification.path('demo', 'VC-001')).toBe('/project/demo/verification?focus=VC-001');
    expect(ENTITY_META.specification.path('demo', 'SRS-001')).toBe('/project/demo/specifications?focus=SRS-001');
    expect(ENTITY_META.change.path('demo', 'CR-001')).toBe('/project/demo/change-requests?focus=CR-001');
    expect(ENTITY_META.risk.path('demo', 'RSK-001')).toBe('/project/demo/risks?focus=RSK-001');
  });

  it('encodes ids so a space or slash cannot break the url', () => {
    expect(ENTITY_META.requirement.path('demo', 'REQ 001/x')).toBe('/project/demo/requirements/REQ%20001%2Fx');
    expect(ENTITY_META.component.path('demo', 'MAIN SPAR')).toBe('/project/demo/components/MAIN%20SPAR');
  });

  it('gives every kind an icon, a colour and a label', () => {
    for (const [kind, meta] of Object.entries(ENTITY_META)) {
      expect(meta.icon, kind).toBeTruthy();
      expect(meta.cls, kind).toMatch(/^text-cs-/);
      expect(meta.label, kind).toBeTruthy();
    }
  });
});

describe('component type icons', () => {
  it('covers every component type the API accepts', () => {
    // A type with no entry would fall back and render as the wrong icon.
    for (const t of COMPONENT_TYPES) {
      expect(COMPONENT_TYPE_META[t], t).toBeTruthy();
    }
  });

  it('uses a distinct colour per type', () => {
    const colours = COMPONENT_TYPES.map((t) => COMPONENT_TYPE_META[t].cls);
    expect(new Set(colours).size).toBe(COMPONENT_TYPES.length);
  });
});
