// Single home for the canvas palette. Every colour is a `--cs-*` token so it
// re-steps for the light theme instead of freezing at its dark-mode value.

export const statusColors: Record<string, { fill: string; text: string }> = {
  proposed: { fill: 'hsl(var(--cs-blue))', text: 'hsl(var(--cs-blue))' },
  in_review: { fill: 'hsl(var(--cs-yellow))', text: 'hsl(var(--cs-yellow))' },
  approved: { fill: 'hsl(var(--cs-green))', text: 'hsl(var(--cs-green))' },
  implemented: { fill: 'hsl(var(--cs-purple))', text: 'hsl(var(--cs-purple))' },
  verified: { fill: 'hsl(var(--cs-teal))', text: 'hsl(var(--cs-teal))' },
  rejected: { fill: 'hsl(var(--cs-red))', text: 'hsl(var(--cs-red))' },
  deprecated: { fill: 'hsl(var(--cs-grey))', text: 'hsl(var(--cs-grey))' },
};

export const priorityColors: Record<string, string> = {
  low: 'hsl(var(--cs-grey))',
  medium: 'hsl(var(--cs-blue))',
  high: 'hsl(var(--cs-orange))',
  critical: 'hsl(var(--cs-red))',
};

export const constraintColors: Record<string, string> = {
  pass: 'hsl(var(--cs-teal))',
  fail: 'hsl(var(--cs-red))',
  error: 'hsl(var(--cs-red))',
  unknown: 'hsl(var(--cs-yellow))',
  not_applicable: 'hsl(var(--cs-grey))',
};

export const edgeColors: Record<string, string> = {
  refines: 'hsl(var(--cs-blue))',
  satisfies: 'hsl(var(--cs-green))',
  verified_by: 'hsl(var(--cs-purple))',
  derives: 'hsl(var(--cs-orange))',
  conflicts: 'hsl(var(--cs-red))',
  duplicates: 'hsl(var(--cs-grey))',
  cascades: 'hsl(var(--cs-pink))',
};

/** Fallback for an unknown status/priority/relation type. */
export const FALLBACK_COLOR = 'hsl(var(--cs-grey))';

/** Turn an `hsl(h,s%,l%)` status colour into a translucent glow colour so nodes
 *  can cast a soft, status-tinted bloom. Legacy comma-hsl in → hsla out; token
 *  colours (`hsl(var(--cs-*))`) use the slash-alpha form, which is the only
 *  valid syntax once the space-separated variable is substituted. */
export function glow(hslColor: string, alpha: number): string {
  if (hslColor.includes('var(')) {
    return hslColor.replace(/\)$/, ` / ${alpha})`);
  }
  return hslColor.replace('hsl(', 'hsla(').replace(/\)$/, `, ${alpha})`);
}
