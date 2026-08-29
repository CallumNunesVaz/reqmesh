"""Rename a requirement, rewriting everything that referred to it.

An id is not just a label here: it is the YAML filename, the parent pointer of
every child, and the target of every relation anywhere in the project. Changing
it in one place and not the others is how a project ends up with dangling
traces that no page surfaces.

This is the same rewrite ``services.reparent`` performs when a move re-prefixes
a subtree, narrowed to a single node and made available on its own — which also
means a re-prefixed move is now reversible, where before there was no way back.
"""
from __future__ import annotations

import keyword
import re
from typing import cast

from app.services.history import record_change
from app.services.link_registry import kind_matches, links_into, targets_of
from app.services.naming import get_naming
from app.services.naming import matches_scheme as matches_scheme  # noqa: F401  (re-export: one rule)
from app.services.reparent import collect_subtree, leading_prefix, renumber_subtree

#: The cascade modes a rename may request. ``self`` keeps today's behaviour.
CASCADE_MODES = ("self", "children", "descendants")


def suggest_id(requirements: list[dict], meta: dict, parent_id: str | None) -> str:
    """The default new id: the parent's prefix plus the next free slot.

    Mirrors the shared ``next_id`` generator's scheme so a rename and a create
    agree about what this project's ids look like.
    """
    naming = get_naming(meta, "requirements")
    prefix_len = int(naming.get("prefix_length", 4) or 4)
    separator = naming.get("separator", "")
    suffix_len = int(naming.get("suffix_length", 4) or 4)
    prefix_hint = naming.get("prefix_hint", "REQ")

    prefix = ""
    if parent_id:
        if separator and separator in parent_id:
            prefix = parent_id.split(separator)[0]
        else:
            prefix = parent_id[:prefix_len].upper()
    if not prefix:
        prefix = prefix_hint.upper()

    base = f"{prefix}{separator}" if separator else prefix
    max_suffix = -1
    for r in requirements:
        rid = r.get("id", "")
        if rid.startswith(base):
            rest = rid[len(base):]
            try:
                max_suffix = max(max_suffix, int(rest))
            except ValueError:
                pass
    return f"{base}{str(max_suffix + 1 if max_suffix >= 0 else 1).zfill(suffix_len)}"


def _rewrite_text(text: str, id_map: dict[str, str]) -> str:
    """Rewrite bare ``[[old]]`` / ``old`` mentions in rich text, id-by-id.

    Ids only match on their own: the lookarounds treat ``-`` as a word
    character (as ``autoLink.tsx`` does), so ``REQ01`` never matches inside
    ``REQ012`` and ``REQ-0001`` matches as a whole. ``[[old]]`` is handled by
    the same pattern — the brackets are word boundaries.
    """
    if not text:
        return text
    for old_id, new_id in sorted(id_map.items(), key=lambda kv: -len(kv[0])):
        pattern = re.compile(r"(?<![\w-])" + re.escape(old_id) + r"(?![\w-])")

        def repl(_m: re.Match[str], new_id: str = new_id) -> str:
            return new_id
        text = pattern.sub(repl, text)
    return text


def _rewrite_expr(text: str, id_map: dict[str, str]) -> str:
    """Rewrite ``old.param`` references in parameter/constraint expressions.

    Narrower than :func:`_rewrite_text`: only the ``id.param`` form is a
    requirement reference, so the id must be followed by ``.``. A component
    rollup like ``rollup('C172', 'mass')`` is left alone.
    """
    if not text:
        return text
    for old_id, new_id in sorted(id_map.items(), key=lambda kv: -len(kv[0])):
        pattern = re.compile(r"(?<![\w-])" + re.escape(old_id) + r"(?=\.)")

        def repl(_m: re.Match[str], new_id: str = new_id) -> str:
            return new_id
        text = pattern.sub(repl, text)
    return text


