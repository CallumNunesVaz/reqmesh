"""Project naming standards — the one place ids are generated and judged.

A project's Naming Standards (Project Settings → Naming Standards) define an id
pattern per entity kind. This module owns the two jobs that pattern implies:

- ``next_id`` generates the next unused id for a kind, auto-incrementing the
  suffix across both numeric and alphanumeric schemes.
- ``matches_scheme`` is the (deliberately permissive) check a *create* enforces,
  generalised from the requirement-only check that used to live in
  ``services.rename``.

The defaults mirror ``DEFAULT_NAMING`` in ``ProjectSettingsPage.tsx`` — a kind
absent from ``_meta.yaml``'s ``naming`` block falls back to them, which is the
normal case for existing projects. Keeping them in one place is what stops the
generator, the enforcement, and the settings page's preview from drifting.
"""
from __future__ import annotations

import re

#: The six kinds a naming standard configures. Keyed exactly as ``_meta.yaml``
#: stores them and as the settings page labels them.
KINDS = (
    "requirements",
    "components",
    "verification",
    "risks",
    "change_requests",
    "specifications",
)

DEFAULT_NAMING: dict[str, dict] = {
    "requirements":    {"prefix_length": 4, "prefix_type": "alpha", "prefix_hint": "REQ",  "separator": "",  "suffix_length": 4, "suffix_type": "numeric"},
    "components":       {"prefix_length": 4, "prefix_type": "alpha", "prefix_hint": "COMP", "separator": "",  "suffix_length": 4, "suffix_type": "numeric"},
    "verification":     {"prefix_length": 2, "prefix_type": "alpha", "prefix_hint": "VC",   "separator": "",  "suffix_length": 4, "suffix_type": "numeric"},
    "risks":            {"prefix_length": 3, "prefix_type": "alpha", "prefix_hint": "RSK",  "separator": "",  "suffix_length": 5, "suffix_type": "numeric"},
    "change_requests":  {"prefix_length": 2, "prefix_type": "alpha", "prefix_hint": "CR",   "separator": "",  "suffix_length": 6, "suffix_type": "numeric"},
    "specifications":   {"prefix_length": 5, "prefix_type": "alpha", "prefix_hint": "SPEC", "separator": "-", "suffix_length": 4, "suffix_type": "alphanumeric"},
}

#: Kind (``_meta.yaml`` key) → store collection name. ``verification`` is the
#: odd one out: the settings page calls the kind "verification" while the store
#: writes ``verification_cases/``.
KIND_COLLECTION = {
    "requirements": "requirements",
    "components": "components",
    "verification": "verification_cases",
    "risks": "risks",
    "change_requests": "change_requests",
    "specifications": "specifications",
}


def get_naming(meta: dict, kind: str) -> dict:
    """The effective naming rule for *kind*, configured values over defaults."""
    defaults = DEFAULT_NAMING.get(kind) or DEFAULT_NAMING["requirements"]
    configured = (meta.get("naming") or {}).get(kind) or {}
    merged = dict(defaults)
    for key, value in configured.items():
        if value is not None:
            merged[key] = value
    return merged


def enforce_enabled(meta: dict) -> bool:
    """Whether create-time enforcement is on for this project.

    The switch lives at the top of the ``naming`` block, beside the per-kind
    rules, so it can be read without knowing which kind is being created.
    Absent means on — the user asked for enforcement and wants it by default.
    A project migrated from another tool sets ``enforce: false`` to keep its
    legacy ids working; that is the escape hatch, not a global kill-switch.
    """
    return bool((meta.get("naming") or {}).get("enforce", True))


def ids_for(store, kind: str) -> list[str]:
    """The existing ids of *kind*, in store order."""
    return [item.get("id", "") for item in store.list_items(KIND_COLLECTION[kind])]


