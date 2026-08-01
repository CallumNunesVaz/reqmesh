import { ApiError, type ReferencedError, type Referrer } from '../api/client';

/** Group referrers for display: "2 specifications, 1 risk". */
export function summarise(referrers: Referrer[]): string {
  const counts = new Map<string, number>();
  for (const r of referrers) counts.set(r.label, (counts.get(r.label) || 0) + 1);
  return [...counts.entries()]
    .map(([label, n]) => `${n} × ${label}`)
    .join(', ');
}

export function referencedDetail(err: unknown): ReferencedError | null {
  const data = err instanceof ApiError ? err.data : undefined;
  if (data && typeof data === 'object' && (data as Record<string, unknown>).error === 'referenced') {
    return data as ReferencedError;
  }
  return null;
}

/**
 * Run a delete, and if the server refuses because other records reference the
 * entity, ask once and retry with force.
 *
 * The server deliberately does not clean up those references itself: doing so
 * would edit records the deleter may not own, and land in git history as an
 * unattributed change to someone else's document. So the decision comes back
 * here, to the person with the context — but it has to arrive as a real
 * question, not a raw 409 the page swallows into "Delete failed".
 */
export async function deleteWithReferenceCheck(
  run: (force: boolean) => Promise<unknown>,
  confirm: (message: string) => Promise<boolean> | boolean,
): Promise<boolean> {
  try {
    await run(false);
    return true;
  } catch (err) {
    const detail = referencedDetail(err);
    if (!detail) throw err;

    const listed = detail.referrers
      .slice(0, 8)
      .map((r) => `  • ${r.id}${r.name ? ` — ${r.name}` : ''} (${r.label})`)
      .join('\n');
    const more = detail.referrers.length > 8
      ? `\n  …and ${detail.referrers.length - 8} more`
      : '';

    const ok = await confirm(
      `${detail.referrers.length} record(s) reference ${detail.id} — `
      + `${summarise(detail.referrers)}.\n\n${listed}${more}\n\n`
      + `Deleting it will leave those references pointing at nothing. Delete anyway?`,
    );
    if (!ok) return false;
    await run(true);
    return true;
  }
}
