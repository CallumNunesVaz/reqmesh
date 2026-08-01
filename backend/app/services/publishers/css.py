"""CSS for the HTML→PDF report. Extracted from ``publisher.py``."""
from __future__ import annotations

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
