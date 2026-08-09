import { useMemo, useState } from 'react';
import {
  KeyboardSensor, PointerSensor, useSensor, useSensors,
  type DragEndEvent, type DragOverEvent, type DragStartEvent,
} from '@dnd-kit/core';
import { dragPayload, isValidDrop, topLevelOf, type Node } from '../lib/hierarchy';

/** Sentinel droppable id for the "make top level" strip. */
export const TOP_LEVEL_ID = '__top_level__';

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
  };
}
