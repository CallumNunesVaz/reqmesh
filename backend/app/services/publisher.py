from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from html import escape as esc
from typing import Any

from app.core.config import settings as global_settings
from app.services.sanitize import sanitize_html
from app.services.html_text import strip_html
from app.services.verification_links import attach as attach_verification_cases
from app.services.entity_kinds import resolve_entity_label
from app.services.mention_resolve import ParamValue, resolve_parameter_mentions
from app.services.publishers.css import CSS
from app.services.publishers.latex_helpers import (
    latex_engine_available,
    compile_latex_to_pdf,
    compile_latex_to_pdf_detailed,
    WATERMARK_APPLIED_MARKER,
    WATERMARK_OMITTED_MARKER,
    _darken,
    latex_escape,
    truncate_words,
)

logger = logging.getLogger(__name__)

# Re-export for backward compatibility — callers (updater, system_routes,
# publish_routes) import from publisher directly.
__all__ = [
    "Publisher",
    "compile_latex_to_pdf",
    "compile_latex_to_pdf_detailed",
    "latex_engine_available",
    "watermark_preamble",
]

# Aliases with the underscore prefix the Publisher class expects.
_latex_escape = latex_escape
_truncate_words = truncate_words


def watermark_preamble(status_txt: str) -> list[str]:
    """LaTeX that stamps a DRAFT watermark on every page, guarded like ``tikz``.

    ``draftwatermark`` is not in a minimal TeX install — tectonic fetches it
    from its bundle on demand, so it is absent from a warmed cache until fetched
    and unreachable in ``offline_mode``. Loading it unconditionally therefore
    fails a draft report where a non-draft one builds fine. The load is guarded
    by ``\\IfFileExists`` and the settings calls by ``\\ifdefined``, so a missing
    or incompatible package costs the watermark and nothing else.

    ``\\typeout`` markers record which branch ran, so the compile step can report
    that a draft lost its DRAFT mark rather than ship an unmarked draft silently.
    """
    return [
        r"\IfFileExists{draftwatermark.sty}{\usepackage{draftwatermark}\newcommand{\rmhaswatermark}{1}}{}",
        r"\ifdefined\rmhaswatermark",
        f"  \\SetWatermarkText{{{status_txt or 'DRAFT'}}}",
        r"  \SetWatermarkScale{0.5}",
        r"  \SetWatermarkColor[gray]{0.92}",
        r"  \typeout{" + WATERMARK_APPLIED_MARKER + "}",
        r"\else",
        r"  \typeout{" + WATERMARK_OMITTED_MARKER + "}",
        r"\fi",
    ]


