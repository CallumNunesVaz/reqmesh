import type { RenameCascade } from '../api/client';

export interface CascadeOption {
  value: RenameCascade;
  label: string;
  hint: string;
}

/** The three cascade choices the rename dialog offers, in display order. */
export const CASCADE_OPTIONS: CascadeOption[] = [
  { value: 'self', label: 'This requirement', hint: 'Rename only this requirement.' },
  { value: 'children', label: 'Children', hint: 'Also re-prefix its immediate leaf children; groups keep their id.' },
  { value: 'descendants', label: 'Descendants', hint: 'Re-prefix this requirement and its whole subtree.' },
];

/** One line per rename, for the preview and the done state. */
export function formatRenames(renames: { from: string; to: string }[]): string {
  return renames.map((r) => `${r.from} → ${r.to}`).join('\n');
}
