from __future__ import annotations

import os
import uuid
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Template


CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', system-ui, sans-serif; color: #1a1a2e; font-size: 11pt; line-height: 1.5; padding: 40px 50px; }
.cover { text-align: center; padding: 120px 0 60px; page-break-after: always; }
.cover h1 { font-size: 28pt; font-weight: 800; color: #1a1a2e; margin-bottom: 8px; }
.cover h2 { font-size: 14pt; font-weight: 400; color: #64748b; }
.cover .meta { margin-top: 60px; font-size: 10pt; color: #94a3b8; }
.cover .meta span { display: block; margin: 4px 0; }
h1 { font-size: 18pt; font-weight: 700; color: #0f172a; margin: 32px 0 12px; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; page-break-before: always; }
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
.matrix td { text-align: center; }
.matrix td.link { background: #dbeafe; font-weight: 600; }
.matrix td.no-link { color: #cbd5e1; }
.relations { margin: 8px 0; }
.rel-item { display: inline-block; padding: 3px 10px; margin: 2px 4px 2px 0; border-radius: 4px; font-size: 8.5pt; background: #f1f5f9; }
.rel-item span.type { font-weight: 600; color: #6366f1; }
.gap-warn { background: #fef3c7; border-left: 3px solid #f59e0b; padding: 8px 12px; margin: 6px 0; font-size: 9pt; }
.gap-warn .issues { color: #d97706; font-weight: 600; }
.conflict-item { background: #fee2e2; border-left: 3px solid #ef4444; padding: 8px 12px; margin: 6px 0; font-size: 9pt; }
.risk-sev-critical { background: #fee2e2; }
.risk-sev-high { background: #fef3c7; }
.risk-sev-medium { background: #f1f5f9; }
.chart-bar { display: flex; align-items: center; margin: 6px 0; font-size: 9pt; }
.chart-bar .label { width: 140px; text-align: right; padding-right: 10px; color: #64748b; }
.chart-bar .bar-bg { flex: 1; background: #f1f5f9; border-radius: 3px; height: 16px; overflow: hidden; }
.chart-bar .bar-fill { height: 100%; border-radius: 3px; }
.quality-row { margin: 4px 0; display: flex; align-items: center; }
.quality-row .q-label { width: 140px; text-align: right; padding-right: 10px; font-size: 9pt; color: #64748b; }
.quality-row .q-bar { flex: 1; background: #f1f5f9; border-radius: 3px; height: 12px; overflow: hidden; }
.quality-row .q-fill { height: 100%; border-radius: 3px; }
.page-break { page-break-before: always; }
.footer { text-align: center; font-size: 8pt; color: #94a3b8; margin-top: 40px; border-top: 1px solid #e2e8f0; padding-top: 12px; }
"""


class Publisher:
    def __init__(self, store, subsystems: list[str] | None = None):
        self.store = store
        self.project_id = store.root.name
        self.meta = store.read_meta()
        all_reqs = store.list_requirements()
        self.vcs = store.list_verification_cases()
        self.specs = store.list_specifications()
        self.traces = store.read_traces()

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

    def _badge(self, status: str) -> str:
        return f'<span class="badge badge-{status}">{status}</span>'

    def _build_hierarchy(self, parent=None, depth=0):
        html = ""
        for r in self.reqs:
            if r.get("parent") == parent:
                indent = depth * 20
                desc = r.get("description", "").replace("<p>", "").replace("</p>", "")
                relations = r.get("relations", [])
                attrs = r.get("attributes", [])

                rel_html = ""
                for rel in relations:
                    rel_html += f'<span class="rel-item"><span class="type">{rel["type"]}</span> → {rel["target"]}</span>'

                attr_html = ""
                for a in attrs:
                    attr_html += f'<span style="margin-right:8px;font-size:9pt;"><strong>{a["key"]}:</strong> {a["value"]}</span>'

                rationale = r.get("rationale", "")
                source = r.get("source", "")
                allocated = r.get("allocated_to", "")
                baseline = r.get("baseline", "")

                html += f"""
                <div style="margin-left:{indent}px; margin-bottom:14px; padding:10px 14px; border-left:3px solid #e2e8f0; border-radius:0 6px 6px 0; background:#fff;">
                  <div style="font-weight:700; font-size:12pt; margin-bottom:2px;">
                    <span style="font-family:monospace; color:#64748b; font-size:10pt;">{r['id']}</span>
                    <span style="margin-left:6px;">{r.get('name', 'Untitled')}</span>
                    {self._badge(r.get('status','proposed'))}
                    <span class="badge badge-{r.get('priority','medium')}">{r.get('priority','medium')}</span>
                    {f'<span class="badge" style="background:#e0e7ff;color:#4338ca;">{r["type"].replace("_"," ")}</span>' if r.get('type') else ''}
                  </div>
                  {f'<div class="desc">{desc}</div>' if desc else ''}
                  {f'<div class="field"><strong>Rationale:</strong> {rationale}</div>' if rationale else ''}
                  {f'<div class="field"><strong>Source:</strong> {source}</div>' if source else ''}
                  {f'<div class="field"><strong>Allocated to:</strong> {allocated}</div>' if allocated else ''}
                  {f'<div class="field"><strong>Baseline:</strong> {baseline}</div>' if baseline else ''}
                  {attr_html and f'<div class="field">{attr_html}</div>'}
                  {rel_html and f'<div class="relations">{rel_html}</div>'}
                </div>"""
                html += self._build_hierarchy(r["id"], depth + 1)
        return html

    def _trace_matrix(self):
        req_ids = [r["id"] for r in self.reqs]
        vc_ids = [v["id"] for v in self.vcs]
        links_map = {}
        for t in self.traces.get("links", []):
            links_map.setdefault(t["source"], {})[t["target"]] = t["type"]
        for r in self.reqs:
            for rel in r.get("relations", []):
                links_map.setdefault(r["id"], {})[rel["target"]] = rel["type"]

        html = '<table class="matrix"><thead><tr><th></th>'
        for vc_id in vc_ids:
            html += f'<th>{vc_id}</th>'
        html += '</tr></thead><tbody>'
        for req in self.reqs:
            html += f'<tr><td style="font-weight:600;font-family:monospace;">{req["id"]}</td>'
            for vc_id in vc_ids:
                link = links_map.get(req["id"], {}).get(vc_id)
                if link:
                    html += f'<td class="link">{link}</td>'
                else:
                    html += '<td class="no-link">-</td>'
            html += '</tr>'
        html += '</tbody></table>'
        return html

    def _vc_table(self):
        html = '<table><thead><tr><th>ID</th><th>Name</th><th>Method</th><th>Status</th><th>Linked Reqs</th></tr></thead><tbody>'
        for vc in self.vcs:
            html += f"""<tr>
              <td style="font-family:monospace;">{vc['id']}</td>
              <td>{vc.get('name','')}</td>
              <td>{vc.get('method','')}</td>
              <td>{self._badge(vc.get('status','pending'))}</td>
              <td>{', '.join(vc.get('verified_requirements',[]))}</td>
            </tr>"""
        html += '</tbody></table>'
        return html

    def _quality_chart(self, metrics: dict):
        html = '<div>'
        for key, pct in metrics.get("quality_pct", {}).items():
            color = "#16a34a" if pct >= 80 else "#d97706" if pct >= 50 else "#dc2626"
            html += f'<div class="chart-bar"><div class="label">{key.replace("_"," ")}</div><div class="bar-bg"><div class="bar-fill" style="width:{pct}%;background:{color}"></div></div><span style="margin-left:8px;font-size:9pt;">{pct}%</span></div>'
        html += '</div>'
        return html

    def _gaps_section(self, gaps: list):
        html = ""
        for g in gaps:
            issues = ", ".join(i.replace("_", " ") for i in g["issues"])
            html += f'<div class="gap-warn"><strong>{g["id"]}</strong> - {g["name"]}: <span class="issues">{issues}</span></div>'
        return html

    def _risk_table(self, risks: list | None):
        if not risks:
            return ""
        html = '<table><thead><tr><th>ID</th><th>Title</th><th>Severity</th><th>Probability</th><th>Status</th></tr></thead><tbody>'
        for r in risks:
            sev = r.get("severity", "medium")
            html += f"""<tr class="risk-sev-{sev}">
              <td style="font-family:monospace;">{r['id']}</td>
              <td>{r.get('title','')}</td>
              <td><span class="badge badge-{sev}">{sev}</span></td>
              <td>{r.get('probability','')}</td>
              <td>{self._badge(r.get('status','open'))}</td>
            </tr>"""
        html += '</tbody></table>'
        return html

    def _conflicts_section(self, conflicts: list):
        html = ""
        for c in conflicts:
            if c["type"] == "duplicate_name":
                html += f'<div class="conflict-item"><strong>Duplicate name:</strong> "{c["name"]}" - IDs: {", ".join(c.get("ids",[]))}</div>'
            else:
                html += f'<div class="conflict-item"><strong>Conflict:</strong> {c.get("a","")} ↔ {c.get("b","")}</div>'
        return html

    def build_html(self, sections: list | None = None) -> str:
        if sections is None:
            sections = ["cover", "requirements", "verification", "traceability", "quality", "gaps", "risks", "conflicts"]

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        project_name = self.meta.get("name", self.project_id)

        html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>{project_name} - Requirements Report</title>
<style>{CSS}</style></head><body>
"""

        if "cover" in sections:
            html += f"""
            <div class="cover">
              <h1>{project_name}</h1>
              <h2>Requirements Specification Report</h2>
              <div class="meta">
                <span>Generated: {now}</span>
                <span>Project: {self.project_id}</span>
                <span>Requirements: {len(self.reqs)}</span>
                <span>Verification Cases: {len(self.vcs)}</span>
                <span>Baselines: {len(set(r.get('baseline','') for r in self.reqs if r.get('baseline')))}</span>
              </div>
            </div>"""

        if "requirements" in sections:
            html += f"""<h1>Requirements Hierarchy</h1>
            <p style="color:#64748b;font-size:10pt;margin-bottom:16px;">{len(self.reqs)} requirements across {len(set(r.get('parent') or 'root' for r in self.reqs))} groups</p>
            {self._build_hierarchy()}"""

        if "verification" in sections:
            html += f"""<h1>Verification Cases</h1>
            {self._vc_table()}"""

        if "traceability" in sections:
            html += f"""<h1>Traceability Matrix</h1>
            {self._trace_matrix()}"""

        if "quality" in sections:
            total = len(self.reqs)
            quality = {"description": 0, "rationale": 0, "source": 0, "allocation": 0, "traceability": 0}
            for r in self.reqs:
                if r.get("description", "").strip(): quality["description"] += 1
                if r.get("rationale", "").strip(): quality["rationale"] += 1
                if r.get("source", "").strip(): quality["source"] += 1
                if r.get("allocated_to", "").strip(): quality["allocation"] += 1
                if r.get("relations"): quality["traceability"] += 1
            qpct = {k: round(v/total*100) if total else 0 for k, v in quality.items()}
            html += f"""<h1>Quality Metrics</h1>
            {self._quality_chart({"quality_pct": qpct})}"""

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
                html += f"""<h1>Gap Analysis</h1>
                <p style="color:#64748b;font-size:10pt;">{len(gaps)} requirements with issues</p>
                {self._gaps_section(gaps)}"""

        if "risks" in sections:
            risks = self.store.list_items("risks")
            if risks:
                html += f"""<h1>Risk Register</h1>
                {self._risk_table(risks)}"""

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
                html += f"""<h1>Conflicts</h1>
                <p style="color:#64748b;font-size:10pt;">{len(conflicts)} conflicts detected</p>
                {self._conflicts_section(conflicts)}"""

        html += f'<div class="footer">Generated by reqmesh &mdash; {now}</div></body></html>'
        return html

    def build_markdown(self) -> str:
        md = f"# {self.meta.get('name', self.project_id)}\n\n"
        md += f"**Project:** {self.project_id}  \n"
        md += f"**Requirements:** {len(self.reqs)}  \n"
        md += f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n"
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
        latex = r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{geometry}
\geometry{a4paper, margin=1in}
\usepackage{xcolor}
\definecolor{prop}{RGB}{59,130,246}
\definecolor{appr}{RGB}{34,197,94}
\definecolor{impl}{RGB}{168,85,247}
\definecolor{veri}{RGB}{16,185,129}
\definecolor{rej}{RGB}{239,68,68}
\usepackage{longtable}
\usepackage{hyperref}
\title{""" + self.meta.get("name", self.project_id) + r"""}
\date{""" + datetime.now(timezone.utc).strftime("%Y-%m-%d") + r"""}
\begin{document}
\maketitle
\section{Requirements}"""
        for r in self.reqs:
            status = r.get("status", "proposed")
            latex += f"\n\n\\subsection{{{r['id']} — {r.get('name','Untitled')}}}\n"
            desc = r.get("description", "").replace("<p>", "").replace("</p>", "")
            if desc.strip():
                latex += f"{desc}\n\n"
            latex += f"\\textbf{{Status:}} {status} \\hspace{{1em}} \\textbf{{Priority:}} {r.get('priority','medium')}\n"
            if r.get("rationale"):
                latex += f"\\textbf{{Rationale:}} {r['rationale']}\n"
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
        # Imported lazily: weasyprint pulls in heavy system libraries, and the
        # rest of the API should work without PDF support installed.
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
