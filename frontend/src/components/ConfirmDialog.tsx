import { createContext, useContext, useState, useCallback } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import Modal from './Modal';

interface ConfirmOptions {
  resultLabel?: string;
  destructive?: boolean;
}

interface ConfirmState {
  message: string;
  title?: string;
  resultLabel?: string;
  destructive?: boolean;
  resolve: (value: boolean) => void;
}

type ConfirmFn = (message: string, title?: string, options?: ConfirmOptions) => Promise<boolean>;

const ConfirmCtx = createContext<ConfirmFn | null>(null);

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<ConfirmState | null>(null);

  const confirm = useCallback((message: string, title?: string, options?: ConfirmOptions): Promise<boolean> => {
    return new Promise((resolve) => {
      setState({ message, title, resultLabel: options?.resultLabel, destructive: options?.destructive, resolve });
    });
  }, []);

  const close = (value: boolean) => {
    state?.resolve(value);
    setState(null);
  };

  return (
    <ConfirmCtx.Provider value={confirm}>
      {children}
      {/* `elevated`: a confirm can be raised from inside another dialog, so it
          has to outrank one. It was z-[60] against everyone else's z-50 before
          the shells were extracted. */}
      <Modal open={state !== null} onClose={() => close(false)} elevated panelClassName="w-full max-w-sm p-5">
        {state && (
          <>
            <div className="flex items-start gap-3">
              <div className="w-9 h-9 rounded-full bg-cs-amber/10 flex items-center justify-center shrink-0">
                <AlertTriangle size={18} className="text-cs-amber" />
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
              <button
                onClick={() => close(true)}
                className={state.destructive === false ? 'btn-primary text-xs' : 'btn-danger text-xs'}
              >
                {state.resultLabel || 'Confirm'}
              </button>
            </div>
          </>
        )}
      </Modal>
    </ConfirmCtx.Provider>
  );
}

export function useConfirm() {
  const ctx = useContext(ConfirmCtx);
  if (!ctx) throw new Error('useConfirm must be used within a ConfirmProvider');
  return ctx;
}
