/**
 * Hand-written helpers over the generated rule table.
 *
 * The rule *data* lives in `./generated/qualityRules` (written by
 * `backend/gen_quality_rules.py` — never hand-edit it). This module holds the
 * small amount of logic that is code rather than data: the modal-keyword
 * highlighter and the pattern-rule scanner used by the inline description
 * helper. The full client-side score lives in `./quality`.
 */
import {
  QUALITY_RULES,
  MODALS,
  type QualityRule,
  type Severity,
} from './generated/qualityRules';

export { MODALS };
export type { QualityRule, Severity };

export type ModalStrength = 'binding' | 'advisory';

export interface RuleFinding {
  rule: string;
  severity: Severity;
  message: string;
  start: number;
  end: number;
}

/** One regex matching every modal keyword, longest-first.
 *
 *  Alternation order is what makes "shall not" match as a unit rather than
 *  "shall" followed by a stray "not" — the arrays are pre-sorted by length in
 *  the backend, and flattening must preserve that. */
export function modalRegex(): RegExp {
  const all = [...MODALS.binding, ...MODALS.advisory].sort((a, b) => b.length - a.length);
  return new RegExp(`\\b(${all.map((w) => w.replace(/ /g, '\\s+')).join('|')})\\b`, 'gi');
}

/** The strength of a matched keyword, for colouring. */
export function modalStrength(word: string): ModalStrength | null {
  const norm = word.toLowerCase().replace(/\s+/g, ' ');
  if (MODALS.binding.includes(norm)) return 'binding';
  if (MODALS.advisory.includes(norm)) return 'advisory';
  return null;
}

/** A fresh RegExp per call — `g`-flagged instances carry `lastIndex`. */
export function ruleRegex(rule: QualityRule): RegExp {
  return new RegExp(rule.pattern, 'gi');
}

/** Run every enabled pattern rule over `plain`, in rule order. */
export function runPatternRules(plain: string): RuleFinding[] {
  const findings: RuleFinding[] = [];
  for (const rule of QUALITY_RULES) {
    if (!rule.enabled) continue;
    const re = ruleRegex(rule);
    let m: RegExpExecArray | null;
    while ((m = re.exec(plain)) !== null) {
      findings.push({
        rule: rule.id,
        severity: rule.severity,
        message: rule.message.replace('{match}', m[0]),
        start: m.index,
        end: m.index + m[0].length,
      });
      // A zero-width match would spin forever otherwise.
      if (m[0].length === 0) re.lastIndex += 1;
    }
  }
  return findings;
}
