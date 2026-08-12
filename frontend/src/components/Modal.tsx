import { useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import BodyPortal from './BodyPortal';

/**
 * The one shared modal shell.
 *
 * Every dialog used to hand-roll a `fixed inset-0` overlay, and the copies had
 * drifted apart — three radii, four backdrops, four z-indices — and none of
 * them declared a role or trapped focus, so Tab walked straight through a
 * dialog into the page behind it. This component owns the portal, the
 * backdrop, the centring, escape-to-close, the panel chrome, and the focus
 * trap. Settled values (the most common in the app at the time of extraction):
 *
 *   radius    rounded-xl
 *   backdrop  bg-background/80 backdrop-blur-sm
 *   z-index   z-50, or z-[60] with `elevated` — see that prop
 *
 * Callers keep everything about their own content and size via `panelClassName`.
 */
interface ModalProps {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  /** Panel size/overflow overrides. Modal supplies the shared chrome. */
  panelClassName?: string;
  /** 'center' (default) or 'top' for the viewport-anchored panels. */
  align?: 'center' | 'top';
  /** Viewport top padding used when `align="top"`. */
  topOffset?: string;
  /** Close on Escape. Defaults to false — most dialogs historically didn't. */
  closeOnEscape?: boolean;
  /**
   * Render above other modals. Only the confirmation dialog needs it: a confirm
   * can be raised *from* another dialog, and at equal z-index which one wins is
   * decided by whichever portal mounted second. It sat at `z-[60]` against
   * everyone else's `z-50` before this extraction, and that was deliberate.
   */
  elevated?: boolean;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function Modal({
  open,
  onClose,
  children,
  panelClassName = '',
  align = 'center',
  topOffset = 'pt-[8vh]',
  closeOnEscape = false,
  elevated = false,
}: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  // Trap focus inside the panel while it is open. The one behavioural change
  // this refactor makes: without it, Tab reaches the page behind the dialog.
  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    if (!panel) return;

    const focusable = () =>
      Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => el.offsetParent !== null,
      );

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      const items = focusable();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || !panel.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else if (active === last || !panel.contains(active)) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown, true);

    // Focus the first control on open — unless something inside already took
    // focus (an `autoFocus` field commits before this effect runs).
    const active = document.activeElement;
    if (!panel.contains(active)) {
      (focusable()[0] ?? panel).focus();
    }

    return () => document.removeEventListener('keydown', onKeyDown, true);
  }, [open]);

  useEffect(() => {
    if (!open || !closeOnEscape) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener('keydown', onKey, true);
    return () => document.removeEventListener('keydown', onKey, true);
  }, [open, closeOnEscape, onClose]);

  const position =
    align === 'top'
      ? `flex items-start justify-center px-4 ${topOffset}`
      : 'flex items-center justify-center px-4';

  return (
    <BodyPortal>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className={`fixed inset-0 ${elevated ? 'z-[60]' : 'z-50'} bg-background/80 backdrop-blur-sm ${position}`}
            onClick={onClose}
          >
            <motion.div
              ref={panelRef}
              // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role
              role="dialog"
              aria-modal="true"
              tabIndex={-1}
              initial={{ opacity: 0, scale: 0.95, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 8 }}
              transition={{ duration: 0.12 }}
              onClick={(e) => e.stopPropagation()}
              className={`relative bg-card border rounded-xl shadow-2xl ${panelClassName}`}
            >
              {children}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </BodyPortal>
  );
}
