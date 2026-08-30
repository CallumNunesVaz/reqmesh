import { useEffect, useState, useId, useMemo, useRef } from 'react';
import { motion } from 'framer-motion';
import { Plus, X, Sigma, CheckCircle2, XCircle, HelpCircle, AlertTriangle, MinusCircle, FlaskConical, Ruler, Boxes, ArrowUp, ArrowDown, Beaker, Play, Pencil, Check, Lock } from 'lucide-react';
import type {
  Parameter, Constraint, Definition,
  EvaluatedRequirement, EvaluatedConstraint, EvalVerdict, ConstraintStatus,
} from '../api/client';
import { KNOWN_UNITS } from '../api/client';
import { EntityLink } from './entities';
import { useWhatIf } from './WhatIfContext';
import {
  buildParameterReferences, filterReferences, identifierFragment, resolveParameterEdit,
  type ParamOwner, type ParamReference,
} from '../lib/parametrics';
import { tokenizeExpr, type ExprTokenKind } from '../lib/exprTokens';
import Reveal from './Reveal';

/** Shared <datalist> of known units for parameter-unit autocomplete. */
const UNITS_LIST_ID = 'rm-known-units';
export function UnitsDatalist() {
  return <datalist id={UNITS_LIST_ID}>{KNOWN_UNITS.map((u) => <option key={u} value={u}>{u}</option>)}</datalist>;
}

/** Small amber warning chip for a dimensional-consistency issue. */
function UnitWarning({ message }: { message: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-3xs text-cs-amber shrink-0" title={message}>
      <Ruler size={10} /> units
    </span>
  );
}

