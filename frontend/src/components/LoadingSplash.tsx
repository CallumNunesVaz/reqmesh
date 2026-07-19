// Generic long-load splash: blurs whatever is underneath and spins the
// reqmesh mark in the foreground. Position it inside any `relative` container
// (or pass fullscreen for viewport-level loads). The overlay fades in after a
// beat so fast loads never flash it.

interface LoadingSplashProps {
  label?: string;
  fullscreen?: boolean;
  /** Fade the overlay out; unmount it once the exit animation has run. */
  leaving?: boolean;
}

export default function LoadingSplash({ label, fullscreen = false, leaving = false }: LoadingSplashProps) {
  return (
    <div
      className={`${fullscreen ? 'fixed' : 'absolute'} inset-0 z-[70] flex flex-col items-center justify-center gap-3 bg-background/40 backdrop-blur-sm rm-splash ${leaving ? 'rm-splash-leave' : ''}`}
      role="status"
      aria-label={label || 'Loading'}
    >
      <img src="/reqmesh-mark.png" alt="" className="w-12 h-12 rm-splash-spin" draggable={false} />
      {label && <div className="text-xs text-muted-foreground font-medium">{label}</div>}
      <style>{`
        .rm-splash {
          opacity: 0;
          animation: rm-splash-in 0.25s ease-out 0.15s forwards;
        }
        @keyframes rm-splash-in {
          to { opacity: 1; }
        }
        .rm-splash-leave {
          animation: rm-splash-out 0.35s ease forwards;
        }
        @keyframes rm-splash-out {
          from { opacity: 1; }
          to { opacity: 0; }
        }
        .rm-splash-spin {
          animation: rm-splash-spin 1.4s cubic-bezier(0.55, 0.12, 0.45, 0.88) infinite;
          filter: drop-shadow(0 2px 8px hsl(var(--foreground) / 0.15));
        }
        @keyframes rm-splash-spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
