import { useDraggable, useDroppable } from '@dnd-kit/core';
import { GripVertical } from 'lucide-react';
import { TOP_LEVEL_ID } from '../hooks/useTreeDrag';

/**
 * Makes a tree row a drop target and exposes a grip that starts a drag.
 *
 * The listeners live on the grip, not the row, so the row keeps its own
 * click-to-navigate and its checkbox keeps working. The grip only appears on
 * hover — and only in edit mode, since the caller does not render this at all
 * otherwise.
 */
export function DropRow({
  id, disabled, isOver, valid, children,
}: {
  id: string;
  disabled?: boolean;
  isOver: boolean;
  valid: boolean;
  children: React.ReactNode;
}) {
  const { setNodeRef } = useDroppable({ id, disabled });
  const ring = isOver
    ? (valid ? 'ring-2 ring-primary/60 bg-primary/5' : 'ring-2 ring-destructive/40 cursor-not-allowed')
    : '';
  return (
    <div ref={setNodeRef} className={`rounded-lg transition-shadow ${ring}`}>
      {children}
    </div>
  );
}

export function DragGrip({ id, label }: { id: string; label: string }) {
  const { attributes, listeners, setNodeRef } = useDraggable({ id });
  return (
    <button
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      onClick={(e) => e.stopPropagation()}
      title={`Drag to move ${label}`}
      aria-label={`Drag to move ${label}`}
      className="p-1 rounded text-muted-foreground/50 hover:text-foreground cursor-grab active:cursor-grabbing opacity-0 group-hover:opacity-100 transition-opacity"
    >
      <GripVertical size={13} />
    </button>
  );
}

/** The "drop here to make top level" strip, shown only while dragging.
 *  A visible target beats a hidden edge zone nobody discovers. */
export function TopLevelDropZone({ active, isOver }: { active: boolean; isOver: boolean }) {
  const { setNodeRef } = useDroppable({ id: TOP_LEVEL_ID, disabled: !active });
  if (!active) return null;
  return (
    <div
      ref={setNodeRef}
      className={`mb-2 px-3 py-2 text-[11px] text-center rounded-lg border-2 border-dashed transition-colors ${
        isOver ? 'border-primary bg-primary/10 text-primary' : 'border-border text-muted-foreground'
      }`}
    >
      Drop here to make top level
    </div>
  );
}
