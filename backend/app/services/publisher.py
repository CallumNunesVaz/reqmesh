from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape as esc

from app.core.config import settings as global_settings


def _latex_escape(text: str) -> str:
    text = text.replace("\\", "\x00")
    for char, repl in (
        ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"), ("_", r"\_"),
        ("{", r"\{"), ("}", r"\}"),
        ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}"),
    ):
        text = text.replace(char, repl)
    return text.replace("\x00", r"\textbackslash{}")


# ── CSS with page-margin boxes (headers / footers) ────────────────────────────

CSS = """
@page {
  size: A4;
  margin: 2.5cm 2cm 3cm 2cm;
  @top-center {
    content: string(doc-header);
    font-family: 'Segoe UI', system-ui, sans-serif;
    font-size: 8pt;
    color: #94a3b8;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 4px;
    margin-bottom: 8px;
  }
  @bottom-center {
    content: counter(page);
    font-family: 'Segoe UI', system-ui, sans-serif;
    font-size: 8pt;
    color: #94a3b8;
    border-top: 1px solid #e2e8f0;
    padding-top: 4px;
  }
  @bottom-left {
    content: string(doc-footer);
    font-family: 'Segoe UI', system-ui, sans-serif;
    font-size: 7pt;
    color: #cbd5e1;
  }
}
@page :first {
  @top-center { content: none; border: none; }
  @bottom-center { content: none; border: none; }
  @bottom-left { content: none; }
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', system-ui, sans-serif; color: #1a1a2e; font-size: 11pt; line-height: 1.5; }
.cover { text-align: center; padding: 140px 0 60px; page-break-after: always; }
.cover .logo { max-width: 200px; max-height: 80px; margin-bottom: 24px; }
.cover h1 { font-size: 28pt; font-weight: 800; color: #1a1a2e; margin-bottom: 8px; }
.cover h2 { font-size: 14pt; font-weight: 400; color: #64748b; margin-bottom: 8px; }
.cover .company { font-size: 12pt; color: #475569; margin-bottom: 4px; }
.cover .dept { font-size: 10pt; color: #94a3b8; }
.cover .meta { margin-top: 60px; font-size: 10pt; color: #94a3b8; }
.cover .meta span { display: block; margin: 4px 0; }
.toc { page-break-after: always; }
.toc h1 { font-size: 18pt; font-weight: 700; color: #0f172a; margin: 0 0 16px; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; page-break-before: avoid; }
.toc ul { list-style: none; padding-left: 0; }
.toc li { padding: 4px 0; font-size: 10pt; }
.toc li a { color: #334155; text-decoration: none; }
.toc li a::after { content: leader('. ') target-counter(attr(href), page); }
.toc li.toc-h1 { font-weight: 600; font-size: 11pt; margin-top: 6px; }
.toc li.toc-h2 { padding-left: 16px; color: #64748b; }
.toc li.toc-h3 { padding-left: 32px; font-size: 9pt; color: #94a3b8; }
h1 { font-size: 18pt; font-weight: 700; color: #0f172a; margin: 32px 0 12px; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; page-break-before: always; string-set: doc-header content(); }
h1:first-of-type { page-break-before: avoid; }
h2 { font-size: 14pt; font-weight: 600; color: #334155; margin: 20px 0 8px; }
h3 { font-size: 12pt; font-weight: 600; color: #475569; margin: 14px 0 6px; }
table { width: 100%; border-collapse: collapse; margin: 10px 0 18px; font-size: 9.5pt; }
th { background: #f1f5f9; font-weight: 600; text-align: left; padding: 8px 10px; border-bottom: 2px solid #cbd5e1; text-transform: uppercase; font-size: 8pt; letter-spacing: 0.5px; color: #64748b; }
td { padding: 6px 10px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
tr:nth-child(even) td { background: #f8fafc; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 8pt; font-weight: 600; text-transform: uppercase; }
.badge-proposed { background: #dbeafe; color: #1d4ed8; }
.badge-approved { background: #dcfce7; color: #16a34a; }
.badge-implemented { background: #f3e8ff; color: #9333ea; }
.badge-verified { background: #d1fae5; color: #059669; }
.badge-rejected { background: #fee2e2; color: #dc2626; }
.badge-high { border-left: 3px solid #f59e0b; padding-left: 6px; }
.badge-critical { border-left: 3px solid #ef4444; padding-left: 6px; }
.badge-passed { background: #dcfce7; color: #16a34a; }
.badge-failed { background: #fee2e2; color: #dc2626; }
.badge-pending { background: #fef3c7; color: #d97706; }
.desc { font-size: 10pt; color: #475569; margin: 4px 0; }
.field { margin: 4px 0; font-size: 9pt; }
.field strong { color: #64748b; width: 120px; display: inline-block; }
a.entity-link { color: #2563eb; text-decoration: none; font-family: monospace; font-size: 9pt; }
a.entity-link:hover { text-decoration: underline; }
.matrix td { text-align: center; }
.matrix td.link { background: #dbeafe; font-weight: 600; }
.matrix td.link a { color: #1d4ed8; text-decoration: none; }
.matrix td.no-link { color: #cbd5e1; }
.relations { margin: 8px 0; }
.rel-item { display: inline-block; padding: 3px 10px; margin: 2px 4px 2px 0; border-radius: 4px; font-size: 8.5pt; background: #f1f5f9; }
.rel-item a { color: #2563eb; text-decoration: none; }
.gap-warn { background: #fef3c7; border-left: 3px solid #f59e0b; padding: 8px 12px; margin: 6px 0; font-size: 9pt; }
.gap-warn .issues { color: #d97706; font-weight: 600; }
.conflict-item { background: #fee2e2; border-left: 3px solid #ef4444; padding: 8px 12px; margin: 6px 0; font-size: 9pt; }
.risk-sev-critical { background: #fee2e2; }
.risk-sev-high { background: #fef3c7; }
.risk-sev-medium { background: #f1f5f9; }
.summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin: 16px 0; }
.summary-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 16px; text-align: center; }
.summary-card .num { font-size: 22pt; font-weight: 800; color: #0f172a; }
.summary-card .label { font-size: 8pt; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }
.chart-bar { display: flex; align-items: center; margin: 6px 0; font-size: 9pt; }
.chart-bar .label { width: 140px; text-align: right; padding-right: 10px; color: #64748b; }
.chart-bar .bar-bg { flex: 1; background: #f1f5f9; border-radius: 3px; height: 16px; overflow: hidden; }
.chart-bar .bar-fill { height: 100%; border-radius: 3px; }
.chart-bar .pct { margin-left: 8px; font-size: 9pt; color: #64748b; width: 36px; }
.quality-row { margin: 4px 0; display: flex; align-items: center; }
.quality-row .q-label { width: 140px; text-align: right; padding-right: 10px; font-size: 9pt; color: #64748b; }
.quality-row .q-bar { flex: 1; background: #f1f5f9; border-radius: 3px; height: 12px; overflow: hidden; }
.quality-row .q-fill { height: 100%; border-radius: 3px; }
.page-break { page-break-before: always; }
"""


