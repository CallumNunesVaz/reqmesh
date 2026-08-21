import type { Node } from '@xyflow/react';

// Applies selection-derived styling (`isSelected` / `dimmed`) onto node `data`.
// This is what makes the node components' `memo(...)` actually hold: a node
// whose booleans did not change is returned by reference, so React Flow (and
// the memoised component) see the exact same `data` object and bail out.

export interface SelectionRestyleInput {
  selectedReqId: string | null;
  hasSelection: boolean;
  connectedIds: ReadonlySet<string>;
}

export function applySelectionToNodes(
  nodes: readonly Node[],
  input: SelectionRestyleInput,
): Node[] {
  const { selectedReqId, hasSelection, connectedIds } = input;
  let changed = false;
  const next = nodes.map((n) => {
    const d = n.data as Record<string, unknown> | undefined;
    const isSelected = selectedReqId === n.id;
    const dimmed = hasSelection && !connectedIds.has(n.id);
    if (d?.isSelected === isSelected && d?.dimmed === dimmed) return n;
    changed = true;
    return { ...n, data: { ...d, isSelected, dimmed } };
  });
  return changed ? next : nodes as Node[];
}
