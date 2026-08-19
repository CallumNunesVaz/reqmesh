import type { Risk } from '../api/client';

/**
 * The group filters narrow risks by the part of the tree they touch. The
 * requirement and component trees each expose nodes shaped `{ id, children }`,
 * so the matching here is generic over that minimum; the concrete tree types
 * from the API (``RequirementTreeNode``, ``ComponentTreeNode``) are structurally
 * compatible and pass straight through.
 */
export interface TreeNode {
  id: string;
  children: TreeNode[];
}

/** Ids in `groupId`'s subtree, inclusive of `groupId` itself. */
export function subtreeIds(nodes: TreeNode[], groupId: string): Set<string> {
  const ids = new Set<string>();
  const find = (list: TreeNode[]): boolean => {
    for (const n of list) {
      if (n.id === groupId) {
        const collect = (x: TreeNode): void => {
          ids.add(x.id);
          x.children.forEach(collect);
        };
        collect(n);
        return true;
      }
      if (n.children.length > 0 && find(n.children)) return true;
    }
    return false;
  };
  find(nodes);
  return ids;
}

/** Does this risk touch the group's subtree, in either direction? */
export function riskInGroup(risk: Risk, subtree: Set<string>): boolean {
  const linked = [
    ...(risk.linked_requirements ?? []),
    ...(risk.mitigating_requirements ?? []),
    ...(risk.linked_components ?? []),
    ...(risk.mitigating_components ?? []),
  ];
  return linked.some((id) => subtree.has(id));
}

/** A flattened node for the group pickers: id, display name, and depth. */
export interface TreeOption {
  id: string;
  name: string;
  depth: number;
}

/** Depth-first flatten with depth, so a picker can show the hierarchy. */
export function flattenTree<T extends { id: string; name?: string; children: T[] }>(
  nodes: T[],
  depth = 0,
): TreeOption[] {
  return nodes.flatMap((n) => [
    { id: n.id, name: n.name ?? n.id, depth },
    ...flattenTree(n.children, depth + 1),
  ]);
}
