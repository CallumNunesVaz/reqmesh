import { Info } from 'lucide-react';
import type { TruncationInfo } from '../api/client';

/**
 * An informational banner shown on list pages when the server returns fewer
 * items than exist — the user is looking at a truncated view and should
 * narrow their search or apply filters to see the rest.
 */
export default function TruncationBanner({ info }: { info: TruncationInfo }) {
  return (
    <div className="rounded-lg border border-blue-500/20 bg-blue-500/[0.04] p-3 mb-4">
      <div className="flex items-start gap-2">
        <Info size={14} className="text-blue-400 shrink-0 mt-0.5" />
        <p className="text-sm text-card-foreground/80">
          Showing {info.shown.toLocaleString()} of {info.total.toLocaleString()}.{' '}
          Search or filter to narrow the list.
        </p>
      </div>
    </div>
  );
}
