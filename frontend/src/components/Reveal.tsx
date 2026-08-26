import { motion } from 'framer-motion';
import type { ReactNode } from 'react';
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

export interface RevealProps {
  /** Position in the stagger. Capped at 6 — content that far down the page is
   *  usually below the fold, where a delay is a cost with no benefit. */
  step?: 0 | 1 | 2 | 3 | 4 | 5 | 6;
  className?: string;
  children: ReactNode;
}

export default function Reveal({ step = 0, className, children }: RevealProps) {
  const reduced = useReducedMotion();

  if (reduced) {
    return <div className={className}>{children}</div>;
  }

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: step * BEAT_SECONDS }}
    >
      {children}
    </motion.div>
  );
}
