/**
 * The route lists behind the keyboard-shortcut handler and the help dialog.
 *
 * Both `useKeyboardShortcuts` (which decides whether the current path is a list
 * or detail page) and `ShortcutHelp` (which tells the user which pages the list
 * shortcuts apply to) read from here. Keep them in one place: the dialog and the
 * handler drift apart the moment someone extends one regex and forgets the other.
 */

export const LIST_ROUTES = [
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
] as const;

export const DETAIL_ROUTES = ['requirements', 'components'] as const;

/** `/project/:projectId/<route>` — a list page. */
export function isListPath(pathname: string): boolean {
  return new RegExp(`/project/[^/]+/(${LIST_ROUTES.join('|')})$`).test(pathname);
}

/** `/project/:projectId/<route>/<id>` — a detail page. */
export function isDetailPath(pathname: string): boolean {
  return new RegExp(`/project/[^/]+/(${DETAIL_ROUTES.join('|')})/[^/]+`).test(pathname);
}
