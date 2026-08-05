import { X } from 'lucide-react';
import { EntityLink, type EntityKind } from './entities';

/**
 * A linked-entity field: chips that navigate to the entity, each removable,
 * plus a "+ link…" select to add another. Originally local to
 * ComponentDetailPage (satisfies / verification_cases); factored out so the
 * same editing pattern can back every entity-to-entity relationship the app
 * shows read-only in a detail pane — risk↔requirement, requirement↔component
 * allocation — instead of each growing its own copy.
 */
export function LinkEditor({ label, hint, kind, linked, options, editable, onAdd, onRemove, nameOf }: {
  /** Omit when an enclosing heading already names the field (e.g. an <h2>
   *  card title) — an empty <label> would otherwise still take up a line. */
  label?: string; hint: string; kind: EntityKind;
  linked: string[]; options: { id: string; name: string }[];
  editable: boolean; onAdd: (id: string) => void; onRemove: (id: string) => void;
  nameOf: (id: string) => string;
}) {
  const available = options.filter((o) => !linked.includes(o.id));
  return (
    // `data-link-editor` names this editor so a test can address it directly.
    // The e2e suite used to reach the "Mitigated By" picker as the *last*
    // select on the risk card; adding the component pickers after it silently
    // repointed that selector at a different control, and the test failed on a
    // timeout rather than on an assertion. Position is not a stable handle when
    // controls get added beside it.
    <div data-link-editor={label || kind}>
      {label && <label className="label">{label}</label>}
      <p className="text-[11px] text-muted-foreground -mt-1 mb-1.5">{hint}</p>
      {linked.length === 0 && <p className="text-xs text-muted-foreground italic mb-1.5">None linked</p>}
      <div className="flex flex-wrap gap-1.5 mb-2">
        {linked.map((id) => (
          <span key={id} className="inline-flex items-center gap-1 pl-2 pr-1.5 py-0.5 rounded-full bg-muted text-xs">
            <EntityLink kind={kind} id={id} name={nameOf(id) || undefined} className="max-w-[140px] hover:text-foreground" />
            {editable && (
              <button onClick={() => onRemove(id)} className="text-muted-foreground hover:text-destructive" title="Unlink">
                <X size={11} />
              </button>
            )}
          </span>
        ))}
      </div>
      {editable && available.length > 0 && (
        <select className="input text-xs" value="" onChange={(e) => onAdd(e.target.value)}>
          <option value="">+ link…</option>
          {available.map((o) => <option key={o.id} value={o.id}>{o.id} — {o.name}</option>)}
        </select>
      )}
    </div>
  );
}
