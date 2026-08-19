/**
 * Client-side requirement scoring, generated from the Python rules.
 *
 * `scoreRequirement` is the live preview counterpart of
 * `backend/app/services/quality.py::score_requirement`. It consumes the
 * generated rule table in `./generated/qualityRules` — the same data the
 * server scores against — so the two agree by construction rather than by a
 * hand-port that can drift.
 *
 * The rule *data* is generated; the scoring *logic* here is deliberately small
 * and mirrors the Python exactly. `stripHtml` must produce the same plain text
 * as `quality.py::strip_html`, or every score differs.
 */
import {
  QUALITY_RULES,
  DEFAULT_CONFIG,
  type QualityRule,
  type Severity,
} from './generated/qualityRules';

export type { Severity };

export interface QualityFinding {
  rule: string;
  severity: Severity;
  message: string;
  /** Offsets into the plain-text form of the scored text. */
  start: number;
  end: number;
}

export interface QualityConfig {
  min_words?: number;
  max_words?: number;
  rules?: Record<string, boolean>;
  weights?: Record<string, number>;
}

export interface QualityScore {
  score: number;
  findings: QualityFinding[];
}

// The block-level tags the Python `_HTMLStripper` inserts spaces around. Keeping
// this list in sync with `quality.py::_BLOCK_TAGS` is part of the cross-check.
const BLOCK_TAGS = new Set([
  'p', 'div', 'br', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'td', 'th', 'tr', 'section', 'article', 'header', 'footer', 'blockquote',
]);

const NAMED_ENTITIES: Record<string, string> = {
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  apos: "'",
  nbsp: '\u00a0',
  ndash: '\u2013',
  mdash: '\u2014',
  hellip: '\u2026',
  lsquo: '\u2018',
  rsquo: '\u2019',
  ldquo: '\u201c',
  rdquo: '\u201d',
};

/** The subset of `html.unescape` the editor actually emits. Unknown entities
 *  and malformed numeric references are left as-is, matching the lenient
 *  behaviour of the Python scorer's unescape for the strings we score. */
function htmlUnescape(s: string): string {
  return s.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);/g, (whole, body: string) => {
    if (body[0] === '#') {
      const hex = body[1] === 'x' || body[1] === 'X';
      const code = Number.parseInt(body.slice(hex ? 2 : 1), hex ? 16 : 10);
      if (!Number.isNaN(code) && code >= 0) {
        try {
          return String.fromCodePoint(code);
        } catch {
          return whole;
        }
      }
      return whole;
    }
    return NAMED_ENTITIES[body] ?? whole;
  });
}

/**
 * Strip HTML to plain text the same way `quality.py::strip_html` does: block
 * tags separate text with a single space, everything else is removed, and the
 * surviving text is HTML-unescaped.
 */
export function stripHtml(text: string): string {
  const out: string[] = [];
  let lastData = false;
  const re = /<!--[\s\S]*?-->|<\/?([a-zA-Z][a-zA-Z0-9]*)(?:\s[^<>]*?)?>/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const before = text.slice(last, m.index);
    if (before) {
      out.push(before);
      lastData = true;
    }
    const token = m[0];
    if (!token.startsWith('<!--')) {
      const tag = (m[1] || '').toLowerCase();
      if (BLOCK_TAGS.has(tag)) {
        if (!token.startsWith('</')) {
          if (lastData) {
            out.push(' ');
            lastData = false;
          }
          // A self-closing `<br/>` is both a start and an end tag in the
          // Python parser; mirror that second separator.
          if (token.endsWith('/>')) {
            out.push(' ');
            lastData = false;
          }
        } else {
          out.push(' ');
          lastData = false;
        }
      }
    }
    last = m.index + token.length;
  }
  const tail = text.slice(last);
  if (tail) {
    out.push(tail);
  }
  return htmlUnescape(out.join(''));
}

/** `len(plain.split())` — words are runs of non-whitespace. */
function wordCount(plain: string): number {
  return plain.split(/\s+/).filter((w) => w.length > 0).length;
}

/** A fresh, case-insensitive, global regex per call — `g`-flagged regexes carry
 *  `lastIndex` between calls, so a shared instance drops matches. */
function ruleRegex(rule: QualityRule, global: boolean): RegExp {
  return new RegExp(rule.pattern, global ? 'gi' : 'i');
}

/**
 * Score draft description text, mirroring `score_requirement`.
 *
 * `text` is the raw editor HTML; it is stripped before matching. `config`, when
 * given, is the project's resolved config (from `GET /quality`); when omitted,
 * the generated defaults are used. Both carry the same `rules` / `weights` /
 * `min_words` / `max_words` shape `_load_config` produces server-side.
 *
 * Two server-only checks are *not* reproduced here, deliberately:
 * `untestable` (needs `verification_method`) and the `name` half of the scored
 * text (the preview scores the description only). The server's score is
 * authoritative on save and reconciles the display.
 */
export function scoreRequirement(text: string, config?: QualityConfig): QualityScore {
  const rules = config?.rules ?? DEFAULT_CONFIG.rules;
  const weights = config?.weights ?? DEFAULT_CONFIG.weights;
  const plain = stripHtml(text).trim();

  const findings: QualityFinding[] = [];
  let penalty = 0;

  for (const rule of QUALITY_RULES) {
    if (!rule.enabled || rules[rule.config] === false) continue;
    const re = ruleRegex(rule, true);
    let m: RegExpExecArray | null;
    while ((m = re.exec(plain)) !== null) {
      findings.push({
        rule: rule.id,
        severity: rule.severity,
        message: rule.message.replace('{match}', m[0]),
        start: m.index,
        end: m.index + m[0].length,
      });
      penalty += weights[rule.config] ?? rule.weight;
      if (m[0].length === 0) re.lastIndex += 1;
    }
  }

  // no_obligation — a bespoke check that *inverts* the disabled pattern rule:
  // a statement with none of the obligation verbs is flagged.
  if (rules['no_obligation'] !== false) {
    const rule = QUALITY_RULES.find((r) => r.id === 'no_obligation');
    if (rule && !ruleRegex(rule, false).test(plain)) {
      findings.push({
        rule: rule.id,
        severity: rule.severity,
        message: rule.message.replace('{match}', ''),
        start: 0,
        end: plain.length,
      });
      penalty += weights[rule.config] ?? rule.weight;
    }
  }

  // word_count — too short / too long, against the project's min/max.
  if (rules['word_count'] !== false) {
    const wc = wordCount(plain);
    const minW = config?.min_words ?? DEFAULT_CONFIG.min_words;
    const maxW = config?.max_words ?? DEFAULT_CONFIG.max_words;
    const weight = weights['word_count'] ?? 10;
    if (wc < minW) {
      findings.push({
        rule: 'word_count',
        severity: 'warning',
        message: `Too short: ${wc} words (minimum ${minW})`,
        start: 0,
        end: plain.length,
      });
      penalty += weight;
    } else if (wc > maxW) {
      findings.push({
        rule: 'word_count',
        severity: 'info',
        message: `Too long: ${wc} words (maximum ${maxW})`,
        start: 0,
        end: plain.length,
      });
      penalty += Math.floor(weight / 2);
    }
  }

  // The denominator is the sum of *every* weight in the config — including
  // rules that are disabled — exactly as the server computes it.
  const maxPenalty = Object.values(weights).reduce((a, b) => a + b, 0);
  const clamped = Math.max(0, maxPenalty - Math.min(penalty, maxPenalty));
  const score = Number((BigInt(clamped) * 100n) / BigInt(maxPenalty));
  return { score, findings };
}