def _rewrite_expr_fields(record: dict, id_map: dict[str, str]) -> bool:
    """Rewrite ``expr``/``assume``/``bindings`` on a parameter or constraint.

    Mutates a *copy* supplied by the caller; returns whether anything changed.
    """
    changed = False
    for key in ("expr", "assume"):
        value = record.get(key)
        if isinstance(value, str) and value:
            rewritten = _rewrite_expr(value, id_map)
            if rewritten != value:
                record[key] = rewritten
                changed = True
    bindings = record.get("bindings")
    if isinstance(bindings, dict) and bindings:
        new_bindings = {
            k: (_rewrite_expr(v, id_map) if isinstance(v, str) and v else v)
            for k, v in bindings.items()
        }
        if new_bindings != bindings:
            record["bindings"] = new_bindings
            changed = True
    return changed


def _rewrite_text_references(store, id_map: dict[str, str]) -> None:
    """Rewrite the references the link registry deliberately does not cover.

    Parameter/constraint expressions and rich-text mentions are text rather
    than declared links, so no registry row points at them — but a rename still
    breaks every one of them, so they are swept here with a narrow rewriter.
    """
    for req in store.list_requirements():
        patch: dict = {}
        for field in ("description", "rationale", "source"):
            text = req.get(field)
            if isinstance(text, str) and text:
                rewritten = _rewrite_text(text, id_map)
                if rewritten != text:
                    patch[field] = rewritten

        parameters = req.get("parameters")
        if isinstance(parameters, list) and parameters:
            new_parameters: list[dict] = []
            changed = False
            for parameter in parameters:
                if not isinstance(parameter, dict):
                    new_parameters.append(parameter)
                    continue
                copy = dict(parameter)
                changed |= _rewrite_expr_fields(copy, id_map)
                new_parameters.append(copy)
            if changed:
                patch["parameters"] = new_parameters

        constraints = req.get("constraints")
        if isinstance(constraints, list) and constraints:
            new_constraints: list[dict] = []
            changed = False
            for constraint in constraints:
                if not isinstance(constraint, dict):
                    new_constraints.append(constraint)
                    continue
                copy = dict(constraint)
                changed |= _rewrite_expr_fields(copy, id_map)
                new_constraints.append(copy)
            if changed:
                patch["constraints"] = new_constraints

        if patch:
            store.update_requirement(req["id"], patch)


def _is_valid_parameter_name(name: str) -> bool:
    """Whether *name* is a usable identifier in an expression.

    Expressions are parsed with :mod:`ast`, so a parameter name is referenced
    as a Python name (bare) or attribute (``id.name``). Anything ``ast`` cannot
    parse as a name — including the Python keywords, which ``isidentifier``
    alone accepts — is refused.
    """
    return bool(name) and name.isidentifier() and not keyword.iskeyword(name)


def _rewrite_param_qualified(text: str, owner_id: str, old_name: str,
                             new_name: str) -> str:
    """Rewrite ``owner.old`` → ``owner.new`` in *text*.

    The lookarounds treat ``-`` as a word character (as ``_rewrite_text`` does),
    so ``owner.old`` only matches on its own — ``owner.temp_max_limit`` is not
    touched when renaming ``temp_max``, and ``PREQ-1.temp_max`` is not touched
    when the owner is ``REQ-1``.
    """
    if not text:
        return text
    replacement = f"{owner_id}.{new_name}"
    pattern = re.compile(
        r"(?<![\w-])" + re.escape(owner_id) + r"\." + re.escape(old_name) + r"(?![\w-])"
    )
    return pattern.sub(lambda _m: replacement, text)


def _rewrite_param_bare(text: str, old_name: str, new_name: str) -> str:
    """Rewrite a bare ``old`` identifier → ``new``.

    Only ever used inside the owner's own record, where a bare ``temp_max`` is
    that owner's parameter. The lookbehind also refuses a preceding ``.`` so a
    qualified reference to a *different* owner (``OTHER.temp_max``) is never
    mistaken for the bare form.
    """
    if not text:
        return text
    pattern = re.compile(r"(?<![\w.-])" + re.escape(old_name) + r"(?![\w-])")
    return pattern.sub(lambda _m: new_name, text)


