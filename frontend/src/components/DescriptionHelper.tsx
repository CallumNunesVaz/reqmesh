import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { expandHeight } from '../lib/animations';
import { BookOpen, ChevronDown, ChevronRight, CheckCircle2, AlertTriangle, XCircle, Info } from 'lucide-react';
import { useStore } from '../store';
import { runPatternRules } from '../lib/qualityRules';

interface Finding {
  rule: string;
  severity: 'error' | 'warning' | 'info';
  message: string;
  start?: number;
  end?: number;
}

const MEASURABLE_TERMS = /\b\d+(?:\.\d+)?\s*(?:%|percent|ms|s|sec|seconds?|minutes?|hours?|days?|weeks?|months?|years?|bytes?|KB|MB|GB|TB|Hz|kHz|MHz|GHz|bps|fps|px|mm|cm|m|km|g|kg|lb|°C|°F)\b/i;

function stripHtml(text: string): string {
  return text.replace(/<[^>]*>/g, '').trim();
}

function clientCheck(text: string, verificationMethod: string): Finding[] {
  const plain = stripHtml(text);
  const findings: Finding[] = [];

  // Pattern rules from the single source of truth
  findings.push(...runPatternRules(plain));

  const wordCount = plain.split(/\s+/).filter(Boolean).length;
  if (wordCount < 5) {
    findings.push({ rule: 'word_count', severity: 'warning', message: `Only ${wordCount} words — requirements should be at least 5 words to be meaningful` });
  } else if (wordCount > 200) {
    findings.push({ rule: 'word_count', severity: 'info', message: `${wordCount} words — consider splitting into multiple requirements for clarity` });
  }

  if (verificationMethod === 'test' && !MEASURABLE_TERMS.test(plain)) {
    findings.push({ rule: 'untestable', severity: 'warning', message: 'Marked for test verification but contains no measurable criteria (numbers with units like "500 ms", "10 kg")' });
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
        <div className="flex items-center gap-2 text-3xs">
          {errors.length > 0 && <span className="badge bg-cs-red/10 text-cs-red">{errors.length} issue{errors.length > 1 ? 's' : ''}</span>}
          {warnings.length > 0 && <span className="badge bg-cs-amber/10 text-cs-amber">{warnings.length} suggestion{warnings.length > 1 ? 's' : ''}</span>}
          {infos.length > 0 && <span className="badge bg-muted text-muted-foreground">{infos.length} note{infos.length > 1 ? 's' : ''}</span>}
          {findings.length === 0 && <span className="text-cs-green text-3xs flex items-center gap-1"><CheckCircle2 size={10} /> Good writing</span>}
          <button onClick={() => setOpen(!open)} className="text-muted-foreground/50 hover:text-muted-foreground ml-auto flex items-center gap-0.5">
            <BookOpen size={10} />
            {open ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
          </button>
        </div>
      )}

      {/* Expanded detail panel */}
      <AnimatePresence>
        {open && (
          <motion.div variants={expandHeight} initial="initial" animate="animate" exit="exit" className="overflow-hidden">
            <div className="card p-3 bg-cs-amber/[0.03] border-cs-amber/10 space-y-2">
              {/* Guideline reference */}
              <p className="text-3xs text-muted-foreground/70 leading-relaxed border-b border-cs-amber/10 pb-2">
                Requirements text guidelines (based on INCOSE, EARS, and ISO 29148 practices). These checks run automatically against your description.
              </p>

              {GUIDELINES.map((g) => {
                const GIcon = g.icon;
                return (
                  <div key={g.id}>
                    <button
                      onClick={() => setExpanded(expanded === g.id ? null : g.id)}
                      className="flex items-center gap-1.5 w-full text-left py-0.5 hover:bg-cs-amber/5 rounded-md px-1 transition-colors"
                    >
                      <GIcon size={11} className="text-cs-amber/70 shrink-0" />
                      <span className="text-3xs font-medium text-foreground/80">{g.title}</span>
                      <span className="flex-1" />
                      {expanded === g.id ? <ChevronDown size={10} className="text-muted-foreground" /> : <ChevronRight size={10} className="text-muted-foreground" />}
                    </button>
                    {expanded === g.id && (
                      <p className="text-4xs text-muted-foreground/60 leading-relaxed ml-5 pl-3 border-l border-cs-amber/10 mt-0.5 mb-1">
                        {g.content}
                      </p>
                    )}
                  </div>
                );
              })}

              {/* Inline findings */}
              {findings.length > 0 && (
                <div className="border-t border-cs-amber/10 pt-2 space-y-1">
                  <p className="text-4xs font-semibold text-foreground/60 uppercase tracking-wider">Current issues in this description</p>
                  {findings.map((f, i) => {
                    const FIcon = f.severity === 'error' ? XCircle : f.severity === 'warning' ? AlertTriangle : Info;
                    const color = f.severity === 'error' ? 'text-cs-red' : f.severity === 'warning' ? 'text-cs-amber' : 'text-muted-foreground';
                    return (
                      <div key={i} className={`flex items-start gap-1.5 text-4xs ${color} leading-relaxed`}>
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
