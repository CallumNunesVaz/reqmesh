import { describe, it, expect } from 'vitest';
import { LIST_ROUTES, DETAIL_ROUTES, isListPath, isDetailPath } from '../src/lib/keyboardShortcuts';

/**
 * The help dialog used to advertise the list shortcuts to everyone while the
 * handler matched only seven routes, so `j`/`k`/`Enter`/`n`/`/` were documented
 * and dead on five list pages.
 *
 * That can no longer drift — and **not because of this file**. `ShortcutHelp`
 * renders `LIST_ROUTES`/`DETAIL_ROUTES` beneath each section heading, and
 * `useKeyboardShortcuts` matches on those same constants, so the dialog cannot
 * claim a page the handler does not cover: it is displaying the handler's own
 * list. No test could check that from here anyway, since this file cannot see
 * the dialog.
 *
 * What is worth pinning is below: that the two regexes built from those
 * constants match what they should and nothing else — `system-states/foo` is a
 * detail path, not a list one, and that boundary is easy to break.
 * `EXPECTED_LIST_ROUTES` is only a change-detector; it makes widening the
 * shortcut surface something a person typed twice rather than a side effect.
 */

const EXPECTED_LIST_ROUTES = [
  'requirements',
  'components',
  'specifications',
  'verification',
  'traces',
  'change-requests',
  'risks',
  'decisions',
  'analysis',
  'definitions',
  'baselines',
  'system-states',
];

describe('keyboard shortcut route lists stay in sync', () => {
  it('LIST_ROUTES has not changed without someone meaning it to', () => {
    expect([...LIST_ROUTES]).toEqual(EXPECTED_LIST_ROUTES);
  });

  it('isListPath matches every LIST_ROUTES page', () => {
    for (const route of LIST_ROUTES) {
      expect(isListPath(`/project/cessna-172/${route}`), `should match /${route}`).toBe(true);
    }
  });

  it('isListPath matches no other project page', () => {
    for (const route of ['metrics', 'publish', 'allocation', 'search', 'graph', 'settings', 'system-states/foo']) {
      expect(isListPath(`/project/cessna-172/${route}`), `should not match /${route}`).toBe(false);
    }
    expect(isListPath('/project/cessna-172/requirements/R1')).toBe(false);
    expect(isListPath('/project/cessna-172')).toBe(false);
    expect(isListPath('/project/cessna-172/')).toBe(false);
  });

  it('DETAIL_ROUTES is unchanged — only requirements and components have detail pages', () => {
    expect([...DETAIL_ROUTES]).toEqual(['requirements', 'components']);
  });

  it('isDetailPath matches only requirements and components details', () => {
    expect(isDetailPath('/project/cessna-172/requirements/R1')).toBe(true);
    expect(isDetailPath('/project/cessna-172/components/C1')).toBe(true);
    expect(isDetailPath('/project/cessna-172/specifications/S1')).toBe(false);
    expect(isDetailPath('/project/cessna-172/verification/V1')).toBe(false);
    expect(isDetailPath('/project/cessna-172/requirements')).toBe(false);
    expect(isDetailPath('/project/cessna-172/components')).toBe(false);
  });
});