def _rewrite_param_rollup(text: str, owner_id: str, old_name: str,
                          new_name: str) -> str:
    """Rewrite ``rollup('owner', 'old')`` → ``rollup('owner', 'new')``.

    Only the quoted string arguments are touched, and only when the component
    id is the owner and the parameter name matches in full — the closing quote
    is the boundary, so ``rollup('C172', 'mass_factor')`` is never half-rewritten
    when renaming ``mass``.
    """
    if not text:
        return text
    pattern = re.compile(
        r"rollup\(\s*(['\"])" + re.escape(owner_id) + r"\1\s*,\s*(['\"])"
        + re.escape(old_name) + r"\2\s*\)"
    )

    def repl(m: re.Match) -> str:
        q1, q2 = m.group(1), m.group(2)
        return f"rollup({q1}{owner_id}{q1}, {q2}{new_name}{q2})"

    return pattern.sub(repl, text)


def _rewrite_param_expr_string(text: str, owner_id: str, old_name: str,
                               new_name: str, own: bool) -> str:
    """Rewrite one expression string against a parameter rename.

    Qualified ``owner.old`` references and component rollups are swept on every
    record; the bare ``old`` form is rewritten only when *own* is true (the
    owner's own record), where a bare name is that owner's parameter.
    """
    rewritten = _rewrite_param_qualified(text, owner_id, old_name, new_name)
    rewritten = _rewrite_param_rollup(rewritten, owner_id, old_name, new_name)
    if own:
        rewritten = _rewrite_param_bare(rewritten, old_name, new_name)
    return rewritten


def _rewrite_param_expr_fields(record: dict, owner_id: str, old_name: str,
                               new_name: str, own: bool) -> tuple[int, bool]:
    """Rewrite ``expr``/``assume``/``bindings`` on a record's parameters and
    constraints. Mutates *record* in place; returns ``(strings_rewritten,
    changed)``.
    """
    strings = 0
    changed = False
    for list_key in ("parameters", "constraints"):
        items = record.get(list_key)
        if not isinstance(items, list) or not items:
            continue
        new_items: list[dict] = []
        list_changed = False
        for item in items:
            if not isinstance(item, dict):
                new_items.append(item)
                continue
            copy = dict(item)
            item_strings = 0
            for key in ("expr", "assume"):
                value = copy.get(key)
                if isinstance(value, str) and value:
                    rewritten = _rewrite_param_expr_string(
                        value, owner_id, old_name, new_name, own)
                    if rewritten != value:
                        copy[key] = rewritten
                        item_strings += 1
            bindings = copy.get("bindings")
            if isinstance(bindings, dict) and bindings:
                new_bindings = {}
                for k, v in bindings.items():
                    if isinstance(v, str) and v:
                        rewritten = _rewrite_param_expr_string(
                            v, owner_id, old_name, new_name, own)
                        if rewritten != v:
                            new_bindings[k] = rewritten
                            item_strings += 1
                        else:
                            new_bindings[k] = v
                    else:
                        new_bindings[k] = v
                if new_bindings != bindings:
                    copy["bindings"] = new_bindings
            if item_strings:
                list_changed = True
                strings += item_strings
            new_items.append(copy)
        if list_changed:
            record[list_key] = new_items
            changed = True
    return strings, changed


def _rewrite_param_text_fields(record: dict, owner_id: str, old_name: str,
                               new_name: str,
                               text_fields: tuple[str, ...]) -> tuple[int, bool]:
    """Rewrite parameter mentions in a record's text fields; returns
    ``(strings_rewritten, changed)``. Mentions are always fully qualified, so
    only the ``owner.old`` form applies.
    """
    strings = 0
    changed = False
    for field in text_fields:
        value = record.get(field)
        if isinstance(value, str) and value:
            rewritten = _rewrite_param_qualified(value, owner_id, old_name, new_name)
            if rewritten != value:
                record[field] = rewritten
                strings += 1
                changed = True
    return strings, changed


