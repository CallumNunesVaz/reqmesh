import { useState, useCallback, useEffect, useRef, createContext, useContext } from 'react';
import { X, CheckCircle2, AlertTriangle } from 'lucide-react';

export type ToastKind = 'success' | 'error';
export interface Toast { id: number; kind: ToastKind; message: string }

/** Append a toast, keeping at most `limit` — the newest win. Pure, so the
 *  queue logic is testable without rendering. */
export function pushToast(current: Toast[], kind: ToastKind, message: string,
                          nextId: number, limit = 3): Toast[] {
  const next = [...current, { id: nextId, kind, message }];
  while (next.length > limit) next.shift();
  return next;
}

interface ToastCtxValue {
  toasts: Toast[];
  addToast: (kind: ToastKind, message: string) => void;
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

function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: (id: number) => void }) {
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

  const bg = toast.kind === 'success' ? 'bg-emerald-600' : 'bg-red-600';

  return (
    <div
      role="alert"
      className={`flex items-center gap-2 px-4 py-2.5 rounded-lg shadow-lg text-white text-sm ${bg} ${
        reducedMotion.current ? '' : 'transition-all duration-300'
      } ${entering ? 'translate-y-4 opacity-0' : 'translate-y-0 opacity-100'}`}
    >
      {toast.kind === 'success' ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
      <span className="flex-1">{toast.message}</span>
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

  const addToast = useCallback((kind: ToastKind, message: string) => {
    const id = nextId.current++;
    setToasts((prev) => pushToast(prev, kind, message, id));
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
