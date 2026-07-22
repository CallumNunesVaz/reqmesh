from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from html import escape as esc
from pathlib import Path

from app.core.config import settings as global_settings

logger = logging.getLogger(__name__)

# LaTeX engines we know how to drive, in order of preference. tectonic is a
# single self-contained binary that fetches its package bundle on demand, so it
# needs no full TeX Live install; the classic engines run two passes so the
# table of contents and longtables resolve.
_LATEX_ENGINES = ("tectonic", "pdflatex", "lualatex", "xelatex")


def latex_engine_available() -> str | None:
    """Return the name of the first available LaTeX engine, or None."""
    for engine in _LATEX_ENGINES:
        if shutil.which(engine):
            return engine
    return None


def compile_latex_to_pdf(latex: str, out_path: str) -> bool:
    """Compile a LaTeX document to ``out_path``.

    Returns True on success. Returns False (and logs a warning) if no engine is
    installed or the compile fails, so callers can fall back to another renderer
    rather than surface a hard error to the user.
    """
    engine = latex_engine_available()
    if engine is None:
        logger.warning("No LaTeX engine found (%s); cannot render PDF from LaTeX.",
                       ", ".join(_LATEX_ENGINES))
        return False
    with tempfile.TemporaryDirectory(prefix="reqmesh-tex-") as tmp:
        tmp_dir = Path(tmp)
        tex_file = tmp_dir / "report.tex"
        tex_file.write_text(latex, encoding="utf-8")
        if engine == "tectonic":
            cmds = [[engine, "--outdir", str(tmp_dir), "--chatter", "minimal",
                     str(tex_file)]]
        else:
            # Two passes so \tableofcontents and longtable column widths settle.
            base = [engine, "-interaction=nonstopmode", "-halt-on-error",
                    "-output-directory", str(tmp_dir), str(tex_file)]
            cmds = [base, base]
        try:
            for cmd in cmds:
                subprocess.run(cmd, cwd=tmp_dir, capture_output=True, timeout=120,
                               check=True)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            log = ""
            if isinstance(exc, subprocess.CalledProcessError) and exc.stdout:
                log = exc.stdout.decode("utf-8", "replace")[-2000:]
            logger.warning("LaTeX compile with %s failed: %s\n%s", engine, exc, log)
            return False
        pdf = tmp_dir / "report.pdf"
        if not pdf.exists():
            logger.warning("LaTeX compile with %s produced no PDF.", engine)
            return False
        shutil.copyfile(pdf, out_path)
        return True


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
    _all_latex_sections = [
        "traceability", "specifications", "baselines", "changes",
        "quality", "gaps", "decisions", "glossary", "conflicts",
        "parameters", "verification_details", "system_states",
    ]

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

    def build_latex(self, sections: list[str] | None = None) -> str:
        import os as _os
        if sections is None:
            sections = self._all_latex_sections
        hdr = self._header_config()
        project_name = _latex_escape(self.meta.get("name", self.project_id))
        company = _latex_escape(hdr["company"] or "\\mbox{}")
        dept = _latex_escape(hdr["dept"] or "\\mbox{}")
        doc_title = _latex_escape(hdr["title"] or "Requirements Specification Report")
        now_esc = _latex_escape(self.now_str)
        project_id_esc = _latex_escape(self.project_id)

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
        specs_count = len(self.specs)
        comps_count = len(self.components)
        risks_list = self.store.list_items("risks")
        risk_count = len(risks_list)

        L = []  # LaTeX lines

        L.append(r"\documentclass[11pt,a4paper]{article}")
        L.append(r"\usepackage[utf8]{inputenc}")
        L.append(r"\usepackage[T1]{fontenc}")
        L.append(r"\usepackage{geometry}")
        L.append(r"\geometry{margin=2.5cm}")
        L.append(r"\usepackage[table]{xcolor}")
        L.append(r"\usepackage{fancyhdr}")
        L.append(r"\usepackage{hyperref}")
        L.append(r"\hypersetup{colorlinks=true,linkcolor=black!60!blue,urlcolor=black!60!blue}")
        L.append(r"\usepackage{longtable}")
        L.append(r"\usepackage{booktabs}")
        L.append(r"\usepackage{tabularx}")
        L.append(r"\usepackage{tocloft}")
        L.append(r"\usepackage{titlesec}")
        L.append(r"\usepackage{parskip}")
        L.append(r"\usepackage{ifthen}")
        L.append(r"\pagestyle{fancy}")
        L.append(r"\fancyhf{}")
        L.append(f"\\fancyhead[L]{{\\small\\sffamily\\color{{gray}}{company}}}")
        L.append(f"\\fancyhead[R]{{\\small\\sffamily\\color{{gray}}{doc_title}}}")
        L.append(r"\fancyfoot[C]{\thepage}")
        L.append(r"\renewcommand{\headrulewidth}{0.4pt}")
        L.append(r"\renewcommand{\footrulewidth}{0.4pt}")

        # Colours
        L.append(r"\definecolor{prop}{RGB}{59,130,246}")
        L.append(r"\definecolor{appr}{RGB}{34,197,94}")
        L.append(r"\definecolor{impl}{RGB}{168,85,247}")
        L.append(r"\definecolor{veri}{RGB}{16,185,129}")
        L.append(r"\definecolor{rej}{RGB}{239,68,68}")
        L.append(r"\definecolor{depr}{RGB}{148,163,184}")
        L.append(r"\definecolor{prihigh}{RGB}{245,158,11}")
        L.append(r"\definecolor{pricrit}{RGB}{239,68,68}")
        L.append(r"\definecolor{prlow}{RGB}{148,163,184}")
        L.append(r"\definecolor{primed}{RGB}{59,130,246}")
        L.append(r"\definecolor{tabhead}{RGB}{241,245,249}")

        # Badge commands. String comparison is done with \ifthenelse/\equal
        # (ifthen package) rather than pdfTeX's \pdfstrcmp so the report compiles
        # under any engine — pdflatex, xelatex, lualatex, or tectonic.
        L.append(r"\newcommand{\statusbadge}[1]{%")
        L.append(r"  \ifthenelse{\equal{#1}{proposed}}{\colorbox{prop!20}{\textcolor{prop}{\textbf{\small #1}}}}{%")
        L.append(r"  \ifthenelse{\equal{#1}{approved}}{\colorbox{appr!20}{\textcolor{appr}{\textbf{\small #1}}}}{%")
        L.append(r"  \ifthenelse{\equal{#1}{implemented}}{\colorbox{impl!20}{\textcolor{impl}{\textbf{\small #1}}}}{%")
        L.append(r"  \ifthenelse{\equal{#1}{verified}}{\colorbox{veri!20}{\textcolor{veri}{\textbf{\small #1}}}}{%")
        L.append(r"  \ifthenelse{\equal{#1}{rejected}}{\colorbox{rej!20}{\textcolor{rej}{\textbf{\small #1}}}}{%")
        L.append(r"  \colorbox{tabhead}{\textcolor{depr}{\textbf{\small #1}}}}}}}}}")
        L.append(r"\newcommand{\prioritybadge}[1]{%")
        L.append(r"  \ifthenelse{\equal{#1}{critical}}{\textcolor{pricrit}{\textbf{#1}}}{%")
        L.append(r"  \ifthenelse{\equal{#1}{high}}{\textcolor{prihigh}{\textbf{#1}}}{%")
        L.append(r"  \ifthenelse{\equal{#1}{medium}}{\textcolor{primed}{\textbf{#1}}}{%")
        L.append(r"  \textcolor{prlow}{\textbf{#1}}}}}}")

        L.append(r"\begin{document}")

        # ── Title page ────────────────────────────────────────────────────
        L.append(r"\begin{titlepage}")
        L.append(r"\centering")
        L.append(r"\vspace*{4cm}")
        L.append(f"{{\\Huge\\bfseries {project_name}}}\\par")
        L.append(r"\vspace{1cm}")
        L.append(f"{{\\Large {doc_title}}}\\par")
        L.append(r"\vspace{1.5cm}")
        L.append(f"{{\\large {company}}}\\par")
        L.append(f"{{\\normalsize {dept}}}\\par")
        L.append(r"\vfill")
        L.append(f"{{\\normalsize Generated: {now_esc}}}\\par")
        L.append(f"{{\\normalsize Project: {project_id_esc}}}\\par")
        L.append(f"{{\\normalsize Requirements: {total}}}\\par")
        L.append(f"{{\\normalsize Verification Cases: {vc_count}}}\\par")
        L.append(r"\end{titlepage}")

        # ── Table of Contents ─────────────────────────────────────────────
        L.append(r"\tableofcontents")
        L.append(r"\newpage")

        # ── 1. Introduction ───────────────────────────────────────────────
        L.append(r"\section{Introduction}")
        L.append(r"This document presents the requirements specification for the")
        L.append(f"\\textbf{{{project_name}}} project.  It includes a project overview,")
        L.append(r"a categorised listing of all requirements organised by type, a component")
        L.append(r"inventory, verification cases, and the risk register.")
        L.append(r"")
        L.append(r"The requirements in this document follow the ISO/IEC 15288:2023 framework")
        L.append(r"for stakeholder needs and system requirements definition.")
        L.append(r"\newpage")

        # ── 2. Project Overview ───────────────────────────────────────────
        L.append(r"\section{Project Overview}")
        L.append(r"")
        L.append(r"\begin{tabularx}{\textwidth}{XXXX}")
        L.append(r"\hline")
        L.append(r"\rowcolor{tabhead}")
        L.append(r"\textbf{Requirements} & \textbf{Verification Cases} & \textbf{Components} & \textbf{Risks} \\")
        L.append(r"\hline")
        L.append(f"{total} & {vc_count} & {comps_count} & {risk_count} \\\\")
        L.append(r"\hline")
        L.append(r"\end{tabularx}")
        L.append(r"")
        L.append(r"\vspace{1em}")

        L.append(r"\subsection{Status Distribution}")
        L.append(r"\begin{tabularx}{\textwidth}{Xrr}")
        for label, count in sorted(status_dist.items(), key=lambda x: -x[1]):
            pct = round(count / total * 100) if total else 0
            L.append(f"  {_latex_escape(label.replace('_',' ').title())} & {count} & {pct}\\% \\\\")
        L.append(r"\end{tabularx}")
        L.append(r"\vspace{1em}")

        L.append(r"\subsection{Priority Distribution}")
        L.append(r"\begin{tabularx}{\textwidth}{Xrr}")
        for label, count in sorted(priority_dist.items(), key=lambda x: -x[1]):
            pct = round(count / total * 100) if total else 0
            L.append(f"  {_latex_escape(label.title())} & {count} & {pct}\\% \\\\")
        L.append(r"\end{tabularx}")
        L.append(r"\vspace{1em}")

        L.append(r"\subsection{Type Distribution}")
        L.append(r"\begin{tabularx}{\textwidth}{Xrr}")
        for label, count in sorted(type_dist.items(), key=lambda x: -x[1]):
            pct = round(count / total * 100) if total else 0
            display = label.replace('_', ' ').title()
            L.append(f"  {_latex_escape(display)} & {count} & {pct}\\% \\\\")
        L.append(r"\end{tabularx}")
        L.append(r"\newpage")

        # ── 3. Requirements by Type ───────────────────────────────────────
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
            L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{3cm} >{\raggedright\arraybackslash}p{3.5cm} >{\raggedright\arraybackslash}p{2cm} >{\raggedright\arraybackslash}p{2cm} >{\raggedright\arraybackslash}p{3cm}@{}}")
            L.append(r"\toprule")
            L.append(r"\rowcolor{tabhead}")
            L.append(r"\textbf{ID} & \textbf{Name} & \textbf{Status} & \textbf{Priority} & \textbf{Description} \\")
            L.append(r"\midrule")
            L.append(r"\endfirsthead")
            L.append(r"\toprule")
            L.append(r"\rowcolor{tabhead}")
            L.append(r"\textbf{ID} & \textbf{Name} & \textbf{Status} & \textbf{Priority} & \textbf{Description} \\")
            L.append(r"\midrule")
            L.append(r"\endhead")
            L.append(r"\bottomrule")
            L.append(r"\endfoot")

            for r in reqs_in_type:
                rid = _latex_escape(r["id"])
                name = _latex_escape(r.get("name", "Untitled"))
                status = r.get("status", "proposed")
                priority = r.get("priority", "medium")
                desc = _latex_escape(
                    r.get("description", "")
                    .replace("<p>", "").replace("</p>", "")
                    .replace("<br>", " ")
                    .replace("\n", " ")[:200]
                )
                rationale = _latex_escape(r.get("rationale", ""))
                source = _latex_escape(r.get("source", ""))
                allocated = _latex_escape(r.get("allocated_to", ""))
                baselines = ", ".join(r.get("baselines", []))

                extras = []
                if rationale:
                    extras.append(f"Rationale: {rationale}")
                if source:
                    extras.append(f"Source: {source}")
                if allocated:
                    extras.append(f"Allocated to: {allocated}")
                if baselines:
                    extras.append(f"Baselines: {_latex_escape(baselines)}")
                extra_str = " \\\\\n  \\textit{" + "}\\\\\n  \\textit{".join(extras) + "}" if extras else ""

                L.append(f"\\texttt{{{rid}}} & {name} & \\statusbadge{{{status}}} & \\prioritybadge{{{priority}}} & {desc}{extra_str} \\\\")
                L.append(r"\midrule")

            L.append(r"\end{longtable}")
            L.append(r"\newpage")

        # ── 4. Components ─────────────────────────────────────────────────
        if self.components:
            L.append(r"\section{Components}")
            L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{3cm} >{\raggedright\arraybackslash}p{3.5cm} >{\raggedright\arraybackslash}p{2.5cm} >{\raggedright\arraybackslash}p{3cm} >{\raggedright\arraybackslash}p{2cm}@{}}")
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
                cid = _latex_escape(c["id"])
                name = _latex_escape(c.get("name", ""))
                ctype = _latex_escape(c.get("type", "part"))
                pn = _latex_escape(c.get("part_number", ""))
                sat = _latex_escape(", ".join(c.get("satisfies", [])))
                L.append(f"\\texttt{{{cid}}} & {name} & {ctype} & \\texttt{{{pn}}} & {sat} \\\\")
                L.append(r"\midrule")
            L.append(r"\end{longtable}")
            L.append(r"\newpage")

        # ── 5. Verification Cases ─────────────────────────────────────────
        if self.vcs:
            L.append(r"\section{Verification Cases}")
            L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{2.5cm} >{\raggedright\arraybackslash}p{3cm} >{\raggedright\arraybackslash}p{2cm} >{\raggedright\arraybackslash}p{2cm} >{\raggedright\arraybackslash}p{4cm}@{}}")
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
                vid = _latex_escape(vc["id"])
                name = _latex_escape(vc.get("name", ""))
                method = _latex_escape(vc.get("method", ""))
                status = vc.get("status", "pending")
                verified = _latex_escape(", ".join(vc.get("verified_requirements", [])))
                L.append(f"\\texttt{{{vid}}} & {name} & {method} & \\statusbadge{{{status}}} & {verified} \\\\")
                L.append(r"\midrule")
            L.append(r"\end{longtable}")
            L.append(r"\newpage")

        # ── 6. Risks ──────────────────────────────────────────────────────
        if risks_list:
            L.append(r"\section{Risk Register}")
            L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{2.5cm} >{\raggedright\arraybackslash}p{3.5cm} >{\raggedright\arraybackslash}p{2cm} >{\raggedright\arraybackslash}p{2cm} >{\raggedright\arraybackslash}p{2cm} >{\raggedright\arraybackslash}p{2.5cm}@{}}")
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
                mitigation = _latex_escape(r.get("mitigation", "")[:150])
                L.append(f"\\texttt{{{rid}}} & {title} & \\prioritybadge{{{sev}}} & {prob} & \\statusbadge{{{status}}} & {mitigation} \\\\")
                L.append(r"\midrule")
            L.append(r"\end{longtable}")

        # ── Traceability Matrix ───────────────────────────────────────────
        if "traceability" in sections:
            L.append(r"\section{Traceability Matrix}")
            vc_ids = [v["id"] for v in self.vcs]
            links_map: dict[str, dict[str, str]] = {}
            for t in self.traces.get("links", []):
                links_map.setdefault(t["source"], {})[t["target"]] = t["type"]
            for r in self.reqs:
                for rel in r.get("relations", []):
                    links_map.setdefault(r["id"], {})[rel["target"]] = rel["type"]
            if vc_ids:
                col_spec = "l" + "c" * len(vc_ids)
                L.append(f"\\begin{{longtable}}{{{col_spec}}}")
                L.append(r"\toprule")
                L.append(r"\rowcolor{tabhead}")
                header_cells = r"\textbf{Requirement}"
                for vc_id in vc_ids:
                    header_cells += f" & \\textbf{{{_latex_escape(vc_id)}}}"
                L.append(header_cells + r" \\")
                L.append(r"\midrule")
                L.append(r"\endfirsthead")
                L.append(r"\toprule")
                L.append(r"\rowcolor{tabhead}")
                L.append(header_cells + r" \\")
                L.append(r"\midrule")
                L.append(r"\endhead")
                L.append(r"\bottomrule")
                L.append(r"\endfoot")
                for req in self.reqs:
                    row = f"\\texttt{{{_latex_escape(req['id'])}}}"
                    for vc_id in vc_ids:
                        link = links_map.get(req["id"], {}).get(vc_id)
                        if link:
                            row += f" & {_latex_escape(link)}"
                        else:
                            row += r" & --"
                    L.append(row + r" \\")
                    L.append(r"\midrule")
                L.append(r"\end{longtable}")
            L.append(r"\newpage")

        # ── Specifications ────────────────────────────────────────────────
        if "specifications" in sections:
            L.append(r"\section{Specifications}")
            for spec in self.specs:
                sid = _latex_escape(spec["id"])
                name = _latex_escape(spec.get("name", ""))
                desc = _latex_escape(spec.get("description", "")[:200])
                reqs = _latex_escape(", ".join(spec.get("requirements", [])))
                L.append(f"\\subsection*{{{sid} -- {name}}}")
                L.append(f"{desc}")
                if spec.get("requirements"):
                    L.append(f"\\textbf{{Linked Requirements:}} \\texttt{{{reqs}}}")
                L.append(r"\vspace{0.5em}")
            L.append(r"\newpage")

        # ── Baselines ─────────────────────────────────────────────────────
        if "baselines" in sections:
            L.append(r"\section{Baselines}")
            baseline_map: dict[str, list[str]] = {}
            for r in self.reqs:
                for b in r.get("baselines", []):
                    baseline_map.setdefault(b, []).append(r["id"])
            if baseline_map:
                L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{4cm} >{\raggedright\arraybackslash}p{2cm} >{\raggedright\arraybackslash}p{7cm}@{}}")
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
            L.append(r"\newpage")

        # ── Change Requests ───────────────────────────────────────────────
        if "changes" in sections:
            crs = self.store.list_items("change_requests")
            if crs:
                L.append(r"\section{Change Requests}")
                L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{2.5cm} >{\raggedright\arraybackslash}p{3.5cm} >{\raggedright\arraybackslash}p{2cm} >{\raggedright\arraybackslash}p{5cm}@{}}")
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
                    affected = _latex_escape(", ".join(cr.get("affected_requirements", [])))
                    L.append(f"\\texttt{{{cid}}} & {title} & \\statusbadge{{{status}}} & {affected} \\\\")
                    L.append(r"\midrule")
                L.append(r"\end{longtable}")
                L.append(r"\newpage")

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
            L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{4cm} >{\raggedright\arraybackslash}p{3cm} >{\raggedright\arraybackslash}p{3cm}@{}}")
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
            L.append(r"\newpage")

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
                L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{3cm} >{\raggedright\arraybackslash}p{3.5cm} >{\raggedright\arraybackslash}p{6.5cm}@{}}")
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
            L.append(r"\newpage")

        # ── Decisions ────────────────────────────────────────────────────
        if "decisions" in sections:
            decisions = self.store.list_items("decisions")
            if decisions:
                L.append(r"\section{Decisions}")
                L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{2.5cm} >{\raggedright\arraybackslash}p{3cm} >{\raggedright\arraybackslash}p{3.5cm} >{\raggedright\arraybackslash}p{3.5cm} >{\raggedright\arraybackslash}p{2cm}@{}}")
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
                    decision = _latex_escape(d.get("decision", "")[:150])
                    rationale = _latex_escape(d.get("rationale", "")[:150])
                    status = d.get("status", "open")
                    L.append(f"\\texttt{{{did}}} & {title} & {decision} & {rationale} & \\statusbadge{{{status}}} \\\\")
                    L.append(r"\midrule")
                L.append(r"\end{longtable}")
                L.append(r"\newpage")

        # ── Glossary ──────────────────────────────────────────────────────
        if "glossary" in sections:
            L.append(r"\section{Glossary}")
            L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{4cm} >{\raggedright\arraybackslash}p{9cm}@{}}")
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
            L.append(r"\newpage")

        # ── Conflicts ─────────────────────────────────────────────────────
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
                L.append(r"\newpage")

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
                    L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{3cm} >{\raggedright\arraybackslash}p{2.5cm} >{\raggedright\arraybackslash}p{2cm} >{\raggedright\arraybackslash}p{5cm}@{}}")
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
                    L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{8cm} >{\raggedright\arraybackslash}p{4cm}@{}}")
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
                        L.append(f"{cexpr} & \\statusbadge{{{cstatus}}} \\\\")
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
                L.append(f"\\textbf{{Status:}} \\statusbadge{{{status}}}")
                L.append(r"")
                steps = vc.get("test_steps", [])
                if steps:
                    L.append(r"\textbf{Test Steps}")
                    L.append(r"\vspace{0.3em}")
                    L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{5cm} >{\raggedright\arraybackslash}p{4cm} >{\raggedright\arraybackslash}p{4cm}@{}}")
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
                    L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{3cm} >{\raggedright\arraybackslash}p{2.5cm} >{\raggedright\arraybackslash}p{2.5cm} >{\raggedright\arraybackslash}p{2.5cm} >{\raggedright\arraybackslash}p{2cm}@{}}")
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
                        notes = _latex_escape(h.get("notes", "")[:100])
                        executor = _latex_escape(h.get("executor", ""))
                        duration = _latex_escape(str(h.get("duration", "")))
                        L.append(f"{ts} & \\statusbadge{{{hstatus}}} & {notes} & {executor} & {duration} \\\\")
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
                L.append(r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{4cm} >{\raggedright\arraybackslash}p{9cm}@{}}")
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
        """
        if compile_latex_to_pdf(self.build_latex(), path):
            return path
        from weasyprint import HTML as WHTML
        WHTML(string=self.build_html()).write_pdf(path)
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