export const VERDICT_META: Record<EvalVerdict | ConstraintStatus, { cls: string; icon: typeof CheckCircle2; label: string }> = {
  pass: { cls: 'bg-cs-green/10 text-cs-green border-cs-green/30', icon: CheckCircle2, label: 'pass' },
  fail: { cls: 'bg-cs-red/10 text-cs-red border-cs-red/30', icon: XCircle, label: 'fail' },
  unknown: { cls: 'bg-cs-amber/10 text-cs-amber border-cs-amber/30', icon: HelpCircle, label: 'unknown' },
  error: { cls: 'bg-cs-red/10 text-cs-red border-cs-red/30', icon: AlertTriangle, label: 'error' },
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
export function MarginTag({ margin }: { margin: NonNullable<EvaluatedConstraint['margin']> }) {
  const ok = margin.value >= 0;
  return (
    <span className={`text-3xs tabular-nums font-mono ${ok ? 'text-cs-green' : 'text-cs-red'}`}>
      margin {margin.value > 0 ? '+' : ''}{margin.value}
      {margin.pct !== undefined ? ` (${margin.pct > 0 ? '+' : ''}${margin.pct}%)` : ''}
    </span>
  );
}

/** Decorative gauge behind a constraint row, showing how close the margin is to
 *  failing. Absolute and `aria-hidden` so it contributes no height and no
 *  accessibility noise — `MarginTag`'s number stays the accessible answer. */
export function MarginBar({ margin }: { margin: NonNullable<EvaluatedConstraint['margin']> }): JSX.Element | null {
  if (margin.pct === undefined) return null;
  const fill = Math.round(Math.min(Math.abs(margin.pct), 100));
  return (
    <div
      data-margin-bar
      data-margin-fill={fill}
      aria-hidden="true"
      className={`absolute inset-y-0 left-0 rounded-md pointer-events-none ${margin.value >= 0 ? 'bg-cs-green/10' : 'bg-cs-red/10'}`}
      style={{ width: `${fill}%` }}
    />
  );
}

/** The `--cs-*` step per token class. Uses the theme tokens only — no raw hex
 *  and no literal palette classes — so the colours re-step for the light theme
 *  where literals would not. */
const EXPR_TOKEN_CLASS: Record<ExprTokenKind, string> = {
  number: 'text-cs-orange',
  string: 'text-cs-green',
  ref: 'text-cs-blue',
  func: 'text-cs-purple',
  ident: 'text-foreground',
  operator: 'text-cs-pink',
  punct: 'text-muted-foreground',
  text: '',
};

/** Read-only, token-coloured rendering of one expression. `className` applies
 *  to the wrapper (e.g. `font-mono`); each token gets its own colour span. */
function Expr({ expr, className = '' }: { expr: string; className?: string }) {
  return (
    <span className={className}>
      {tokenizeExpr(expr).map((t, i) => (
        <span key={i} className={EXPR_TOKEN_CLASS[t.kind] || undefined}>{t.text}</span>
      ))}
    </span>
  );
}

/**
 * Auto-growing expression field with the inline reference helper.
 *
 * A `<textarea>` (rather than an `<input>`) so a long expression wraps and
 * grows instead of being truncated to one line. Enter submits (no newline is
 * ever valid in an expression), and while typing the identifier fragment under
 * the caret filters a fuzzy list of `refs`; picking one inserts at the caret.
 */
export function ExpressionField({ value, onChange, onSubmit, placeholder, className, refs }: {
  value: string;
  onChange: (next: string) => void;
  onSubmit?: () => void;
  placeholder?: string;
  className?: string;
  refs: ParamReference[];
}) {
  const taRef = useRef<HTMLTextAreaElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [caret, setCaret] = useState(0);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const listboxId = useId();
  const optionId = (i: number) => `${listboxId}-opt-${i}`;

  const fragment = identifierFragment(value, caret);
  const filtered = useMemo(() => filterReferences(refs, fragment), [refs, fragment]);
  // Only trigger on fragments that name something — a digit-only fragment (the
  // tail of a number being typed) would open the list on every value.
  const show = open && /[A-Za-z]/.test(fragment) && filtered.length > 0;

  // Auto-grow to the content's height.
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${ta.scrollHeight}px`;
  }, [value]);

  // Close on click outside.
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, []);

  // Scroll the highlighted option into view.
  useEffect(() => {
    const el = containerRef.current?.querySelector<HTMLElement>(`[data-ref-idx="${highlight}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [highlight]);

  const insert = (r: ParamReference) => {
    const start = caret - fragment.length;
    const nextVal = value.slice(0, start) + r.ref + value.slice(caret);
    onChange(nextVal);
    setOpen(false);
    const pos = start + (r.caret ?? r.ref.length);
    requestAnimationFrame(() => {
      const ta = taRef.current;
      if (!ta) return;
      ta.focus();
      ta.setSelectionRange(pos, pos);
      setCaret(pos);
    });
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (show) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setHighlight((h) => Math.min(h + 1, filtered.length - 1)); return; }
      if (e.key === 'ArrowUp') { e.preventDefault(); setHighlight((h) => Math.max(h - 1, 0)); return; }
      if (e.key === 'Enter') { e.preventDefault(); insert(filtered[highlight]); return; }
      if (e.key === 'Escape') { e.preventDefault(); setOpen(false); return; }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSubmit?.();
    }
  };

  return (
    <div ref={containerRef} className="relative min-w-0 flex-1">
      <div
        ref={mirrorRef}
        data-expr-highlight
        aria-hidden="true"
        className={`${className ?? ''} absolute inset-0 pointer-events-none overflow-hidden whitespace-pre-wrap break-words`}
      >
        {tokenizeExpr(value).map((t, i) => (
          <span key={i} className={EXPR_TOKEN_CLASS[t.kind] || undefined}>{t.text}</span>
        ))}
      </div>
      {/* oxlint-disable jsx-a11y/prefer-tag-over-role -- a combobox textarea: no
          native element reproduces a filterable expression suggestion list. */}
      <textarea
        ref={taRef}
        rows={1}
        className={`${className ?? ''} relative bg-transparent text-transparent caret-foreground placeholder:text-muted-foreground`}
        value={value}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={show}
        aria-controls={show ? listboxId : undefined}
        aria-activedescendant={show ? optionId(highlight) : undefined}
        onChange={(e) => {
          onChange(e.target.value);
          setCaret(e.target.selectionStart ?? e.target.value.length);
          setOpen(true);
          setHighlight(0);
        }}
        onClick={(e) => setCaret((e.target as HTMLTextAreaElement).selectionStart ?? value.length)}
        onKeyUp={(e) => setCaret((e.target as HTMLTextAreaElement).selectionStart ?? value.length)}
        onFocus={() => { if (fragment) setOpen(true); }}
        onKeyDown={onKeyDown}
        onScroll={(e) => {
          const mirror = mirrorRef.current;
          if (!mirror) return;
          const ta = e.target as HTMLTextAreaElement;
          mirror.scrollTop = ta.scrollTop;
          mirror.scrollLeft = ta.scrollLeft;
        }}
      />
      {/* oxlint-enable jsx-a11y/prefer-tag-over-role */}
      {show && (
        /* oxlint-disable jsx-a11y/prefer-tag-over-role -- a combobox popup: there
           is no native element that reproduces a filterable suggestion list. */
        <div
          id={listboxId}
          role="listbox"
          className="absolute z-50 left-0 min-w-full mt-1 max-h-52 overflow-y-auto rounded-lg border bg-popover shadow-lg"
        >
          {filtered.map((r, i) => (
            <div
              key={`${r.ref}-${i}`}
              id={optionId(i)}
              data-ref-idx={i}
              role="option"
              aria-selected={i === highlight}
              tabIndex={-1}
              onMouseDown={(e) => { e.preventDefault(); insert(r); }}
              onMouseEnter={() => setHighlight(i)}
              className={`flex items-center gap-2 px-3 py-1.5 text-xs cursor-pointer transition-colors ${
                i === highlight ? 'bg-primary/10 text-primary' : 'text-popover-foreground hover:bg-accent'
              }`}
            >
              <span className="font-mono text-3xs opacity-60 shrink-0">{r.ref}</span>
              <span className="truncate">{r.label}</span>
            </div>
          ))}
        </div>
        /* oxlint-enable jsx-a11y/prefer-tag-over-role */
      )}
    </div>
  );
}

