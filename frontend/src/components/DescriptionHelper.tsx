import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { BookOpen, ChevronDown, ChevronRight, CheckCircle2, AlertTriangle, XCircle, Info } from 'lucide-react';
import { useStore } from '../store';

interface Finding {
  rule: string;
  severity: 'error' | 'warning' | 'info';
  message: string;
}

const WEAK_WORDS = /\b(should|may|might|could|would|appropriate|adequate|sufficient|as needed|if needed|if required|and\/or|user-friendly|user friendly|fast|robust|flexible|scalable|easy|simple|simply|easily|normally|typically|generally|usually|reasonable|reasonably)\b/gi;

const VAGUE_QUANTIFIERS = /\b(some|several|many|few|minimal|maximal|enough|sufficient|a lot of|a number of|a few|a couple of)\b/gi;

const PLACEHOLDER_RE = /\b(TODO|FIXME|TBD|XXX|HACK)\b|\?\?\?|\?\?/gi;

const MEASURABLE_TERMS = /\b\d+(?:\.\d+)?\s*(?:%|percent|ms|s|sec|seconds?|minutes?|hours?|days?|weeks?|months?|years?|bytes?|KB|MB|GB|TB|Hz|kHz|MHz|GHz|bps|fps|px|mm|cm|m|km|g|kg|lb|°C|°F)\b/i;

function stripHtml(text: string): string {
  return text.replace(/<[^>]*>/g, '').trim();
}

function clientCheck(text: string, verificationMethod: string): Finding[] {
  const plain = stripHtml(text);
  const findings: Finding[] = [];

  let m: RegExpExecArray | null;
  WEAK_WORDS.lastIndex = 0;
  while ((m = WEAK_WORDS.exec(plain)) !== null) {
    findings.push({ rule: 'weak_words', severity: 'warning', message: `"${m[0]}" is imprecise — use "must" or "shall" for normative requirements` });
  }

  VAGUE_QUANTIFIERS.lastIndex = 0;
  while ((m = VAGUE_QUANTIFIERS.exec(plain)) !== null) {
    findings.push({ rule: 'vague_quantifier', severity: 'warning', message: `"${m[0]}" is vague — use a specific number or bound` });
  }

  PLACEHOLDER_RE.lastIndex = 0;
  while ((m = PLACEHOLDER_RE.exec(plain)) !== null) {
    findings.push({ rule: 'placeholder', severity: 'error', message: `"${m[0]}" is a placeholder — replace with concrete content before review` });
  }

  const wordCount = plain.split(/\s+/).filter(Boolean).length;
  if (wordCount < 5) {
    findings.push({ rule: 'word_count', severity: 'warning', message: `Only ${wordCount} words — requirements should be at least 5 words to be meaningful` });
  } else if (wordCount > 200) {
    findings.push({ rule: 'word_count', severity: 'info', message: `${wordCount} words — consider splitting into multiple requirements for clarity` });
  }

  if (verificationMethod === 'test' && !MEASURABLE_TERMS.test(plain)) {
    findings.push({ rule: 'untestable', severity: 'warning', message: 'Marked for test verification but contains no measurable criteria (numbers with units like "500 ms", "10 kg")' });
  }

  if (/and\b.*\band\b/i.test(plain)) {
    findings.push({ rule: 'non_atomic', severity: 'info', message: 'Multiple conjunctions — may describe more than one requirement' });
  }

  return findings;
}

const GUIDELINES = [
  {
    id: 'normative',
    title: 'Use normative language',
    icon: CheckCircle2,
    content: 'Requirements must use imperative, testable language. Prefer "must" or "shall" over "should", "may", or "might". Avoid marketing adjectives like "fast", "robust", or "user-friendly" — they cannot be verified.',
  },
  {
    id: 'atomic',
    title: 'One requirement per statement',
    icon: Info,
    content: 'Each requirement should describe exactly one thing. If you find yourself using "and" to join multiple clauses, consider splitting into separate requirements. This makes verification and tracing straightforward.',
  },
  {
    id: 'measurable',
    title: 'Include measurable criteria',
    icon: AlertTriangle,
    content: 'Especially for test-based verification, include specific numeric bounds with units: "respond within 500 ms", "withstand 3.8g load", "capacity of 53 gallons". This makes the requirement objectively testable.',
  },
  {
    id: 'no_placeholders',
    title: 'No placeholders',
    icon: XCircle,
    content: 'Avoid TODO, TBD, FIXME, or ??? in normative text. Use the status field to mark a requirement as draft, but the description itself must be complete and reviewable.',
  },
  {
    id: 'context',
    title: 'Provide rationale and source',
    icon: Info,
    content: 'Why does this requirement exist? What regulation, standard, or stakeholder request drives it? A clear rationale helps downstream designers make good trade-off decisions when constraints conflict.',
  },
];