def _rewrite_parameter_references(store, owner_id: str, old_name: str,
                                  new_name: str) -> tuple[int, int, set[str]]:
    """Sweep every requirement and component, rewriting references to the
    renamed parameter. Returns ``(expressions, mentions, touched_ids)``.
    """
    expressions = 0
    mentions = 0
    touched: set[str] = set()

    for req in store.list_requirements():
        before = dict(req)
        own = req["id"] == owner_id
        expr_count, expr_changed = _rewrite_param_expr_fields(
            before, owner_id, old_name, new_name, own)
        text_count, text_changed = _rewrite_param_text_fields(
            before, owner_id, old_name, new_name, ("description", "rationale", "source"))
        if expr_changed or text_changed:
            patch = {k: before[k] for k in before if req.get(k) != before[k]}
            if patch:
                store.update_requirement(req["id"], patch)
                touched.add(req["id"])
            expressions += expr_count
            mentions += text_count

    for comp in store.list_components():
        before = dict(comp)
        own = comp["id"] == owner_id
        expr_count, expr_changed = _rewrite_param_expr_fields(
            before, owner_id, old_name, new_name, own)
        text_count, text_changed = _rewrite_param_text_fields(
            before, owner_id, old_name, new_name, ("description",))
        if expr_changed or text_changed:
            patch = {k: before[k] for k in before if comp.get(k) != before[k]}
            if patch:
                store.update_component(comp["id"], patch)
                touched.add(comp["id"])
            expressions += expr_count
            mentions += text_count

    return expressions, mentions, touched


def _plan_rename_id_map(requirements: list[dict], old_id: str, new_id: str,
                        cascade: str) -> dict[str, str]:
    """Every old id the rename will move, mapped to its new id.

    The root always moves to *new_id* exactly. For ``children`` the immediate
    *leaf* children are re-prefixed; for ``descendants`` the whole subtree is;
    for ``self`` nothing else. Re-prefixing shares :func:`renumber_subtree`
    with the bulk reparent, so the two cannot disagree about the scheme.
    """
    id_map = {old_id: new_id}
    new_prefix = leading_prefix(new_id)
    old_prefix = leading_prefix(old_id)
    if cascade == "self" or not new_prefix or not old_prefix or new_prefix == old_prefix:
        return id_map

    children_by_parent: dict[str | None, list[str]] = {}
    for r in requirements:
        children_by_parent.setdefault(r.get("parent"), []).append(r["id"])

    if cascade == "descendants":
        extra = collect_subtree(children_by_parent, old_id)[1:]
    elif cascade == "children":
        immediate = children_by_parent.get(old_id, [])
        extra = [c for c in immediate if c not in children_by_parent]
    else:
        extra = []

    if not extra:
        return id_map

    # Mirror the new id's separator + zero-padded width, and reserve its number
    # so a descendant can never be allocated onto the root's new id.
    pm = re.match(r"^[A-Za-z]+(\D*)(\d+)$", new_id)
    sep, width = (pm.group(1), len(pm.group(2))) if pm else ("", 4)
    used: set[int] = set()
    for r in requirements:
        mm = re.match(r"^" + re.escape(new_prefix) + r"\D*(\d+)$", r["id"])
        if mm:
            used.add(int(mm.group(1)))
    mm = re.match(r"^" + re.escape(new_prefix) + r"\D*(\d+)$", new_id)
    if mm:
        used.add(int(mm.group(1)))

    local_map = renumber_subtree(extra, old_prefix, new_prefix, sep, width, used)
    id_map.update({k: v for k, v in local_map.items() if k != v})
    return id_map


def _plan_link_sweep(store, id_map: dict[str, str]):
    """The inbound references the rename will rewrite, without writing them.

    Returns ``(children, relinked, updates)`` — the tree-linked records whose
    parent moved, the other records relinked, and the ``(holder, id, field,
    value)`` writes to perform. Iterating ``links_into`` means a link added to
    the model later is swept here without a second edit.
    """
    children: list[str] = []
    relinked: list[str] = []
    updates: list[tuple[str, str, str, object]] = []
    for link in links_into("requirements"):
        try:
            items = store.list_items(link.holder)
        except Exception:
            # A collection that does not exist in this project is not an error.
            continue
        for item in items:
            if not kind_matches(item, link):
                continue
            targets = targets_of(item, link)
            if not any(t in id_map for t in targets):
                continue
            new_targets = [id_map.get(t, t) for t in targets]
            new_value = new_targets if link.many else new_targets[0]
            updates.append((link.holder, item["id"], link.field, new_value))
            if link.tree:
                if item["id"] not in children:
                    children.append(item["id"])
            elif item["id"] not in relinked:
                relinked.append(item["id"])
    return children, relinked, updates


