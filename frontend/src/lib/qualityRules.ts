/**
 * The requirement-lint rule set, generated from the backend.
 *
 * `qualityRules.json` is written by `backend/gen_quality_rules.py` from
 * `app/services/quality_rules.py` — do not hand-edit it, and do not add rules
 * here. The live editor feedback and the server-side score have to check the
 * same things; they previously had separately maintained regex copies and had
 * already drifted apart.
 *
 * Patterns are authored to be valid in both Python `re` and JavaScript
 * `RegExp`, and are compiled here with `gi` — global so every occurrence is
 * reported, case-insensitive to match the backend.
 */
import pack from './qualityRules.json';

export type Severity = 'error' | 'warning' | 'info';

export interface QualityRule {
  id: string;
  title: string;
  severity: Severity;
  /** Portable regex source. Compile with `ruleRegex`, never with a cached instance. */
  pattern: string;
  /** Template containing a single `{match}` placeholder. */
  message: string;
  weight: number;
  /** The INCOSE Guide to Writing Requirements rule this implements, or ''. */
  incose: string;
  enabled: boolean;
}

export interface RuleFinding {
  rule: string;
  severity: Severity;
  message: string;
  /** Offsets into the plain-text form of the description. */
  start: number;
  end: number;
}

export const QUALITY_RULES: QualityRule[] = (pack.rules as QualityRule[]).filter((r) => r.enabled);

/** How strongly a modal keyword obliges. Drives its colour. */
export type ModalStrength = 'binding' | 'advisory';

/** Modal keyword sets, longest phrase first so "shall not" wins over "shall". */
export const MODALS: Record<ModalStrength, string[]> = pack.modals;

/**
 * One regex matching every modal keyword, longest-first.
 *
 * Alternation order is what makes "shall not" match as a unit rather than
 * "shall" followed by a stray "not" — the arrays are pre-sorted by length in
 * the backend, and flattening must preserve that.
 */
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

/**
 * A fresh RegExp per call.
 *
 * These are `g`-flagged, so they carry `lastIndex` between calls — sharing one
 * instance across inputs makes matches disappear on every other keystroke.
 */
export function ruleRegex(rule: QualityRule): RegExp {
  return new RegExp(rule.pattern, 'gi');
}

/** Run every enabled pattern rule over `plain`, in rule order. */
export function runPatternRules(plain: string): RuleFinding[] {
  const findings: RuleFinding[] = [];
  for (const rule of QUALITY_RULES) {
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