interface DescriptionHelperProps {
  description: string;
  verificationMethod: string;
  showPanel?: boolean;
}

export default function DescriptionHelper({ description, verificationMethod }: DescriptionHelperProps) {
  const helpersEnabled = useStore((s) => s.helpersEnabled);
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  const findings = useMemo(() => clientCheck(description, verificationMethod), [description, verificationMethod]);

  if (!helpersEnabled) return null;

  const errors = findings.filter(f => f.severity === 'error');
  const warnings = findings.filter(f => f.severity === 'warning');
  const infos = findings.filter(f => f.severity === 'info');

  return (
    <div className="space-y-2">
      {/* Live quality bar */}
      {findings.length > 0 && (
        <div className="flex items-center gap-2 text-[10px]">
          {errors.length > 0 && <span className="badge bg-red-500/10 text-red-400">{errors.length} issue{errors.length > 1 ? 's' : ''}</span>}
          {warnings.length > 0 && <span className="badge bg-amber-500/10 text-amber-400">{warnings.length} suggestion{warnings.length > 1 ? 's' : ''}</span>}
          {infos.length > 0 && <span className="badge bg-muted text-muted-foreground">{infos.length} note{infos.length > 1 ? 's' : ''}</span>}
          {findings.length === 0 && <span className="text-emerald-400 text-[10px] flex items-center gap-1"><CheckCircle2 size={10} /> Good writing</span>}
          <button onClick={() => setOpen(!open)} className="text-muted-foreground/50 hover:text-muted-foreground ml-auto flex items-center gap-0.5">
            <BookOpen size={10} />
            {open ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
          </button>
        </div>
      )}

      {/* Expanded detail panel */}
      <AnimatePresence>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="card p-3 bg-amber-500/[0.03] border-amber-500/10 space-y-2">
              {/* Guideline reference */}
              <p className="text-[10px] text-muted-foreground/70 leading-relaxed border-b border-amber-500/10 pb-2">
                Requirements text guidelines (based on INCOSE, EARS, and ISO 29148 practices). These checks run automatically against your description.
              </p>

              {GUIDELINES.map((g) => {
                const GIcon = g.icon;
                return (
                  <div key={g.id}>
                    <button
                      onClick={() => setExpanded(expanded === g.id ? null : g.id)}
                      className="flex items-center gap-1.5 w-full text-left py-0.5 hover:bg-amber-500/5 rounded px-1 transition-colors"
                    >
                      <GIcon size={11} className="text-amber-400/70 shrink-0" />
                      <span className="text-[10px] font-medium text-foreground/80">{g.title}</span>
                      <span className="flex-1" />
                      {expanded === g.id ? <ChevronDown size={10} className="text-muted-foreground" /> : <ChevronRight size={10} className="text-muted-foreground" />}
                    </button>
                    {expanded === g.id && (
                      <p className="text-[9px] text-muted-foreground/60 leading-relaxed ml-5 pl-3 border-l border-amber-500/10 mt-0.5 mb-1">
                        {g.content}
                      </p>
                    )}
                  </div>
                );
              })}

              {/* Inline findings */}
              {findings.length > 0 && (
                <div className="border-t border-amber-500/10 pt-2 space-y-1">
                  <p className="text-[9px] font-semibold text-foreground/60 uppercase tracking-wider">Current issues in this description</p>
                  {findings.map((f, i) => {
                    const FIcon = f.severity === 'error' ? XCircle : f.severity === 'warning' ? AlertTriangle : Info;
                    const color = f.severity === 'error' ? 'text-red-400' : f.severity === 'warning' ? 'text-amber-400' : 'text-muted-foreground';
                    return (
                      <div key={i} className={`flex items-start gap-1.5 text-[9px] ${color} leading-relaxed`}>
                        <FIcon size={10} className="mt-px shrink-0" />
                        <span>{f.message}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