class Publisher:
    def __init__(self, store, subsystems: list[str] | None = None):
        self.store = store
        self.project_id = store.root.name
        self.meta = store.read_meta()
        all_reqs = store.list_requirements()
        self.vcs = store.list_verification_cases()
        self.specs = store.list_specifications()
        self.components = store.list_components()
        self.traces = store.read_traces()
        self.now = datetime.now(timezone.utc)
        self.now_str = self.now.strftime("%Y-%m-%d %H:%M UTC")
        self._toc = []  # list of (level, label, anchor) for TOC

        if subsystems:
            ids = set()
            def collect(root_id):
                ids.add(root_id)
                for r in all_reqs:
                    if r.get("parent") == root_id:
                        collect(r["id"])
            for sid in subsystems:
                collect(sid)
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

    # ── Helpers ─────────────────────────────────────────────────────────────────

    def _badge(self, status: str) -> str:
        return f'<span class="badge badge-{esc(status, quote=True)}">{esc(status)}</span>'

    def _link(self, entity_id: str, label: str | None = None) -> str:
        """Hyperlink to a requirement, VC, component, spec, or risk by ID."""
        display = label or entity_id
        if entity_id in self._all_req_ids:
            return f'<a class="entity-link" href="#req-{esc(entity_id, quote=True)}">{esc(display)}</a>'
        if entity_id in self._vc_by_id:
            return f'<a class="entity-link" href="#vc-{esc(entity_id, quote=True)}">{esc(display)}</a>'
        if entity_id in self._comp_by_id:
            return f'<a class="entity-link" href="#comp-{esc(entity_id, quote=True)}">{esc(display)}</a>'
        if entity_id in self._spec_by_id:
            return f'<a class="entity-link" href="#spec-{esc(entity_id, quote=True)}">{esc(display)}</a>'
        return esc(display)

    def _anchor(self, prefix: str, entity_id: str) -> str:
        return f'id="{prefix}-{esc(entity_id, quote=True)}"'

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
        if show_git:
            import subprocess
            try:
                sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                              cwd=str(self.store.root), stderr=subprocess.DEVNULL).decode().strip()
                footer = f"rev {sha} · {footer}"
            except Exception:
                pass

        return {
            "logo_url": logo_url,
            "company": company,
            "dept": dept,
            "title": title,
            "header_str": header_str,
            "footer_str": footer,
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
        elif logo:
            logo_html = f'<img class="logo" src="{esc(logo)}" alt="Logo" />'

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
        vc_failed = sum(1 for v in self.vcs if v.get("status") == "failed")
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
                desc = r.get("description", "").replace("<p>", "").replace("</p>", "")
                relations = r.get("relations", [])
                attrs = r.get("attributes", [])

                rel_html = ""
                for rel in relations:
                    rel_html += f'<span class="rel-item"><span class="type">{esc(rel["type"])}</span> → {self._link(rel["target"])}</span>'

                attr_html = ""
                for a in attrs:
                    attr_html += f'<span style="margin-right:8px;font-size:9pt;"><strong>{esc(a["key"])}:</strong> {esc(a["value"])}</span>'

                rationale = esc(r.get("rationale", ""))
                source = esc(r.get("source", ""))
                allocated = esc(r.get("allocated_to", ""))
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
            <p class="desc">{esc(spec.get('description', '')[:300])}</p>
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
        html = '<table><thead><tr><th>ID</th><th>Title</th><th>Severity</th><th>Probability</th><th>Status</th></tr></thead><tbody>'
        for r in risks:
            sev = esc(r.get("severity", "medium"), quote=True)
            html += f"""<tr class="risk-sev-{sev}">
              <td style="font-family:monospace;">{esc(r['id'])}</td>
              <td>{esc(r.get('title',''))}</td>
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
        crs = self.store.list_items("change-requests")
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

    def build_html(self, sections: list | None = None) -> str:
        if sections is None:
            sections = ["cover", "summary", "requirements", "components", "specifications",
                        "verification", "traceability", "quality", "gaps", "risks", "changes", "conflicts"]

        hdr = self._header_config()
        project_name = esc(self.meta.get("name", self.project_id))
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
<style>{CSS}
@page {{{header_css}{footer_css}}}
</style></head><body>
"""

        if "cover" in sections:
            html += self._cover(hdr)

        if "summary" in sections:
            html += self._summary_section()

        html += self._toc_html()

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
            html += f'<h1 id="sec-verification">Verification Cases</h1>'
            self._add_toc(1, "Verification Cases", "sec-verification")
            html += self._vc_table()

        if "traceability" in sections:
            html += f'<h1 id="sec-traces">Traceability Matrix</h1>'
            self._add_toc(1, "Traceability Matrix", "sec-traces")
            html += self._trace_matrix()

        if "quality" in sections:
            html += f'<h1 id="sec-quality">Quality Metrics</h1>'
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
                html += f'<h1 id="sec-gaps">Gap Analysis</h1>'
                self._add_toc(1, "Gap Analysis", "sec-gaps")
                html += f'<p style="color:#64748b;font-size:10pt;">{len(gaps)} requirements with issues</p>'
                html += self._gaps_section(gaps)

        if "risks" in sections:
            risks = self.store.list_items("risks")
            if risks:
                html += f'<h1 id="sec-risks">Risk Register</h1>'
                self._add_toc(1, "Risk Register", "sec-risks")
                html += self._risk_table(risks)

        if "changes" in sections:
            html += self._changes_section()

        if "conflicts" in sections:
            conflicts = []
            dupes = {}
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
                html += f'<h1 id="sec-conflicts">Conflicts</h1>'
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
            desc = r.get("description", "").replace("<p>", "").replace("</p>", "").replace("<br>", "\n")
            if desc.strip():
                md += f"{desc}\n\n"
            if r.get("rationale"):
                md += f"**Rationale:** {r['rationale']}\n\n"
            if r.get("source"):
                md += f"**Source:** {r['source']}\n\n"
            rels = r.get("relations", [])
            if rels:
                md += "**Relations:** "
                md += ", ".join(f"{rel['type']}→{rel['target']}" for rel in rels)
                md += "\n\n"
            parent = r.get("parent")
            if parent:
                md += f"**Parent:** {parent}\n\n"
        return md

    def build_latex(self) -> str:
        import os as _os
        latex = r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{geometry}
\geometry{a4paper, margin=1in}
\usepackage{xcolor}
\usepackage{fancyhdr}
\usepackage{hyperref}
\usepackage{longtable}
\usepackage{tocloft}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[C]{""" + _latex_escape(getattr(global_settings, "report_company_name", "") or "") + r"""}
\fancyfoot[C]{\thepage}
\renewcommand{\headrulewidth}{0.4pt}
\renewcommand{\footrulewidth}{0.4pt}
\definecolor{prop}{RGB}{59,130,246}
\definecolor{appr}{RGB}{34,197,94}
\definecolor{impl}{RGB}{168,85,247}
\definecolor{veri}{RGB}{16,185,129}
\definecolor{rej}{RGB}{239,68,68}
\title{""" + _latex_escape(self.meta.get("name", self.project_id)) + r"""}
\date{""" + self.now.strftime("%Y-%m-%d") + r"""}
\begin{document}
\maketitle
\tableofcontents
\newpage
\section{Requirements}"""
        for r in self.reqs:
            status = r.get("status", "proposed")
            latex += f"\n\n\\subsection{{{_latex_escape(r['id'])} — {_latex_escape(r.get('name','Untitled'))}}}\n"
            latex += f"\\label{{req-{r['id']}}}\n"
            desc = r.get("description", "").replace("<p>", "").replace("</p>", "")
            if desc.strip():
                latex += f"{_latex_escape(desc)}\n\n"
            latex += f"\\textbf{{Status:}} {_latex_escape(status)} \\hspace{{1em}} \\textbf{{Priority:}} {_latex_escape(r.get('priority','medium'))}\n"
            if r.get("rationale"):
                latex += f"\\textbf{{Rationale:}} {_latex_escape(r['rationale'])}\n"
        latex += "\n\\end{document}"
        return latex

    def to_html_string(self) -> str:
        return self.build_html()

    def to_html_file(self, path: str) -> str:
        html = self.build_html()
        with open(path, "w") as f:
            f.write(html)
        return path

    def to_pdf_file(self, path: str) -> str:
        from weasyprint import HTML as WHTML
        html = self.build_html()
        WHTML(string=html).write_pdf(path)
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
