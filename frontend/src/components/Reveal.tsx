import { motion } from 'framer-motion';
import type { KeyboardEvent, ReactNode } from 'react';
import { useReducedMotion } from '../hooks/useReducedMotion';

/**
 * The page-entry rise-and-fade, in one place.
 *
 * This incantation was copy-pasted 55 times across 27 files:
 *
 *   <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
 *               transition={{ delay: 0.15 }} className="card p-5">
 *
 * with **26 distinct delay values** — 0.05, 0.1, 0.12, 0.15, 0.18, 0.19, 0.2,
 * 0.22, 0.225, 0.23, 0.24, 0.25, 0.26, 0.27, 0.28, 0.3, 0.31, 0.315, 0.32,
 * 0.33, 0.35, 0.4, 0.5, 0.55, 0.6, 0.65. Nobody chose 0.225 and 0.315 as
 * distinct design values; they accreted. `step` replaces them with a fixed
 * beat, so a stagger is a position in a sequence rather than a number someone
 * typed.
 *
 * Reduced motion renders a plain element with no animation at all — not a
 * faster one. "Reduce" means remove, and a 200ms slide is still a slide.
 */

/** One beat. `step={3}` is a 0.15s delay. */
const BEAT_SECONDS = 0.05;

/** Content past this point is usually below the fold, where a delay is a cost
 *  with no benefit. */
const MAX_STEP = 6;

export interface RevealProps {
  /** Position in the stagger. Takes a plain number rather than a literal union
   *  so a list can pass its loop index — the adoption sweep found several
   *  `delay: i * 0.05` call sites that a union type could not express — and
   *  clamps here so no caller has to remember the cap. */
  step?: number;
  /** Passed through: the entity-focus system scrolls to rows by `entity-<id>`,
   *  so a row that animates in still has to be addressable. */
  id?: string;
  /** When given, the element becomes a real button for keyboard users too.
   *  The card grids that pass this (project cards, overview stat tiles) were
   *  clickable divs with no keyboard path at all — `motion.div` hid that from
   *  the linter, a plain div does not. */
  onClick?: () => void;
  className?: string;
  children: ReactNode;
}

export default function Reveal({ step = 0, id, onClick, className, children }: RevealProps) {
  const reduced = useReducedMotion();

  const beats = Math.min(Math.max(Math.round(step), 0), MAX_STEP);

  // Enter and Space are what a button responds to; without these the card is
  // mouse-only.
  const interactive = onClick
    ? {
      onClick,
      role: 'button',
      tabIndex: 0,
      onKeyDown: (e: KeyboardEvent) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); }
      },
    }
    : {};

  if (reduced) {
    return <div id={id} className={className} {...interactive}>{children}</div>;
  }

  return (
    <motion.div
      id={id}
      {...interactive}
      className={className}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: beats * BEAT_SECONDS }}
    >
      {children}
    </motion.div>
  );
}
