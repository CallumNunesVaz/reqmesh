import type { EntityKind } from '../components/entities';

/**
 * The backend's search kind names are not all `EntityKind` values —
 * `services/search.py` returns `change_request` where the frontend calls it
 * `change` — so search results have to be translated rather than used directly.
 *
 * `searchKinds.test.ts` reads the kind branches straight out of
 * `services/search.py` and fails if this map does not cover every one. That
 * test is the only thing keeping the two sides in step: without it a new
 * backend kind renders as an unlinked, unfilterable id and nobody finds out.
 * Do not reintroduce a hand-copied list of the backend's kinds here for it to
 * compare against — that is what it replaced, and it passed while the two real
 * kinds it was meant to catch were both missing.
 */
export const BACKEND_KIND_TO_ENTITY: Record<string, EntityKind | undefined> = {
  requirement: 'requirement',
  verification: 'verification',
  component: 'component',
  specification: 'specification',
  change_request: 'change',
  risk: 'risk',
  comment: 'comment',
  decision: 'decision',
  definition: 'definition',
  analysis: 'analysis',
  baseline: 'baseline',
};

/** The kind filter offered on the search page, in the order it is shown. */
export const SEARCHABLE_KINDS = [
  'requirement', 'component', 'specification', 'verification',
  'change_request', 'risk', 'comment', 'decision', 'definition', 'analysis',
  'baseline',
] as const;
