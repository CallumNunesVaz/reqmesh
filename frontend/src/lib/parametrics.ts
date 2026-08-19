import type { Definition, Parameter } from '../api/client';

/**
 * Pure helpers behind the editable parametrics card. Kept free of React so the
 * round-trip and reference-list behaviour is unit-testable in a node env.
 */

/** A single insertable entry offered by the inline reference helper. */
export interface ParamReference {
  /** Text inserted at the caret. */
  ref: string;
  /** Display label shown in the list (current value alongside the ref). */
  label: string;
  /** Caret offset within `ref` after insertion; defaults to the end. */
  caret?: number;
}

/** A project entity that owns parameters (a requirement or a component). */
export interface ParamOwner {
  id: string;
  parameters: Parameter[];
}

const IDENT = /[A-Za-z0-9_.]/;

/** The identifier fragment immediately before `caret` — what the helper
 *  matches against. Includes the trailing `.` of `REQM0002.` so typing that
 *  narrows to that entity's parameters. */
export function identifierFragment(text: string, caret: number): string {
  const end = Math.min(caret, text.length);
  let start = end;
  while (start > 0 && IDENT.test(text[start - 1])) start -= 1;
  return text.slice(start, end);
}

function valueSuffix(value: number | null | undefined, unit?: string): string {
  if (value == null) return unit ? ` · ${unit}` : '';
  return unit ? ` → ${value} ${unit}` : ` → ${value}`;
}

/** Build the full reference list for one expression field.
 *
 *  Own parameters are offered by bare name, every other requirement's and
 *  component's parameter as `ID.param`, the documented `rollup(...)` helper,
 *  and each reusable definition by id. `evalValues` (keyed `ID.param`) is used
 *  when present so the label shows the *evaluated* value; otherwise the literal
 *  `value` is shown. */
export function buildParameterReferences(opts: {
  ownId: string;
  ownParameters: Parameter[];
  others: ParamOwner[];
  definitions: Definition[];
  evalValues?: Map<string, number | null>;
}): ParamReference[] {
  const valueOf = (id: string, p: Parameter): number | null => {
    const ev = opts.evalValues?.get(`${id}.${p.name}`);
    if (ev != null) return ev;
    return p.value ?? null;
  };

  const out: ParamReference[] = [];
  for (const p of opts.ownParameters) {
    out.push({ ref: p.name, label: `${p.name}${valueSuffix(valueOf(opts.ownId, p), p.unit)}` });
  }
  for (const owner of opts.others) {
    for (const p of owner.parameters) {
      out.push({
        ref: `${owner.id}.${p.name}`,
        label: `${owner.id}.${p.name}${valueSuffix(valueOf(owner.id, p), p.unit)}`,
      });
    }
  }
  for (const d of opts.definitions) {
    const params = d.parameters?.length ? `(${d.parameters.join(', ')})` : '';
    out.push({ ref: d.id, label: `${d.id}${params} — ${d.expr}` });
  }
  // The documented tree-sum helper, inserted with the caret between the quotes.
  out.push({
    ref: "rollup('', '')",
    label: "rollup('COMP', 'param') — sum over the component tree ×quantity",
    caret: 8,
  });
  return out;
}

/** Case-insensitive substring filter — fuzzy enough to let `min` surface
 *  `REQM0002.min`, and exact enough that `REQM0002.` narrows to that entity. */
export function filterReferences(refs: ParamReference[], fragment: string): ParamReference[] {
  const q = fragment.toLowerCase();
  if (!q) return refs;
  return refs.filter(
    (r) => r.ref.toLowerCase().includes(q) || r.label.toLowerCase().includes(q),
  );
}

/** Compute the `Parameter` handed to `onSave` for a row edit.
 *
 *  Spreads the original so `kind`, `value_type`, `calc_def` and `bindings`
 *  round-trip untouched — dropping them on save is the data-loss bug this
 *  function exists to make impossible. A non-empty expr nulls `value` and vice
 *  versa, matching `addParameter`. */
export function resolveParameterEdit(
  original: Parameter,
  draft: { name: string; value: string; unit: string; expr: string },
): Parameter {
  const next: Parameter = { ...original };
  next.name = draft.name.trim();
  next.unit = draft.unit.trim();
  const expr = draft.expr.trim();
  if (expr) {
    next.expr = expr;
    next.value = null;
  } else {
    next.expr = null;
    next.value = draft.value.trim() === '' ? null : Number(draft.value);
  }
  return next;
}