class Publisher:
    # Default (full) report. "changelog" is deliberately absent — it is an
    # opt-in, date-bounded section, so an unqualified export never carries one.
    _all_latex_sections = [
        "cover", "summary", "requirements", "components", "verification", "risks",
        "traceability", "specifications", "baselines", "changes",
        "quality", "gaps", "decisions", "glossary", "conflicts",
        "parameters", "verification_details", "system_states",
    ]

    def __init__(self, store, subsystems: list[str] | None = None,
                 components: list[str] | None = None,
                 baselines: list[str] | None = None):
        """Build a publisher over a project store, optionally scoped.

        Three scope filters narrow which requirements are exported:

        * ``subsystems`` — requirement-tree roots (each is expanded downward);
        * ``components`` — component-tree roots, resolved to the requirements
          they (and their descendants) satisfy;
        * ``baselines`` — baseline *names*, matched against the names held by
          ``requirement.baselines`` (a baseline is a label, not a record).

        Each filter is either ``None`` (omitted — everything passes) or a list,
        which may be empty (the filter passes nothing). Omitted and empty are
        deliberately different: a caller that says "no components" (``[]``) must
        get zero requirements, not "forget the filter and give me everything".

        The filters combine by **intersection**: a requirement is exported only
        if it passes every filter that is present. ``subsystems ∩ components``
        already behaved that way; ``baselines`` joins them on the same rule, so
        e.g. ``components=["YOKE"]`` + ``baselines=["SRR"]`` yields exactly the
        requirements in both, never the union.
        """
        self.store = store
        self.project_id = store.root.name
        self.meta = store.read_meta()
        all_reqs = store.list_requirements()
        self.vcs = store.list_verification_cases()
        attach_verification_cases(store, all_reqs, self.vcs)
        self.specs = store.list_specifications()
        self.components = store.list_components()
        self.traces = store.read_traces()
        self.now = datetime.now(timezone.utc)
        self.now_str = self.now.strftime("%Y-%m-%d %H:%M UTC")
        self._toc: list[tuple[int, str, str]] = []  # list of (level, label, anchor) for TOC

        # Record every entity id in the project before any scope filter, so
        # _unresolved_suffix can distinguish "filtered out" from "not in the
        # project at all".
        self._project_ids: set[str] = set()
        for r in all_reqs:
            self._project_ids.add(r["id"])
        for v in self.vcs:
            self._project_ids.add(v["id"])
        for c in self.components:
            self._project_ids.add(c["id"])
        for s in self.specs:
            self._project_ids.add(s["id"])

        # ── Subsystem scope: expand each requirement-tree root downward ──────
        sub_ids: set[str] | None = None
        if subsystems is not None:
            sub_ids = set()
            def collect(root_id):
                sub_ids.add(root_id)
                for r in all_reqs:
                    if r.get("parent") == root_id:
                        collect(r["id"])
            for sid in subsystems:
                collect(sid)

        # ── Component scope: expand the component tree, collect satisfied reqs ──
        comp_req_ids: set[str] | None = None
        if components is not None:
            comp_ids_expanded: set[str] = set()
            def _collect_component(root_id):
                # Guard on the visited set, not just on arrival: component YAML
                # is hand-editable and arrives by git pull, so a self-parent or
                # a parent cycle is reachable without the API ever allowing it,
                # and would otherwise recurse until the stack gives out.
                if root_id in comp_ids_expanded:
                    return
                comp_ids_expanded.add(root_id)
                for c in self.components:
                    if c.get("parent") == root_id:
                        _collect_component(c["id"])
            for cid in components:
                _collect_component(cid)
            comp_req_ids = set()
            for c in self.components:
                if c["id"] in comp_ids_expanded:
                    for rid in c.get("satisfies", []):
                        comp_req_ids.add(rid)

        # ── Baseline scope: match the baseline *names* requirements carry ─────
        base_req_ids: set[str] | None = None
        if baselines is not None:
            wanted = set(baselines)
            base_req_ids = {r["id"] for r in all_reqs
                            if wanted & set(r.get("baselines", []))}

        # The three filters intersect — see the __init__ docstring.
        present = [s for s in (sub_ids, comp_req_ids, base_req_ids) if s is not None]
        if present:
            ids = set.intersection(*present)
            self.reqs = [r for r in all_reqs if r["id"] in ids]
            self.traces = {
                "links": [l for l in self.traces.get("links", [])
                          if l.get("source") in ids and l.get("target") in ids]
            }
            self.vcs = [v for v in self.vcs if any(
                rid in ids for rid in v.get("verified_requirements", [])
            )]
        else:
            self.reqs = all_reqs

        self._vc_by_id = {v["id"]: v for v in self.vcs}
        self._comp_by_id = {c["id"]: c for c in self.components}
        self._spec_by_id = {s["id"]: s for s in self.specs}
        self._all_req_ids = {r["id"]: r for r in self.reqs}
        # Built lazily on first mention resolution (see _parameter_lookup).
        self._parameter_lookup_cache = None

    # ── Helpers ─────────────────────────────────────────────────────────────────

    def _badge(self, status: str) -> str:
        return f'<span class="badge badge-{esc(status, quote=True)}">{esc(status)}</span>'

    def _unresolved_suffix(self, entity_id: str) -> str:
        """'' when the id is in this document, else the reason it is not."""
        if (entity_id in self._all_req_ids or entity_id in self._vc_by_id or
                entity_id in self._comp_by_id or entity_id in self._spec_by_id):
            return ""
        if entity_id in self._project_ids:
            return " (not in this document)"
        return " (unresolved reference)"

    def _parameter_lookup(self):
        """The ``lookup`` callable passed to ``resolve_parameter_mentions``.

        Built once and cached. Resolves a reference against every parameter in
        the project — requirements and components alike — with the same
        evaluator the ``/evaluation`` endpoint uses. A derived parameter's
        computed value is rounded to 6 dp to match what the API surfaces; a
        literal parameter resolves to its stored value. Returns ``None`` for a
        reference that cannot be resolved (unknown id, unknown name, no value).
        """
        if self._parameter_lookup_cache is not None:
            return self._parameter_lookup_cache

        from app.services.evaluation import EvalError, Evaluator, UnknownValue

        try:
            definitions = self.store.list_items("definitions")
        except Exception:
            definitions = []

        evaluator = Evaluator(
            self.store.list_requirements(),
            self.store.list_components(),
            definitions=definitions,
        )

        def lookup(entity_id: str, name: str) -> ParamValue | None:
            ref = f"{entity_id}.{name}"
            param = evaluator.params.get(ref)
            if param is None:
                return None
            try:
                value = evaluator.resolve(ref)
            except (UnknownValue, EvalError):
                return None
            if param.get("expr") or param.get("calc_def"):
                value = round(value, 6)
            return ParamValue(value=value, unit=param.get("unit", "") or "")

        self._parameter_lookup_cache = lookup
        return lookup

    def _resolve(self, text: str) -> str:
        """Resolve parameter mentions in *text*, leaving everything else alone."""
        if not text or "[[" not in text:
            return text
        return resolve_parameter_mentions(text, self._parameter_lookup())

    def _link(self, entity_id: str, label: str | None = None) -> str:
        """Hyperlink to a requirement, VC, component, spec, or risk by ID."""
        display = label or entity_id
        suffix = self._unresolved_suffix(entity_id)
        if suffix:
            return f'<span class="entity-missing" style="opacity:.7">{esc(display)}{esc(suffix)}</span>'
        if entity_id in self._all_req_ids:
            return f'<a class="entity-link" href="#req-{esc(entity_id, quote=True)}">{esc(display)}</a>'
        if entity_id in self._vc_by_id:
            return f'<a class="entity-link" href="#vc-{esc(entity_id, quote=True)}">{esc(display)}</a>'
        if entity_id in self._comp_by_id:
            return f'<a class="entity-link" href="#comp-{esc(entity_id, quote=True)}">{esc(display)}</a>'
        if entity_id in self._spec_by_id:
            return f'<a class="entity-link" href="#spec-{esc(entity_id, quote=True)}">{esc(display)}</a>'
        return esc(display)

    def _latex_link(self, entity_id: str, label: str | None = None) -> str:
        """LaTeX hyperlink to a requirement, VC, component, spec, or risk anchor."""
        display = label or entity_id
        suffix = self._unresolved_suffix(entity_id)
        if suffix:
            return f"{_latex_escape(display)}{_latex_escape(suffix)}"
        if entity_id in self._all_req_ids:
            prefix = "req"
        elif entity_id in self._vc_by_id:
            prefix = "vc"
        elif entity_id in self._comp_by_id:
            prefix = "comp"
        elif entity_id in self._spec_by_id:
            prefix = "spec"
        else:
            return _latex_escape(display)
        return f"\\hyperlink{{{prefix}-{_latex_escape(entity_id)}}}{{{_latex_escape(display)}}}"

    def _anchor(self, prefix: str, entity_id: str) -> str:
        return f'id="{prefix}-{esc(entity_id, quote=True)}"'

    # ── Changelog (optional date-bounded diff report) ────────────────────────────

    def _entity_label(self, item_id: str) -> tuple[str, str]:
        """(kind, name) for an audited item id — history is keyed by id alone.

        Delegates to the shared ``resolve_entity_label`` so the activity
        endpoint and every future caller agree on the same precedence order.
        """
        return resolve_entity_label(self.store, item_id)

    @staticmethod
    def _fmt_value(v) -> str:
        """One-line rendering of a before/after value for the changelog."""
        if v is None or v == "":
            return "—"
        if isinstance(v, bool):
            return "yes" if v else "no"
        if isinstance(v, (list, tuple)):
            if not v:
                return "—"
            parts = [Publisher._fmt_value(x) for x in v]
            return ", ".join(parts)
        if isinstance(v, dict):
            return ", ".join(f"{k}={Publisher._fmt_value(x)}" for k, x in v.items())
        text = re.sub(r"<[^>]+>", "", str(v))          # descriptions are HTML
        text = " ".join(text.split())
        return text

    def changelog(self, since: str = "", until: str = "") -> dict:
        """Audit entries in [since, until], newest first, with item context.

        Returns ``{entries, counts, items, since, until}`` — shared by the
        LaTeX and HTML renderers so both read identically.
        """
        raw = self.store.list_all_history(since, until)
        # Only report on items inside the current subsystem filter, so a
        # filtered report's changelog matches the rest of the document.
        scoped = self._all_req_ids
        entries = []
        counts: dict[str, int] = {}
        for e in raw:
            item_id = e.get("item_id", "")
            # Requirement ids outside the filter are dropped; non-requirement
            # items (components, risks, …) are never subsystem-scoped.
            if scoped and item_id not in scoped and self._entity_label(item_id)[0] == "Requirement":
                continue
            kind, name = self._entity_label(item_id)
            action = str(e.get("action", "update"))
            counts[action] = counts.get(action, 0) + 1
            raw_changes = e.get("changes") or {}
            if not name:
                # A deleted item no longer resolves to a record — recover its
                # name from the audit entry, which is precisely the case a
                # changelog reader needs spelled out.
                for key in ("name", "title"):
                    ba = raw_changes.get(key)
                    if isinstance(ba, dict):
                        name = str(ba.get("before") or ba.get("after") or "")
                        if name:
                            break
            # A create diffs nothing→everything and a delete everything→nothing,
            # so the field list is the whole record with every value pointing at
            # "—". The action badge already says it; listing 20 empty
            # transitions only buries the real edits.
            changes = {} if action in ("create", "delete") else raw_changes
            fields = []
            for field, ba in sorted(changes.items()):
                if not isinstance(ba, dict):
                    continue
                fields.append({
                    "field": field.replace("_", " "),
                    "before": self._fmt_value(ba.get("before")),
                    "after": self._fmt_value(ba.get("after")),
                })
            entries.append({
                "timestamp": str(e.get("timestamp", "")),
                "date": str(e.get("timestamp", ""))[:10],
                "time": str(e.get("timestamp", ""))[11:16],
                "item_id": item_id, "kind": kind, "name": name,
                "action": action, "user": str(e.get("user", "")) or "—",
                "fields": fields,
            })
        entries.reverse()  # newest first
        return {
            "entries": entries,
            "counts": counts,
            "items": len({e["item_id"] for e in entries}),
            "since": since,
            "until": until,
        }

    # ── Report header config ────────────────────────────────────────────────────

    def _header_config(self):
        logo_url = getattr(global_settings, "report_logo_url", "")
        company = esc(getattr(global_settings, "report_company_name", "") or global_settings.instance_name)
        dept = esc(getattr(global_settings, "report_department", "") or "")
        title = esc(getattr(global_settings, "report_document_title", "") or "Requirements Specification Report")
        show_git = getattr(global_settings, "report_show_git_commit", False)

        # Build the page header string for @top-center
        header_str = f"{company} — {title}" if company else title
        if dept:
            header_str += f" · {dept}"

        # Footer string for @bottom-left
        footer = self.now_str
        git_sha = ""
        try:
            import subprocess
            git_sha = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(self.store.root), stderr=subprocess.DEVNULL).decode().strip()
        except Exception:
            git_sha = ""
        if show_git and git_sha:
            footer = f"rev {git_sha} · {footer}"

        # ── Formal document-control fields (SRS/SyRS conventions) ────────────
        doc_number = getattr(global_settings, "report_document_number", "") or ""
        classification = getattr(global_settings, "report_classification", "") or ""
        status = getattr(global_settings, "report_status", "") or ""
        prepared_by = getattr(global_settings, "report_prepared_by", "") or ""
        reviewed_by = getattr(global_settings, "report_reviewed_by", "") or ""
        approved_by = getattr(global_settings, "report_approved_by", "") or ""
        distribution = list(getattr(global_settings, "report_distribution", []) or [])

        # Revision: explicit setting → latest baseline → git sha → default.
        revision = getattr(global_settings, "report_revision", "") or ""
        if not revision:
            try:
                baselines = self.store.list_items("baselines")
            except Exception:
                baselines = []
            if baselines:
                latest = max(baselines, key=lambda b: b.get("frozen_at", ""))
                revision = latest.get("name", "")
        if not revision and git_sha:
            revision = f"git-{git_sha}"
        if not revision:
            revision = "1.0"

        is_draft = status.strip().lower() in {
            "draft", "working", "preliminary", "in review", "in_review", "wip"}

        raw_color = getattr(global_settings, "report_color", "") or "#2094f3"
        accent_color = raw_color.strip()
        if not re.match(r"^#[0-9a-fA-F]{6}$", accent_color):
            accent_color = "#2094f3"
        accent_dark = _darken(accent_color, 0.65)

        return {
            "logo_url": logo_url,
            "company": company,
            "dept": dept,
            "title": title,
            "header_str": header_str,
            "footer_str": footer,
            "doc_number": doc_number,
            "revision": revision,
            "classification": classification,
            "status": status,
            "prepared_by": prepared_by,
            "reviewed_by": reviewed_by,
            "approved_by": approved_by,
            "distribution": distribution,
            "is_draft": is_draft,
            "git_sha": git_sha,
            "accent_color": accent_color,
            "accent_dark": accent_dark,
        }

    # ── Section builders ────────────────────────────────────────────────────────

    def _toc_html(self) -> str:
        html = '<div class="toc"><h1>Table of Contents</h1><ul>'
        for level, label, anchor in self._toc:
            cls = f"toc-h{level}"
            html += f'<li class="{cls}"><a href="#{esc(anchor, quote=True)}">{esc(label)}</a></li>'
        html += '</ul></div>'
        return html

    def _add_toc(self, level: int, label: str, anchor: str):
        self._toc.append((level, label, anchor))

    def _cover(self, hdr: dict) -> str:
        logo_html = ""
        logo = hdr["logo_url"]
        if logo and logo.startswith("data:"):
            logo_html = f'<img class="logo" src="{esc(logo)}" alt="Logo" />'
        # A non-data: URL is dropped: fetching it server-side during render is an
        # SSRF / local-file vector (FAB-SEC FAB-4). The Settings UI produces a
        # data: URI from an uploaded PNG.

        company_line = f'<div class="company">{hdr["company"]}</div>' if hdr["company"] else ""
        dept_line = f'<div class="dept">{hdr["dept"]}</div>' if hdr["dept"] else ""

        return f"""
        <div class="cover">
          {logo_html}
          <h1>{esc(self.meta.get("name", self.project_id))}</h1>
          <h2>{hdr["title"]}</h2>
          {company_line}
          {dept_line}
          <div class="meta">
            <span>Generated: {self.now_str}</span>
            <span>Project: {self.project_id}</span>
            <span>Requirements: {len(self.reqs)}</span>
            <span>Verification Cases: {len(self.vcs)}</span>
            <span>Baselines: {len(set(b for r in self.reqs for b in r.get('baselines', [])))}</span>
          </div>
        </div>"""

    def _summary_section(self) -> str:
        """Project overview metrics section — mirrors ProjectOverview page."""
        total = len(self.reqs)
        if total == 0:
            return ""

        status_dist: dict[str, int] = {}
        priority_dist: dict[str, int] = {}
        type_dist: dict[str, int] = {}
        vc_count = len(self.vcs)
        vc_passed = sum(1 for v in self.vcs if v.get("status") == "passed")
        specs_count = len(self.specs)
        comps_count = len(self.components)
        risks = self.store.list_items("risks")
        risk_count = len(risks)

        for r in self.reqs:
            s = r.get("status", "proposed")
            status_dist[s] = status_dist.get(s, 0) + 1
            p = r.get("priority", "medium")
            priority_dist[p] = priority_dist.get(p, 0) + 1
            t = r.get("type", "functional")
            type_dist[t] = type_dist.get(t, 0) + 1

        def bar(labels: dict[str, int], colors: dict[str, str], title: str) -> str:
            html = f'<div style="margin-bottom:14px;"><strong style="font-size:10pt;">{esc(title)}</strong>'
            for label, count in sorted(labels.items(), key=lambda x: -x[1]):
                pct = round(count / total * 100) if total else 0
                color = colors.get(label, "#94a3b8")
                html += f'<div class="chart-bar"><div class="label">{esc(label.replace("_"," ").title())}</div><div class="bar-bg"><div class="bar-fill" style="width:{pct}%;background:{color}"></div></div><span class="pct">{pct}%</span></div>'
            html += '</div>'
            return html

        status_colors = {"proposed": "#3b82f6", "approved": "#22c55e", "implemented": "#a855f7",
                         "verified": "#10b981", "rejected": "#ef4444", "deprecated": "#94a3b8"}
        priority_colors = {"low": "#94a3b8", "medium": "#3b82f6", "high": "#f59e0b", "critical": "#ef4444"}
        # Non-functional variants all keep the cyan family; everything else indigo.
        type_colors = {t: ("#009d96" if t.startswith("non_functional") else "#6366f1") for t in type_dist}

        html = '<h1 id="sec-summary">Project Summary</h1>'
        self._add_toc(1, "Project Summary", "sec-summary")

        html += '<div class="summary-grid">'
        cards = [
            (str(total), "Requirements"),
            (str(vc_count), "Verification Cases"),
            (str(specs_count), "Specifications"),
            (str(comps_count), "Components"),
            (str(risk_count), "Risks"),
            (f"{vc_passed}/{vc_count}" if vc_count else "—", "VC Passed"),
        ]
        for num, label in cards:
            html += f'<div class="summary-card"><div class="num">{esc(num)}</div><div class="label">{esc(label)}</div></div>'
        html += '</div>'

        html += bar(status_dist, status_colors, "Status Distribution")
        html += bar(priority_dist, priority_colors, "Priority Distribution")
        html += bar(type_dist, type_colors, "Type Distribution")

        return html

    def _build_hierarchy(self, parent=None, depth=0):
        html = ""
        for r in self.reqs:
            if r.get("parent") == parent:
                indent = depth * 20
                rid = r["id"]
                # The only field emitted as HTML rather than escaped, so it is
                # the one that must be sanitised. Applied here as well as on
                # write, because descriptions stored before sanitisation
                # existed are still in the YAML.
                desc = sanitize_html(self._resolve(r.get("description", ""))).replace("<p>", "").replace("</p>", "")
                relations = r.get("relations", [])
                attrs = r.get("attributes", [])

                rel_html = ""
                for rel in relations:
                    rel_html += f'<span class="rel-item"><span class="type">{esc(rel["type"])}</span> → {self._link(rel["target"])}</span>'

                attr_html = ""
                for a in attrs:
                    attr_html += f'<span style="margin-right:8px;font-size:9pt;"><strong>{esc(a["key"])}:</strong> {esc(a["value"])}</span>'

                rationale = sanitize_html(self._resolve(r.get("rationale", ""))).replace("<p>", "").replace("</p>", "")
                source = esc(self._resolve(r.get("source", "")))
                allocated = esc(self._resolve(r.get("allocated_to", "")))
                baseline = esc(", ".join(r.get("baselines", [])))
                subject = r.get("subject")
                subject_link = self._link(subject) if subject else ""
                vc_links = ", ".join(self._link(vc_id) for vc_id in r.get("verification_cases", []))
                cascade_from = r.get("cascade_from")
                cascade_html = f'<div class="field"><strong>Cascaded from:</strong> {self._link(cascade_from)}</div>' if cascade_from else ""

                html += f"""
                <div {self._anchor('req', rid)} style="margin-left:{indent}px; margin-bottom:14px; padding:10px 14px; border-left:3px solid #e2e8f0; border-radius:0 6px 6px 0; background:#fff;">
                  <div style="font-weight:700; font-size:12pt; margin-bottom:2px;">
                    <span style="font-family:monospace; color:#64748b; font-size:10pt;">{esc(rid)}</span>
                    <span style="margin-left:6px;">{esc(r.get('name', 'Untitled'))}</span>
                    {self._badge(r.get('status','proposed'))}
                    <span class="badge badge-{esc(r.get('priority','medium'), quote=True)}">{esc(r.get('priority','medium'))}</span>
                    {f'<span class="badge" style="background:#e0e7ff;color:#4338ca;">{esc(r["type"].replace("_"," "))}</span>' if r.get('type') else ''}
                  </div>
                  {f'<div class="desc">{desc}</div>' if desc else ''}
                  {f'<div class="field"><strong>Rationale:</strong> {rationale}</div>' if rationale else ''}
                  {f'<div class="field"><strong>Source:</strong> {source}</div>' if source else ''}
                  {f'<div class="field"><strong>Allocated to:</strong> {allocated}</div>' if allocated else ''}
                  {f'<div class="field"><strong>Subject:</strong> {subject_link}</div>' if subject else ''}
                  {f'<div class="field"><strong>Baseline:</strong> {baseline}</div>' if baseline else ''}
                  {f'<div class="field"><strong>Verification Cases:</strong> {vc_links}</div>' if vc_links else ''}
                  {cascade_html}
                  {attr_html and f'<div class="field">{attr_html}</div>'}
                  {rel_html and f'<div class="relations">{rel_html}</div>'}
                </div>"""
                html += self._build_hierarchy(rid, depth + 1)
        return html

    def _trace_matrix(self):
        vc_ids = [v["id"] for v in self.vcs]
        links_map = {}
        for t in self.traces.get("links", []):
            links_map.setdefault(t["source"], {})[t["target"]] = t["type"]
        for r in self.reqs:
            for rel in r.get("relations", []):
                links_map.setdefault(r["id"], {})[rel["target"]] = rel["type"]

        html = '<table class="matrix"><thead><tr><th></th>'
        for vc_id in vc_ids:
            html += f'<th>{esc(vc_id)}</th>'
        html += '</tr></thead><tbody>'
        for req in self.reqs:
            html += f'<tr><td style="font-weight:600;font-family:monospace;">{esc(req["id"])}</td>'
            for vc_id in vc_ids:
                link = links_map.get(req["id"], {}).get(vc_id)
                if link:
                    html += f'<td class="link"><a href="#vc-{esc(vc_id, quote=True)}">{esc(link)}</a></td>'
                else:
                    html += '<td class="no-link">-</td>'
            html += '</tr>'
        html += '</tbody></table>'
        return html

    def _vc_table(self):
        html = '<table><thead><tr><th>ID</th><th>Name</th><th>Method</th><th>Status</th><th>Verified Reqs</th></tr></thead><tbody>'
        for vc in self.vcs:
            linked = ", ".join(self._link(rid) for rid in vc.get("verified_requirements", []))
            html += f"""<tr {self._anchor('vc', vc['id'])}>
              <td style="font-family:monospace;">{esc(vc['id'])}</td>
              <td>{esc(vc.get('name',''))}</td>
              <td>{esc(vc.get('method',''))}</td>
              <td>{self._badge(vc.get('status','pending'))}</td>
              <td>{linked or '—'}</td>
            </tr>"""
        html += '</tbody></table>'
        return html

    def _component_section(self):
        if not self.components:
            return ""
        html = '<h1 id="sec-components">Components</h1>'
        self._add_toc(1, "Components", "sec-components")
        html += '<table><thead><tr><th>ID</th><th>Name</th><th>Type</th><th>Part Number</th><th>Satisfies</th></tr></thead><tbody>'
        for c in self.components:
            sat = ", ".join(self._link(rid) for rid in c.get("satisfies", []))
            html += f"""<tr {self._anchor('comp', c['id'])}>
              <td style="font-family:monospace;">{esc(c['id'])}</td>
              <td>{esc(c.get('name',''))}</td>
              <td><span class="badge">{esc(c.get('type','part'))}</span></td>
              <td style="font-family:monospace;">{esc(c.get('part_number',''))}</td>
              <td>{sat or '—'}</td>
            </tr>"""
        html += '</tbody></table>'
        return html

    def _specs_section(self):
        if not self.specs:
            return ""
        html = '<h1 id="sec-specifications">Specifications</h1>'
        self._add_toc(1, "Specifications", "sec-specifications")
        for spec in self.specs:
            html += f"""<h2 {self._anchor('spec', spec['id'])}>{esc(spec['id'])} — {esc(spec.get('name', ''))}</h2>
            <p class="desc">{esc(self._resolve(spec.get('description', ''))[:300])}</p>
            <div class="field"><strong>Requirements:</strong> {", ".join(self._link(rid) for rid in spec.get('requirements', [])) or '—'}</div>"""
        return html

    def _quality_chart(self):
        total = len(self.reqs)
        quality = {"description": 0, "rationale": 0, "source": 0, "allocation": 0, "traceability": 0}
        for r in self.reqs:
            if r.get("description", "").strip(): quality["description"] += 1
            if r.get("rationale", "").strip(): quality["rationale"] += 1
            if r.get("source", "").strip(): quality["source"] += 1
            if r.get("allocated_to", "").strip(): quality["allocation"] += 1
            if r.get("relations"): quality["traceability"] += 1
        qpct = {k: round(v/total*100) if total else 0 for k, v in quality.items()}

        html = '<div>'
        for key, pct in qpct.items():
            color = "#16a34a" if pct >= 80 else "#d97706" if pct >= 50 else "#dc2626"
            html += f'<div class="chart-bar"><div class="label">{key.replace("_"," ")}</div><div class="bar-bg"><div class="bar-fill" style="width:{pct}%;background:{color}"></div></div><span class="pct">{pct}%</span></div>'
        html += '</div>'
        return html

    def _gaps_section(self, gaps: list):
        html = ""
        for g in gaps:
            issues = ", ".join(i.replace("_", " ") for i in g["issues"])
            html += f'<div class="gap-warn">{self._link(g["id"])} — {esc(g["name"])}: <span class="issues">{esc(issues)}</span></div>'
        return html

    def _risk_table(self, risks: list | None):
        if not risks:
            return ""
        html = ('<table><thead><tr><th>ID</th><th>Title</th><th>Failure Mode</th>'
                '<th>Effect</th><th>Cause</th><th>Severity</th><th>Probability</th>'
                '<th>Status</th></tr></thead><tbody>')

        def _rich(value: str) -> str:
            # The FMECA fields are stored as rich text (the UI edits them with
            # the same editor as descriptions), so sanitise and drop the outer
            # paragraph wrapper the way the requirement hierarchy does.
            return sanitize_html(self._resolve(value or "")).replace("<p>", "").replace("</p>", "")

        for r in risks:
            sev = esc(r.get("severity", "medium"), quote=True)
            failure_mode = _rich(r.get("failure_mode", ""))
            effect = _rich(r.get("effect", ""))
            cause = _rich(r.get("cause", ""))
            html += f"""<tr class="risk-sev-{sev}">
              <td style="font-family:monospace;">{esc(r['id'])}</td>
              <td>{esc(r.get('title',''))}</td>
              <td>{failure_mode or '—'}</td>
              <td>{effect or '—'}</td>
              <td>{cause or '—'}</td>
              <td><span class="badge badge-{sev}">{sev}</span></td>
              <td>{esc(r.get('probability',''))}</td>
              <td>{self._badge(r.get('status','open'))}</td>
            </tr>"""
        html += '</tbody></table>'
        return html

    def _conflicts_section(self, conflicts: list):
        html = ""
        for c in conflicts:
            if c["type"] == "duplicate_name":
                html += f'<div class="conflict-item"><strong>Duplicate name:</strong> "{esc(c["name"])}" — IDs: {esc(", ".join(c.get("ids",[])))}</div>'
            else:
                html += f'<div class="conflict-item"><strong>Conflict:</strong> {esc(c.get("a",""))} ↔ {esc(c.get("b",""))}</div>'
        return html

    def _changes_section(self):
        crs = self.store.list_items("change_requests")
        if not crs:
            return ""
        html = '<h1 id="sec-changes">Change Requests</h1>'
        self._add_toc(1, "Change Requests", "sec-changes")
        html += '<table><thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Affected Requirements</th></tr></thead><tbody>'
        for cr in crs:
            affected = ", ".join(self._link(rid) for rid in cr.get("affected_requirements", []))
            html += f"""<tr>
              <td style="font-family:monospace;">{esc(cr['id'])}</td>
              <td>{esc(cr.get('title',''))}</td>
              <td>{self._badge(cr.get('status','open'))}</td>
              <td>{affected or '—'}</td>
            </tr>"""
        html += '</tbody></table>'
        return html

    # ── Main build ──────────────────────────────────────────────────────────────

    def _changelog_html(self, since: str, until: str) -> str:
        log = self.changelog(since, until)
        entries = log["entries"]
        span = esc(f"{since or 'project start'} to {until or self.now.strftime('%Y-%m-%d')}")
        html = ('<h1 id="sec-changelog">Changelog</h1>'
                f'<p style="color:#64748b;font-size:10pt;">Every recorded change between '
                f'<strong>{span}</strong>, newest first.</p>')
        self._add_toc(1, "Changelog", "sec-changelog")
        if not entries:
            return html + '<p>No changes were recorded in this period.</p>'
        acts = log["counts"]
        html += f"""<div class="summary-grid">
          <div class="summary-card"><div class="num">{len(entries)}</div><div class="label">Changes</div></div>
          <div class="summary-card"><div class="num">{log['items']}</div><div class="label">Items</div></div>
          <div class="summary-card"><div class="num">{acts.get('create', 0)}</div><div class="label">Created</div></div>
        </div>"""
        html += ('<table><thead><tr><th>Date</th><th>Item</th><th>Name</th>'
                 '<th>Action</th><th>User</th></tr></thead><tbody>')
        for e in entries:
            detail = ""
            if e["fields"]:
                rows = "".join(
                    f'<div class="field"><strong>{esc(f["field"])}</strong> '
                    f'<span style="color:#dc2626;">{esc(_truncate_words(f["before"], 90))}</span> → '
                    f'<span style="color:#16a34a;">{esc(_truncate_words(f["after"], 90))}</span></div>'
                    for f in e["fields"][:12])
                extra = (f'<div class="field"><em>+{len(e["fields"]) - 12} more fields</em></div>'
                         if len(e["fields"]) > 12 else "")
                detail = (f'<tr><td colspan="5" style="padding-top:0;">{rows}{extra}</td></tr>')
            html += f"""<tr>
              <td style="white-space:nowrap;">{esc(e['date'])} {esc(e['time'])}</td>
              <td>{self._link(e['item_id'])}</td>
              <td>{esc(_truncate_words(e['name'] or e['kind'], 60))}</td>
              <td>{self._badge(e['action'])}</td>
              <td>{esc(e['user'])}</td>
            </tr>{detail}"""
        return html + '</tbody></table>'

    def build_html(self, sections: list | None = None,
                   changelog_from: str = "", changelog_to: str = "") -> str:
        if sections is None:
            sections = ["cover", "summary", "requirements", "components", "specifications",
                        "verification", "traceability", "quality", "gaps", "risks", "changes", "conflicts"]

        hdr = self._header_config()
        project_name = esc(self.meta.get("name", self.project_id))
        # Inject the selected accent colour into the HTML CSS. The stylesheet
        # uses two deliberately different shades — #2563eb for the accent and
        # #1d4ed8 for its darker companion — so they map to accent and
        # accent_dark respectively. Collapsing both onto one value flattened
        # every hover and heading-rule contrast the design relies on.
        accent_hex = hdr.get("accent_color", "#2094f3")
        accent_dark_hex = hdr.get("accent_dark", _darken(accent_hex, 0.65))
        css_with_accent = CSS.replace("#2563eb", accent_hex).replace("#1d4ed8", accent_dark_hex)
        footer_css = f"""
  @bottom-left {{
    content: "{esc(hdr['footer_str'], quote=True)}";
    font-family: 'Segoe UI', system-ui, sans-serif;
    font-size: 7pt;
    color: #cbd5e1;
  }}
"""
        header_css = ""
        if hdr["header_str"]:
            header_css = f"""
  @top-center {{
    content: "{esc(hdr['header_str'], quote=True)}";
    font-family: 'Segoe UI', system-ui, sans-serif;
    font-size: 8pt;
    color: #94a3b8;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 4px;
  }}
"""

        html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>{project_name} — {hdr["title"]}</title>