/**
 * In-place editor for one parameter row, shared by `ParametricsCard` and
 * `ParameterEditor`. Preserves `kind`/`value_type`/`calc_def`/`bindings` by
 * resolving through `resolveParameterEdit` (spread the original, edit only the
 * four editable fields).
 */
function ParameterEditRow({ original, refs, onSave, onCancel }: {
  original: Parameter;
  refs: ParamReference[];
  onSave: (next: Parameter) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState({
    name: original.name,
    value: original.value != null ? String(original.value) : '',
    unit: original.unit ?? '',
    expr: original.expr ?? '',
  });
  const nameId = useId();

  const commit = () => {
    if (!draft.name.trim()) return;
    onSave(resolveParameterEdit(original, draft));
  };

  return (
    <motion.div data-param-edit={original.name} layout className="flex items-center gap-2 text-xs py-1.5 px-2 rounded-md bg-accent/40 ring-1 ring-primary/20">
      <input
        id={nameId}
        className="input w-28 text-xs font-mono shrink-0"
        placeholder="name"
        value={draft.name}
        onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commit(); } }}
      />
      <input
        className="input w-20 text-xs font-mono shrink-0"
        placeholder="value"
        value={draft.value}
        onChange={(e) => setDraft((d) => ({ ...d, value: e.target.value, expr: e.target.value.trim() ? '' : d.expr }))}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commit(); } }}
      />
      <ExpressionField
        className="input text-xs font-mono resize-none"
        placeholder="or expr: GROS0001.mass - empty"
        value={draft.expr}
        onChange={(v) => setDraft((d) => ({ ...d, expr: v, value: v.trim() ? '' : d.value }))}
        onSubmit={commit}
        refs={refs}
      />
      <input
        className="input w-16 text-xs shrink-0"
        list={UNITS_LIST_ID}
        placeholder="unit"
        value={draft.unit}
        onChange={(e) => setDraft({ ...draft, unit: e.target.value })}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commit(); } }}
      />
      <UnitsDatalist />
      <button onClick={commit} className="btn-secondary shrink-0 p-1.5" title="Save parameter">
        <Check size={12} />
      </button>
      <button onClick={onCancel} className="text-muted-foreground hover:text-foreground shrink-0 p-1.5" title="Cancel">
        <X size={12} />
      </button>
    </motion.div>
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
  /** Every other parameter in the project (other requirements + components),
   *  offered by the reference helper as `ID.param`. */
  references?: ParamOwner[];
}