def matches_scheme(new_id: str, meta: dict, kind: str) -> str | None:
    """Reason *new_id* does not fit the project's naming scheme, or None.

    Deliberately permissive: the scheme describes what generated ids look like,
    not a law every hand-written id must obey — projects migrating from another
    tool carry legacy ids that would never round-trip through a strict check.
    Only the shape that would break the suffix arithmetic is refused.
    """
    naming = get_naming(meta, kind)
    separator = naming.get("separator", "")
    suffix_type = naming.get("suffix_type", "numeric")

    if separator and separator not in new_id:
        return f"Expected '{separator}' between the prefix and the number"

    tail = new_id.split(separator)[-1] if separator else new_id
    if suffix_type == "numeric":
        if not re.search(r"(\d+)$", tail):
            return "Expected the id to end in a number"
    elif not re.search(r"[A-Za-z0-9]$", tail):
        return "Expected the id to end in a letter or number"
    return None


def _alnum_value(rest: str) -> int | None:
    """A letter suffix as a base-26 value (``'a'`` == 0), or None if not letters.

    Case-insensitive so a legacy uppercase id (``SPEC-SYS``) participates in the
    same sequence as the lowercase ids the generator produces. Anything that is
    not purely letters — digits, punctuation, a stray hyphen — is a legacy id the
    increment must ignore, not an error.
    """
    value = 0
    for ch in rest:
        lowered = ch.lower()
        if "a" <= lowered <= "z":
            value = value * 26 + (ord(lowered) - ord("a"))
        else:
            return None
    return value


def _base26_encode(value: int) -> str:
    """Encode a non-negative integer in base-26, ``'a'`` == 0, no leading zeros."""
    if value == 0:
        return "a"
    out = []
    while value > 0:
        value, r = divmod(value, 26)
        out.append(chr(ord("a") + r))
    return "".join(reversed(out))


def _suffix_for(naming: dict, next_val: int) -> str:
    suffix_len = int(naming.get("suffix_length", 4) or 4)
    if naming.get("suffix_type", "numeric") == "numeric":
        return str(next_val).zfill(suffix_len)
    # Pad with the alphabet's zero ('a'), so the first suffix is ``aaaa…`` and
    # the counter reads as the lexical sequence the settings preview shows.
    return _base26_encode(next_val).rjust(suffix_len, "a")


def _prefix_from_parent(parent_id: str, naming: dict) -> str | None:
    separator = naming.get("separator", "")
    prefix_len = int(naming.get("prefix_length", 4) or 4)
    if not parent_id:
        return None
    if separator and separator in parent_id:
        return parent_id.split(separator)[0]
    return parent_id[:prefix_len].upper()


def next_id(ids: list[str], meta: dict, kind: str, parent_id: str | None = None) -> dict:
    """The next free id for *kind*, following the project's naming scheme.

    Returns ``{"prefix", "next_id"}``. The prefix comes from *parent_id* when
    given (a child shares its parent's prefix), else from the configured hint.
    Only ids matching the configured prefix and separator participate in the
    suffix increment, so a legacy id from a migrated project neither pushes the
    counter to an absurd value nor raises.
    """
    naming = get_naming(meta, kind)
    prefix_hint = naming.get("prefix_hint", "REQ")
    separator = naming.get("separator", "")
    suffix_type = naming.get("suffix_type", "numeric")

    prefix = _prefix_from_parent(parent_id, naming) if parent_id else None
    if not prefix:
        prefix = prefix_hint.upper()

    base = prefix + separator if separator else prefix
    max_suffix = -1
    for rid in ids:
        if rid.startswith(base):
            rest = rid[len(base):]
            if suffix_type == "numeric":
                try:
                    max_suffix = max(max_suffix, int(rest))
                except ValueError:
                    pass
            else:
                value = _alnum_value(rest)
                if value is not None:
                    max_suffix = max(max_suffix, value)

    next_val = max_suffix + 1 if max_suffix >= 0 else (1 if suffix_type == "numeric" else 0)
    suffix = _suffix_for(naming, next_val)
    result = f"{base}{suffix}"

    # Never hand back an id that already exists — a legacy id that happens to
    # equal the computed slot (or a suffix gap) must not be re-suggested.
    existing = set(ids)
    while result in existing:
        next_val += 1
        result = f"{base}{_suffix_for(naming, next_val)}"

    return {"prefix": prefix, "next_id": result}
