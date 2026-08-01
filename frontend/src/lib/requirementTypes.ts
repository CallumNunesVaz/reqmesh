import {
  AlertTriangle, Briefcase, CheckCircle, Cpu, Gauge, Leaf, Plug, Shield, User, Zap,
} from 'lucide-react';

/**
 * The single source of truth for requirement types in the UI.
 *
 * These used to be declared six times over — a full 16-entry map on the
 * requirements list, a parallel 16-entry array on the detail page, three
 * nine-entry colour/icon maps (overview, detail, graph) that leaned on a
 * `startsWith('non_functional')` rule to cover the rest, and a hand-written
 * five-option dropdown on the allocation matrix. They had drifted: the
 * allocation matrix offered 5 of the 16 and labelled `non_functional_performance`
 * as plain "Non-Functional", so filtering by it quietly excluded the other seven
 * non-functional variants; the overview drew four different types with the same
 * padlock icon.
 *
 * The order here is the order the backend enum declares (see
 * backend/app/models/requirement.py::RequirementType) and is the order every
 * dropdown renders in. `e2e/inventory.spec.ts` asserts this list still matches
 * the enum the API advertises, so adding a type on one side and forgetting the
 * other fails a test rather than silently dropping options from a filter.
 */

export interface RequirementTypeMeta {
  /** Human label, used in every dropdown, badge and legend. */
  label: string;
  icon: typeof Zap;
  /** The `--cs-*` palette token this type is drawn in. */
  token: string;
}

export const REQUIREMENT_TYPE_META: Record<string, RequirementTypeMeta> = {
  functional: { label: 'Functional', icon: Zap, token: 'blue' },
  non_functional_performance: { label: 'Non-Functional – Performance', icon: Gauge, token: 'teal' },
  non_functional_security: { label: 'Non-Functional – Security', icon: Gauge, token: 'teal' },
  non_functional_usability: { label: 'Non-Functional – Usability', icon: Gauge, token: 'teal' },
  non_functional_maintainability: { label: 'Non-Functional – Maintainability', icon: Gauge, token: 'teal' },
  non_functional_reliability: { label: 'Non-Functional – Reliability', icon: Gauge, token: 'teal' },
  non_functional_scalability: { label: 'Non-Functional – Scalability', icon: Gauge, token: 'teal' },
  non_functional_portability: { label: 'Non-Functional – Portability', icon: Gauge, token: 'teal' },
  interface: { label: 'Interface', icon: Plug, token: 'purple' },
  user: { label: 'User', icon: User, token: 'yellow' },
  system: { label: 'System', icon: Cpu, token: 'pink' },
  business: { label: 'Business', icon: Briefcase, token: 'blue' },
  regulatory_compliance: { label: 'Regulatory/Compliance', icon: Shield, token: 'red' },
  safety: { label: 'Safety', icon: AlertTriangle, token: 'orange' },
  environmental: { label: 'Environmental', icon: Leaf, token: 'green' },
  verification: { label: 'Verification', icon: CheckCircle, token: 'teal' },
};

/** Every type key, in declaration order. */
export const REQUIREMENT_TYPES = Object.keys(REQUIREMENT_TYPE_META);

const FALLBACK: RequirementTypeMeta = { label: 'Functional', icon: Zap, token: 'grey' };

/**
 * Metadata for a type, including ones this build does not know about.
 *
 * Projects imported from other tools — and the older demo data, which used
 * `design` and `constraint` — carry types outside the enum. They are drawn in
 * the neutral grey with their raw name humanised, rather than being silently
 * relabelled as Functional, which is what the old `|| typeMeta.functional`
 * fallbacks did.
 */
export function reqTypeMeta(type: string | undefined | null): RequirementTypeMeta {
  if (!type) return FALLBACK;
  const known = REQUIREMENT_TYPE_META[type];
  if (known) return known;
  return { ...FALLBACK, label: formatReqType(type) };
}

/** Title-cased label for a type key, including unknown ones. */
export function formatReqType(type: string): string {
  const known = REQUIREMENT_TYPE_META[type];
  if (known) return known.label;
  const humanised = type
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
  return type.startsWith('non_functional_')
    ? 'Non-Functional – ' + humanised.slice('Non Functional '.length)
    : humanised;
}

/**
 * The options a type `<select>` should offer, given what is currently stored.
 *
 * A `<select>` whose value matches no `<option>` falls back to displaying the
 * first one, so a requirement stored as `design` or `constraint` — types the
 * demo project still uses and the enum no longer has — rendered as "Functional"
 * and was silently rewritten to functional by the next save of any field. That
 * is data loss triggered by opening a page.
 *
 * Keeping the stored value in the list makes it visible and preserves it;
 * picking anything else is then a deliberate act.
 */
export function typeOptionsFor(current: string | undefined | null): string[] {
  if (current && !REQUIREMENT_TYPE_META[current]) return [current, ...REQUIREMENT_TYPES];
  return REQUIREMENT_TYPES;
}

/** Tailwind text colour class, e.g. `text-cs-blue`. */
export const reqTypeClass = (type: string): string => `text-cs-${reqTypeMeta(type).token}`;

/**
 * CSS colour for charts, graph nodes and inline styles.
 *
 * Resolves through the palette variable rather than a hardcoded hex, so a type
 * keeps matching its badge when the theme changes — the previous hex tables did
 * not, and drew light-theme chart slices in dark-theme colours.
 */
export const reqTypeColor = (type: string): string => `hsl(var(--cs-${reqTypeMeta(type).token}))`;

export const reqTypeIcon = (type: string): typeof Zap => reqTypeMeta(type).icon;
