/**
 * Window event dispatched to open the command palette.
 *
 * Lives in its own module so the palette itself can be lazily imported: the
 * shortcut that fires the event must not pull the palette's chunk into the
 * initial bundle.
 */
export const OPEN_PALETTE_EVENT = 'rt-open-palette';
