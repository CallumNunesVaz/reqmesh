// Turn an `hsl(h,s%,l%)` status colour into a translucent glow colour so nodes
// can cast a soft, status-tinted bloom. Legacy comma-hsl in → hsla out.
export function glow(hslColor: string, alpha: number): string {
  return hslColor.replace('hsl(', 'hsla(').replace(/\)$/, `, ${alpha})`);
}
