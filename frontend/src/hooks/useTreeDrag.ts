import { useMemo, useState } from 'react';
import {
  KeyboardSensor, PointerSensor, useSensor, useSensors,
  closestCenter, pointerWithin, type ClientRect, type CollisionDetection,
  type DragEndEvent, type DragOverEvent, type DragStartEvent,
} from '@dnd-kit/core';
import { dragPayload, isValidDrop, topLevelOf, type Node } from '../lib/hierarchy';

/** Sentinel droppable id for the "make top level" strip. */
export const TOP_LEVEL_ID = '__top_level__';

/** The tight bounding box around every droppable in a context. */
function droppableBounds(rects: Iterable<ClientRect>) {
  let top = Infinity, left = Infinity, bottom = -Infinity, right = -Infinity;
  for (const r of rects) {
    top = Math.min(top, r.top);
    left = Math.min(left, r.left);
    bottom = Math.max(bottom, r.bottom);
    right = Math.max(right, r.right);
  }
  return top === Infinity ? null : { top, left, bottom, right };
}

/** The gap around the tree (card padding and the space to the page edge) that
 *  still counts as "over the tree" for the closest-centre fallback. */
const FALLBACK_MARGIN = 24;

/**
 * Resolve the drop target by the pointer, not the dragged element's centre.
 *
 * The draggable is the small grip at the row's left edge, so `closestCenter`
 * (which compares the dragged element's translated centre to each droppable's
 * centre) sits half a row or more above the cursor and drifts further with row
 * height. `pointerWithin` uses the cursor itself, so the row highlighted is the
 * row the pointer is actually over, and that is the row that receives the drop.
 *
 * When the pointer leaves every droppable it falls back to `closestCenter`, so
 * the highlight does not flicker off mid-drag over the gap between the tree and
 * the page edge. But once the pointer has left the tree entirely — the header,
 * the sidebar, the graph canvas — there is no droppable to fall back onto, so
 * returning nothing lets the drop cancel instead of landing on whatever row
 * happens to be nearest.
 */
const collisionDetection: CollisionDetection = (args) => {
  const within = pointerWithin(args);
  if (within.length > 0) return within;

  const { pointerCoordinates, droppableRects } = args;
  if (pointerCoordinates) {
    const bounds = droppableBounds(droppableRects.values());
    if (
      bounds &&
      (pointerCoordinates.x < bounds.left - FALLBACK_MARGIN ||
        pointerCoordinates.x > bounds.right + FALLBACK_MARGIN ||
        pointerCoordinates.y < bounds.top - FALLBACK_MARGIN ||
        pointerCoordinates.y > bounds.bottom + FALLBACK_MARGIN)
    ) {
      return [];
    }
  }
  return closestCenter(args);
};

/**
 * Shared drag-to-reparent wiring for the requirement and component trees.
 *
 * Every tree row is also a link — clicking it navigates. The 6px activation
 * distance is what keeps both behaviours: below it the click still navigates,
 * above it a move starts. Hand-rolling that threshold on two trees and a
 * sortable list is more code than the dependency it avoids.
 *
 * A drop never mutates. It hands the resolved payload back so the caller can
 * open the same confirm dialog the menu path uses — otherwise a drag would be
 * the one route to a project-wide id rewrite that skips the warning.
 */
export function useTreeDrag<T extends Node>(opts: {
  items: T[];
  selectedIds: Set<string>;
  onDrop: (movingIds: string[], newParent: string | null) => void;
}) {
  const [draggingIds, setDraggingIds] = useState<string[]>([]);
  const [overId, setOverId] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor),
  );

  const onDragStart = (e: DragStartEvent) => {
    const id = String(e.active.id);
    setDraggingIds(dragPayload(opts.selectedIds, id));
  };

  const onDragOver = (e: DragOverEvent) => {
    setOverId(e.over ? String(e.over.id) : null);
  };

  const onDragCancel = () => {
    setDraggingIds([]);
    setOverId(null);
  };

  const onDragEnd = (e: DragEndEvent) => {
    const moving = draggingIds;
    const over = e.over ? String(e.over.id) : null;
    setDraggingIds([]);
    setOverId(null);
    if (!over || moving.length === 0) return;

    const target = over === TOP_LEVEL_ID ? null : over;
    if (!isValidDrop(opts.items, moving, target)) return;
    // Dragging a parent and its child together should move the parent once,
    // not have the two fight over where the child lands.
    opts.onDrop(topLevelOf(opts.items, moving), target);
  };

  /** Whether the row currently hovered is a legal destination — drives the
   *  ring colour, and stops an illegal drop looking droppable. */
  const dropIsValid = useMemo(() => {
    if (!overId || draggingIds.length === 0) return false;
    return isValidDrop(opts.items, draggingIds, overId === TOP_LEVEL_ID ? null : overId);
  }, [overId, draggingIds, opts.items]);

  return {
    sensors,
    draggingIds,
    overId,
    dropIsValid,
    isDragging: draggingIds.length > 0,
    dndHandlers: { onDragStart, onDragOver, onDragEnd, onDragCancel },
    collisionDetection,
  };
}
