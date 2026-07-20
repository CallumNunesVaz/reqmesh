import { useEffect, useState } from 'react';
import { Boxes, Plus, X, Trash2, Play, FlaskConical, Sigma } from 'lucide-react';
import { api, type Definition, type AnalysisCase, type EvaluationData } from '../api/client';
import { VerdictBadge } from './parametrics';

/**
 * Admin/editor manager for reusable SysML v2-style parametric definitions
 * (constraint def / calc def). Kept deliberately simple: a list with inline
 * create, since a definition is just a name, formals, and an expression.
 */
export function DefinitionsManager({ projectId, editable }: { projectId: string; editable: boolean }) {
  const [defs, setDefs] = useState<Definition[]>([]);
  const [draft, setDraft] = useState<{ id: string; type: 'constraint' | 'calc'; name: string; parameters: string; expr: string; unit: string }>(
    { id: '', type: 'constraint', name: '', parameters: '', expr: '', unit: '' });
  const [error, setError] = useState('');

  const load = () => api.listDefinitions(projectId).then(setDefs).catch(() => setDefs([]));
  useEffect(() => { load(); }, [projectId]);

  const add = async () => {
    if (!draft.id.trim() || !draft.expr.trim()) return;
    try {
      await api.createDefinition(projectId, {
        id: draft.id.trim(), type: draft.type, name: draft.name.trim(),
        parameters: draft.parameters.split(',').map((s) => s.trim()).filter(Boolean),
        expr: draft.expr.trim(), unit: draft.unit.trim(),
      });
      setDraft({ id: '', type: 'constraint', name: '', parameters: '', expr: '', unit: '' });
      setError('');
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add definition');
    }
  };

  const remove = async (id: string) => { await api.deleteDefinition(projectId, id).catch(() => {}); load(); };

  if (!editable && defs.length === 0) return null;

  return (
    <div className="card p-5">
      <h2 className="font-semibold text-sm text-card-foreground mb-1 flex items-center gap-2">
        <Boxes size={16} className="text-cs-teal" /> Reusable Definitions
      </h2>
      <p className="text-xs text-muted-foreground mb-3">
        SysML v2 constraint/calc definitions — write a rule once over formal parameters, then bind it on any requirement.
      </p>

      {defs.length > 0 && (
        <div className="space-y-1 mb-3">
          {defs.map((d) => (
            <div key={d.id} className="flex items-center gap-2 text-xs py-1.5 px-2 rounded hover:bg-accent group">
              <span className={`badge border shrink-0 ${d.type === 'calc' ? 'text-cs-purple border-cs-purple/30' : 'text-cs-teal border-cs-teal/30'}`}>
                {d.type === 'calc' ? <Sigma size={10} /> : <Boxes size={10} />} {d.type}
              </span>
              <span className="font-mono font-medium text-foreground shrink-0">{d.name || d.id}</span>
              <span className="font-mono text-muted-foreground">
                ({d.parameters.join(', ')}) = {d.expr}{d.unit ? ` [${d.unit}]` : ''}
              </span>
              <div className="flex-1" />
              {editable && (
                <button onClick={() => remove(d.id)} className="text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all">
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {editable && (
        <>
          <div className="flex flex-wrap gap-1 items-center">
            <select className="input text-xs py-1 w-24" value={draft.type}
              onChange={(e) => setDraft({ ...draft, type: e.target.value as 'constraint' | 'calc' })}>
              <option value="constraint">constraint</option>
              <option value="calc">calc</option>
            </select>
            <input className="input w-28 text-xs font-mono" placeholder="id" value={draft.id}
              onChange={(e) => setDraft({ ...draft, id: e.target.value })} />
            <input className="input w-32 text-xs" placeholder="name (optional)" value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            <input className="input w-40 text-xs font-mono" placeholder="formals: actual, limit" value={draft.parameters}
              onChange={(e) => setDraft({ ...draft, parameters: e.target.value })} />
            <input className="input flex-1 min-w-[10rem] text-xs font-mono" placeholder={draft.type === 'calc' ? 'expr: w * h' : 'expr: actual <= limit'} value={draft.expr}
              onChange={(e) => setDraft({ ...draft, expr: e.target.value })} />
            {draft.type === 'calc' && (
              <input className="input w-16 text-xs" placeholder="unit" value={draft.unit}
                onChange={(e) => setDraft({ ...draft, unit: e.target.value })} />
            )}
            <button onClick={add} className="btn-secondary shrink-0 p-2" disabled={!draft.id.trim() || !draft.expr.trim()}>
              <Plus size={12} />
            </button>
          </div>
          {error && <p className="text-[11px] text-destructive mt-1.5">{error}</p>}
        </>
      )}
    </div>
  );
}

/**
 * Runner for scoped what-if analysis cases: define hypothetical parameter
 * overrides and a requirement scope, then evaluate against the live solver.
 */
export function AnalysisCasesPanel({ projectId, editable }: { projectId: string; editable: boolean }) {
  const [cases, setCases] = useState<AnalysisCase[]>([]);
  const [result, setResult] = useState<(EvaluationData & { case: AnalysisCase }) | null>(null);
  const [running, setRunning] = useState('');
  const [draft, setDraft] = useState({ id: '', name: '', scope: '', overrides: '' });
  const [error, setError] = useState('');

  const load = () => api.listAnalysisCases(projectId).then(setCases).catch(() => setCases([]));
  useEffect(() => { load(); }, [projectId]);

  const add = async () => {
    if (!draft.id.trim()) return;
    const overrides: Record<string, number> = {};
    for (const line of draft.overrides.split('\n')) {
      const [k, v] = line.split('=').map((s) => s.trim());
      if (k && v && !isNaN(Number(v))) overrides[k] = Number(v);
    }
    try {
      await api.createAnalysisCase(projectId, {
        id: draft.id.trim(), name: draft.name.trim(),
        scope: draft.scope.split(',').map((s) => s.trim()).filter(Boolean),
        overrides,
      });
      setDraft({ id: '', name: '', scope: '', overrides: '' });
      setError('');
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add case');
    }
  };

  const run = async (id: string) => {
    setRunning(id);
    try { setResult(await api.runAnalysisCase(projectId, id)); }
    catch (e) { setError(e instanceof Error ? e.message : 'Run failed'); }
    finally { setRunning(''); }
  };

  const remove = async (id: string) => {
    await api.deleteAnalysisCase(projectId, id).catch(() => {});
    if (result?.case.id === id) setResult(null);
    load();
  };

  if (!editable && cases.length === 0) return null;

  return (
    <div className="card p-5">
      <h2 className="font-semibold text-sm text-card-foreground mb-1 flex items-center gap-2">
        <FlaskConical size={16} className="text-cs-purple" /> Analysis Cases
      </h2>
      <p className="text-xs text-muted-foreground mb-3">
        What-if evaluation: apply hypothetical parameter values over a scope and see how verdicts change — reusing the live solver.
      </p>

      {cases.length > 0 && (
        <div className="space-y-1 mb-3">
          {cases.map((c) => (
            <div key={c.id} className="flex items-center gap-2 text-xs py-1.5 px-2 rounded hover:bg-accent group">
              <span className="font-mono font-medium text-foreground shrink-0">{c.name || c.id}</span>
              <span className="text-muted-foreground truncate">
                {c.scope.length ? `scope: ${c.scope.join(', ')}` : 'whole project'}
                {Object.keys(c.overrides).length ? ` · ${Object.entries(c.overrides).map(([k, v]) => `${k}=${v}`).join(', ')}` : ''}
              </span>
              <div className="flex-1" />
              <button onClick={() => run(c.id)} className="btn-ghost text-xs px-2 py-1" disabled={running === c.id}>
                <Play size={12} /> Run
              </button>
              {editable && (
                <button onClick={() => remove(c.id)} className="text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all">
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {result && (
        <div className="rounded-lg border border-cs-purple/30 bg-cs-purple/5 p-3 mb-3">
          <div className="text-xs font-medium mb-2">Result — {result.case.name || result.case.id}</div>
          <div className="space-y-1">
            {result.requirements.map((r) => (
              <div key={r.id} className="flex items-center gap-2 text-xs">
                <span className="font-mono text-foreground w-28 truncate">{r.id}</span>
                <span className="text-muted-foreground flex-1 truncate">{r.name}</span>
                <VerdictBadge status={r.verdict} />
              </div>
            ))}
            {result.requirements.length === 0 && <div className="text-xs text-muted-foreground">No requirements in scope.</div>}
          </div>
        </div>
      )}

      {editable && (
        <>
          <div className="flex flex-wrap gap-1 items-start">
            <input className="input w-28 text-xs font-mono" placeholder="id" value={draft.id}
              onChange={(e) => setDraft({ ...draft, id: e.target.value })} />
            <input className="input w-32 text-xs" placeholder="name" value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            <input className="input w-40 text-xs font-mono" placeholder="scope: R1, R2 (blank=all)" value={draft.scope}
              onChange={(e) => setDraft({ ...draft, scope: e.target.value })} />
            <textarea className="input flex-1 min-w-[12rem] text-xs font-mono h-14 resize-none"
              placeholder={'overrides (one per line):\nGROS0001.mass = 1200'} value={draft.overrides}
              onChange={(e) => setDraft({ ...draft, overrides: e.target.value })} />
            <button onClick={add} className="btn-secondary shrink-0 p-2" disabled={!draft.id.trim()}>
              <Plus size={12} />
            </button>
          </div>
          {error && <p className="text-[11px] text-destructive mt-1.5">{error}</p>}
        </>
      )}
    </div>
  );
}
