from __future__ import annotations

from app.services.history import diff_fields
from app.services.fingerprint import compute_fingerprint


def redline(store, cr: dict) -> dict:
    """Compute a before/after redline for a change request.

    Returns a dict matching the CRRedline shape:
        {id, targets: [{id, name, diffs, stale, creates}], blocked}
    """
    targets = []
    blocked = False
    creates_list = cr.get("creates", [])

    for target_id in cr.get("changes", {}):
        proposed = cr["changes"][target_id]
        current_req = store.get_requirement(target_id)

        if current_req is None:
            creates = target_id in creates_list
            if creates:
                targets.append({
                    "id": target_id,
                    "name": proposed.get("name", target_id),
                    "diffs": {f: {"before": None, "after": v} for f, v in proposed.items()},
                    "stale": False,
                    "creates": True,
                })
            else:
                # Target no longer exists and is not being proposed — deleted.
                targets.append({
                    "id": target_id,
                    "name": target_id,
                    "diffs": {},
                    "stale": True,
                    "creates": False,
                })
                blocked = True
            continue

        # Build the "after" state: current overlaid with proposal.
        after = dict(current_req)
        for field, value in proposed.items():
            after[field] = value

        # diff_fields returns {field: {before, after}} for changed bookkeeping
        # fields only.  We need only the fields *in the proposal*, filtered
        # to those where the proposal differs from current — a field already
        # equal is omitted.
        all_diffs = diff_fields(current_req, after)

        # Keep only the fields that are in the proposal and actually differ.
        diffs = {}
        for field in proposed:
            if field in all_diffs:
                diffs[field] = all_diffs[field]

        # Staleness: only when a fingerprint exists *and* does not match.
        fp = cr.get("base_fingerprints", {}).get(target_id)
        stale = False
        if fp is not None and fp != "":
            current_fp = compute_fingerprint(current_req)
            stale = fp != current_fp

        if stale:
            blocked = True

        # Collision: target exists but CR also lists it in creates.
        if target_id in creates_list:
            stale = True
            blocked = True

        targets.append({
            "id": target_id,
            "name": current_req.get("name", target_id),
            "diffs": diffs,
            "stale": stale,
            "creates": target_id in creates_list,
        })

    return {
        "id": cr["id"],
        "targets": targets,
        "blocked": blocked,
    }