def _plan_relation_sweep(store, id_map: dict[str, str]):
    """The relation targets the rename will rewrite, without writing them.

    Relations are kept out of the registry on purpose: a ``Relation.target`` is
    polymorphic (a requirement *or* a verification case), which the registry's
    fixed per-row ``target`` cannot express without teaching every consumer
    (delete guard, integrity) a new shape. So the rename sweeps them locally —
    only targets that equal a renamed requirement id are repointed, and a
    ``verified_by`` relation to a verification case is left untouched. Returns
    ``(relinked, updates)`` in the same shape as :func:`_plan_link_sweep`.
    """
    relinked: list[str] = []
    updates: list[tuple[str, str, str, object]] = []
    for req in store.list_requirements():
        relations = req.get("relations")
        if not isinstance(relations, list) or not relations:
            continue
        new_relations = []
        changed = False
        for rel in relations:
            if isinstance(rel, dict) and rel.get("target") in id_map:
                new_relations.append({**rel, "target": id_map[rel["target"]]})
                changed = True
            else:
                new_relations.append(rel)
        if changed:
            updates.append(("requirements", req["id"], "relations", new_relations))
            if req["id"] not in relinked:
                relinked.append(req["id"])
    return relinked, updates


def rename_requirement(store, old_id: str, new_id: str, username: str = "",
                       cascade: str = "self", dry_run: bool = False) -> dict:
    """Move *old_id* to *new_id* and repoint everything that referenced it.

    Returns ``{"id", "children", "relinked", "renames"}`` — the new id, the
    children whose parent pointer moved, the records whose references were
    rewritten, and every old→new rename performed (for the cascade preview).

    ``cascade`` controls how far the new prefix reaches: ``self`` (default) is
    today's behaviour, ``children`` re-prefixes the immediate *leaf* children,
    ``descendants`` the whole subtree. ``dry_run`` returns the planned renames
    and the records that would be relinked without writing anything.

    The inbound references are *derived* from ``link_registry.links_into``
    rather than hand-listed, so a link added to the model later is rewritten
    here without a second edit. Relations are the one exception: their targets
    are polymorphic, so the registry cannot declare them and they are swept
    locally by :func:`_plan_relation_sweep`.

    Ordering matches ``rename_component``: write the new record before deleting
    the old one (the reverse order would leave the project with neither if the
    create failed), and only then rewrite referrers. This is ordered, not
    atomic — a failure midway through the referrer sweep leaves the record at
    the new id with some inbound references still naming the old one (dangling,
    but resolvable), never the old id deleted alongside a half-written new one.
    """
    node = store.get_requirement(old_id)
    if node is None:
        raise ValueError(f"Requirement not found: {old_id}")
    if new_id == old_id:
        return {"id": old_id, "children": [], "relinked": [], "renames": []}
    if store.get_requirement(new_id) is not None:
        raise ValueError(f"A requirement with id {new_id} already exists")
    if cascade not in CASCADE_MODES:
        raise ValueError(f"Unknown cascade mode: {cascade}")

    id_map = _plan_rename_id_map(store.list_requirements(), old_id, new_id, cascade)
    renames = [{"from": k, "to": v} for k, v in sorted(id_map.items())]

    if dry_run:
        children, relinked, _updates = _plan_link_sweep(store, id_map)
        relation_relinked, _relation_updates = _plan_relation_sweep(store, id_map)
        for rel_id in relation_relinked:
            if rel_id not in relinked:
                relinked.append(rel_id)
        return {
            "dry_run": True,
            "id": new_id,
            "renames": renames,
            "children": children,
            "relinked": relinked,
        }

    # Write the new records before deleting the old ones; a descendant keeps its
    # old parent pointer until the sweep below repoints it (dangling, resolvable).
    for old, new in id_map.items():
        before = store.get_requirement(old)
        if before is None:
            continue
        moved = dict(before)
        moved["id"] = new
        store.create_requirement(moved)
        store.delete_requirement(old)
        record_change(store, new, "rename", before, moved, username)

    children, relinked, updates = _plan_link_sweep(store, id_map)
    relation_relinked, relation_updates = _plan_relation_sweep(store, id_map)
    for rel_id in relation_relinked:
        if rel_id not in relinked:
            relinked.append(rel_id)
    for holder, item_id, field, value in updates + relation_updates:
        store.update_item(holder, item_id, {field: value})

    _rewrite_requirement_snapshots(store, id_map)
    _rewrite_text_references(store, id_map)

    return {"id": new_id, "children": children, "relinked": relinked, "renames": renames}


