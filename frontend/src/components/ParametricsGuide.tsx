import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { BookOpen, ChevronDown, ChevronRight, Sigma, CheckCircle2, XCircle, HelpCircle, AlertTriangle, FlaskConical, Layers, ArrowRightLeft, Ruler, Boxes } from 'lucide-react';
import { useStore } from '../store';

const sections = [
  {
    id: 'parameters',
    icon: Layers,
    title: 'Parameters',
    questions: [
      { q: 'What is a parameter?',
        a: 'A named number with a unit (like "mass = 767 kg" or "max_current = 48 A"). Parameters belong to requirements or components — they describe measurable properties.' },
      { q: 'What is a derived parameter?',
        a: 'Instead of a fixed value, you can write an expression. For example: `useful_load = mtow - empty_mass`. The engine computes the answer for you.' },
      { q: 'How do I reference another requirement\'s parameter?',
        a: 'Use `REQ-ID.param_name` — like `AFRM0005.max_load`. The engine resolves the value across the project.' },
    ],
  },
  {
    id: 'rollups',
    icon: ChevronRight,
    title: 'Budget Rollups',
    questions: [
      { q: 'What is a rollup?',
        a: 'It sums a parameter across every part of a component tree. So `rollup(\'AVIO\', \'current\')` adds up the current draw of every LRU under the AVIO subsystem. Quantity is multiplied automatically (e.g. 2× GDU displays).' },
      { q: 'When would I use one?',
        a: 'Weight & balance: `rollup(\'C172\', \'mass\')` tells you the tracked total mass. Electrical load: `rollup(\'AVIO\', \'current\')` gives the total avionics current to size the alternator.' },
    ],
  },
  {
    id: 'constraints',
    icon: ArrowRightLeft,
    title: 'Constraints',
    questions: [
      { q: 'What is a constraint?',
        a: 'A pass/fail check. Example: `useful_load >= 400` means "useful load must be at least 400 kg". Constraints compare parameters against each other or against fixed numbers.' },
      { q: 'What verdicts can a constraint have?',
        a: '🟢 pass — the check succeeds. 🔴 fail — it doesn\'t. 🟡 unknown — a parameter has no value yet. 🔴 error — malformed expression. ⚫ n/a — the assumption (see below) isn\'t met.' },
      { q: 'What is an assumption clause?',
        a: 'A precondition. `OAT >= -20` means "this constraint only applies when outside air temp is −20°C or warmer". If the assumption fails, the constraint gets "n/a" instead of "fail". Useful for weather-dependent or configuration-dependent rules.' },
      { q: 'What is the margin?',
        a: 'How close you are to the boundary. If `max_load >= 5.7` and your value is 5.92, the margin is `+0.22 (+3.8%)`. Positive = safe. Negative = violated.' },
    ],
  },
  {
    id: 'units',
    icon: Ruler,
    title: 'Units',
    questions: [
      { q: 'Do units do anything?',
        a: 'Yes. reqmesh knows common SI/aero units (kg, m, N, W, A, kt, psi…) and their dimensions. When a derived parameter or a comparison mixes incompatible quantities — like adding a mass to a length — it shows an amber "units" warning. Type a unit and pick from the suggestions.' },
      { q: 'Does a units warning fail my constraint?',
        a: 'No. Dimensional checks are advisory only — the pass/fail verdict is unchanged. Unknown or blank units are simply not checked, so ad-hoc units (like "passengers") never warn.' },
    ],
  },
  {
    id: 'definitions',
    icon: Boxes,
    title: 'Reusable Definitions',
    questions: [
      { q: 'What is a definition?',
        a: 'A rule written once and reused. A constraint def like `MassBudget(actual, limit) = actual <= limit` can be applied on any requirement by binding its formals to real parameters. A calc def (e.g. `Area(w, h) = w * h`) derives a parameter value the same way.' },
      { q: 'How do I use one?',
        a: 'Create definitions on the Metrics & Analysis page. Then on a requirement, under "Use a definition", pick it and bind each formal to a parameter ref (like `AFRM0000.design_mass`). This is the SysML v2 constraint/calc usage with binding.' },
    ],
  },
  {
    id: 'analysis',
    icon: FlaskConical,
    title: 'Analysis Cases',
    questions: [
      { q: 'What is an analysis case?',
        a: 'A saved what-if run. You give it a scope (which requirements) and hypothetical parameter overrides (like `AFRM0000.empty_mass = 779`), then hit Run to see how verdicts change — without editing the model. It reuses the same solver as the live evaluation.' },
      { q: 'Where do I create them?',
        a: 'On the Metrics & Analysis page, under "Analysis Cases". Enter overrides one per line as `ENTITY.param = value`.' },
    ],
  },
  {
    id: 'measured',
    icon: FlaskConical,
    title: 'Measured Verdicts',
    questions: [
      { q: 'What is a measured verdict?',
        a: 'When a verification case records actual measurements, the engine overrides modelled values with real data. So you get two verdicts side-by-side: "design" (as-modelled) and "measured" (as-tested).' },
      { q: 'How do I record a measurement?',
        a: 'On a verification case page, add a measurement with the fully-qualified parameter name (e.g. `AFRM0005.max_load = 5.92`) and the value. The evaluator picks it up automatically.' },
    ],
  },
  {
    id: 'expr',
    icon: Sigma,
    title: 'Expression Language',
    questions: [
      { q: 'What operators are available?',
        a: 'Arithmetic: `+`, `-`, `*`, `/`, `**` (power), `%`. Comparisons: `<`, `<=`, `>`, `>=`, `==`, `!=`, and chained like `5 < x < 10`. Logic: `and`, `or`, `not`. Functions: `min(a,b)`, `max(a,b)`, `abs(x)`, `sqrt(x)`, `floor(x)`, `ceil(x)`, `round(x)`.' },
      { q: 'Can I chain comparisons?',
        a: 'Yes — `2300 <= static_rpm <= 2400` works just like in maths. Both bounds must pass.' },
      { q: 'Is it safe against injection?',
        a: 'Yes. The evaluator parses expressions with a whitelist of allowed operations. It cannot execute arbitrary code.' },
    ],
  },
];

