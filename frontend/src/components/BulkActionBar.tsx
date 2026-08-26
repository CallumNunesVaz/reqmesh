import { X } from 'lucide-react';

/**
 * The shared sticky bulk-action bar.
 *
 * Five list pages repeated the same wrapper plus the same "N selected /
 * Select all / ✕" trio byte-for-byte, and drifted only in which action buttons
 * they offered. This owns the wrapper and the trio; each page passes its own
 * actions as children.
 */
interface BulkActionBarProps {
  count: number;
  onSelectAll: () => void;
  onClear: () => void;
  children?: React.ReactNode;
}

export default function BulkActionBar({ count, onSelectAll, onClear, children }: BulkActionBarProps) {
  return (
    <div className="sticky bottom-6 z-40 mx-auto w-fit max-w-full flex flex-wrap items-center justify-center gap-3 bg-card border rounded-lg shadow-2xl px-4 py-3">
      <span className="text-xs font-medium text-foreground">{count} selected</span>
      {children}
      <button onClick={onSelectAll} className="text-3xs text-muted-foreground hover:text-foreground">Select all</button>
      <button onClick={onClear} className="text-3xs text-muted-foreground hover:text-foreground">
        <X size={13} />
      </button>
    </div>
  );
}