def _rewrite_requirement_snapshots(store, id_map: dict[str, str]) -> None:
    """Repoint renamed requirement ids inside every frozen baseline.

    A frozen baseline carries its requirement snapshot in ``snapshot``, keyed
    by requirement id — and each entry's ``parent`` and ``relations[].target``
    are requirement ids too — so a rename must move the key and repoint those
    fields. The component half lives in :func:`_rewrite_baseline_snapshots`.
    """
    baselines_dir = store.root / "baselines"
    if not baselines_dir.exists():
        return
    for f in sorted(baselines_dir.glob("*.yaml")):
        baseline = store._read_yaml(f)
        if not baseline:
            continue
        snapshot = baseline.get("snapshot")
        if not isinstance(snapshot, dict):
            continue
        changed = False
        new_snapshot: dict[str, dict] = {}
        for rid, entry in snapshot.items():
            new_rid = cast(str, id_map.get(rid, rid))
            if new_rid != rid:
                changed = True
            if isinstance(entry, dict):
                if entry.get("parent") in id_map:
                    entry["parent"] = id_map[entry["parent"]]
                    changed = True
                relations = entry.get("relations")
                if isinstance(relations, list):
                    for rel in relations:
                        if isinstance(rel, dict) and rel.get("target") in id_map:
                            rel["target"] = id_map[rel["target"]]
                            changed = True
            new_snapshot[new_rid] = entry
        if changed:
            baseline["snapshot"] = new_snapshot
            store.write_item("baselines", f.stem, baseline)


def _rewrite_baseline_snapshots(store, old_id: str, new_id: str) -> None:
    """Repoint a renamed component inside every frozen baseline.

    Live baseline membership carries baseline *names*, so nothing on a component
    changes there. But a frozen baseline's ``component_snapshot`` is keyed by
    component id — and each entry's ``parent`` is a component id — so a rename
    must move the key and repoint any snapshot whose parent was the old id.

    Frozen baselines written by the API ``freeze`` route carry no ``id`` field,
    so ``list_items("baselines")`` (which skips id-less files) would miss them;
    the directory is scanned directly instead.
    """
    baselines_dir = store.root / "baselines"
    if not baselines_dir.exists():
        return
    for f in sorted(baselines_dir.glob("*.yaml")):
        baseline = store._read_yaml(f)
        if not baseline:
            continue
        snapshot = baseline.get("component_snapshot")
        if not isinstance(snapshot, dict):
            continue
        changed = False
        new_snapshot: dict[str, dict] = {}
        for cid, comp in snapshot.items():
            if cid == old_id:
                cid = new_id
                changed = True
            if isinstance(comp, dict) and comp.get("parent") == old_id:
                comp["parent"] = new_id
                changed = True
            new_snapshot[cid] = comp
        if changed:
            baseline["component_snapshot"] = new_snapshot
            store.write_item("baselines", f.stem, baseline)