export default function ParametricsGuide() {
  const helpersEnabled = useStore((s) => s.helpersEnabled);
  const [open, setOpen] = useState(false);
  const [expandedSection, setExpandedSection] = useState<string | null>(null);

  if (!helpersEnabled) return null;

  return (
    <div className="card p-4 bg-violet-500/[0.03] border-violet-500/10">
      <button onClick={() => setOpen(!open)} className="flex items-center gap-2 w-full text-left">
        <BookOpen size={14} className="text-violet-400 shrink-0" />
        <span className="text-xs font-semibold text-foreground">Parametrics &amp; Constraints — How it works</span>
        <span className="flex-1" />
        {open ? <ChevronDown size={14} className="text-muted-foreground" /> : <ChevronRight size={14} className="text-muted-foreground" />}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="mt-3 space-y-1.5 border-t border-violet-500/10 pt-3">
              <p className="text-[10px] text-muted-foreground/70 leading-relaxed mb-3">
                You don't need to know SysML v2. This page explains the parametrics engine in plain terms.
              </p>

              {sections.map((section) => {
                const SecIcon = section.icon;
                const isExpanded = expandedSection === section.id;
                return (
                  <div key={section.id}>
                    <button
                      onClick={() => setExpandedSection(isExpanded ? null : section.id)}
                      className="flex items-center gap-1.5 w-full text-left py-1 hover:bg-violet-500/5 rounded px-1 transition-colors"
                    >
                      <SecIcon size={12} className="text-violet-400/70 shrink-0" />
                      <span className="text-[11px] font-medium text-foreground/80">{section.title}</span>
                      <span className="flex-1" />
                      {isExpanded ? <ChevronDown size={11} className="text-muted-foreground" /> : <ChevronRight size={11} className="text-muted-foreground" />}
                    </button>

                    <AnimatePresence>
                      {isExpanded && (
                        <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                          <div className="space-y-1.5 ml-5 pl-3 border-l border-violet-500/10 mb-1 mt-0.5">
                            {section.questions.map((item, qi) => (
                              <div key={qi}>
                                <p className="text-[10px] font-medium text-foreground/70">{item.q}</p>
                                <p className="text-[10px] text-muted-foreground/60 leading-relaxed">{item.a}</p>
                              </div>
                            ))}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
