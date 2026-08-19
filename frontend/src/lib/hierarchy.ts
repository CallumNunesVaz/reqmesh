/** Parent/child helpers shared by the requirement and component trees.
 *
 *  Generalised from ComponentDetailPage's local `branchIds`, which existed to
 *  keep a component out of its own branch in the parent picker. The same rule
 *  governs drag-to-reparent and the bulk move, and all three must agree —
 *  a drop the picker would have refused is still a cycle.
 *
 *  The fixed-point loop rather than a recursive walk is deliberate: it
 *  terminates on corrupt data. `_meta.yaml` and the YAML store are hand-editable
 *  and arrive by git pull, so a parent cycle can exist on disk, and a recursive
 *  descent would not come back.
 */

export interface Node {
  id: string;
  parent?: string | null;
}

/** A node's id plus every id beneath it. */
export function branchIds<T extends Node>(items: T[], rootId: string): Set<string> {
  const ids = new Set([rootId]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const item of items) {
      if (item.parent && ids.has(item.parent) && !ids.has(item.id)) {
        ids.add(item.id);
        grew = true;
      }
    }
  }
  return ids;
}

/** The union of several branches — the moving set for a multi-row drag. */
export function subtreeOf<T extends Node>(items: T[], rootIds: string[]): Set<string> {
  const all = new Set<string>();
  for (const rootId of rootIds) {
    for (const id of branchIds(items, rootId)) all.add(id);
  }
  return all;
}

/** Everything that may legally become the parent of *movingIds*, in id order. */
export function validParents<T extends Node>(items: T[], movingIds: string[]): T[] {
  const blocked = subtreeOf(items, movingIds);
  return items
    .filter((item) => !blocked.has(item.id))
    .sort((a, b) => a.id.localeCompare(b.id));
}

/** Whether *movingIds* may be dropped onto *targetId* (null = make top level). */
export function isValidDrop<T extends Node>(
  items: T[],
  movingIds: string[],
  targetId: string | null,
): boolean {
  if (movingIds.length === 0) return false;
  if (targetId === null) {
    // Already top-level rows have nowhere to go.
    const byId = new Map(items.map((i) => [i.id, i]));
    return movingIds.some((id) => (byId.get(id)?.parent ?? null) !== null);
  }
  if (movingIds.includes(targetId)) return false;
  if (subtreeOf(items, movingIds).has(targetId)) return false;
  // A row already directly under the target would not move.
  const byId = new Map(items.map((i) => [i.id, i]));
  return movingIds.some((id) => (byId.get(id)?.parent ?? null) !== targetId);
}

/** What a drag actually moves.
 *
 *  Dragging a row that is part of the current selection moves the whole
 *  selection; dragging an unselected row moves just that row and leaves the
 *  selection alone. Anything else surprises the user in one direction or the
 *  other — silently moving twenty rows they forgot were ticked, or silently
 *  dropping a selection they built on purpose.
 */
export function dragPayload(selectedIds: Set<string>, draggedId: string): string[] {
  if (!selectedIds.has(draggedId)) return [draggedId];
  return [...selectedIds];
}

/** Roots only: dragging a parent and its child together should move the parent
 *  once, not fight over the child. */
export function topLevelOf<T extends Node>(items: T[], ids: string[]): string[] {
  const moving = new Set(ids);
  const byId = new Map(items.map((i) => [i.id, i]));
  return ids.filter((id) => {
    let cursor = byId.get(id)?.parent ?? null;
    const seen = new Set<string>([id]);
    while (cursor && !seen.has(cursor)) {
      if (moving.has(cursor)) return false;
      seen.add(cursor);
      cursor = byId.get(cursor)?.parent ?? null;
    }
    return true;
  });
}

/** A node id and its depth in the tree, for indenting axis labels. */
export interface OrderedNode {
  id: string;
  depth: number;
}

/** Depth-first ordering of a node list by its parent links.
 *
 *  Parents come before their children, and each child sits one level deeper
 *  than its parent. A node whose parent id is absent from the list is a root at
 *  depth 0 rather than being dropped — the YAML store is hand-editable, and an
 *  axis that silently omits a row is worse than one that shows an orphan at
 *  depth 0. A parent cycle terminates at the first revisit instead of hanging;
 *  the members a cycle keeps out of any root then surface as roots themselves.
 */
export function depthFirstOrder<T extends Node>(items: T[]): OrderedNode[] {
  const ids = new Set(items.map((i) => i.id));
  const children = new Map<string, T[]>();
  for (const item of items) {
    const parent = item.parent && ids.has(item.parent) ? item.parent : null;
    if (parent === null) continue;
    if (!children.has(parent)) children.set(parent, []);
    children.get(parent)!.push(item);
  }
  for (const list of children.values()) list.sort((a, b) => a.id.localeCompare(b.id));

  const ordered: OrderedNode[] = [];
  const seen = new Set<string>();

  const emit = (root: string) => {
    const stack: Array<{ id: string; depth: number }> = [{ id: root, depth: 0 }];
    while (stack.length) {
      const { id, depth } = stack.pop()!;
      if (seen.has(id)) continue;
      seen.add(id);
      ordered.push({ id, depth });
      const kids = children.get(id) ?? [];
      for (let i = kids.length - 1; i >= 0; i--) {
        stack.push({ id: kids[i].id, depth: depth + 1 });
      }
    }
  };

  // Roots first — top-level nodes and orphans — then anything a cycle kept out.
  const roots = items
    .filter((item) => !item.parent || !ids.has(item.parent))
    .sort((a, b) => a.id.localeCompare(b.id));
  for (const root of roots) emit(root.id);
  for (const item of items) if (!seen.has(item.id)) emit(item.id);

  return ordered;
}