/**
 * The SysML-flavoured card on a requirement: typed numeric parameters
 * (literal or derived by expression), boolean constraints over them with a
 * live verdict and margin, and the measured verdict when verification cases
 * have recorded evidence.
 */
export function ParametricsCard({ reqId, parameters, constraints, evaluated, editable, onSave, definitions = [], references = [] }: ParametricsCardProps) {
  const [draft, setDraft] = useState({ name: '', value: '', expr: '', unit: '' });
  const [newConstraint, setNewConstraint] = useState({ expr: '', assume: '' });
  const [editingIdx, setEditingIdx] = useState(-1);
  const constraintDefs = definitions.filter((d) => d.type === 'constraint');
  const [defDraft, setDefDraft] = useState<{ id: string; bindings: Record<string, string> }>({ id: '', bindings: {} });
  const selectedDef = constraintDefs.find((d) => d.id === defDraft.id);
  // useWhatIf() must be called unconditionally (Rules of Hooks); `editable`
  // toggles with edit mode, so a conditional call would change the hook count.
  const whatIfCtx = useWhatIf();
  const whatIf = editable ? whatIfCtx : null;
  const [whatIfOpen, setWhatIfOpen] = useState<Set<string>>(new Set());

  const addDefConstraint = () => {
    if (!selectedDef) return;
    const bindings: Record<string, string> = {};
    for (const f of selectedDef.parameters) bindings[f] = (defDraft.bindings[f] || '').trim();
    onSave({ constraints: [...constraints, { constraint_def: selectedDef.id, bindings }] });
    setDefDraft({ id: '', bindings: {} });
  };

  // Evaluated results keyed for the display rows.
  const evalParams = new Map((evaluated?.parameters ?? []).map((p) => [p.name, p]));

  // The reference helper's project-wide list. Own params are offered by bare
  // name, every other entity's as `ID.param`, plus `rollup` and the definitions.
  const refs = useMemo(() => {
    const evalValues = new Map<string, number | null>();
    for (const p of evaluated?.parameters ?? []) evalValues.set(`${reqId}.${p.name}`, p.value ?? null);
    return buildParameterReferences({
      ownId: reqId, ownParameters: parameters, others: references, definitions, evalValues,
    });
  }, [reqId, parameters, references, definitions, evaluated]);

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

  const saveEdit = (i: number, next: Parameter) => {
    onSave({ parameters: parameters.map((p, idx) => (idx === i ? next : p)) });
    setEditingIdx(-1);
  };

  const addConstraint = () => {
    if (!newConstraint.expr.trim()) return;
    onSave({ constraints: [...constraints, { expr: newConstraint.expr.trim(), assume: newConstraint.assume.trim() || null }] });
    setNewConstraint({ expr: '', assume: '' });
  };

  const removeConstraint = (i: number) =>
    onSave({ constraints: constraints.filter((_, idx) => idx !== i) });

  const moveConstraintUp = (i: number) => {
    if (i === 0) return;
    const next = [...constraints];
    [next[i - 1], next[i]] = [next[i], next[i - 1]];
    onSave({ constraints: next });
  };

  const moveConstraintDown = (i: number) => {
    if (i >= constraints.length - 1) return;
    const next = [...constraints];
    [next[i], next[i + 1]] = [next[i + 1], next[i]];
    onSave({ constraints: next });
  };

  if (!editable && parameters.length === 0 && constraints.length === 0) return null;

  return (
    <Reveal step={2} className="card p-5">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="font-semibold text-sm text-card-foreground flex items-center gap-1.5">
          <Sigma size={14} className="text-cs-teal" /> Parameters &amp; Constraints
        </h2>
        {evaluated && evaluated.verdict !== 'none' && <VerdictBadge status={evaluated.verdict} />}
        {evaluated?.measured_verdict && (
          <VerdictBadge status={evaluated.measured_verdict} prefix="measured" />
        )}
        {whatIf && (
          <button
            onClick={() => whatIf.evaluate()}
            disabled={Object.keys(whatIf.overrides).length === 0}
            className="ml-auto inline-flex items-center gap-1 text-3xs px-2 py-1 rounded-md border bg-primary/10 text-primary border-primary/30 hover:bg-primary/20 disabled:opacity-30 disabled:cursor-not-allowed transition-colors shrink-0"
            title="Evaluate overrides"
          >
            <Play size={10} /> Evaluate
          </button>
        )}
      </div>

      {/* Parameters */}
      {parameters.length > 0 && (
        <div className="space-y-1 mb-3">
          {parameters.map((p, i) => {
            if (editable && editingIdx === i) {
              return (
                <ParameterEditRow
                  key={`edit-${p.name}-${i}`}
                  original={p}
                  refs={refs}
                  onSave={(next) => saveEdit(i, next)}
                  onCancel={() => setEditingIdx(-1)}
                />
              );
            }
            const ev = evalParams.get(p.name);
            const ref = `${reqId}.${p.name}`;
            const isLiteral = !p.expr && !p.calc_def && p.value != null;
            const isOverridden = whatIf && whatIf.overrides[ref] !== undefined;
            const origVal = whatIf?.base[ref];
            const whatIfOpenNow = whatIfOpen.has(ref);
            return (
              <motion.div key={`${p.name}-${i}`} data-param={p.name} layout className={`flex items-start gap-2 text-xs py-1.5 px-2 rounded-md hover:bg-accent group ${isOverridden ? 'ring-1 ring-dashed ring-cs-blue/50 bg-cs-blue/5' : ''}`}>
                <span className="font-mono font-medium text-foreground w-28 shrink-0 truncate">{p.name}</span>
                {p.expr || p.calc_def ? (
                  <span className="flex-1 min-w-0 break-words">
                    <span className="font-mono text-muted-foreground">{'= '}</span>
                    <Expr expr={p.expr || p.calc_def || ''} className="font-mono" />
                    <span className="font-mono text-cs-teal ml-2 tabular-nums">
                      {ev?.value != null ? `→ ${ev.value}` : ev?.detail ? `(${ev.detail})` : ''}
                    </span>
                  </span>
                ) : (
                  <span className="flex-1 min-w-0">
                    {isOverridden ? (
                      <span className="flex items-center gap-1.5">
                        <span data-override-baseline className="font-mono text-muted-foreground line-through">{origVal}</span>
                        <span className="text-4xs text-muted-foreground">→</span>
                        <span className="font-mono text-cs-blue font-semibold">{whatIf!.overrides[ref]}</span>
                      </span>
                    ) : (
                      <span className="font-mono text-foreground tabular-nums">{p.value ?? '—'}</span>
                    )}
                    {whatIf && isLiteral && (
                      <span className="inline-flex items-center gap-1 ml-1.5">
                        {whatIfOpenNow && (
                          <>
                            {/* The value being masked, so it stays readable while
                                a replacement is typed. Only until the override is
                                committed — from then on the `isOverridden` branch
                                above already renders `original -> override`, and a
                                second struck-through copy here is pure noise.
                                `origVal` is `whatIf.base[ref]`, the true baseline;
                                `p.value` only coincides with it today. */}
                            {!isOverridden && (
                              <span data-override-baseline className="font-mono text-muted-foreground line-through">
                                {origVal ?? p.value}
                              </span>
                            )}
                            <input
                              className="input w-20 text-xs font-mono py-0.5 px-1"
                              type="number"
                              step="any"
                              value={whatIf.overrides[ref] ?? ''}
                              placeholder={String(p.value ?? '')}
                              onClick={(e) => e.stopPropagation()}
                              onChange={(e) => {
                                const n = parseFloat(e.target.value);
                                if (!isNaN(n)) {
                                  whatIf.setOverride(ref, n, p.value ?? 0);
                                }
                              }}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                  e.preventDefault();
                                  whatIf.evaluate();
                                }
                              }}
                            />
                          </>
                        )}
                        <button
                          className={`shrink-0 ${whatIfOpenNow ? 'text-cs-blue' : 'text-muted-foreground hover:text-cs-blue'} transition-colors`}
                          title="What-if override"
                          onClick={(e) => {
                            e.stopPropagation();
                            setWhatIfOpen((prev) => {
                              const next = new Set(prev);
                              if (next.has(ref)) {
                                next.delete(ref);
                                whatIf.removeOverride(ref);
                              } else {
                                next.add(ref);
                              }
                              return next;
                            });
                          }}
                        >
                          <Beaker size={13} />
                        </button>
                      </span>
                    )}
                  </span>
                )}
                <span className="text-muted-foreground shrink-0 w-12 truncate">{p.unit}</span>
                {ev?.measured !== undefined && (
                  <span className="inline-flex items-center gap-1 text-3xs font-mono text-cs-purple shrink-0" title={`Measured by ${ev.measured_by}`}>
                    <FlaskConical size={10} /> {ev.measured}
                    {ev.measured_by && <EntityLink kind="verification" id={ev.measured_by} showIcon={false} className="text-cs-purple/80" />}
                  </span>
                )}
                {ev?.error && <span className="text-3xs text-cs-red shrink-0" title={ev.error}>error</span>}
                {ev?.unit_warning && <UnitWarning message={ev.unit_warning} />}
                {editable && (
                  <span className="flex items-center gap-0.5">
                    {p.calc_def ? (
                      <span className="shrink-0 text-muted-foreground" title="Derived from a calc definition — delete to change its binding">
                        <Lock size={12} />
                      </span>
                    ) : (
                      <button onClick={() => setEditingIdx(i)} className="text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-[color,opacity]" title="Edit parameter">
                        <Pencil size={12} />
                      </button>
                    )}
                    <button onClick={() => removeParameter(i)} className="text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-[color,opacity]" title="Remove parameter">
                      <X size={12} />
                    </button>
                  </span>
                )}
              </motion.div>
            );
          })}
        </div>
      )}

      {editable && (
        <div className="flex gap-1 mb-4">
          <input className="input w-28 text-xs font-mono shrink-0" placeholder="name" value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addParameter(); } }} />
          <input className="input w-20 text-xs font-mono shrink-0" placeholder="value" value={draft.value}
            onChange={(e) => setDraft({ ...draft, value: e.target.value })}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addParameter(); } }} />
          <ExpressionField
            className="input text-xs font-mono resize-none"
            placeholder="or expr: GROS0001.mass - empty"
            value={draft.expr}
            onChange={(v) => setDraft({ ...draft, expr: v })}
            onSubmit={addParameter}
            refs={refs}
          />
          <input className="input w-16 text-xs shrink-0" placeholder="unit" list={UNITS_LIST_ID} value={draft.unit}
            onChange={(e) => setDraft({ ...draft, unit: e.target.value })}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addParameter(); } }} />
          <button onClick={addParameter} className="btn-secondary shrink-0 p-2" disabled={!draft.name.trim()} title="Add parameter">
            <Plus size={12} />
          </button>
          <UnitsDatalist />
        </div>
      )}

      {/* Constraints */}
      {(constraints.length > 0 || editable) && (
        <h3 className="text-2xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Constraints</h3>
      )}
      {constraints.length > 0 && (
        <div className="space-y-1 mb-3">
          {constraints.map((c, i) => {
            const ev = evaluated?.constraints?.[i];
            const mev = evaluated?.measured_constraints?.[i];
            return (
              <div key={i} className="relative overflow-hidden flex items-start gap-2 text-xs py-1.5 px-2 rounded-md hover:bg-accent group">
                {ev?.margin && <MarginBar margin={ev.margin} />}
                <div className="relative flex items-start gap-2 flex-1 min-w-0">
                  <div className="flex-1 min-w-0 break-words">
                    <Expr expr={c.expr ?? ''} className="font-mono" />
                    {c.assume && <span className="font-mono text-muted-foreground ml-2">{'when '}<Expr expr={c.assume} /></span>}
                    {ev?.detail && <span className="text-muted-foreground ml-2">({ev.detail})</span>}
                  </div>
                  {ev?.margin && <MarginTag margin={ev.margin} />}
                  {ev?.unit_warning && <UnitWarning message={ev.unit_warning} />}
                  {ev && <VerdictBadge status={ev.status} />}
                  {mev && mev.status !== ev?.status && <VerdictBadge status={mev.status} prefix="measured" />}
                  {editable && (
                    <span className="flex items-center gap-0.5">
                      <button onClick={() => moveConstraintUp(i)} disabled={i === 0}
                        className="text-muted-foreground hover:text-foreground disabled:opacity-25 opacity-0 group-hover:opacity-100 transition-[color,opacity]">
                        <ArrowUp size={10} />
                      </button>
                      <button onClick={() => moveConstraintDown(i)} disabled={i >= constraints.length - 1}
                        className="text-muted-foreground hover:text-foreground disabled:opacity-25 opacity-0 group-hover:opacity-100 transition-[color,opacity]">
                        <ArrowDown size={10} />
                      </button>
                      <button onClick={() => removeConstraint(i)} className="text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-[color,opacity] ml-1">
                        <X size={12} />
                      </button>
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {editable && (
        <div className="flex items-start gap-1">
          <ExpressionField
            className="input text-xs font-mono resize-none"
            placeholder={`expr: gross <= 1160 or rollup('WING01','mass') <= limit`}
            value={newConstraint.expr}
            onChange={(v) => setNewConstraint({ ...newConstraint, expr: v })}
            onSubmit={addConstraint}
            refs={refs}
          />
          <ExpressionField
            className="input text-xs font-mono resize-none"
            placeholder="assume (optional)"
            value={newConstraint.assume}
            onChange={(v) => setNewConstraint({ ...newConstraint, assume: v })}
            onSubmit={addConstraint}
            refs={refs}
          />
          <button onClick={addConstraint} className="btn-secondary shrink-0 p-2" disabled={!newConstraint.expr.trim()} title="Add constraint">
            <Plus size={12} />
          </button>
        </div>
      )}

      {/* Add a constraint from a reusable definition, binding its formals. */}
      {editable && constraintDefs.length > 0 && (
        <div className="mt-2 p-2 rounded-md border border-dashed border-border/70 bg-accent/20">
          <div className="flex items-center gap-1.5 mb-1.5 text-2xs text-muted-foreground">
            <Boxes size={12} className="text-cs-teal" /> Use a definition
            <select
              className="select text-xs py-0.5 ml-1"
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
                  <label className="text-4xs font-mono text-muted-foreground px-1">{f}</label>
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
        <p className="text-3xs text-muted-foreground mt-3">
          Reference own parameters by name, others as <code className="font-mono">ID.param</code>;{' '}
          <code className="font-mono">rollup('COMP', 'param')</code> sums over the component tree ×quantity.
        </p>
      )}
    </Reveal>
  );
}

/** Compact numeric-parameter editor used on the component detail panel. */
export function ParameterEditor({ parameters, editable, onChange, id = '', references = [], definitions = [] }: {
  parameters: Parameter[];
  editable: boolean;
  onChange: (next: Parameter[]) => void;
  /** The owning component's id — keys own parameters in the reference helper. */
  id?: string;
  /** Other project parameters offered by the reference helper as `ID.param`. */
  references?: ParamOwner[];
  definitions?: Definition[];
}) {
  const [draft, setDraft] = useState({ name: '', value: '', unit: '', expr: '' });
  const [editingIdx, setEditingIdx] = useState(-1);
  useEffect(() => setDraft({ name: '', value: '', unit: '', expr: '' }), [parameters]);
  const paramNameId = useId();

  const refs = useMemo(() => buildParameterReferences({
    ownId: id, ownParameters: parameters, others: references, definitions,
  }), [id, parameters, references, definitions]);

  if (!editable && parameters.length === 0) return null;

  const addParameter = () => {
    if (!draft.name.trim()) return;
    onChange([...parameters, {
      name: draft.name.trim(),
      unit: draft.unit.trim(),
      value: draft.expr.trim() ? null : (draft.value.trim() === '' ? null : Number(draft.value)),
      expr: draft.expr.trim() || null,
    }]);
    setDraft({ name: '', value: '', unit: '', expr: '' });
  };

  return (
    <div>
      <label className="label flex items-center gap-1" htmlFor={paramNameId}><Sigma size={11} className="text-cs-teal" /> Parameters</label>
      <p className="text-2xs text-muted-foreground -mt-1 mb-1.5">Quantities budget rollups can sum</p>
      {parameters.length > 0 && (
        <div className="space-y-1 mb-2">
          {parameters.map((p, i) => {
            if (editable && editingIdx === i) {
              return (
                <ParameterEditRow
                  key={`edit-${p.name}-${i}`}
                  original={p}
                  refs={refs}
                  onSave={(next) => { onChange(parameters.map((pp, idx) => (idx === i ? next : pp))); setEditingIdx(-1); }}
                  onCancel={() => setEditingIdx(-1)}
                />
              );
            }
            return (
              <motion.div key={`${p.name}-${i}`} layout className="flex items-center gap-2 text-xs py-1 px-2 rounded-md hover:bg-accent group">
                <span className="font-mono font-medium text-foreground flex-1 truncate">{p.name}</span>
                <span className="font-mono tabular-nums">{p.expr ? `= ${p.expr}` : p.value ?? '—'}</span>
                <span className="text-muted-foreground w-10 truncate">{p.unit}</span>
                {editable && (
                  <span className="flex items-center gap-0.5">
                    {p.calc_def ? (
                      <span className="shrink-0 text-muted-foreground" title="Derived from a calc definition — delete to change its binding">
                        <Lock size={11} />
                      </span>
                    ) : (
                      <button onClick={() => setEditingIdx(i)}
                        className="text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-[color,opacity]" title="Edit parameter">
                        <Pencil size={11} />
                      </button>
                    )}
                    <button onClick={() => onChange(parameters.filter((_, idx) => idx !== i))}
                      className="text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-[color,opacity]">
                      <X size={11} />
                    </button>
                  </span>
                )}
              </motion.div>
            );
          })}
        </div>
      )}
      {editable && (
        <div className="flex items-center gap-1">
          <input id={paramNameId} className="input w-28 text-xs font-mono shrink-0" placeholder="name" value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addParameter(); } }} />
          <input className="input w-20 text-xs font-mono shrink-0" placeholder="value" value={draft.value}
            onChange={(e) => setDraft({ ...draft, value: e.target.value })}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addParameter(); } }} />
          <ExpressionField
            className="input text-xs font-mono resize-none"
            placeholder="or expr"
            value={draft.expr}
            onChange={(v) => setDraft({ ...draft, expr: v })}
            onSubmit={addParameter}
            refs={refs}
          />
          <input className="input w-14 text-xs shrink-0" placeholder="unit" list={UNITS_LIST_ID} value={draft.unit}
            onChange={(e) => setDraft({ ...draft, unit: e.target.value })}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addParameter(); } }} />
          <UnitsDatalist />
          <button
            onClick={addParameter}
            className="btn-secondary shrink-0 p-1.5"
            disabled={!draft.name.trim() || (draft.expr.trim() === '' && draft.value.trim() === '')}
            title="Add parameter"
          >
            <Plus size={12} />
          </button>
        </div>
      )}
    </div>
  );
}
