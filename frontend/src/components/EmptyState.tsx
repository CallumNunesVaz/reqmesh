import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';

/**
 * The one empty-state look.
 *
 * Sixteen pages each rendered their own `card p-12 text-center` block with an
 * icon, a title and a hint — near-identical, but drifting in icon size, muted
 * shade and spacing. The ones that did *not* follow that shape were worse
 * rather than different: `ActivityChart` rendered a full-height card containing
 * a single line of grey text, which reads as a broken panel rather than an
 * empty one.
 *
 * `variant="bare"` exists for that case: a component that is already inside a
 * card needs the content without a second card around it. Wrapping a card in a
 * card is the specific bug this avoids.
 */
export interface EmptyStateProps {
  /** Decorative only — the title carries the meaning, so this is aria-hidden. */
  icon?: LucideIcon;
  /** What is empty. One line. */
  title: string;
  /** Optional second line: what to do about it. */
  hint?: string;
  /** Only ever wire this to a handler the page already has. */
  action?: { label: string; onClick: () => void };
  /** Anything the page already renders below the hint — most pages have a
   *  "Clear filters" link rather than a button, and those keep their own
   *  markup rather than being forced into `action`. */
  children?: ReactNode;
  /** `bare` drops the card chrome, for use inside a card that already exists. */
  variant?: 'card' | 'bare';
  className?: string;
}

export default function EmptyState({
  icon: Icon, title, hint, action, children, variant = 'card', className = '',
}: EmptyStateProps) {
  const shell = variant === 'card' ? 'card p-12' : 'py-10';
  return (
    <div className={`${shell} text-center ${className}`}>
      {Icon && <Icon size={48} aria-hidden className="mx-auto text-muted-foreground/40 mb-4" />}
      <p className="text-card-foreground font-medium">{title}</p>
      {hint && <p className="text-sm text-muted-foreground mt-1">{hint}</p>}
      {action && (
        <button onClick={action.onClick} className="btn-secondary mt-4">
          {action.label}
        </button>
      )}
      {children}
    </div>
  );
}
