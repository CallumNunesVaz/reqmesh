export interface ComponentNode { id: string; parent?: string | null }
export interface SatisfyingComponent { id: string; satisfies?: string[] }

/**
 * Compute the effective set of hidden component ids: the explicitly hidden ids,
 * plus every component that has an explicitly hidden ancestor at any depth.
 *
 * Walks iteratively with a visited set so a parent cycle or self-parent in
 * hand-editable YAML never hangs.
 */
export function effectiveHiddenComponents(
  components: readonly ComponentNode[],
  hiddenComponents: readonly string[],
): Set<string> {
  // Build a map from parent id → child ids so we can walk downward from
  // each explicitly hidden node.  Components with parent: null or parent
  // undefined are top-level and have no parent entry.
  const childrenByParent = new Map<string, string[]>();
  for (const c of components) {
    if (c.parent) {
      const list = childrenByParent.get(c.parent);
      if (list) list.push(c.id);
      else childrenByParent.set(c.parent, [c.id]);
    }
  }

  // Seed the result with explicitly-hidden ids.  An id that doesn't match any
  // component still appears (the spec requires it).
  const result = new Set<string>(hiddenComponents);

  // Walk downward from every explicitly hidden node, adding every descendant.
  // Use a visited set so a parent cycle or self-parent never hangs.
  for (const hid of hiddenComponents) {
    const queue: string[] = [];
    const localVisited = new Set<string>();
    // Push direct children
    for (const child of childrenByParent.get(hid) || []) {
      queue.push(child);
    }
    while (queue.length > 0) {
      const cur = queue.shift()!;
      if (localVisited.has(cur)) continue;
      localVisited.add(cur);
      result.add(cur);
      for (const child of childrenByParent.get(cur) || []) {
        if (!localVisited.has(child)) queue.push(child);
      }
    }
  }

  return result;
}

/**
 * Returns true when a requirement is hidden by component visibility.
 *
 * If no component satisfies the requirement, it is never governed by component
 * visibility (returns false). Otherwise it is hidden only when **every**
 * satisfying component is in `effectiveHidden`.
 */
export function isReqHiddenByComponents(
  reqId: string,
  components: readonly SatisfyingComponent[],
  effectiveHidden: ReadonlySet<string>,
): boolean {
  const satisfyingIds: string[] = [];
  for (const c of components) {
    if (c.satisfies?.includes(reqId)) {
      satisfyingIds.push(c.id);
    }
  }
  if (satisfyingIds.length === 0) return false;
  return satisfyingIds.every((id) => effectiveHidden.has(id));
}

/**
 * Returns true when a requirement is hidden by baseline visibility.
 *
 * If the requirement has no baselines (undefined or empty), it is never hidden.
 * Otherwise it is hidden only when **every** baseline is in `hiddenBaselines`.
 */
export function isReqHiddenByBaselines(
  reqBaselines: readonly string[] | undefined,
  hiddenBaselines: readonly string[],
): boolean {
  if (!reqBaselines || reqBaselines.length === 0) return false;
  return reqBaselines.every((b) => hiddenBaselines.includes(b));
}

/**
 * Converts a legacy include-list to a hidden-set.
 *
 * An undefined or empty include-list meant "show everything", so nothing is
 * hidden. Otherwise return every id in `allIds` that is NOT in `legacyIncluded`,
 * preserving `allIds` order.
 */
export function migrateLegacyFilterList(
  legacyIncluded: readonly string[] | undefined,
  allIds: readonly string[],
): string[] {
  if (!legacyIncluded || legacyIncluded.length === 0) return [];
  const includedSet = new Set(legacyIncluded);
  return allIds.filter((id) => !includedSet.has(id));
}

/**
 * Returns the ids of components that either satisfy at least one requirement
 * **or** appear in `hiddenComponents`, sorted ascending with no duplicates.
 *
 * This is exactly the "component has a reason to appear in the filter panel"
 * rule — an explicitly hidden component is always reversible from the panel
 * that shows it, even if it satisfies nothing.
 */
export function filterableComponentIds(
  components: readonly (ComponentNode & { satisfies?: string[] })[],
  hiddenComponents: readonly string[],
): string[] {
  const hiddenSet = new Set(hiddenComponents);
  const ids = new Set<string>();
  for (const c of components) {
    if ((c.satisfies && c.satisfies.length > 0) || hiddenSet.has(c.id)) {
      ids.add(c.id);
    }
  }
  // Only include hidden ids that correspond to a real component.
  return [...ids].sort();
}
