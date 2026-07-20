import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Plus, X, Sigma, CheckCircle2, XCircle, HelpCircle, AlertTriangle, MinusCircle, FlaskConical, Ruler, Boxes } from 'lucide-react';
import type {
  Parameter, Constraint, Definition,
  EvaluatedRequirement, EvaluatedConstraint, EvalVerdict, ConstraintStatus,
} from '../api/client';
import { KNOWN_UNITS } from '../api/client';
import { EntityLink } from './entities';

/** Shared <datalist> of known units for parameter-unit autocomplete. */
const UNITS_LIST_ID = 'rm-known-units';
export function UnitsDatalist() {
  return <datalist id={UNITS_LIST_ID}>{KNOWN_UNITS.map((u) => <option key={u} value={u} />)}</datalist>;
}

/** Small amber warning chip for a dimensional-consistency issue. */
function UnitWarning({ message }: { message: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-[10px] text-amber-400 shrink-0" title={message}>
      <Ruler size={10} /> units
    </span>
  );
}

export const VERDICT_META: Record<EvalVerdict | ConstraintStatus, { cls: string; icon: typeof CheckCircle2; label: string }> = {
  pass: { cls: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30', icon: CheckCircle2, label: 'pass' },
  fail: { cls: 'bg-red-500/10 text-red-400 border-red-500/30', icon: XCircle, label: 'fail' },
  unknown: { cls: 'bg-amber-500/10 text-amber-400 border-amber-500/30', icon: HelpCircle, label: 'unknown' },
  error: { cls: 'bg-red-500/10 text-red-400 border-red-500/30', icon: AlertTriangle, label: 'error' },
  not_applicable: { cls: 'bg-muted text-muted-foreground border-transparent', icon: MinusCircle, label: 'n/a' },
  none: { cls: 'bg-muted text-muted-foreground border-transparent', icon: MinusCircle, label: '—' },
};

export function VerdictBadge({ status, prefix }: { status: EvalVerdict | ConstraintStatus; prefix?: string }) {
  const meta = VERDICT_META[status] ?? VERDICT_META.none;
  const Icon = meta.icon;
  return (
    <span className={`inline-flex items-center gap-1 badge border ${meta.cls}`}>
      <Icon size={11} />
      {prefix ? `${prefix} ` : ''}{meta.label}
    </span>
  );
}

/** `margin.value` headroom, signed; shown beside a comparison constraint. */
function MarginTag({ margin }: { margin: NonNullable<EvaluatedConstraint['margin']> }) {
  const ok = margin.value >= 0;
  return (
    <span className={`text-[10px] font-mono ${ok ? 'text-emerald-400' : 'text-red-400'}`}>
      margin {margin.value > 0 ? '+' : ''}{margin.value}
      {margin.pct !== undefined ? ` (${margin.pct > 0 ? '+' : ''}${margin.pct}%)` : ''}
    </span>
  );
}

interface ParametricsCardProps {
  reqId: string;
  parameters: Parameter[];
  constraints: Constraint[];
  evaluated?: EvaluatedRequirement;
  editable: boolean;
  onSave: (updates: { parameters?: Parameter[]; constraints?: Constraint[] }) => void;
  /** Reusable definitions available to bind as constraint/calc usages. */
  definitions?: Definition[];
}

/**
 * The SysML-flavoured card on a requirement: typed numeric parameters
 * (literal or derived by expression), boolean constraints over them with a
 * live verdict and margin, and the measured verdict when verification cases
 * have recorded evidence.
 */
export function ParametricsCard({ reqId, parameters, constraints, evaluated, editable, onSave, definitions = [] }: ParametricsCardProps) {
  const [draft, setDraft] = useState({ name: '', value: '', expr: '', unit: '' });
  const [newConstraint, setNewConstraint] = useState({ expr: '', assume: '' });
  const constraintDefs = definitions.filter((d) => d.type === 'constraint');
  const [defDraft, setDefDraft] = useState<{ id: string; bindings: Record<string, string> }>({ id: '', bindings: {} });
  const selectedDef = constraintDefs.find((d) => d.id === defDraft.id);

  const addDefConstraint = () => {
    if (!selectedDef) return;
    const bindings: Record<string, string> = {};
    for (const f of selectedDef.parameters) bindings[f] = (defDraft.bindings[f] || '').trim();
    onSave({ constraints: [...constraints, { constraint_def: selectedDef.id, bindings }] });
    setDefDraft({ id: '', bindings: {} });
  };

  // Evaluated results keyed for the display rows.
  const evalParams = new Map((evaluated?.parameters ?? []).map((p) => [p.name, p]));

  const addParameter = () => {
    if (!draft.name.trim()) return;
    const p: Parameter = {
      name: draft.name.trim(),
      unit: draft.unit.trim(),
      value: draft.expr.trim() ? null : (draft.value.trim() === '' ? null : Number(draft.value)),
      expr: draft.expr.trim() || null,
    };
    onSave({ parameters: [...parameters, p] });
    setDraft({ name: '', value: '', expr: '', unit: '' });
  };

  const removeParameter = (i: number) =>
    onSave({ parameters: parameters.filter((_, idx) => idx !== i) });

  const addConstraint = () => {
    if (!newConstraint.expr.trim()) return;
    onSave({ constraints: [...constraints, { expr: newConstraint.expr.trim(), assume: newConstraint.assume.trim() || null }] });
    setNewConstraint({ expr: '', assume: '' });
  };

  const removeConstraint = (i: number) =>
    onSave({ constraints: constraints.filter((_, idx) => idx !== i) });

  if (!editable && parameters.length === 0 && constraints.length === 0) return null;

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 }} className="card p-5">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="font-semibold text-sm text-card-foreground flex items-center gap-1.5">
          <Sigma size={14} className="text-cs-teal" /> Parameters &amp; Constraints
        </h2>
        {evaluated && evaluated.verdict !== 'none' && <VerdictBadge status={evaluated.verdict} />}
        {evaluated?.measured_verdict && (
          <VerdictBadge status={evaluated.measured_verdict} prefix="measured" />
        )}
      </div>

      {/* Parameters */}
      {parameters.length > 0 && (
        <div className="space-y-1 mb-3">
          {parameters.map((p, i) => {
            const ev = evalParams.get(p.name);
            return (
              <div key={`${p.name}-${i}`} className="flex items-center gap-2 text-xs py-1.5 px-2 rounded hover:bg-accent group">
                <span className="font-mono font-medium text-foreground w-28 shrink-0 truncate">{p.name}</span>
                {p.expr ? (
                  <span className="flex-1 min-w-0 truncate">
                    <span className="font-mono text-muted-foreground">= {p.expr}</span>
                    <span className="font-mono text-cs-teal ml-2">
                      {ev?.value != null ? `→ ${ev.value}` : ev?.detail ? `(${ev.detail})` : ''}
                    </span>
                  </span>
                ) : (
                  <span className="flex-1 font-mono text-foreground">{p.value ?? '—'}</span>
                )}
                <span className="text-muted-foreground shrink-0 w-12 truncate">{p.unit}</span>
                {ev?.measured !== undefined && (
                  <span className="inline-flex items-center gap-1 text-[10px] font-mono text-cs-purple shrink-0" title={`Measured by ${ev.measured_by}`}>
                    <FlaskConical size={10} /> {ev.measured}
                    {ev.measured_by && <EntityLink kind="verification" id={ev.measured_by} showIcon={false} className="text-cs-purple/80" />}
                  </span>
                )}
                {ev?.error && <span className="text-[10px] text-red-400 shrink-0" title={ev.error}>error</span>}
                {ev?.unit_warning && <UnitWarning message={ev.unit_warning} />}
                {editable && (
                  <button onClick={() => removeParameter(i)} className="text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all">
                    <X size={12} />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {editable && (
        <div className="flex gap-1 mb-4">
          <input className="input flex-1 text-xs font-mono" placeholder="name" value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          <input className="input w-20 text-xs font-mono" placeholder="value" value={draft.value}
            onChange={(e) => setDraft({ ...draft, value: e.target.value })} />
          <input className="input flex-1 text-xs font-mono" placeholder="or expr: GROS0001.mass - empty" value={draft.expr}
            onChange={(e) => setDraft({ ...draft, expr: e.target.value })} />
          <input className="input w-16 text-xs" placeholder="unit" list={UNITS_LIST_ID} value={draft.unit}
            onChange={(e) => setDraft({ ...draft, unit: e.target.value })} />
          <button onClick={addParameter} className="btn-secondary shrink-0 p-2" disabled={!draft.name.trim()}>
            <Plus size={12} />
          </button>
          <UnitsDatalist />
        </div>
      )}

      {/* Constraints */}
      {(constraints.length > 0 || editable) && (
        <h3 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">Constraints</h3>
      )}
      {constraints.length > 0 && (
        <div className="space-y-1 mb-3">
          {constraints.map((c, i) => {
            const ev = evaluated?.constraints?.[i];
            const mev = evaluated?.measured_constraints?.[i];
            return (
              <div key={i} className="flex items-center gap-2 text-xs py-1.5 px-2 rounded hover:bg-accent group">
                <div className="flex-1 min-w-0">
                  <span className="font-mono text-foreground">{c.expr}</span>
                  {c.assume && <span className="font-mono text-muted-foreground ml-2">when {c.assume}</span>}
                  {ev?.detail && <span className="text-muted-foreground ml-2">({ev.detail})</span>}
                </div>
                {ev?.margin && <MarginTag margin={ev.margin} />}
                {ev?.unit_warning && <UnitWarning message={ev.unit_warning} />}
                {ev && <VerdictBadge status={ev.status} />}
                {mev && mev.status !== ev?.status && <VerdictBadge status={mev.status} prefix="measured" />}
                {editable && (
                  <button onClick={() => removeConstraint(i)} className="text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all">
                    <X size={12} />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {editable && (
        <div className="flex gap-1">
          <input className="input flex-1 text-xs font-mono" placeholder={`expr: gross <= 1160 or rollup('WING','mass') <= limit`} value={newConstraint.expr}
            onChange={(e) => setNewConstraint({ ...newConstraint, expr: e.target.value })} />
          <input className="input w-40 text-xs font-mono" placeholder="assume (optional)" value={newConstraint.assume}
            onChange={(e) => setNewConstraint({ ...newConstraint, assume: e.target.value })} />
          <button onClick={addConstraint} className="btn-secondary shrink-0 p-2" disabled={!newConstraint.expr.trim()}>
            <Plus size={12} />
          </button>
        </div>
      )}

      {/* Add a constraint from a reusable definition, binding its formals. */}
      {editable && constraintDefs.length > 0 && (
        <div className="mt-2 p-2 rounded border border-dashed border-border/70 bg-accent/20">
          <div className="flex items-center gap-1.5 mb-1.5 text-[11px] text-muted-foreground">
            <Boxes size={12} className="text-cs-teal" /> Use a definition
            <select
              className="input text-xs py-0.5 ml-1"
              value={defDraft.id}
              onChange={(e) => setDefDraft({ id: e.target.value, bindings: {} })}
            >
              <option value="">choose…</option>
              {constraintDefs.map((d) => (
                <option key={d.id} value={d.id}>{d.name || d.id} — {d.expr}</option>
              ))}
            </select>
          </div>
          {selectedDef && (
            <div className="flex flex-wrap items-end gap-1">
              {selectedDef.parameters.map((f) => (
                <div key={f} className="flex flex-col">
                  <label className="text-[9px] font-mono text-muted-foreground px-1">{f}</label>
                  <input
                    className="input w-32 text-xs font-mono"
                    placeholder="ID.param"
                    value={defDraft.bindings[f] || ''}
                    onChange={(e) => setDefDraft({ ...defDraft, bindings: { ...defDraft.bindings, [f]: e.target.value } })}
                  />
                </div>
              ))}
              <button onClick={addDefConstraint} className="btn-secondary shrink-0 p-2"
                disabled={selectedDef.parameters.some((f) => !(defDraft.bindings[f] || '').trim())}>
                <Plus size={12} />
              </button>
            </div>
          )}
        </div>
      )}

      {editable && (
        <p className="text-[10px] text-muted-foreground mt-3">
          Reference own parameters by name, others as <code className="font-mono">ID.param</code>;{' '}
          <code className="font-mono">rollup('COMP', 'param')</code> sums over the component tree ×quantity.
        </p>
      )}
    </motion.div>
  );
}

/** Compact numeric-parameter editor used on the component detail panel. */
export function ParameterEditor({ parameters, editable, onChange }: {
  parameters: Parameter[];
  editable: boolean;
  onChange: (next: Parameter[]) => void;
}) {
  const [draft, setDraft] = useState({ name: '', value: '', unit: '' });
  useEffect(() => setDraft({ name: '', value: '', unit: '' }), [parameters]);

  if (!editable && parameters.length === 0) return null;

  return (
    <div>
      <label className="label flex items-center gap-1"><Sigma size={11} className="text-cs-teal" /> Parameters</label>
      <p className="text-[11px] text-muted-foreground -mt-1 mb-1.5">Quantities budget rollups can sum</p>
      {parameters.length > 0 && (
        <div className="space-y-1 mb-2">
          {parameters.map((p, i) => (
            <div key={`${p.name}-${i}`} className="flex items-center gap-2 text-xs py-1 px-2 rounded hover:bg-accent group">
              <span className="font-mono font-medium text-foreground flex-1 truncate">{p.name}</span>
              <span className="font-mono">{p.expr ? `= ${p.expr}` : p.value ?? '—'}</span>
              <span className="text-muted-foreground w-10 truncate">{p.unit}</span>
              {editable && (
                <button onClick={() => onChange(parameters.filter((_, idx) => idx !== i))}
                  className="text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all">
                  <X size={11} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      {editable && (
        <div className="flex gap-1">
          <input className="input flex-1 text-xs font-mono" placeholder="name" value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          <input className="input w-20 text-xs font-mono" placeholder="value" value={draft.value}
            onChange={(e) => setDraft({ ...draft, value: e.target.value })} />
          <input className="input w-14 text-xs" placeholder="unit" value={draft.unit}
            onChange={(e) => setDraft({ ...draft, unit: e.target.value })} />
          <button
            onClick={() => {
              if (!draft.name.trim() || draft.value.trim() === '') return;
              onChange([...parameters, { name: draft.name.trim(), value: Number(draft.value), unit: draft.unit.trim() }]);
            }}
            className="btn-secondary shrink-0 p-1.5"
            disabled={!draft.name.trim() || draft.value.trim() === ''}
          >
            <Plus size={12} />
          </button>
        </div>
      )}
    </div>
  );
}
