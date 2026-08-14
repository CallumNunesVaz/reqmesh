/** Per-component effective quantities for the component tree.
 *
 *  The list row shows a component's own `quantity`; the build needs the
 *  effective figure — own quantity multiplied by every ancestor's, up to the
 *  root. A 5× part under a 3× assembly is 15× in the build, and the list used
 *  to say 5×.
 *
 *  The walk is deliberately iterative with a visited set: `_meta.yaml` and the
 *  YAML store are hand-editable and arrive by git pull, so a parent cycle can
 *  exist on disk, and a recursive descent through one would freeze the page.
 */

/**
 * Effective quantity per component id: own quantity × every ancestor's.
 *
 * - A cycle in `parent` terminates the walk rather than hanging.
 * - A missing or non-positive `quantity` is treated as 1, not 0 — a zero would
 *   silently annihilate a whole subtree's rollup.
 * - A `parent` pointing at a component that does not exist terminates the walk.
 */
export function rollupQuantities(
  components: { id: string; parent?: string | null; quantity: number }[],
): Map<string, number> {
  const byId = new Map<string, { parent: string | null; quantity: number }>();
  for (const c of components) {
    byId.set(c.id, {
      parent: c.parent ? c.parent : null,
      quantity: c.quantity > 0 ? c.quantity : 1,
    });
  }

  const result = new Map<string, number>();

  for (const c of components) {
    if (result.has(c.id)) continue;

    // Walk up from `c.id`, collecting the ancestor chain until a root (no
    // parent, or a parent that names nothing) or a revisit (a cycle). `seen`
    // bounds the walk, so a cycle terminates instead of spinning forever.
    const chain: string[] = [];
    const seen = new Set<string>();
    let cursor: string | null = c.id;
    while (cursor !== null && byId.has(cursor) && !seen.has(cursor)) {
      seen.add(cursor);
      chain.push(cursor);
      cursor = byId.get(cursor)!.parent;
    }

    // Fold from the top of the chain down so each node's ancestors are already
    // folded in. A cycle ends the chain early; those nodes keep their own
    // quantity, which is what "treat a cycle as terminating" means here.
    let product = 1;
    for (let i = chain.length - 1; i >= 0; i--) {
      const id = chain[i];
      product *= byId.get(id)!.quantity;
      result.set(id, product);
    }
  }

  return result;
}
