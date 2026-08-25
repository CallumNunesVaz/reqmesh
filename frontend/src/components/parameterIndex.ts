import { useEffect, useState } from 'react';
import { api, type EvaluatedRequirement, type Parameter } from '../api/client';
import { useStore } from '../store';

/**
 * The project-wide parameter index: every fully-qualified `ID.param`
 * reference, plus the resolved value+unit each one renders as.
 *
 * This is the parameter counterpart of `entityIndex.ts`. Where the entity
 * index feeds the command palette and auto-linking, this one feeds the
 * `@`-mention picker and the read-mode resolution of `[[ID.param]]` / bare
 * `ID.param` tokens. A single cached fetch serves both, so the picker and
 * every read surface agree on what a reference resolves to.
 */

/** A resolved parameter, ready to render as `value unit`. */
export interface ParameterValue {
  value: number | null;
  unit: string;
}

/** One row of the index, for the picker. */
export interface ParameterRef {
  /** Fully-qualified reference — `ID.param`. */
  ref: string;
  /** The owning entity id (`ID`). */
  entityId: string;
  /** Bare parameter name (`param`). */
  name: string;
  unit: string;
  /** Resolved display value: the literal for a literal parameter, the
   *  evaluated value for a derived one. Null when neither is available. */
  value: number | null;
  derived: boolean;
}

export interface ParameterIndex {
  refs: ParameterRef[];
  values: Map<string, ParameterValue>;
}

/** The number, formatted exactly as the parametrics card shows it: the raw
 *  number for a literal, the evaluated 6dp-rounded value for a derived one —
 *  both are JS number-to-string, so a mention reads like the card's display of
 *  the same parameter. */
export function formatParamValue(value: number): string {
  return String(value);
}

/** `value unit` for a resolvable parameter, e.g. `30 °C`. */
export function paramText(v: ParameterValue): string {
  return v.unit ? `${formatParamValue(v.value!)} ${v.unit}` : formatParamValue(v.value!);
}

/** The two states a parameter mention can render into. */
export type ParamResolution =
  | { kind: 'value'; text: string }
  | { kind: 'broken' };

/** Resolve a reference against the index. Missing and valueless references are
 *  both `broken` — never an empty string, never a crash. */
export function resolveParam(ref: string, values: Map<string, ParameterValue>): ParamResolution {
  const v = values.get(ref);
  if (v && v.value != null) return { kind: 'value', text: paramText(v) };
  return { kind: 'broken' };
}

function buildIndex(
  reqs: { id: string; parameters?: Parameter[] }[],
  comps: { id: string; parameters?: Parameter[] }[],
  evalById: Map<string, EvaluatedRequirement>,
): ParameterIndex {
  const refs: ParameterRef[] = [];
  const values = new Map<string, ParameterValue>();

  const add = (id: string, p: Parameter) => {
    const name = p.name?.trim();
    if (!name) return;
    const ref = `${id}.${name}`;
    const derived = Boolean(p.expr || p.calc_def);
    // A derived parameter resolves through the evaluation endpoint, which
    // returns the computed, 6dp-rounded value — the same number the parametrics
    // card shows after the arrow. A literal resolves to its raw stored value,
    // also matching the card's inline render. Both are JS-number-to-string,
    // so the mention reads exactly like the card's display of the parameter.
    const evaluated = evalById.get(id)?.parameters.find((e) => e.name === name)?.value ?? null;
    const value = derived ? evaluated : (p.value ?? null);
    refs.push({ ref, entityId: id, name, unit: p.unit ?? '', value, derived });
    values.set(ref, { value, unit: p.unit ?? '' });
  };

  for (const r of reqs) for (const p of r.parameters ?? []) add(r.id, p);
  for (const c of comps) for (const p of c.parameters ?? []) add(c.id, p);
  return { refs, values };
}

/**
 * Overlay one entity's in-progress parameters onto the index's ref list.
 *
 * The index is built from the API, so it only ever knows what has been saved.
 * A parameter typed into the parametrics card lives in the page's draft state
 * until the requirement is saved, and without this it is invisible to the
 * `@`-picker — you cannot mention the parameter you just added. The expression
 * helper never had the problem because it is handed the draft list directly
 * (`buildParameterReferences`); this brings the description surfaces in line.
 *
 * Local entries win on `ref`, so a parameter edited but not yet saved offers
 * its *draft* name and unit rather than the stale saved ones. A derived
 * parameter carries no value until the server evaluates it, which the picker
 * already renders as "no value yet" rather than as an error.
 */
export function overlayLocalParams(
  refs: ParameterRef[],
  entityId: string | undefined,
  params: Parameter[] | undefined,
): ParameterRef[] {
  if (!entityId || !params?.length) return refs;
  const local: ParameterRef[] = [];
  for (const p of params) {
    const name = p.name?.trim();
    if (!name) continue;
    local.push({
      ref: `${entityId}.${name}`,
      entityId,
      name,
      unit: p.unit ?? '',
      value: p.expr || p.calc_def ? null : (p.value ?? null),
      derived: Boolean(p.expr || p.calc_def),
    });
  }
  if (!local.length) return refs;
  const overridden = new Set(local.map((r) => r.ref));
  // Anything the draft still owns is replaced; every other entity's parameters
  // (and this entity's saved-but-since-deleted ones) keep the index's ordering.
  return [...refs.filter((r) => !overridden.has(r.ref) && r.entityId !== entityId), ...local];
}

let cache: { key: string; promise: Promise<ParameterIndex> } | null = null;

/**
 * Every parameter in the project, with its resolved value. Cached per
 * (project, dataVersion) exactly like `loadEntityIndex`, so an SSE change event
 * invalidates both together.
 */
export function loadParameterIndex(projectId: string): Promise<ParameterIndex> {
  const key = `${projectId}:${useStore.getState().dataVersion}`;
  if (cache?.key === key) return cache.promise;
  const promise = Promise.all([
    api.listRequirements(projectId).catch(() => []),
    api.listComponents(projectId).catch(() => []),
    api.getEvaluation(projectId).catch(() => null),
  ]).then(([reqs, comps, evaluation]) => {
    const evalById = new Map((evaluation?.requirements ?? []).map((r) => [r.id, r]));
    return buildIndex(reqs, comps, evalById);
  });
  cache = { key, promise };
  return promise;
}

/** The full index — refs for the picker, values for resolution. */
export function useParameterIndex(projectId?: string): ParameterIndex {
  const dataVersion = useStore((s) => s.dataVersion);
  const [index, setIndex] = useState<ParameterIndex>({ refs: [], values: new Map() });
  useEffect(() => {
    if (!projectId) return;
    let alive = true;
    loadParameterIndex(projectId).then((i) => { if (alive) setIndex(i); });
    return () => { alive = false; };
  }, [projectId, dataVersion]);
  return index;
}

/** ref -> { value, unit } for read-mode resolution. */
export function useParameterValues(projectId?: string): Map<string, ParameterValue> {
  const dataVersion = useStore((s) => s.dataVersion);
  const [values, setValues] = useState<Map<string, ParameterValue>>(new Map());
  useEffect(() => {
    if (!projectId) return;
    let alive = true;
    loadParameterIndex(projectId).then((i) => { if (alive) setValues(i.values); });
    return () => { alive = false; };
  }, [projectId, dataVersion]);
  return values;
}
