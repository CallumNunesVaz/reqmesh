import { useMemo, useState } from 'react';
import type { PresenceUser } from '../api/client';

interface PresenceBarProps {
  users: PresenceUser[];
  self?: string;
}

// Deterministic colour per username so the same person keeps their swatch.
const COLORS = [
  'bg-cs-blue', 'bg-cs-green', 'bg-cs-purple', 'bg-cs-teal',
  'bg-cs-orange', 'bg-cs-pink', 'bg-cs-red',
];

function colorFor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) & 0xffffffff;
  return COLORS[Math.abs(hash) % COLORS.length];
}

function initials(name: string): string {
  const parts = name.trim().split(/[\s_-]+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

export default function PresenceBar({ users, self }: PresenceBarProps) {
  const [hovered, setHovered] = useState(false);

  // Collapse multiple tabs/sessions of the same user into one avatar.
  const unique = useMemo(() => {
    const seen = new Map<string, PresenceUser>();
    for (const u of users) if (!seen.has(u.username)) seen.set(u.username, u);
    return [...seen.values()];
  }, [users]);

  if (unique.length === 0) return null;

  const shown = unique.slice(0, 4);
  const overflow = unique.length - shown.length;

  return (
    <div
      className="relative flex items-center"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      title={`${unique.length} viewer${unique.length === 1 ? '' : 's'} online`}
    >
      <div className="flex -space-x-2">
        {shown.map((u) => (
          <div
            key={u.username}
            className={`w-6 h-6 rounded-full ${colorFor(u.username)} text-white text-[9px] font-semibold flex items-center justify-center ring-2 ring-card`}
          >
            {initials(u.username)}
          </div>
        ))}
        {overflow > 0 && (
          <div className="w-6 h-6 rounded-full bg-muted text-muted-foreground text-[9px] font-semibold flex items-center justify-center ring-2 ring-card">
            +{overflow}
          </div>
        )}
      </div>

      {hovered && (
        <div className="absolute top-8 right-0 z-50 bg-card border rounded-lg shadow-xl py-1.5 min-w-[160px]">
          <div className="px-3 py-1 text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
            Online now
          </div>
          {unique.map((u) => (
            <div key={u.username} className="flex items-center gap-2 px-3 py-1 text-xs">
              <span className={`w-2 h-2 rounded-full ${colorFor(u.username)}`} />
              <span className="text-foreground truncate">{u.username}</span>
              {u.username === self && <span className="text-[9px] text-muted-foreground">(you)</span>}
              <span className="ml-auto text-[9px] text-muted-foreground">{u.role}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