def rename_component(store, old_id: str, new_id: str, username: str = "") -> dict:
    """Move *old_id* to *new_id* and repoint everything that referenced it.

    Returns ``{"id", "children", "relinked"}`` — the new id, the child
    components whose parent pointer moved, and the ids of records whose
    references were rewritten.

    The inbound references are *derived* from ``link_registry.links_into``
    rather than hand-listed, so a link added to the model later is rewritten
    here without a second edit. Field shapes differ (scalars vs lists vs
    kind-discriminated comments), which the registry's ``many``/``kind_field``
    rows describe.

    Ordering matches ``rename_requirement``: write the new record before
    deleting the old one (the reverse order would leave the project with neither
    if the create failed), and only then rewrite referrers. This is ordered, not
    atomic — a failure midway through the referrer sweep leaves the record at
    the new id with some inbound references still naming the old one (dangling,
    but resolvable), never the old id deleted alongside a half-written new one.
    """
    node = store.get_component(old_id)
    if node is None:
        raise ValueError(f"Component not found: {old_id}")
    if new_id == old_id:
        return {"id": old_id, "children": [], "relinked": []}
    if store.get_component(new_id) is not None:
        raise ValueError(f"A component with id {new_id} already exists")

    before = dict(node)
    moved = dict(node)
    moved["id"] = new_id

    store.create_component(moved)
    store.delete_component(old_id)

    children: list[str] = []
    relinked: list[str] = []
    for link in links_into("components"):
        try:
            items = store.list_items(link.holder)
        except Exception:
            # A collection that does not exist in this project is not an error.
            continue
        for item in items:
            if not kind_matches(item, link):
                continue
            targets = targets_of(item, link)
            if old_id not in targets:
                continue
            new_targets = [new_id if t == old_id else t for t in targets]
            store.update_item(link.holder, item["id"],
                              {link.field: new_targets if link.many else new_targets[0]})
            if link.tree:
                if item["id"] not in children:
                    children.append(item["id"])
            elif item["id"] not in relinked:
                relinked.append(item["id"])

    _rewrite_baseline_snapshots(store, old_id, new_id)

    record_change(store, new_id, "rename", before, store.get_component(new_id), username)
    return {"id": new_id, "children": children, "relinked": relinked}


def rename_parameter(store, owner_id: str, old_name: str, new_name: str,
                     username: str = "") -> dict:
    """Rename a parameter on *owner_id*, rewriting every reference to it.

    A parameter is referenced three ways the link registry does not cover, and
    editing the name in place silently breaks all three: ``owner.old`` in
    parameter/constraint expressions, bare ``old`` inside the owner's own
    expressions, and ``[[owner.old]]`` / ``owner.old`` mentions in text. All of
    them are swept here, the same way the requirement and component renames
    sweep their own text references.

    Returns ``{"owner", "old", "new", "expressions_rewritten",
    "mentions_rewritten", "records_touched"}`` — ``expressions_rewritten`` and
    ``mentions_rewritten`` count the expression and text strings rewritten, and
    ``records_touched`` is the sorted ids of every record changed (always
    including the owner, whose parameter's ``name`` moved).
    """
    owner = store.get_requirement(owner_id)
    kind = "requirements"
    if owner is None:
        owner = store.get_component(owner_id)
        kind = "components"
    if owner is None:
        raise ValueError(f"unknown owner: {owner_id}")

    parameters = owner.get("parameters") or []
    names = [p.get("name") for p in parameters if isinstance(p, dict) and p.get("name")]
    if old_name not in names:
        raise ValueError(f"unknown parameter: {old_name}")
    if not _is_valid_parameter_name(new_name):
        raise ValueError(f"invalid parameter name: {new_name}")
    if new_name != old_name and new_name in names:
        raise ValueError(f"parameter already exists: {new_name}")

    if new_name == old_name:
        return {"owner": owner_id, "old": old_name, "new": new_name,
                "expressions_rewritten": 0, "mentions_rewritten": 0,
                "records_touched": []}

    before = dict(owner)

    new_parameters = []
    for p in parameters:
        if isinstance(p, dict) and p.get("name") == old_name:
            new_parameters.append({**p, "name": new_name})
        else:
            new_parameters.append(p)
    if kind == "requirements":
        store.update_requirement(owner_id, {"parameters": new_parameters})
    else:
        store.update_component(owner_id, {"parameters": new_parameters})

    expressions, mentions, touched = _rewrite_parameter_references(
        store, owner_id, old_name, new_name)
    touched.add(owner_id)

    after = store.get_requirement(owner_id) if kind == "requirements" \
        else store.get_component(owner_id)
    record_change(store, owner_id, "rename", before, after, username)

    return {"owner": owner_id, "old": old_name, "new": new_name,
            "expressions_rewritten": expressions,
            "mentions_rewritten": mentions,
            "records_touched": sorted(touched)}
