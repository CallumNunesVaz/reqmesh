import { createContext, useContext, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, X } from 'lucide-react';

interface ConfirmState {
  message: string;
  title?: string;
  resolve: (value: boolean) => void;
}

const ConfirmCtx = createContext<((message: string, title?: string) => Promise<boolean>) | null>(null);

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<ConfirmState | null>(null);

  const confirm = useCallback((message: string, title?: string): Promise<boolean> => {
    return new Promise((resolve) => {
      setState({ message, title, resolve });
    });
  }, []);

  const close = (value: boolean) => {
    state?.resolve(value);
    setState(null);
  };

  return (
    <ConfirmCtx.Provider value={confirm}>
      {children}
      <AnimatePresence>
        {state && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-[60] bg-black/50 backdrop-blur-[2px] flex items-center justify-center px-4"
            onClick={() => close(false)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 8 }}
              transition={{ duration: 0.12 }}
              onClick={(e) => e.stopPropagation()}
              className="card w-full max-w-sm p-5 shadow-2xl"
            >
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-full bg-amber-500/10 flex items-center justify-center shrink-0">
                  <AlertTriangle size={18} className="text-amber-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm font-semibold text-foreground">
                    {state.title || 'Confirm'}
                  </h3>
                  <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{state.message}</p>
                </div>
                <button onClick={() => close(false)} className="shrink-0 p-1 rounded text-muted-foreground hover:text-foreground hover:bg-accent">
                  <X size={14} />
                </button>
              </div>
              <div className="flex justify-end gap-2 mt-5">
                <button onClick={() => close(false)} className="btn-secondary text-xs">Cancel</button>
                <button onClick={() => close(true)} className="btn-danger text-xs">Confirm</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </ConfirmCtx.Provider>
  );
}

export function useConfirm() {
  const ctx = useContext(ConfirmCtx);
  if (!ctx) throw new Error('useConfirm must be used within a ConfirmProvider');
  return ctx;
}
