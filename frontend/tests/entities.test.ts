import { describe, it, expect } from 'vitest';
import { ENTITY_META, COMPONENT_TYPE_META, entityIconMeta, type EntityKind } from '../src/components/entities';
import { COMPONENT_TYPES } from '../src/api/client';

/**
 * `path` is optional — a comment has no page of its own — so these assertions
 * would silently pass on `undefined` without the guard. Fail loudly instead:
 * every kind named here is one that must stay linkable.
 */
function pathOf(kind: EntityKind, projectId: string, id: string): string {
  const build = ENTITY_META[kind].path;
  if (!build) throw new Error(`${kind} has no path, but this test requires one`);
  return build(projectId, id);
}

describe('entity routes', () => {
  it('sends requirements to their detail page', () => {
    expect(pathOf('requirement', 'demo', 'REQ-001')).toBe('/project/demo/requirements/REQ-001');
  });

  it('sends components to their detail page', () => {
    expect(pathOf('component', 'demo', 'SPAR')).toBe('/project/demo/components/SPAR');
  });

  it('sends risks to their detail page', () => {
    expect(pathOf('risk', 'demo', 'RSK-001')).toBe('/project/demo/risks/RSK-001');
  });

  it('sends verification cases to their detail page', () => {
    expect(pathOf('verification', 'demo', 'VC-001')).toBe('/project/demo/verification/VC-001');
  });

  it('deep-links the entity kinds that have no detail page', () => {
    // These only have list pages, so a reference focuses the row.
    expect(pathOf('specification', 'demo', 'SRS-001')).toBe('/project/demo/specifications?focus=SRS-001');
    expect(pathOf('change', 'demo', 'CR-001')).toBe('/project/demo/change-requests?focus=CR-001');
    expect(pathOf('baseline', 'demo', 'PDR')).toBe('/project/demo/baselines?focus=PDR');
  });

  it('leaves a comment unlinked — search gives us no parent entity to point at', () => {
    expect(ENTITY_META.comment.path).toBeUndefined();
  });

  it('encodes ids so a space or slash cannot break the url', () => {
    expect(pathOf('requirement', 'demo', 'REQ 001/x')).toBe('/project/demo/requirements/REQ%20001%2Fx');
    expect(pathOf('component', 'demo', 'MAIN SPAR')).toBe('/project/demo/components/MAIN%20SPAR');
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

describe('entityIconMeta', () => {
  it('resolves each component type to its COMPONENT_TYPE_META entry', () => {
    for (const t of COMPONENT_TYPES) {
      const got = entityIconMeta('component', t);
      expect(got.icon, t).toBe(COMPONENT_TYPE_META[t].icon);
      expect(got.cls, t).toBe(COMPONENT_TYPE_META[t].cls);
      expect(got.label, t).toBe(COMPONENT_TYPE_META[t].label);
    }
  });

  it('returns six mutually distinct icons for the six component types', () => {
    const icons = COMPONENT_TYPES.map((t) => entityIconMeta('component', t).icon);
    expect(new Set(icons).size).toBe(COMPONENT_TYPES.length);
  });

  it('falls back to ENTITY_META.component when no subtype is given', () => {
    const got = entityIconMeta('component');
    expect(got.icon).toBe(ENTITY_META.component.icon);
    expect(got.cls).toBe(ENTITY_META.component.cls);
    expect(got.label).toBe(ENTITY_META.component.label);
  });

  it('falls back to ENTITY_META.component on an unknown subtype without throwing', () => {
    const got = entityIconMeta('component', 'nonsense');
    expect(got.icon).toBe(ENTITY_META.component.icon);
    expect(got.cls).toBe(ENTITY_META.component.cls);
    expect(got.label).toBe(ENTITY_META.component.label);
  });

  it('trims and lowercases the subtype before lookup', () => {
    const got = entityIconMeta('component', '  PART ');
    expect(got.icon).toBe(COMPONENT_TYPE_META.part.icon);
    expect(got.label).toBe('Part');
  });

  it('ignores subtype for non-component kinds', () => {
    const got = entityIconMeta('requirement', 'part');
    expect(got.icon).toBe(ENTITY_META.requirement.icon);
    expect(got.cls).toBe(ENTITY_META.requirement.cls);
    expect(got.label).toBe(ENTITY_META.requirement.label);
  });

  it('returns the per-type label for a component subtype, not the generic Component label', () => {
    expect(entityIconMeta('component', 'part').label).toBe('Part');
  });

  it('does not resolve inherited Object keys as component types', () => {
    // The YAML is hand-editable, so `type: constructor` is reachable. A plain
    // `key in COMPONENT_TYPE_META` walks the prototype chain and hands back a
    // function with no `.icon`, which throws on render.
    for (const key of ['constructor', 'toString', 'hasOwnProperty', '__proto__']) {
      const got = entityIconMeta('component', key);
      expect(got.icon, key).toBe(ENTITY_META.component.icon);
      expect(got.label, key).toBe('Component');
    }
  });
});
