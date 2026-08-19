import { useState, useCallback, useEffect, useRef, createContext, useContext } from 'react';
import { X, CheckCircle2, AlertTriangle } from 'lucide-react';
import { GuardedLink } from './navGuard';

export type ToastKind = 'success' | 'error';
export interface ToastAction { label: string; to: string }
export interface Toast { id: number; kind: ToastKind; message: string; action?: ToastAction }

/** Append a toast, keeping at most `limit` — the newest win. Pure, so the
 *  queue logic is testable without rendering. */
export function pushToast(current: Toast[], kind: ToastKind, message: string,
                          nextId: number, limit = 3, action?: ToastAction): Toast[] {
  const next = [...current, { id: nextId, kind, message, ...(action ? { action } : {}) }];
  while (next.length > limit) next.shift();
  return next;
}

interface ToastCtxValue {
  toasts: Toast[];
  addToast: (kind: ToastKind, message: string, action?: ToastAction) => void;
  removeToast: (id: number) => void;
}

const ToastCtx = createContext<ToastCtxValue>({
  toasts: [],
  addToast: () => {},
  removeToast: () => {},
});

export function useToasts() {
  return useContext(ToastCtx);
}

export function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: (id: number) => void }) {
  const reducedMotion = useRef(false);
  useEffect(() => {
    reducedMotion.current = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }, []);

  const [entering, setEntering] = useState(true);
  useEffect(() => {
    const t = setTimeout(() => setEntering(false), 50);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    const ms = toast.kind === 'error' ? 8000 : 4000;
    const t = setTimeout(() => onRemove(toast.id), ms);
    return () => clearTimeout(t);
  }, [toast.id, toast.kind, onRemove]);

  const bg = toast.kind === 'success' ? 'bg-cs-green' : 'bg-destructive';

  return (
    <div
      role="alert"
      className={`flex items-center gap-2 px-4 py-2.5 rounded-lg shadow-lg text-white text-sm ${bg} ${
        reducedMotion.current ? '' : 'transition-all duration-300'
      } ${entering ? 'translate-y-4 opacity-0' : 'translate-y-0 opacity-100'}`}
    >
      {toast.kind === 'success' ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
      <span className="flex-1">
        {toast.message}{toast.action ? ' ' : null}
        {toast.action && (
          <GuardedLink
            to={toast.action.to}
            className="underline underline-offset-2 hover:opacity-80"
          >
            {toast.action.label}
          </GuardedLink>
        )}
      </span>
      <button
        onClick={() => onRemove(toast.id)}
        className="p-0.5 rounded hover:bg-white/20 transition-colors"
        aria-label="Dismiss"
      >
        <X size={14} />
      </button>
    </div>
  );
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const addToast = useCallback((kind: ToastKind, message: string, action?: ToastAction) => {
    const id = nextId.current++;
    setToasts((prev) => pushToast(prev, kind, message, id, 3, action));
  }, []);

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastCtx.Provider value={{ toasts, addToast, removeToast }}>
      {children}
      <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex flex-col gap-2 items-center pointer-events-none">
        {toasts.map((t) => (
          <div key={t.id} className="pointer-events-auto">
            <ToastItem toast={t} onRemove={removeToast} />
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
