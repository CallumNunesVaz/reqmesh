/** Payload building for the requirements bulk-edit modal.
 *
 *  Pure on purpose — the node-environment vitest setup has no jsdom and cannot
 *  render the modal, but the payload shape is the part that matters for the
 *  "silent 422" bug: an out-of-range priority score rejected the whole batch.
 *  This keeps the field→payload translation in one place a test can reach.
 */

export interface BulkEditForm {
  type: string;
  priority: string;
  status: string;
  rationale: string;
  source: string;
  allocated_to: string;
  baselines: string[] | null;
  normative: boolean | null;
  system_states: string[] | null;
  subject: string;
  needs: string[] | null;
  priorities: Record<string, number> | null;
  cascade_from: string;
  description: string;
}

/** The empty form the modal resets to. Every field's "no change" sentinel:
 *  `''` for scalars, `null` for the list/object-valued fields. */
export const INITIAL_BULK_EDIT: BulkEditForm = {
  type: '',
  priority: '',
  status: '',
  rationale: '',
  source: '',
  allocated_to: '',
  baselines: null,
  normative: null,
  system_states: null,
  subject: '',
  needs: null,
  priorities: null,
  cascade_from: '',
  description: '',
};

/** Assemble the `updates` payload the bulk endpoint consumes.
 *
 *  `''` means "leave unchanged" for scalar fields; `null` means "leave
 *  unchanged" for the list/object-valued fields, matching the `baselines`
 *  convention in the same component. `priorities` is sent verbatim — the modal
 *  already holds only the stakeholders the user actually touched, so an
 *  untouched stakeholder is absent from the payload, never zeroed.
 */
export function buildBulkUpdates(form: BulkEditForm): Record<string, unknown> {
  const updates: Record<string, unknown> = {};
  if (form.type) updates.type = form.type;
  if (form.priority) updates.priority = form.priority;
  if (form.status) updates.status = form.status;
  if (form.rationale) updates.rationale = form.rationale;
  if (form.source) updates.source = form.source;
  if (form.allocated_to) updates.allocated_to = form.allocated_to;
  if (form.baselines !== null) updates.baselines = form.baselines;
  if (form.normative !== null) updates.normative = form.normative;
  if (form.system_states !== null) updates.system_states = form.system_states;
  if (form.subject) updates.subject = form.subject;
  if (form.needs !== null) updates.needs = form.needs;
  if (form.priorities !== null) updates.priorities = form.priorities;
  // '' means "leave unchanged"; the sentinel clears the field, which the old
  // free-text box could not express at all — you could opt into a cascade but
  // never out of one.
  if (form.cascade_from === '__none__') updates.cascade_from = null;
  else if (form.cascade_from) updates.cascade_from = form.cascade_from;
  if (form.description) updates.description = form.description;
  return updates;
}

/** The value a field holds in its "no change" state. */
function initialValue(k: string): unknown {
  return (INITIAL_BULK_EDIT as unknown as Record<string, unknown>)[k];
}

/** True when a field differs from its "no change" sentinel. */
function changed(k: string, v: unknown): boolean {
  const init = initialValue(k);
  if (init === null) return v !== null;
  if (typeof init === 'boolean') return v !== null;
  return v !== '' && v !== init;
}

/** True when any field differs from its "no change" sentinel. */
export function hasBulkEditChanges(form: BulkEditForm): boolean {
  return Object.entries(form).some(([k, v]) => changed(k, v));
}

/** How many fields differ from their "no change" sentinel. */
export function bulkEditFieldCount(form: BulkEditForm): number {
  return Object.entries(form).filter(([k, v]) => changed(k, v)).length;
}
