import { createPortal } from 'react-dom';

/**
 * Render children into document.body. Needed for `fixed inset-0` overlays that
 * live inside a CSS container (`container-type` implies `contain: layout`,
 * which turns the container into the containing block for fixed descendants —
 * portalling to body keeps overlays viewport-anchored).
 */
export default function BodyPortal({ children }: { children: React.ReactNode }) {
  return createPortal(children, document.body);
}
