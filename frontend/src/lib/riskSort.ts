import type { Risk, RiskBand } from '../api/client';

/**
 * Column sorting for the dense risk list. Kept as pure functions so the band
 * ordering — the one column whose key is not simply a string off the record —
 * can be unit-tested on its own rather than only through the rendered page.
 */

export type RiskSortKey =
  | 'id' | 'title' | 'severity' | 'likelihood' | 'band' | 'status' | 'links';

export type SortDir = 'asc' | 'desc';

/** The risk's likelihood, falling back the same way the backend does. */
const likelihoodOf = (r: Risk): string =>
  r.rating?.likelihood ?? r.likelihood ?? r.probability ?? '';

/**
 * Where a risk's band sits in the matrix's band order (least serious first).
 *
 * Unrated risks — and risks whose band key the matrix no longer defines, which
 * the model tolerates — sort at the far end of the axis (``bands.length``), so
 * an ascending sort keeps the rated register together and a descending sort
 * surfaces the ones whose severity cannot be assessed first. Either way the
 * sort never throws on a level the matrix dropped.
 */
export function bandOrder(risk: Risk, bands: RiskBand[]): number {
  const band = risk.rating?.band;
  if (band) {
    const i = bands.findIndex((b) => b.key === band);
    if (i >= 0) return i;
  }
  return bands.length;
}

const linkCount = (r: Risk): number =>
  (r.linked_requirements ?? []).length
  + (r.mitigating_requirements ?? []).length
  + (r.linked_components ?? []).length
  + (r.mitigating_components ?? []).length;

function valueFor(r: Risk, key: RiskSortKey, bands: RiskBand[]): string | number {
  switch (key) {
    case 'id': return r.id;
    case 'title': return r.title ?? '';
    case 'severity': return r.severity ?? '';
    case 'likelihood': return likelihoodOf(r);
    case 'band': return bandOrder(r, bands);
    case 'status': return r.status ?? '';
    case 'links': return linkCount(r);
  }
}

/** Compare two risks for `key`; negative means `a` first. */
export function compareRisks(
  a: Risk,
  b: Risk,
  key: RiskSortKey,
  dir: SortDir,
  bands: RiskBand[],
): number {
  const av = valueFor(a, key, bands);
  const bv = valueFor(b, key, bands);
  const cmp = typeof av === 'number' && typeof bv === 'number'
    ? av - bv
    : String(av).localeCompare(String(bv));
  return dir === 'asc' ? cmp : -cmp;
}

/** A stable sort of `risks` by `key` in `dir`, using the matrix's band order. */
export function sortRisks(
  risks: Risk[],
  key: RiskSortKey,
  dir: SortDir,
  bands: RiskBand[],
): Risk[] {
  return [...risks].sort((a, b) => compareRisks(a, b, key, dir, bands));
}
