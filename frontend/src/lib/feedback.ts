/** Pure helpers for the success/feedback toasts, kept out of the components so
 *  the singular/plural logic is unit-testable under the node vitest setup,
 *  which has no jsdom and cannot render a hook or a component. */

/** "<count> <noun>(s) <verb>" — singular when one, e.g.
 *  `3 requirements deleted`, `1 risk updated`. */
export function countMessage(count: number, noun: string, verb: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'} ${verb}`;
}
