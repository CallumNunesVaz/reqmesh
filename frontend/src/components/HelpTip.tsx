import { useStore } from '../store';

export function HelpTip({ children }: { children: React.ReactNode }) {
  const helpersEnabled = useStore((s) => s.helpersEnabled);
  if (!helpersEnabled) return null;
  return (
    <p className="text-[10px] text-muted-foreground/60 leading-relaxed mt-0.5 mb-2 italic">
      {children}
    </p>
  );
}

export function HelpBadge({ children }: { children: React.ReactNode }) {
  const helpersEnabled = useStore((s) => s.helpersEnabled);
  if (!helpersEnabled) return null;
  return (
    <span className="text-[9px] text-muted-foreground/50 ml-1 font-normal not-italic">
      — {children}
    </span>
  );
}