<style>{css_with_accent}
@page {{{header_css}{footer_css}}}
</style></head><body>
"""

        if "cover" in sections:
            html += self._cover(hdr)

        if "summary" in sections:
            html += self._summary_section()

        html += self._toc_html()

        if "changelog" in sections:
            html += self._changelog_html(changelog_from, changelog_to)

        if "requirements" in sections:
            html += f"""<h1 id="sec-requirements">Requirements Hierarchy</h1>
            <p style="color:#64748b;font-size:10pt;margin-bottom:16px;">{len(self.reqs)} requirements across {len(set(r.get('parent') or 'root' for r in self.reqs))} groups</p>
            {self._build_hierarchy()}"""
            self._add_toc(1, "Requirements Hierarchy", "sec-requirements")

        if "components" in sections:
            html += self._component_section()

        if "specifications" in sections:
            html += self._specs_section()

        if "verification" in sections:
            html += '<h1 id="sec-verification">Verification Cases</h1>'
            self._add_toc(1, "Verification Cases", "sec-verification")
            html += self._vc_table()

        if "traceability" in sections:
            html += '<h1 id="sec-traces">Traceability Matrix</h1>'
            self._add_toc(1, "Traceability Matrix", "sec-traces")
            html += self._trace_matrix()

        if "quality" in sections:
            html += '<h1 id="sec-quality">Quality Metrics</h1>'
            self._add_toc(1, "Quality Metrics", "sec-quality")
            html += self._quality_chart()

        if "gaps" in sections:
            gaps = []
            for r in self.reqs:
                issues = []
                if not r.get("description", "").strip(): issues.append("no_description")
                if not r.get("rationale", "").strip(): issues.append("no_rationale")
                if not r.get("source", "").strip(): issues.append("no_source")
                if not r.get("relations"): issues.append("unlinked")
                if issues:
                    gaps.append({"id": r["id"], "name": r.get("name", ""), "issues": issues})
            if gaps:
                html += '<h1 id="sec-gaps">Gap Analysis</h1>'
                self._add_toc(1, "Gap Analysis", "sec-gaps")
                html += f'<p style="color:#64748b;font-size:10pt;">{len(gaps)} requirements with issues</p>'
                html += self._gaps_section(gaps)

        if "risks" in sections:
            risks = self.store.list_items("risks")
            if risks:
                html += '<h1 id="sec-risks">Risk Register</h1>'
                self._add_toc(1, "Risk Register", "sec-risks")
                html += self._risk_table(risks)

        if "changes" in sections:
            html += self._changes_section()

        if "conflicts" in sections:
            conflicts = []
            dupes: dict[str, list[str]] = {}
            for r in self.reqs:
                name = r.get("name", "").strip().lower()
                if name:
                    dupes.setdefault(name, []).append(r["id"])
            for name, ids in dupes.items():
                if len(ids) > 1:
                    conflicts.append({"type": "duplicate_name", "name": name, "ids": ids})
            for r in self.reqs:
                for rel in r.get("relations", []):
                    if rel["type"] == "conflicts":
                        conflicts.append({"type": "explicit_conflict", "a": r["id"], "b": rel["target"]})
            if conflicts:
                html += '<h1 id="sec-conflicts">Conflicts</h1>'
                self._add_toc(1, "Conflicts", "sec-conflicts")
                html += f'<p style="color:#64748b;font-size:10pt;">{len(conflicts)} conflicts detected</p>'
                html += self._conflicts_section(conflicts)

        html += '</body></html>'
        return html

    def build_markdown(self) -> str:
        md = f"# {self.meta.get('name', self.project_id)}\n\n"
        md += f"**Project:** {self.project_id}  \n"
        md += f"**Requirements:** {len(self.reqs)}  \n"
        md += f"**Generated:** {self.now_str}\n\n"
        md += "---\n\n## Requirements\n\n"
        for r in self.reqs:
            status = r.get("status", "proposed")
            md += f"### {r['id']} - {r.get('name','Untitled')} `{status}`\n\n"
            desc = self._resolve(r.get("description", "")).replace("<p>", "").replace("</p>", "").replace("<br>", "\n")
            if desc.strip():
                md += f"{desc}\n\n"
            if r.get("rationale"):
                md += f"**Rationale:** {self._resolve(r['rationale'])}\n\n"
            if r.get("source"):
                md += f"**Source:** {self._resolve(r['source'])}\n\n"
            rels = r.get("relations", [])
            if rels:
                md += "**Relations:** "
                md += ", ".join(
                    f"{rel['type']}→{rel['target']}{self._unresolved_suffix(rel['target'])}"
                    for rel in rels
                )
                md += "\n\n"
            parent = r.get("parent")
            if parent:
                md += f"**Parent:** {parent}{self._unresolved_suffix(parent)}\n\n"
        return md

    def _latex_changelog(self, since: str, until: str) -> list[str]:
        """The optional diff report: every audited change in a date window."""
        log = self.changelog(since, until)
        entries = log["entries"]
        L: list[str] = [r"\section{Changelog}"]

        span = f"{since or 'project start'} to {until or self.now.strftime('%Y-%m-%d')}"
        L.append(f"Every recorded change between \\textbf{{{_latex_escape(span)}}}, newest first.")
        if not entries:
            L.append(r"\vspace{0.5em}\par No changes were recorded in this period.")
            L.append(r"\newpage")
            return L

        # Headline counts, reusing the overview's stat cards. The blank line
        # ends the intro paragraph — without it the cards are typeset inline
        # and run past the right margin.
        acts = log["counts"]
        L.append("")
        L.append(r"\vspace{0.4em}")
        L.append(r"\begin{tabularx}{\textwidth}{*{4}{>{\centering\arraybackslash}X}}")
        L.append(r"\toprule")
        L.append(f"\\statcard{{{len(entries)}}}{{CHANGES}} & \\statcard{{{log['items']}}}{{ITEMS}} & "
                 f"\\statcard{{{acts.get('create', 0)}}}{{CREATED}} & "
                 f"\\statcard{{{acts.get('delete', 0)}}}{{DELETED}} \\\\")
        L.append(r"\bottomrule")
        L.append(r"\end{tabularx}")
        L.append(r"\vspace{0.8em}")

        L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.12\textwidth-2\tabcolsep\relax} "
                 r">{\raggedright\arraybackslash}p{\dimexpr0.18\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.34\textwidth-2\tabcolsep\relax} "
                 r">{\raggedright\arraybackslash}p{\dimexpr0.16\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.20\textwidth-2\tabcolsep\relax}@{}}")
        hdr = (r"\rowcolor{tabhead}\textbf{Date} & \textbf{Item} & \textbf{Name} & "
               r"\textbf{Action} & \textbf{User} \\")
        L.append(r"\toprule" + hdr + r"\midrule\endfirsthead")
        L.append(r"\toprule" + hdr + r"\midrule\endhead\bottomrule\endfoot")

        for e in entries:
            when = _latex_escape(f"{e['date']} {e['time']}".strip())
            item = self._latex_link(e["item_id"])
            name = _latex_escape(_truncate_words(e["name"] or e["kind"], 60))
            L.append(f"\\texttt{{\\footnotesize {when}}} & \\texttt{{{item}}} & {name} & "
                     f"\\statusbadge{{{_latex_escape(e['action'])}}} & {_latex_escape(e['user'])} \\\\")
            # Field-level detail spans the full width beneath its header row —
            # the same pattern the requirements tables use for descriptions.
            if e["fields"]:
                rows = []
                for f in e["fields"][:12]:
                    before = _latex_escape(_truncate_words(f["before"], 90))
                    after = _latex_escape(_truncate_words(f["after"], 90))
                    rows.append(f"\\textbf{{{_latex_escape(f['field'])}}}: "
                                f"\\textcolor{{rej}}{{{before}}} $\\rightarrow$ "
                                f"\\textcolor{{appr}}{{{after}}}")
                if len(e["fields"]) > 12:
                    rows.append(f"\\textit{{+{len(e['fields']) - 12} more fields}}")
                detail = " \\newline ".join(rows)
                L.append(f"\\multicolumn{{5}}{{@{{}}p{{\\dimexpr\\textwidth-2\\tabcolsep\\relax}}@{{}}}}"
                         f"{{\\footnotesize {detail}}} \\\\")
            L.append(r"\midrule")
        L.append(r"\end{longtable}")
        L.append(r"\newpage")
        return L

    def _risk_table_latex(self, risks_list: list[dict]) -> list[str]:
        """LaTeX lines for the Risk Register section, or ``[]`` when empty.

        Extracted from ``build_latex`` so the risk block can change (and be
        tested) on its own. Returns the ``\\section{Risk Register}`` line and
        every table line it used to append to ``L``; the caller owns the
        section gating.
        """
        if not risks_list:
            return []
        L: list[str] = []
        L.append(r"\section{Risk Register}")
        L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.12\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.28\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.12\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.12\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.12\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.24\textwidth-2\tabcolsep\relax}@{}}")
        L.append(r"\toprule")
        L.append(r"\rowcolor{tabhead}")
        L.append(r"\textbf{ID} & \textbf{Title} & \textbf{Severity} & \textbf{Probability} & \textbf{Status} & \textbf{Mitigation} \\")
        L.append(r"\midrule")
        L.append(r"\endfirsthead")
        L.append(r"\toprule")
        L.append(r"\rowcolor{tabhead}")
        L.append(r"\textbf{ID} & \textbf{Title} & \textbf{Severity} & \textbf{Probability} & \textbf{Status} & \textbf{Mitigation} \\")
        L.append(r"\midrule")
        L.append(r"\endhead")
        L.append(r"\bottomrule")
        L.append(r"\endfoot")
        for r in risks_list:
            rid = _latex_escape(r["id"])
            title = _latex_escape(r.get("title", ""))
            sev = r.get("severity", "medium")
            prob = _latex_escape(r.get("probability", ""))
            status = r.get("status", "open")
            mitigation = _latex_escape(_truncate_words(self._resolve(r.get("mitigation", "")), 180))
            L.append(f"\\texttt{{{rid}}} & {title} & \\prioritybadge{{{_latex_escape(sev)}}} & {prob} & \\statusbadge{{{_latex_escape(status)}}} & {mitigation} \\\\")
            # FMECA fields ride a full-width detail row beneath the header
            # row, exactly like the requirements-by-type table's description.
            # They are rich text, so strip the markup before escaping.
            fmeca_parts = []
            if r.get("failure_mode", "").strip():
                fmeca_parts.append(
                    f"\\textbf{{Failure Mode:}} {_latex_escape(_truncate_words(strip_html(self._resolve(r.get('failure_mode', ''))), 240))}")
            if r.get("effect", "").strip():
                fmeca_parts.append(
                    f"\\textbf{{Effect:}} {_latex_escape(_truncate_words(strip_html(self._resolve(r.get('effect', ''))), 240))}")
            if r.get("cause", "").strip():
                fmeca_parts.append(
                    f"\\textbf{{Cause:}} {_latex_escape(_truncate_words(strip_html(self._resolve(r.get('cause', ''))), 240))}")
            if fmeca_parts:
                detail = " \\newline ".join(fmeca_parts)
                L.append(f"\\multicolumn{{6}}{{@{{}}p{{\\dimexpr\\textwidth-2\\tabcolsep\\relax}}@{{}}}}{{\\small {detail}}} \\\\[-3pt]")
            L.append(r"\midrule")
        L.append(r"\end{longtable}")
        return L

    def build_latex(self, sections: list[str] | None = None,
                    changelog_from: str = "", changelog_to: str = "") -> str:
        if sections is None:
            sections = self._all_latex_sections
        hdr = self._header_config()
        project_name = _latex_escape(self.meta.get("name", self.project_id))
        company = _latex_escape(hdr["company"] or "")
        dept = _latex_escape(hdr["dept"] or "")
        doc_title = _latex_escape(hdr["title"] or "Requirements Specification Report")
        now_esc = _latex_escape(self.now_str)
        project_id_esc = _latex_escape(self.project_id)
        # Formal document-control fields (raw from settings → escape for LaTeX).
        doc_number = _latex_escape(hdr["doc_number"])
        revision = _latex_escape(hdr["revision"])
        classification = _latex_escape(hdr["classification"])
        status_txt = _latex_escape(hdr["status"])
        prepared_by = _latex_escape(hdr["prepared_by"])
        reviewed_by = _latex_escape(hdr["reviewed_by"])
        approved_by = _latex_escape(hdr["approved_by"])
        distribution = [_latex_escape(x) for x in hdr["distribution"]]
        is_draft = hdr["is_draft"]

        # ── Accent colour ─────────────────────────────────────────────────
        accent_hex = hdr.get("accent_color", "#2094f3").lstrip("#")
        accent_dark_hex = hdr.get("accent_dark", "#0964ae").lstrip("#")
        accent_r = int(accent_hex[0:2], 16)
        accent_g = int(accent_hex[2:4], 16)
        accent_b = int(accent_hex[4:6], 16)
        accent_dark_r = int(accent_dark_hex[0:2], 16)
        accent_dark_g = int(accent_dark_hex[2:4], 16)
        accent_dark_b = int(accent_dark_hex[4:6], 16)
        # Lighter tint for table headers (~15% of full saturation)
        accent_light_r = int(accent_r + (255 - accent_r) * 0.92)
        accent_light_g = int(accent_g + (255 - accent_g) * 0.92)
        accent_light_b = int(accent_b + (255 - accent_b) * 0.92)

        # ── Stats ────────────────────────────────────────────────────────
        total = len(self.reqs)
        status_dist: dict[str, int] = {}
        priority_dist: dict[str, int] = {}
        type_dist: dict[str, int] = {}
        for r in self.reqs:
            s = r.get("status", "proposed")
            status_dist[s] = status_dist.get(s, 0) + 1
            p = r.get("priority", "medium")
            priority_dist[p] = priority_dist.get(p, 0) + 1
            t = r.get("type", "functional")
            type_dist[t] = type_dist.get(t, 0) + 1
        vc_count = len(self.vcs)
        comps_count = len(self.components)
        risks_list = self.store.list_items("risks")
        risk_count = len(risks_list)

        L = []  # LaTeX lines

        L.append(r"\documentclass[11pt,a4paper]{article}")
        # ── Fonts ─────────────────────────────────────────────────────────
        # The app's UI runs on Inter (sans) + JetBrains Mono. Real Inter (and a
        # close JetBrains Mono stand-in, Source Code Pro) need OpenType support,
        # which only exists under XeTeX/LuaTeX — tectonic (the recommended,
        # default engine) is one. Plain pdflatex can't load either, so this
        # branches on the compiling engine via `iftex` and falls back to
        # Helvetica/Courier metric clones (in every base LaTeX install) and, in
        # the worst case, to bundled Computer Modern — never a hard failure.
        L.append(r"\usepackage{iftex}")
        L.append(r"\ifPDFTeX")
        L.append(r"  \usepackage[utf8]{inputenc}")
        L.append(r"  \usepackage[T1]{fontenc}")
        L.append(r"  \IfFileExists{helvet.sty}{\usepackage[scaled=0.92]{helvet}}{}")
        L.append(r"  \renewcommand{\familydefault}{\sfdefault}")
        L.append(r"  \IfFileExists{courier.sty}{\usepackage{courier}}{}")
        L.append(r"\else")
        L.append(r"  \usepackage{fontspec}")
        L.append(r"  \IfFileExists{inter.sty}{\usepackage[default]{inter}}{}")
        L.append(r"  \IfFileExists{sourcecodepro.sty}{\usepackage{sourcecodepro}}{}")
        L.append(r"\fi")
        L.append(r"\usepackage{geometry}")
        L.append(r"\geometry{margin=2.6cm, includehead, includefoot, headsep=14pt, footskip=28pt}")
        L.append(r"\usepackage[table]{xcolor}")
        L.append(r"\usepackage{fancyhdr}")
        L.append(r"\usepackage{lastpage}")
        L.append(r"\usepackage{longtable}")
        L.append(r"\usepackage{booktabs}")
        L.append(r"\usepackage{array}")
        L.append(r"\usepackage{tabularx}")
        L.append(r"\usepackage{ragged2e}")
        L.append(r"\usepackage{enumitem}")
        L.append(r"\usepackage{titlesec}")
        L.append(r"\usepackage{titletoc}")
        L.append(r"\usepackage{parskip}")
        L.append(r"\usepackage{ifthen}")
        L.append(r"\usepackage{makecell}")
        L.append(r"\usepackage{xstring}")
        L.append(r"\usepackage{graphicx}")
        # Pill-shaped badges need tikz for rounded corners; it's not in a
        # minimal texlive-latex-base install, so this is optional too — the
        # \pill fallback further down degrades to a flat colour chip.
        L.append(r"\IfFileExists{tikz.sty}{\usepackage{tikz}\newcommand{\rmhaspill}{1}}{}")
        if is_draft:
            L.extend(watermark_preamble(status_txt))

        # ── Palette ───────────────────────────────────────────────────────
        # Matches the app UI exactly — the Cloudscape light-theme CSS variables
        # (frontend/src/styles/index.css), converted from HSL to RGB, so the
        # report reads as the same product rather than a generic LaTeX doc.
        L.append(f"\\definecolor{{accent}}{{RGB}}{{{accent_r},{accent_g},{accent_b}}}")
        L.append(f"\\definecolor{{accentdark}}{{RGB}}{{{accent_dark_r},{accent_dark_g},{accent_dark_b}}}")
        L.append(r"\definecolor{ink}{RGB}{31,39,51}")           # --foreground — body
        L.append(r"\definecolor{muted}{RGB}{104,119,141}")      # --muted-foreground — captions
        L.append(r"\definecolor{rule}{RGB}{220,224,229}")       # --border — hairlines
        L.append(f"\\definecolor{{prop}}{{RGB}}{{{accent_r},{accent_g},{accent_b}}}")
        L.append(r"\definecolor{appr}{RGB}{34,160,86}")         # --cs-green — approved
        L.append(r"\definecolor{impl}{RGB}{119,62,234}")        # --cs-purple — implemented
        L.append(r"\definecolor{veri}{RGB}{0,143,140}")         # --cs-teal — verified
        L.append(r"\definecolor{rej}{RGB}{237,44,44}")          # --cs-red — rejected
        L.append(r"\definecolor{depr}{RGB}{133,144,147}")       # --cs-grey — deprecated
        L.append(r"\definecolor{prihigh}{RGB}{255,119,0}")      # --cs-orange — high priority
        L.append(r"\definecolor{pricrit}{RGB}{237,44,44}")      # --cs-red — critical priority
        L.append(r"\definecolor{prlow}{RGB}{133,144,147}")      # --cs-grey — low priority
        L.append(f"\\definecolor{{primed}}{{RGB}}{{{accent_r},{accent_g},{accent_b}}}")
        L.append(f"\\definecolor{{tabhead}}{{RGB}}{{{accent_light_r},{accent_light_g},{accent_light_b}}}")
        L.append(r"\definecolor{rowalt}{RGB}{250,251,252}")     # --background — zebra stripe

        L.append(r"\usepackage{hyperref}")
        L.append(r"\hypersetup{colorlinks=true,linkcolor=accent,urlcolor=accent,citecolor=accent}")

        # ── Section headings — coloured, ruled, generously spaced ─────────
        L.append(r"\titleformat{\section}{\Large\bfseries\color{accentdark}}{\thesection}{0.6em}{}"
                 r"[{\vspace{2pt}\color{accent}\titlerule[1.2pt]}]")
        L.append(r"\titleformat{\subsection}{\large\bfseries\color{accent}}{\thesubsection}{0.6em}{}")
        L.append(r"\titlespacing*{\section}{0pt}{22pt}{10pt}")
        L.append(r"\titlespacing*{\subsection}{0pt}{14pt}{6pt}")

        # ── Tables — airy rows, no cramped stretch ────────────────────────
        L.append(r"\setlength{\tabcolsep}{7pt}")
        L.append(r"\renewcommand{\arraystretch}{1.15}")
        L.append(r"\setlength{\LTpre}{6pt}")
        L.append(r"\setlength{\LTpost}{10pt}")
        L.append(r"\setlength{\extrarowheight}{1pt}")
        L.append(r"\setlength{\arrayrulewidth}{0.5pt}")
        L.append(r"\arrayrulecolor{rule}")

        # ── Running head / foot (document-control layout) ─────────────────
        # Header:  doc-number (L) · classification banner (C) · Rev (R)
        # Footer:  company/date (L) · Page X of Y (C) · classification/status (R)
        head_l = doc_number or company
        head_r = (f"Rev {revision}" if revision else doc_title)
        foot_l = company or now_esc
        foot_r = classification or (status_txt if status_txt else "")
        L.append(r"\pagestyle{fancy}")
        L.append(r"\fancyhf{}")
        L.append(f"\\fancyhead[L]{{\\footnotesize\\sffamily\\color{{muted}}{head_l}}}")
        if classification:
            L.append(f"\\fancyhead[C]{{\\footnotesize\\sffamily\\bfseries\\color{{accent}}{classification}}}")
        L.append(f"\\fancyhead[R]{{\\footnotesize\\sffamily\\color{{muted}}{head_r}}}")
        L.append(f"\\fancyfoot[L]{{\\footnotesize\\sffamily\\color{{muted}}{foot_l}}}")
        L.append(r"\fancyfoot[C]{\footnotesize\sffamily\color{muted}Page \thepage\ of \pageref{LastPage}}")
        if foot_r:
            L.append(f"\\fancyfoot[R]{{\\footnotesize\\sffamily\\color{{muted}}{foot_r}}}")
        L.append(r"\renewcommand{\headrulewidth}{0.4pt}")
        L.append(r"\renewcommand{\footrulewidth}{0.4pt}")
        L.append(r"\renewcommand{\headrule}{\color{rule}\hrule width\headwidth height\headrulewidth}")
        L.append(r"\renewcommand{\footrule}{\color{rule}\hrule width\headwidth height\footrulewidth}")

        # Pill-shaped badge, matching the app's rounded status/priority chips
        # (tinted fill + solid text, no border). Rounded corners need tikz; if
        # it isn't installed (see the \IfFileExists guard above) this falls
        # back to a flat colour chip rather than failing the whole document.
        L.append(r"\newcommand{\pill}[2]{%")
        L.append(r"  \ifdefined\rmhaspill")
        L.append(r"    \tikz[baseline=(P.base)]{\node[fill=#1!13,rounded corners=4.5pt,inner xsep=6pt,inner ysep=2.2pt,text=#1,font=\bfseries\footnotesize] (P) {#2};}%")
        L.append(r"  \else")
        L.append(r"    \colorbox{#1!18}{\textcolor{#1}{\textbf{\footnotesize #2}}}%")
        L.append(r"  \fi")
        L.append(r"}")
        # KPI stat card (Project Overview) — a soft tinted, rounded card behind
        # the big number, matching the app's summary cards. Same tikz/fallback
        # split as \pill.
        L.append(r"\newcommand{\statcard}[2]{%")
        L.append(r"  \ifdefined\rmhaspill")
        L.append(r"    \tikz[baseline=(S.base)]{\node[fill=accent!5,rounded corners=6pt,inner sep=10pt,align=center,minimum width=3.0cm] (S) {\shortstack{{\fontsize{26}{30}\selectfont\bfseries\color{accent} #1}\\[3pt]{\footnotesize\color{muted} #2}}};}%")
        L.append(r"  \else")
        L.append(r"    \makecell{{\fontsize{26}{30}\selectfont\bfseries\color{accent} #1}\\[3pt]{\footnotesize\color{muted} #2}}%")
        L.append(r"  \fi")
        L.append(r"}")
        # Distribution bar (Status/Priority/Type tables) — a rounded fill on a
        # neutral track, matching the app's progress-bar convention, instead
        # of a bare coloured rule floating on white.
        L.append(r"\newcommand{\distbar}[3]{%")  # #1 colour, #2 fill width (cm, no unit), #3 track width
        L.append(r"  \ifdefined\rmhaspill")
        L.append(r"    \begin{tikzpicture}[baseline=-0.5ex, x=1cm]")
        L.append(r"      \draw[rule,line width=9pt,line cap=round] (0,0) -- (#3,0);")
        L.append(r"      \draw[#1,line width=9pt,line cap=round] (0,0) -- (#2,0);")
        L.append(r"    \end{tikzpicture}%")
        L.append(r"  \else")
        L.append(r"    \textcolor{#1}{\rule{#2cm}{9pt}}%")
        L.append(r"  \fi")
        L.append(r"}")
        # Badge commands — use \IfStrEqCase (xstring) instead of nested
        # \ifthenelse to avoid brace-counting errors.
        L.append(r"\newcommand{\statusbadge}[1]{%")
        L.append(r"  \IfStrEqCase{#1}{%")
        L.append(r"    {proposed}{\pill{prop}{proposed}}%")
        L.append(r"    {approved}{\pill{appr}{approved}}%")
        L.append(r"    {implemented}{\pill{impl}{implemented}}%")
        L.append(r"    {verified}{\pill{veri}{verified}}%")
        L.append(r"    {rejected}{\pill{rej}{rejected}}%")
        L.append(r"    {passed}{\pill{appr}{passed}}%")
        L.append(r"    {failed}{\pill{rej}{failed}}%")
        L.append(r"    {pending}{\pill{depr}{pending}}%")
        L.append(r"    {in_progress}{\pill{prop}{in progress}}%")
        L.append(r"    {submitted}{\pill{prop}{submitted}}%")
        L.append(r"    {in_review}{\pill{prop}{in review}}%")
        L.append(r"    {open}{\pill{prop}{open}}%")
        L.append(r"    {closed}{\pill{depr}{closed}}%")
        L.append(r"    {mitigated}{\pill{appr}{mitigated}}%")
        L.append(r"    {deprecated}{\pill{depr}{deprecated}}%")
        # Changelog actions.
        L.append(r"    {create}{\pill{appr}{created}}%")
        L.append(r"    {update}{\pill{prop}{updated}}%")
        L.append(r"    {delete}{\pill{rej}{deleted}}%")
        L.append(r"    {review}{\pill{impl}{reviewed}}%")
        L.append(r"  }[\pill{depr}{#1}]%")
        L.append(r"}")
        L.append(r"\newcommand{\prioritybadge}[1]{%")
        L.append(r"  \IfStrEqCase{#1}{%")
        L.append(r"    {critical}{\pill{pricrit}{critical}}%")
        L.append(r"    {high}{\pill{prihigh}{high}}%")
        L.append(r"    {medium}{\pill{primed}{medium}}%")
        L.append(r"    {low}{\pill{prlow}{low}}%")
        L.append(r"  }[\pill{prlow}{#1}]%")
        L.append(r"}")

        L.append(r"\begin{document}")
        L.append(r"\color{ink}")

        # Section gating. cover/summary/requirements/components/verification/
        # risks used to render unconditionally, so a narrow export (e.g. the
        # changelog-only diff report) still emitted the whole document.
        # These blocks emit into `L` across dozens of statements, so rather
        # than re-indent them all under an `if`, each records a mark and rolls
        # `L` back when its section is deselected — the emitted strings are
        # just discarded.
        want = set(sections)
        marks: list[int] = []

        def begin_section() -> None:
            marks.append(len(L))

        def end_section(section_id: str) -> None:
            start = marks.pop()
            if section_id not in want:
                del L[start:]

        # ── Title page ────────────────────────────────────────────────────
        begin_section()
        L.append(r"\begin{titlepage}")
        L.append(r"\thispagestyle{empty}")
        L.append(r"\centering")
        L.append(r"\vspace*{2.4cm}")
        # Classification banner at the top of the cover.
        if classification:
            L.append(f"{{\\normalsize\\sffamily\\bfseries\\color{{accent}} {classification}}}\\par")
            L.append(r"\vspace{1.3cm}")
        else:
            L.append(r"\vspace{0.4cm}")
        L.append(r"{\color{accent}\rule{\textwidth}{2.5pt}}\par")
        L.append(r"\vspace{0.9cm}")
        L.append(f"{{\\fontsize{{34}}{{40}}\\selectfont\\bfseries\\color{{accentdark}} {project_name}}}\\par")
        L.append(r"\vspace{0.7cm}")
        L.append(f"{{\\LARGE\\color{{accent}} {doc_title}}}\\par")
        if status_txt:
            L.append(r"\vspace{0.5cm}")
            L.append(f"{{\\large\\sffamily\\color{{muted}} {status_txt}}}\\par")
        L.append(r"\vspace{0.9cm}")
        L.append(r"{\color{accent}\rule{\textwidth}{2.5pt}}\par")
        L.append(r"\vspace{1.5cm}")
        L.append(f"{{\\Large\\bfseries {company}}}\\par")
        L.append(r"\vspace{0.2cm}")
        L.append(f"{{\\large\\color{{muted}} {dept}}}\\par")
        L.append(r"\vfill")
        # Document-control metadata panel.
        L.append(r"{\color{rule}\rule{0.7\textwidth}{0.5pt}}\par\vspace{0.5cm}")
        L.append(r"\renewcommand{\arraystretch}{1.5}")
        L.append(r"{\normalsize\begin{tabular}{r@{\hskip 1.2em}l}")
        cover_rows = []
        if doc_number:
            cover_rows.append(("Document", f"\\texttt{{{doc_number}}}"))
        cover_rows.append(("Revision", revision))
        cover_rows.append(("Project", f"\\texttt{{{project_id_esc}}}"))
        cover_rows.append(("Date", now_esc))
        cover_rows.append(("Requirements", str(total)))
        cover_rows.append(("Verification cases", str(vc_count)))
        for _lbl, _val in cover_rows:
            L.append(f"{{\\color{{muted}} {_lbl}}} & {_val} \\\\")
        L.append(r"\end{tabular}}\par")
        L.append(r"\renewcommand{\arraystretch}{1.2}")
        L.append(r"\vspace{1.0cm}")
        L.append(r"\end{titlepage}")

        # ── Document Control front matter ─────────────────────────────────
        # Revision history, approval / sign-off block, and distribution list —
        # standard front matter for a controlled engineering document.
        L.append(r"\thispagestyle{fancy}")
        L.append(r"{\color{accentdark}\Large\bfseries Document Control}\par\vspace{2pt}")
        L.append(r"{\color{accent}\rule{\textwidth}{1.2pt}}\par\vspace{12pt}")

        # Revision history — sourced from baselines (frozen snapshots); falls
        # back to a single "initial issue" row.
        L.append(r"{\large\bfseries\color{accent} Revision History}\par\vspace{4pt}")
        L.append(r"\begin{tabularx}{\textwidth}{l l >{\raggedright\arraybackslash}X l}")
        L.append(r"\toprule")
        L.append(r"\rowcolor{tabhead}\textbf{Revision} & \textbf{Date} & \textbf{Description} & \textbf{Author} \\")
        L.append(r"\midrule")
        try:
            baselines = self.store.list_items("baselines")
        except Exception:
            baselines = []
        rev_rows = []
        for b in sorted(baselines, key=lambda x: x.get("frozen_at", "")):
            rname = _latex_escape(b.get("name", ""))
            rdate = _latex_escape((b.get("frozen_at", "") or "")[:10])
            rev_rows.append((rname, rdate, "Baseline snapshot", ""))
        if not rev_rows:
            rev_rows.append((revision, now_esc, "Initial issue", prepared_by or ""))
        for i, (rv, dt, desc, auth) in enumerate(rev_rows):
            stripe = r"\rowcolor{rowalt}" if i % 2 else ""
            L.append(f"{stripe}{rv or '--'} & {dt or '--'} & {desc} & {auth or '--'} \\\\")
        L.append(r"\bottomrule")
        L.append(r"\end{tabularx}")
        L.append(r"\vspace{16pt}")

        # Approval / sign-off block.
        L.append(r"{\large\bfseries\color{accent} Approvals}\par\vspace{4pt}")
        L.append(r"\begin{tabularx}{\textwidth}{l >{\raggedright\arraybackslash}X >{\raggedright\arraybackslash}p{\dimexpr0.18\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.14\textwidth-2\tabcolsep\relax}}")
        L.append(r"\toprule")
        L.append(r"\rowcolor{tabhead}\textbf{Role} & \textbf{Name} & \textbf{Signature} & \textbf{Date} \\")
        L.append(r"\midrule")
        sig = r"\rule{3.6cm}{0.4pt}"
        approvals = [("Prepared by", prepared_by), ("Reviewed by", reviewed_by), ("Approved by", approved_by)]
        for i, (role, who) in enumerate(approvals):
            stripe = r"\rowcolor{rowalt}" if i % 2 else ""
            L.append(f"{stripe}\\textbf{{{role}}} & {who or ''} & {sig} & \\rule{{2cm}}{{0.4pt}} \\\\")
        L.append(r"\bottomrule")
        L.append(r"\end{tabularx}")

        # Distribution list (optional).
        if distribution:
            L.append(r"\vspace{16pt}")
            L.append(r"{\large\bfseries\color{accent} Distribution}\par\vspace{4pt}")
            L.append(r"\begin{itemize}[leftmargin=1.4em, itemsep=1pt, topsep=2pt]")
            for who in distribution:
                L.append(f"  \\item {who}")
            L.append(r"\end{itemize}")
        L.append(r"\clearpage")
        end_section("cover")

        # ── Table of Contents ─────────────────────────────────────────────
        # \tableofcontents emits its own (accent-styled) heading; TOC entries in
        # ink rather than link-blue so a long contents list stays calm.
        L.append(r"\newpage")
        L.append(r"\begingroup\hypersetup{linkcolor=ink}\tableofcontents\endgroup")
        L.append(r"\clearpage")

        # ── 1. Introduction (ISO/IEC/IEEE 29148 structure) ────────────────
        begin_section()
        L.append(r"\section{Introduction}")

        L.append(r"\subsection{Purpose}")
        L.append(f"This document specifies the requirements for the \\textbf{{{project_name}}}")
        L.append(r"system. It defines the functional, performance, interface and constraint")
        L.append(r"requirements that the system shall satisfy, together with the verification")
        L.append(r"approach and supporting engineering data. The keyword \textbf{shall} denotes a")
        L.append(r"mandatory requirement; each requirement carries a unique identifier for")
        L.append(r"traceability.")

        L.append(r"\subsection{Scope}")
        L.append(f"The scope covers the {total} requirement{'s' if total != 1 else ''} of the")
        L.append(f"\\textbf{{{project_name}}} system across all requirement types, the")
        L.append(f"{comps_count} component{'s' if comps_count != 1 else ''} of the synthesised")
        L.append(f"design, {vc_count} verification case{'s' if vc_count != 1 else ''}, and the")
        L.append(r"associated risk register. Requirements engineering follows the")
        L.append(r"ISO/IEC/IEEE~15288 and 29148 frameworks for stakeholder needs and system")
        L.append(r"requirements definition.")

        L.append(r"\subsection{Definitions, Acronyms, and Abbreviations}")
        L.append(r"Terms, acronyms and abbreviations used in this document are defined in the")
        L.append(r"Glossary (Appendix).")

        # Applicable & reference documents — derived from requirement sources
        # and file references.
        L.append(r"\subsection{Applicable and Reference Documents}")
        sources = sorted({(r.get("source") or "").strip() for r in self.reqs
                          if (r.get("source") or "").strip()})
        ref_paths = []
        seen_ref = set()
        for r in self.reqs:
            for ref in r.get("references", []):
                p = (ref.get("path") or "").strip()
                if p and p not in seen_ref:
                    seen_ref.add(p)
                    ref_paths.append(p)
        if sources:
            L.append(r"\textbf{Applicable documents} — sources cited by requirements in this specification:")
            L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.14\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.86\textwidth-2\tabcolsep\relax}@{}}")
            L.append(r"\toprule\rowcolor{tabhead}\textbf{Ref} & \textbf{Document} \\ \midrule")
            L.append(r"\endfirsthead")
            L.append(r"\toprule\rowcolor{tabhead}\textbf{Ref} & \textbf{Document} \\ \midrule")
            L.append(r"\endhead\bottomrule\endfoot")
            for i, s in enumerate(sources, 1):
                stripe = r"\rowcolor{rowalt}" if i % 2 == 0 else ""
                L.append(f"{stripe}\\texttt{{AD-{i:02d}}} & {_latex_escape(s)} \\\\")
            L.append(r"\end{longtable}")
        if ref_paths:
            L.append(r"\textbf{Reference documents} — external artefacts linked from requirements:")
            L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.14\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.86\textwidth-2\tabcolsep\relax}@{}}")
            L.append(r"\toprule\rowcolor{tabhead}\textbf{Ref} & \textbf{Location} \\ \midrule")
            L.append(r"\endfirsthead")
            L.append(r"\toprule\rowcolor{tabhead}\textbf{Ref} & \textbf{Location} \\ \midrule")
            L.append(r"\endhead\bottomrule\endfoot")
            for i, p in enumerate(ref_paths, 1):
                stripe = r"\rowcolor{rowalt}" if i % 2 == 0 else ""
                L.append(f"{stripe}\\texttt{{RD-{i:02d}}} & \\texttt{{{_latex_escape(p)}}} \\\\")
            L.append(r"\end{longtable}")
        if not sources and not ref_paths:
            L.append(r"No external applicable or reference documents are cited.")

        L.append(r"\subsection{Document Overview}")
        L.append(r"The remainder of this document provides a project overview and metrics")
        L.append(r"(Section~\ref{sec:overview}), the requirements organised by type, the")
        L.append(r"component inventory, verification cases and the risk register, a")
        L.append(r"requirements verification traceability matrix, and supporting engineering")
        L.append(r"data. Reference material is provided in the appendices.")

        # ── 2. Project Overview ───────────────────────────────────────────
        L.append(r"\section{Project Overview}\label{sec:overview}")

        def _stat(n, label):
            return f"\\statcard{{{n}}}{{{label}}}"

        L.append(r"\begin{tabularx}{\textwidth}{*{4}{>{\centering\arraybackslash}X}}")
        L.append(r"\toprule")
        L.append(f"{_stat(total, 'REQUIREMENTS')} & {_stat(vc_count, 'VERIFICATION')} & "
                 f"{_stat(comps_count, 'COMPONENTS')} & {_stat(risk_count, 'RISKS')} \\\\")
        L.append(r"\bottomrule")
        L.append(r"\end{tabularx}")
        L.append(r"\vspace{0.6em}")

        # Colour-coded distribution bar charts.
        status_bar_colors = {
            "proposed": "prop", "approved": "appr", "implemented": "impl",
            "verified": "veri", "rejected": "rej", "deprecated": "depr",
            "passed": "appr", "failed": "rej", "pending": "muted",
            "in_progress": "prop", "open": "prop", "closed": "depr", "mitigated": "appr",
        }
        prio_bar_colors = {"critical": "pricrit", "high": "prihigh", "medium": "primed", "low": "prlow"}

        def dist_table(head: str, dist: dict, colors: dict):
            out = [r"\begin{tabularx}{\textwidth}{X r r >{\raggedright\arraybackslash}p{\dimexpr0.40\textwidth-2\tabcolsep\relax}}"]
            out.append(r"\toprule")
            out.append(f"\\rowcolor{{tabhead}}\\textbf{{{head}}} & \\textbf{{Count}} & "
                       r"\textbf{\%} & \textbf{Share} \\")
            out.append(r"\midrule")
            for i, (label, count) in enumerate(sorted(dist.items(), key=lambda x: -x[1])):
                pct = round(count / total * 100) if total else 0
                w = max(round(pct / 100 * 5.5, 2), 0.03)
                color = colors.get(label, "accent")
                disp = _latex_escape(label.replace("_", " ").title())
                bar = f"\\distbar{{{color}}}{{{w}}}{{5.5}}" if pct > 0 else ""
                stripe = r"\rowcolor{rowalt}" if i % 2 else ""
                out.append(f"{stripe}{disp} & {count} & {pct}\\% & {bar} \\\\")
            out.append(r"\bottomrule")
            out.append(r"\end{tabularx}")
            return out

        L.append(r"\subsection{Status Distribution}")
        L.extend(dist_table("Status", status_dist, status_bar_colors))
        L.append(r"\subsection{Priority Distribution}")
        L.extend(dist_table("Priority", priority_dist, prio_bar_colors))
        L.append(r"\subsection{Type Distribution}")
        L.extend(dist_table("Type", type_dist, {}))
        L.append(r"\newpage")
        end_section("summary")

        # ── Changelog (opt-in diff report over a date range) ───────────────
        if "changelog" in want:
            L.extend(self._latex_changelog(changelog_from, changelog_to))

        # ── 3. Requirements by Type ───────────────────────────────────────
        begin_section()
        L.append(r"\section{Requirements by Type}")

        grouped: dict[str, list[dict]] = {}
        for r in self.reqs:
            t = r.get("type", "functional")
            grouped.setdefault(t, []).append(r)

        def type_sort_key(t: str) -> tuple:
            if t == "functional":
                return (0, t)
            if t.startswith("non_functional"):
                return (1, t)
            return (2, t)

        for t in sorted(grouped.keys(), key=type_sort_key):
            reqs_in_type = grouped[t]
            display = t.replace("_", " ").title()
            display = display.replace("Non Functional", "Non-Functional")

            L.append(f"\\subsection{{{_latex_escape(display)}}}")
            n = len(reqs_in_type)
            L.append(f"\\textbf{{{n}}} requirement{'s' if n != 1 else ''} of this type.")
            L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.18\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.46\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.18\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.18\textwidth-2\tabcolsep\relax}@{}}")
            L.append(r"\toprule")
            L.append(r"\rowcolor{tabhead}")
            L.append(r"\textbf{ID} & \textbf{Name} & \textbf{Status} & \textbf{Priority} \\")
            L.append(r"\midrule")
            L.append(r"\endfirsthead")
            L.append(r"\toprule")
            L.append(r"\rowcolor{tabhead}")
            L.append(r"\textbf{ID} & \textbf{Name} & \textbf{Status} & \textbf{Priority} \\")
            L.append(r"\midrule")
            L.append(r"\endhead")
            L.append(r"\bottomrule")
            L.append(r"\endfoot")

            for r in reqs_in_type:
                rid = r["id"]
                rid_esc = _latex_escape(rid)
                name = _latex_escape(r.get("name", "Untitled"))
                status = r.get("status", "proposed")
                priority = r.get("priority", "medium")
                desc = _latex_escape(
                    self._resolve(r.get("description", ""))
                    .replace("<p>", "\n\n").replace("</p>", "")
                    .replace("<br />", "\n").replace("<br>", "\n")
                    .replace("\n\n\n", "\n\n").strip()[:600]
                ).replace("\n\n", r" \par ").replace("\n", r" \\ ")
                rationale = _latex_escape(self._resolve(r.get("rationale", "")))
                source = _latex_escape(self._resolve(r.get("source", "")))
                allocated = _latex_escape(self._resolve(r.get("allocated_to", "")))
                baselines = ", ".join(r.get("baselines", []))
                vc_links = ", ".join(self._latex_link(vid) for vid in r.get("verification_cases", []))
                rel_links = ", ".join(
                    f"{_latex_escape(rel['type'])} \\textrightarrow\\ {self._latex_link(rel['target'])}"
                    for rel in r.get("relations", [])
                )

                extras_parts = []
                if desc:
                    extras_parts.append(desc)
                if rationale:
                    extras_parts.append(f"\\textbf{{Rationale:}} {rationale}")
                if source:
                    extras_parts.append(f"\\textbf{{Source:}} {source}")
                if allocated:
                    extras_parts.append(f"\\textbf{{Allocated to:}} {allocated}")
                if baselines:
                    extras_parts.append(f"\\textbf{{Baselines:}} {_latex_escape(baselines)}")
                if vc_links:
                    extras_parts.append(f"\\textbf{{VCs:}} {vc_links}")
                if rel_links:
                    extras_parts.append(f"\\textbf{{Links:}} {rel_links}")
                extra_str = " \\newline ".join(extras_parts)

                L.append(f"\\hypertarget{{req-{rid_esc}}}{{}}"
                         f"\\texttt{{{rid_esc}}} & {name} & \\statusbadge{{{_latex_escape(status)}}} & \\prioritybadge{{{_latex_escape(priority)}}} \\\\[-2pt]")
                if extra_str:
                    L.append(f"\\multicolumn{{4}}{{@{{}}p{{\\dimexpr\\textwidth-2\\tabcolsep\\relax}}@{{}}}}{{\\small {extra_str}}} \\\\[-3pt]")
                L.append(r"\midrule")

            L.append(r"\end{longtable}")
            L.append(r"\newpage")
        end_section("requirements")

        # ── 4. Components ─────────────────────────────────────────────────
        begin_section()
        if self.components:
            L.append(r"\section{Components}")
            L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.14\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.32\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.16\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.20\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.18\textwidth-2\tabcolsep\relax}@{}}")
            L.append(r"\toprule")
            L.append(r"\rowcolor{tabhead}")
            L.append(r"\textbf{ID} & \textbf{Name} & \textbf{Type} & \textbf{Part Number} & \textbf{Satisfies} \\")
            L.append(r"\midrule")
            L.append(r"\endfirsthead")
            L.append(r"\toprule")
            L.append(r"\rowcolor{tabhead}")
            L.append(r"\textbf{ID} & \textbf{Name} & \textbf{Type} & \textbf{Part Number} & \textbf{Satisfies} \\")
            L.append(r"\midrule")
            L.append(r"\endhead")
            L.append(r"\bottomrule")
            L.append(r"\endfoot")
            for c in self.components:
                cid = c["id"]
                cid_esc = _latex_escape(cid)
                name = _latex_escape(c.get("name", ""))
                ctype = _latex_escape(c.get("type", "part"))
                pn = _latex_escape(c.get("part_number", ""))
                sat = ", ".join(self._latex_link(rid) for rid in c.get("satisfies", []))
                L.append(f"\\hypertarget{{comp-{cid_esc}}}{{}}"
                         f"\\texttt{{{cid_esc}}} & {name} & {ctype} & \\texttt{{{pn}}} & {sat or '---'} \\\\")
                L.append(r"\midrule")
            L.append(r"\end{longtable}")
            L.append(r"\newpage")
        end_section("components")

        # ── 5. Verification Cases ─────────────────────────────────────────
        begin_section()
        if self.vcs:
            L.append(r"\section{Verification Cases}")
            L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.18\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.30\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.14\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.14\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.24\textwidth-2\tabcolsep\relax}@{}}")
            L.append(r"\toprule")
            L.append(r"\rowcolor{tabhead}")
            L.append(r"\textbf{ID} & \textbf{Name} & \textbf{Method} & \textbf{Status} & \textbf{Verified Requirements} \\")
            L.append(r"\midrule")
            L.append(r"\endfirsthead")
            L.append(r"\toprule")
            L.append(r"\rowcolor{tabhead}")
            L.append(r"\textbf{ID} & \textbf{Name} & \textbf{Method} & \textbf{Status} & \textbf{Verified Requirements} \\")
            L.append(r"\midrule")
            L.append(r"\endhead")
            L.append(r"\bottomrule")
            L.append(r"\endfoot")
            for vc in self.vcs:
                vid = vc["id"]
                vid_esc = _latex_escape(vid)
                name = _latex_escape(vc.get("name", ""))
                method = _latex_escape(vc.get("method", ""))
                status = vc.get("status", "pending")
                verified = ", ".join(self._latex_link(rid) for rid in vc.get("verified_requirements", []))
                L.append(f"\\hypertarget{{vc-{vid_esc}}}{{}}"
                         f"\\texttt{{{vid_esc}}} & {name} & {method} & \\statusbadge{{{_latex_escape(status)}}} & {verified or '---'} \\\\")
                L.append(r"\midrule")
            L.append(r"\end{longtable}")
            L.append(r"\newpage")
        end_section("verification")

        # ── 6. Risks ──────────────────────────────────────────────────────
        begin_section()
        L.extend(self._risk_table_latex(risks_list))
        end_section("risks")

        # ── Traceability Matrix ───────────────────────────────────────────
        if "traceability" in sections:
            L.append(r"\section{Requirements Verification Traceability Matrix}")
            L.append(r"Each requirement is mapped to its verification method, the verification")
            L.append(r"case(s) that discharge it, and its current verification status. A")
            L.append(r"requirement with no verification case is a coverage gap, flagged")
            L.append(r"\textcolor{rej}{\textbf{none}} below.")
            L.append(r"\begin{longtable}{@{}>{\ttfamily}p{\dimexpr0.12\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.28\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.12\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.28\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.20\textwidth-2\tabcolsep\relax}@{}}")
            hdr_row = (r"\normalfont\textbf{ID} & \normalfont\textbf{Requirement} & "
                       r"\normalfont\textbf{Method} & \normalfont\textbf{Verified By} & "
                       r"\normalfont\textbf{Status} \\")
            L.append(r"\toprule\rowcolor{tabhead}" + hdr_row + r"\midrule\endfirsthead")
            L.append(r"\toprule\rowcolor{tabhead}" + hdr_row + r"\midrule\endhead\bottomrule\endfoot")
            for i, r in enumerate(self.reqs):
                rid = _latex_escape(r["id"])
                name = _latex_escape(r.get("name", "Untitled"))
                method = _latex_escape(str(r.get("verification_method", "") or ""))
                vcs = r.get("verification_cases", []) or []
                verified_by = (", ".join(self._latex_link(v) for v in vcs)
                               if vcs else r"\textcolor{rej}{\textbf{none}}")
                vstatus = r.get("verification_status", "pending")
                stripe = r"\rowcolor{rowalt}" if i % 2 else ""
                L.append(f"{stripe}{rid} & {name} & {method} & {verified_by} & "
                         f"\\statusbadge{{{_latex_escape(vstatus)}}} \\\\")
            L.append(r"\end{longtable}")
            L.append(r"\newpage")

        # ── Specifications ────────────────────────────────────────────────
        if "specifications" in sections:
            L.append(r"\section{Specifications}")
            for spec in self.specs:
                sid = _latex_escape(spec["id"])
                name = _latex_escape(spec.get("name", ""))
                desc = _latex_escape(_truncate_words(self._resolve(spec.get("description", "")), 240))
                reqs = _latex_escape(", ".join(spec.get("requirements", [])))
                L.append(f"\\subsection*{{{sid} -- {name}}}")
                L.append(f"{desc}")
                if spec.get("requirements"):
                    L.append(f"\\textbf{{Linked Requirements:}} \\texttt{{{reqs}}}")
                L.append(r"\vspace{0.5em}")

        # ── Baselines ─────────────────────────────────────────────────────
        if "baselines" in sections:
            L.append(r"\section{Baselines}")
            baseline_map: dict[str, list[str]] = {}
            for r in self.reqs:
                for b in r.get("baselines", []):
                    baseline_map.setdefault(b, []).append(r["id"])
            if baseline_map:
                L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.28\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.14\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.58\textwidth-2\tabcolsep\relax}@{}}")
                L.append(r"\toprule")
                L.append(r"\rowcolor{tabhead}")
                L.append(r"\textbf{Baseline} & \textbf{Count} & \textbf{Requirements} \\")
                L.append(r"\midrule")
                L.append(r"\endfirsthead")
                L.append(r"\toprule")
                L.append(r"\rowcolor{tabhead}")
                L.append(r"\textbf{Baseline} & \textbf{Count} & \textbf{Requirements} \\")
                L.append(r"\midrule")
                L.append(r"\endhead")
                L.append(r"\bottomrule")
                L.append(r"\endfoot")
                for bname, rids in sorted(baseline_map.items()):
                    escaped_name = _latex_escape(bname)
                    count = len(rids)
                    rlist = _latex_escape(", ".join(rids))
                    L.append(f"{escaped_name} & {count} & {rlist} \\\\")
                    L.append(r"\midrule")
                L.append(r"\end{longtable}")
            else:
                L.append(r"No baselines defined.")

        # ── Change Requests ───────────────────────────────────────────────
        if "changes" in sections:
            crs = self.store.list_items("change_requests")
            if crs:
                L.append(r"\section{Change Requests}")
                L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.14\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.28\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.14\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.44\textwidth-2\tabcolsep\relax}@{}}")
                L.append(r"\toprule")
                L.append(r"\rowcolor{tabhead}")
                L.append(r"\textbf{ID} & \textbf{Title} & \textbf{Status} & \textbf{Affected Requirements} \\")
                L.append(r"\midrule")
                L.append(r"\endfirsthead")
                L.append(r"\toprule")
                L.append(r"\rowcolor{tabhead}")
                L.append(r"\textbf{ID} & \textbf{Title} & \textbf{Status} & \textbf{Affected Requirements} \\")
                L.append(r"\midrule")
                L.append(r"\endhead")
                L.append(r"\bottomrule")
                L.append(r"\endfoot")
                for cr in crs:
                    cid = _latex_escape(cr["id"])
                    title = _latex_escape(cr.get("title", ""))
                    status = cr.get("status", "open")
                    affected = ", ".join(self._latex_link(rid) for rid in cr.get("affected_requirements", []))
                    L.append(f"\\texttt{{{cid}}} & {title} & \\statusbadge{{{_latex_escape(status)}}} & {affected or '---'} \\\\")
                    L.append(r"\midrule")
                L.append(r"\end{longtable}")

        # ── Quality Metrics ───────────────────────────────────────────────
        if "quality" in sections:
            L.append(r"\section{Quality Metrics}")
            total_reqs = len(self.reqs)
            quality: dict[str, int] = {"description": 0, "rationale": 0, "source": 0, "allocation": 0, "traceability": 0}
            for r in self.reqs:
                if r.get("description", "").strip(): quality["description"] += 1
                if r.get("rationale", "").strip(): quality["rationale"] += 1
                if r.get("source", "").strip(): quality["source"] += 1
                if r.get("allocated_to", "").strip(): quality["allocation"] += 1
                if r.get("relations"): quality["traceability"] += 1
            L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.38\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.31\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.31\textwidth-2\tabcolsep\relax}@{}}")
            L.append(r"\toprule")
            L.append(r"\rowcolor{tabhead}")
            L.append(r"\textbf{Metric} & \textbf{Count} & \textbf{Percentage} \\")
            L.append(r"\midrule")
            L.append(r"\endfirsthead")
            L.append(r"\toprule")
            L.append(r"\rowcolor{tabhead}")
            L.append(r"\textbf{Metric} & \textbf{Count} & \textbf{Percentage} \\")
            L.append(r"\midrule")
            L.append(r"\endhead")
            L.append(r"\bottomrule")
            L.append(r"\endfoot")
            for key, cnt in quality.items():
                pct = round(cnt / total_reqs * 100) if total_reqs else 0
                display = key.replace("_", " ").title()
                L.append(f"{_latex_escape(display)} & {cnt} / {total_reqs} & {pct}\\% \\\\")
                L.append(r"\midrule")
            L.append(r"\end{longtable}")

        # ── Gap Analysis ──────────────────────────────────────────────────
        if "gaps" in sections:
            L.append(r"\section{Gap Analysis}")
            gaps = []
            for r in self.reqs:
                issues = []
                if not r.get("description", "").strip(): issues.append("no_description")
                if not r.get("rationale", "").strip(): issues.append("no_rationale")
                if not r.get("source", "").strip(): issues.append("no_source")
                if not r.get("relations"): issues.append("unlinked")
                if issues:
                    gaps.append({"id": r["id"], "name": r.get("name", ""), "issues": issues})
            if gaps:
                L.append(f"{len(gaps)} requirements with issues.")
                L.append(r"\vspace{1em}")
                L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.14\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.30\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.56\textwidth-2\tabcolsep\relax}@{}}")
                L.append(r"\toprule")
                L.append(r"\rowcolor{tabhead}")
                L.append(r"\textbf{ID} & \textbf{Name} & \textbf{Issues} \\")
                L.append(r"\midrule")
                L.append(r"\endfirsthead")
                L.append(r"\toprule")
                L.append(r"\rowcolor{tabhead}")
                L.append(r"\textbf{ID} & \textbf{Name} & \textbf{Issues} \\")
                L.append(r"\midrule")
                L.append(r"\endhead")
                L.append(r"\bottomrule")
                L.append(r"\endfoot")
                for g in gaps:
                    rid = _latex_escape(g["id"])
                    name = _latex_escape(g["name"])
                    issues_str = _latex_escape(", ".join(i.replace("_", " ") for i in g["issues"]))
                    L.append(f"\\texttt{{{rid}}} & {name} & {issues_str} \\\\")
                    L.append(r"\midrule")
                L.append(r"\end{longtable}")
            else:
                L.append(r"No gaps detected.")

        # ── Decisions ────────────────────────────────────────────────────
        if "decisions" in sections:
            decisions = self.store.list_items("decisions")
            if decisions:
                L.append(r"\section{Design Decisions}")
                L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.12\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.22\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.26\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.26\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.14\textwidth-2\tabcolsep\relax}@{}}")
                L.append(r"\toprule")
                L.append(r"\rowcolor{tabhead}")
                L.append(r"\textbf{ID} & \textbf{Title} & \textbf{Decision} & \textbf{Rationale} & \textbf{Status} \\")
                L.append(r"\midrule")
                L.append(r"\endfirsthead")
                L.append(r"\toprule")
                L.append(r"\rowcolor{tabhead}")
                L.append(r"\textbf{ID} & \textbf{Title} & \textbf{Decision} & \textbf{Rationale} & \textbf{Status} \\")
                L.append(r"\midrule")
                L.append(r"\endhead")
                L.append(r"\bottomrule")
                L.append(r"\endfoot")
                for d in decisions:
                    did = _latex_escape(d["id"])
                    title = _latex_escape(d.get("title", ""))
                    decision = _latex_escape(_truncate_words(self._resolve(d.get("decision", "")), 200))
                    rationale = _latex_escape(_truncate_words(self._resolve(d.get("rationale", "")), 200))
                    status = d.get("status", "open")
                    L.append(f"\\texttt{{{did}}} & {title} & {decision} & {rationale} & \\statusbadge{{{_latex_escape(status)}}} \\\\")
                    L.append(r"\midrule")
                L.append(r"\end{longtable}")

        # ── Appendices ────────────────────────────────────────────────────
        # Reference/supporting material becomes lettered appendices (A, B, …).
        appendix_ids = {"glossary", "conflicts", "parameters", "verification_details", "system_states"}
        if appendix_ids & set(sections):
            L.append(r"\clearpage")
            L.append(r"\appendix")
            L.append(r"\titleformat{\section}{\Large\bfseries\color{accentdark}}{Appendix~\thesection}{0.6em}{}"
                     r"[{\vspace{2pt}\color{accent}\titlerule[1.2pt]}]")

        # ── Glossary ──────────────────────────────────────────────────────
        if "glossary" in sections:
            L.append(r"\section{Glossary}")
            L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.25\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.75\textwidth-2\tabcolsep\relax}@{}}")
            L.append(r"\toprule")
            L.append(r"\rowcolor{tabhead}")
            L.append(r"\textbf{Term} & \textbf{Definition} \\")
            L.append(r"\midrule")
            L.append(r"\endfirsthead")
            L.append(r"\toprule")
            L.append(r"\rowcolor{tabhead}")
            L.append(r"\textbf{Term} & \textbf{Definition} \\")
            L.append(r"\midrule")
            L.append(r"\endhead")
            L.append(r"\bottomrule")
            L.append(r"\endfoot")
            glossary_terms = [
                ("Requirement", "A statement that identifies a product or process operational, functional, or design characteristic or constraint, which is unambiguous, testable or measurable, and necessary for product or process acceptability."),
                ("Verification Case", "A defined set of actions, conditions, and expected results used to confirm that a requirement has been correctly implemented."),
                ("Component", "A discrete element of a system that can be implemented, tested, and maintained independently."),
                ("Specification", "A detailed description of the requirements, design, behavior, or characteristics of a system or component."),
                ("Baseline", "A formally approved version of a configuration item that serves as the basis for further development."),
                ("Traceability", "The ability to link requirements to their sources, derived requirements, and related verification cases throughout the project lifecycle."),
                ("Stakeholder Need", "A capability or condition that a stakeholder expects a system to provide or satisfy, per ISO/IEC 15288:2023."),
                ("System Requirement", "A formal statement that defines what a system must do, how it must perform, and the constraints it must satisfy."),
                ("MoE", "Measure of Effectiveness -- operational measures that reflect how well the system achieves its intended purpose in its intended environment."),
                ("MoP", "Measure of Performance -- physical or engineering measures that characterize system performance attributes."),
                ("TPM", "Technical Performance Measure -- quantitative metrics used to track technical progress and predict achievement of requirements."),
                ("Verification", "Confirmation through objective evidence that specified requirements have been fulfilled."),
                ("Validation", "Confirmation through objective evidence that the system meets the needs of its intended users and stakeholders."),
                ("PDR", "Preliminary Design Review -- a technical review held early in development to assess design maturity and alignment with requirements."),
                ("CDR", "Critical Design Review -- a technical review confirming the design is sufficiently mature to proceed to implementation."),
                ("TRR", "Test Readiness Review -- a review held to verify that the system is ready to enter formal testing."),
            ]
            for term, definition in glossary_terms:
                L.append(f"\\textbf{{{_latex_escape(term)}}} & {_latex_escape(definition)} \\\\")
                L.append(r"\midrule")
            L.append(r"\end{longtable}")

        # ── Conflicts ─────────────────────────────────────────────────────
        if "conflicts" in sections:
            conflicts: list[dict[str, Any]] = []
            dupes: dict[str, list[str]] = {}
            for r in self.reqs:
                name = r.get("name", "").strip().lower()
                if name:
                    dupes.setdefault(name, []).append(r["id"])
            for name, ids in dupes.items():
                if len(ids) > 1:
                    conflicts.append({"type": "duplicate_name", "name": name, "ids": ids})
            for r in self.reqs:
                for rel in r.get("relations", []):
                    if rel["type"] == "conflicts":
                        conflicts.append({"type": "explicit_conflict", "a": r["id"], "b": rel["target"]})
            if conflicts:
                L.append(r"\section{Conflicts}")
                L.append(f"{len(conflicts)} conflicts detected.")
                L.append(r"\vspace{1em}")
                for c in conflicts:
                    if c["type"] == "duplicate_name":
                        ids_str = _latex_escape(", ".join(c.get("ids", [])))
                        name_str = _latex_escape(c.get("name", ""))
                        L.append(f"\\textbf{{Duplicate name:}} \\texttt{{{name_str}}} -- IDs: \\texttt{{{ids_str}}}")
                    else:
                        a = _latex_escape(c.get("a", ""))
                        b = _latex_escape(c.get("b", ""))
                        L.append(f"\\textbf{{Conflict:}} \\texttt{{{a}}} $\\leftrightarrow$ \\texttt{{{b}}}")
                    L.append(r"")

        # ── Parameters & Constraints ──────────────────────────────────────
        if "parameters" in sections:
            L.append(r"\section{Parameters \& Constraints}")
            has_any = False
            for r in self.reqs:
                req_params = r.get("parameters", [])
                req_constraints = r.get("constraints", [])
                if not req_params and not req_constraints:
                    continue
                has_any = True
                rid = _latex_escape(r["id"])
                name = _latex_escape(r.get("name", "Untitled"))
                L.append(f"\\subsection*{{{rid} -- {name}}}")
                if req_params:
                    L.append(r"\textbf{Parameters}")
                    L.append(r"\vspace{0.3em}")
                    L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.20\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.18\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.14\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.48\textwidth-2\tabcolsep\relax}@{}}")
                    L.append(r"\toprule")
                    L.append(r"\rowcolor{tabhead}")
                    L.append(r"\textbf{Name} & \textbf{Value} & \textbf{Unit} & \textbf{Expression} \\")
                    L.append(r"\midrule")
                    L.append(r"\endhead")
                    L.append(r"\bottomrule")
                    L.append(r"\endfoot")
                    for p in req_params:
                        pname = _latex_escape(p.get("name", ""))
                        pval = _latex_escape(str(p.get("value", "")))
                        punit = _latex_escape(p.get("unit", ""))
                        pexpr = _latex_escape(p.get("expression", ""))
                        L.append(f"{pname} & {pval} & {punit} & {pexpr} \\\\")
                        L.append(r"\midrule")
                    L.append(r"\end{longtable}")
                if req_constraints:
                    L.append(r"\textbf{Constraints}")
                    L.append(r"\vspace{0.3em}")
                    L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.64\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.36\textwidth-2\tabcolsep\relax}@{}}")
                    L.append(r"\toprule")
                    L.append(r"\rowcolor{tabhead}")
                    L.append(r"\textbf{Expression} & \textbf{Status} \\")
                    L.append(r"\midrule")
                    L.append(r"\endhead")
                    L.append(r"\bottomrule")
                    L.append(r"\endfoot")
                    for con in req_constraints:
                        cexpr = _latex_escape(con.get("expression", ""))
                        cstatus = con.get("status", "pending")
                        L.append(f"{cexpr} & \\statusbadge{{{_latex_escape(cstatus)}}} \\\\")
                        L.append(r"\midrule")
                    L.append(r"\end{longtable}")
                L.append(r"\vspace{1em}")
            if not has_any:
                L.append(r"No requirements with parameters or constraints defined.")
            L.append(r"\newpage")

        # ── Verification Details ──────────────────────────────────────────
        if "verification_details" in sections:
            L.append(r"\section{Verification Details}")
            for vc in self.vcs:
                vid = _latex_escape(vc["id"])
                name = _latex_escape(vc.get("name", ""))
                method = _latex_escape(vc.get("method", ""))
                status = vc.get("status", "pending")
                L.append(f"\\subsection*{{{vid} -- {name}}}")
                L.append(f"\\textbf{{Method:}} {method}")
                L.append(f"\\textbf{{Status:}} \\statusbadge{{{_latex_escape(status)}}}")
                L.append(r"")
                steps = vc.get("test_steps", [])
                if steps:
                    L.append(r"\textbf{Test Steps}")
                    L.append(r"\vspace{0.3em}")
                    L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.38\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.31\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.31\textwidth-2\tabcolsep\relax}@{}}")
                    L.append(r"\toprule")
                    L.append(r"\rowcolor{tabhead}")
                    L.append(r"\textbf{Action} & \textbf{Expected Result} & \textbf{Actual Result} \\")
                    L.append(r"\midrule")
                    L.append(r"\endhead")
                    L.append(r"\bottomrule")
                    L.append(r"\endfoot")
                    for step in steps:
                        action = _latex_escape(step.get("action", ""))
                        expected = _latex_escape(step.get("expected_result", ""))
                        actual = _latex_escape(step.get("actual_result", ""))
                        L.append(f"{action} & {expected} & {actual} \\\\")
                        L.append(r"\midrule")
                    L.append(r"\end{longtable}")
                history = vc.get("execution_history", [])
                if history:
                    L.append(r"\textbf{Execution History}")
                    L.append(r"\vspace{0.3em}")
                    L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.18\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.18\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.28\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.18\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.18\textwidth-2\tabcolsep\relax}@{}}")
                    L.append(r"\toprule")
                    L.append(r"\rowcolor{tabhead}")
                    L.append(r"\textbf{Timestamp} & \textbf{Status} & \textbf{Notes} & \textbf{Executor} & \textbf{Duration} \\")
                    L.append(r"\midrule")
                    L.append(r"\endhead")
                    L.append(r"\bottomrule")
                    L.append(r"\endfoot")
                    for h in history:
                        ts = _latex_escape(h.get("timestamp", ""))
                        hstatus = h.get("status", "pending")
                        notes = _latex_escape(_truncate_words(h.get("notes", ""), 120))
                        executor = _latex_escape(h.get("executor", ""))
                        duration = _latex_escape(str(h.get("duration", "")))
                        L.append(f"{ts} & \\statusbadge{{{_latex_escape(hstatus)}}} & {notes} & {executor} & {duration} \\\\")
                        L.append(r"\midrule")
                    L.append(r"\end{longtable}")
                if not steps and not history:
                    L.append(r"No test steps or execution history defined.")
                L.append(r"\vspace{1em}")
            L.append(r"\newpage")

        # ── System States ─────────────────────────────────────────────────
        if "system_states" in sections:
            L.append(r"\section{System States}")
            state_map: dict[str, list[str]] = {}
            for r in self.reqs:
                for s in r.get("system_states", []):
                    state_map.setdefault(s, []).append(r["id"])
            if state_map:
                L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.25\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.75\textwidth-2\tabcolsep\relax}@{}}")
                L.append(r"\toprule")
                L.append(r"\rowcolor{tabhead}")
                L.append(r"\textbf{System State} & \textbf{Requirements} \\")
                L.append(r"\midrule")
                L.append(r"\endfirsthead")
                L.append(r"\toprule")
                L.append(r"\rowcolor{tabhead}")
                L.append(r"\textbf{System State} & \textbf{Requirements} \\")
                L.append(r"\midrule")
                L.append(r"\endhead")
                L.append(r"\bottomrule")
                L.append(r"\endfoot")
                for state, rids in sorted(state_map.items()):
                    sname = _latex_escape(state)
                    rids_str = _latex_escape(", ".join(rids))
                    L.append(f"{sname} & {rids_str} \\\\")
                    L.append(r"\midrule")
                L.append(r"\end{longtable}")
            else:
                L.append(r"No system states defined.")
            L.append(r"\newpage")

        L.append(r"\end{document}")
        return "\n".join(L)

    def to_html_string(self) -> str:
        return self.build_html()

    def to_html_file(self, path: str) -> str:
        html = self.build_html()
        with open(path, "w") as f:
            f.write(html)
        return path

    def to_pdf_file(self, path: str) -> str:
        """Render the report to PDF.

        Preferred path: typeset the LaTeX report (``build_latex``) with a real
        LaTeX engine, which gives proper tables, coloured status/priority badges
        and a table of contents. If no engine is installed — or the compile
        fails — fall back to the weasyprint HTML→PDF renderer so PDF export
        always works, just without the LaTeX polish.

        The fallback stays because the engine is not guaranteed to be there:
        both images download tectonic at build time and both tolerate that
        download failing (``backend/Dockerfile:17``, ``Dockerfile.prod:47``),
        and a bare-metal install may have no engine at all. Raising instead
        would turn "the PDF looks plainer" into "there is no PDF".

        What it must not be is *quiet*. A degraded render used to be
        indistinguishable from a good one, so a LaTeX compile that had been
        failing for months looked like a working export — which is how the
        badge-escaping bug survived. ``compile_latex_to_pdf`` logs the engine's
        own diagnostics; the warning here records that the document actually
        handed back is the fallback.
        """
        result = compile_latex_to_pdf_detailed(self.build_latex(), path)
        if result.ok:
            if result.watermark_omitted:
                logger.warning(
                    "DRAFT watermark omitted from %s: the draftwatermark TeX "
                    "package is unavailable, so the report rendered without its "
                    "DRAFT mark. Warm the cache (backend/scripts/warm_tectonic.py) "
                    "to restore it.",
                    path,
                )
            return path
        logger.warning(
            "LaTeX PDF render failed; falling back to the weasyprint HTML "
            "renderer for %s. The document will lack tables, badges and a "
            "table of contents. See the log above for the engine's output.",
            path,
        )
        from weasyprint import HTML as WHTML
        from app.services.sanitize import safe_url_fetcher
        WHTML(
            string=self.build_html(),
            url_fetcher=safe_url_fetcher(),
        ).write_pdf(path)
        return path

    def to_markdown_file(self, path: str) -> str:
        md = self.build_markdown()
        with open(path, "w") as f:
            f.write(md)
        return path

    def to_latex_file(self, path: str) -> str:
        latex = self.build_latex()
        with open(path, "w") as f:
            f.write(latex)
        return path
