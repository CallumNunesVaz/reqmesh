import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, FileDown, FileText, FileCode, File, Download, Loader, FileSpreadsheet, Globe, FileType, AlertTriangle, History } from 'lucide-react';
import { api, type RequirementTreeNode } from '../api/client';

interface ExportDialogProps {
  open: boolean;
  onClose: () => void;
  projectId: string;
}

const reportFormats = [
  { id: 'html', label: 'HTML Report', icon: Globe, desc: 'Rich colorized web report with tables, charts and hierarchy', ext: '.html' },
  { id: 'pdf', label: 'PDF Document', icon: File, desc: 'Print-ready PDF with embedded styles and page breaks', ext: '.pdf' },
  { id: 'md', label: 'Markdown', icon: FileText, desc: 'Plain text for version control and wikis', ext: '.md' },
  { id: 'latex', label: 'LaTeX', icon: FileCode, desc: 'Academic-quality source for publications', ext: '.tex' },
];

const dataFormats = [
  { id: 'csv', label: 'CSV', icon: FileSpreadsheet, desc: 'Spreadsheet for Excel/Numbers import', ext: '.csv' },
  { id: 'tsv', label: 'TSV', icon: FileSpreadsheet, desc: 'Tab-separated for data tools', ext: '.tsv' },
  { id: 'xlsx', label: 'Excel (XLSX)', icon: FileSpreadsheet, desc: 'Microsoft Excel worksheet', ext: '.xlsx' },
];

const interchangeFormats = [
  { id: 'reqif', label: 'ReqIF 1.2', icon: FileType, desc: 'Requirements Interchange Format for DOORS/Polarion import', ext: '.xml' },
  { id: 'sysml', label: 'SysML v2', icon: FileCode, desc: 'SysML v2 textual notation for MBSE tools', ext: '.sysml' },
];

// The changelog is deliberately absent from the default selection — it is an
// opt-in, date-bounded section (see CHANGELOG_SECTION).
const allSections = [
  { id: 'cover', label: 'Cover Page' },
  { id: 'summary', label: 'Project Summary' },
  { id: 'requirements', label: 'Requirements by Type' },
  { id: 'components', label: 'Components' },
  { id: 'specifications', label: 'Specifications' },
  { id: 'verification', label: 'Verification Cases' },
  { id: 'verification_details', label: 'Verification Details (steps & history)' },
  { id: 'traceability', label: 'Traceability Matrix' },
  { id: 'baselines', label: 'Baselines' },
  { id: 'changes', label: 'Change Requests' },
  { id: 'risks', label: 'Risk Register' },
  { id: 'decisions', label: 'Design Decisions' },
  { id: 'quality', label: 'Quality Metrics' },
  { id: 'gaps', label: 'Gap Analysis' },
  { id: 'conflicts', label: 'Conflicts' },
  { id: 'parameters', label: 'Parameters & Constraints' },
  { id: 'system_states', label: 'System States' },
  { id: 'glossary', label: 'Glossary' },
];

const CHANGELOG_SECTION = 'changelog';

/** Local (not UTC) YYYY-MM-DD — toISOString() would roll the date backwards
 *  for anyone west of Greenwich in the evening. */
function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function collectSubtreeIds(nodes: RequirementTreeNode[], selected: Set<string>): Set<string> {
  const ids = new Set<string>();
  function walk(list: RequirementTreeNode[]) {
    for (const n of list) {
      if (selected.has(n.id)) {
        function collectAll(node: RequirementTreeNode) {
          ids.add(node.id);
          for (const child of node.children) collectAll(child);
        }
        collectAll(n);
      } else {
        walk(n.children);
      }
    }
  }
  walk(nodes);
  return ids;
}

function flattenTree(nodes: RequirementTreeNode[]): RequirementTreeNode[] {
  const result: RequirementTreeNode[] = [];
  function walk(list: RequirementTreeNode[]) {
    for (const n of list) {
      result.push(n);
      walk(n.children);
    }
  }
  walk(nodes);
  return result;
}

const isReportFormat = (id: string) => reportFormats.some(f => f.id === id);
const allFormats = [...reportFormats, ...dataFormats, ...interchangeFormats];

export default function ExportDialog({ open, onClose, projectId }: ExportDialogProps) {
  const [format, setFormat] = useState('html');
  const [sections, setSections] = useState<string[]>(allSections.map(s => s.id));
  const [downloading, setDownloading] = useState(false);
  const [downloadStatus, setDownloadStatus] = useState('');
  const [fallbackMessage, setFallbackMessage] = useState('');
  const [error, setError] = useState('');
  const [tree, setTree] = useState<RequirementTreeNode[]>([]);
  const [selectedGroups, setSelectedGroups] = useState<Set<string>>(new Set());
  const [groupSelectAll, setGroupSelectAll] = useState(true);
  const [latexAvail, setLatexAvail] = useState(false);
  // Changelog ("diff report"): opt-in, with its own date window. Defaults to
  // the last 30 days ending today.
  const [changelogOn, setChangelogOn] = useState(false);
  const [changelogFrom, setChangelogFrom] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 30);
    return isoDate(d);
  });
  const [changelogTo, setChangelogTo] = useState(() => isoDate(new Date()));
  const datesInvalid = changelogOn && !!changelogFrom && !!changelogTo && changelogFrom > changelogTo;

  useEffect(() => {
    api.getLatexStatus().then(s => setLatexAvail(s.available)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!open || !projectId) return;
    api.getRequirementTree(projectId).then(t => {
      setTree(t);
      setSelectedGroups(new Set(t.map(n => n.id)));
      setGroupSelectAll(true);
    }).catch(console.error);
  }, [open, projectId]);

  const flatTree = flattenTree(tree);
  const subtreeIds = collectSubtreeIds(tree, selectedGroups);

  const toggleSection = (id: string) => {
    setSections(prev => prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]);
  };
  const selectAllSections = () => setSections(allSections.map(s => s.id));
  const selectNoneSections = () => setSections([]);

  const toggleGroup = (id: string) => {
    setSelectedGroups(prev => {
      const next = new Set(prev);
      if (next.has(id)) { next.delete(id); } else { next.add(id); }
      const allIds = new Set(tree.map(n => n.id));
      setGroupSelectAll(next.size === allIds.size);
      return next;
    });
  };

  const handleSelectAllGroups = () => {
    setSelectedGroups(new Set(tree.map(n => n.id)));
    setGroupSelectAll(true);
  };

  const handleSelectNoneGroups = () => {
    setSelectedGroups(new Set());
    setGroupSelectAll(false);
  };

  const selectedCount = subtreeIds.size;
  const totalCount = flatTree.length;

  const handleDownload = async () => {
    setError('');
    setFallbackMessage('');
    setDownloading(true);
    const isPdf = format === 'pdf';
    setDownloadStatus(isPdf ? 'Building report…' : 'Preparing download…');
    const phase2 = setTimeout(() => {
      setDownloadStatus(isPdf ? 'Compiling LaTeX to PDF…' : 'Still working…');
    }, 2500);
    const phase3 = setTimeout(() => {
      if (isPdf) setDownloadStatus('Rendering PDF via HTML fallback…');
    }, 8000);
    try {
      // groupSelectAll means "no filter" (omit the param entirely). Otherwise
      // the filter is explicit and must be sent even when it's empty — an
      // omitted param and an empty one mean very different things to the
      // backend (all requirements vs. none), and collapsing them here used
      // to silently export everything when the user picked "None".
      const hasGroupFilter = !groupSelectAll;
      const subsystems = [...selectedGroups].join(',');
      const wanted = changelogOn ? [...sections, CHANGELOG_SECTION] : sections;
      const secsParam = isReportFormat(format) ? `&sections=${encodeURIComponent(wanted.join(','))}` : '';
      const logParam = (isReportFormat(format) && changelogOn)
        ? `&changelog_from=${encodeURIComponent(changelogFrom)}&changelog_to=${encodeURIComponent(changelogTo)}`
        : '';
      const qs = hasGroupFilter
        ? `?format=${format}&subsystems=${encodeURIComponent(subsystems)}${secsParam}${logParam}`
        : `?format=${format}${secsParam}${logParam}`;
      const auth = (() => { try { return localStorage.getItem('rt-token'); } catch { return null; } })();
      const headers: Record<string, string> = {};
      if (auth) headers['Authorization'] = `Bearer ${auth}`;
      const res = await fetch(`/api/projects/${projectId}/publish/download${qs}`, { headers });
      if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: 'Export failed' }))).detail || 'Export failed');
      const fb = res.headers.get('X-Render-Fallback');
      if (fb) setFallbackMessage(fb);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const fmt = allFormats.find(f => f.id === format);
      a.download = `${projectId}_${format}.${fmt?.ext || format}`;
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(url);
      a.remove();
    } catch (err: any) {
      setError(err.message || 'Download failed');
    } finally {
      clearTimeout(phase2);
      clearTimeout(phase3);
      setDownloading(false);
      setDownloadStatus('');
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="absolute inset-0 bg-background/80 backdrop-blur-sm" onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            className="relative bg-card border rounded-xl shadow-2xl w-full max-w-2xl p-6 mx-4 max-h-[85vh] overflow-y-auto"
          >
            <button onClick={onClose} className="absolute right-4 top-4 text-muted-foreground hover:text-foreground transition-colors">
              <X size={18} />
            </button>

            <h2 className="text-lg font-bold text-foreground mb-1">Export</h2>
            <p className="text-xs text-muted-foreground mb-5">Download a report or export requirements in an interchange format</p>

            <div className="space-y-5">
              {/* --- Report formats --- */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <FileDown size={14} className="text-muted-foreground" />
                  <label className="label">Reports</label>
                  <span className="text-[10px] text-muted-foreground">— formatted documents with section selection</span>
                </div>
                <div className="grid grid-cols-4 gap-2">
                  {reportFormats.map((fmt) => {
                    const Icon = fmt.icon;
                    const active = format === fmt.id;
                    return (
                      <button
                        key={fmt.id}
                        onClick={() => setFormat(fmt.id)}
                        className={`flex flex-col items-center gap-1 p-3 rounded-lg border text-xs transition-all ${
                          active ? 'border-primary bg-primary/5 text-primary' : 'border bg-card text-muted-foreground hover:border-ring/30'
                        }`}
                      >
                        <Icon size={20} />
                        <span className="font-medium">{fmt.label.split(' ')[0]}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* --- Data exports --- */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <FileSpreadsheet size={14} className="text-muted-foreground" />
                  <label className="label">Data Exports</label>
                  <span className="text-[10px] text-muted-foreground">— tabular data for spreadsheets and analysis tools</span>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {dataFormats.map((fmt) => {
                    const Icon = fmt.icon;
                    const active = format === fmt.id;
                    return (
                      <button
                        key={fmt.id}
                        onClick={() => setFormat(fmt.id)}
                        className={`flex flex-col items-center gap-1 p-3 rounded-lg border text-xs transition-all ${
                          active ? 'border-primary bg-primary/5 text-primary' : 'border bg-card text-muted-foreground hover:border-ring/30'
                        }`}
                      >
                        <Icon size={20} />
                        <span className="font-medium">{fmt.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* --- Interchange formats --- */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <FileType size={14} className="text-muted-foreground" />
                  <label className="label">Interchange Formats</label>
                  <span className="text-[10px] text-muted-foreground">— industry standards for tool-to-tool exchange</span>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {interchangeFormats.map((fmt) => {
                    const Icon = fmt.icon;
                    const active = format === fmt.id;
                    return (
                      <button
                        key={fmt.id}
                        onClick={() => setFormat(fmt.id)}
                        className={`flex flex-col items-center gap-1 p-3 rounded-lg border text-xs transition-all ${
                          active ? 'border-primary bg-primary/5 text-primary' : 'border bg-card text-muted-foreground hover:border-ring/30'
                        }`}
                      >
                        <Icon size={20} />
                        <span className="font-medium">{fmt.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* LaTeX warning */}
              {!latexAvail && format === 'pdf' && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs">
                  <p className="font-medium text-amber-400">LaTeX engine not detected — PDF quality reduced</p>
                  <p className="text-muted-foreground mt-0.5">
                    Install <code className="bg-muted px-1 rounded">tectonic</code> (<code>curl -L https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-x86_64-unknown-linux-gnu.tar.gz | tar xz -C ~/.local/bin</code>) for full-quality PDF with coloured badges and table of contents.
                  </p>
                </div>
              )}

              <div className="grid grid-cols-2 gap-5">
                {/* Sections — only for report formats */}
                {isReportFormat(format) ? (
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="label">Sections</label>
                      <div className="flex gap-2">
                        <button onClick={selectAllSections} className="text-[10px] text-muted-foreground hover:text-foreground">All</button>
                        <button onClick={selectNoneSections} className="text-[10px] text-muted-foreground hover:text-foreground">None</button>
                      </div>
                    </div>
                    <div className="space-y-0.5 max-h-64 overflow-y-auto">
                      {allSections.map((sec) => (
                        <label
                          key={sec.id}
                          className={`flex items-center gap-2 px-2 py-1 rounded-md cursor-pointer text-xs transition-colors ${
                            sections.includes(sec.id) ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-accent'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={sections.includes(sec.id)}
                            onChange={() => toggleSection(sec.id)}
                            className="rounded"
                          />
                          {sec.label}
                        </label>
                      ))}
                    </div>

                    {/* Changelog — opt-in, and the only section with its own
                        parameters. It sits outside the scrolling list so the
                        toggle and its date window stay together on screen. */}
                    <div className={`mt-2 rounded-lg border p-2.5 transition-colors ${
                      changelogOn ? 'border-primary/40 bg-primary/5' : 'bg-muted/30'
                    }`}>
                      <label className={`flex items-center gap-2 cursor-pointer text-xs ${
                        changelogOn ? 'text-primary' : 'text-muted-foreground'
                      }`}>
                        <input
                          type="checkbox"
                          checked={changelogOn}
                          onChange={() => setChangelogOn(v => !v)}
                          className="rounded"
                        />
                        <History size={12} className="shrink-0" />
                        <span className="font-medium">Changelog (diff report)</span>
                      </label>

                      {changelogOn && (
                      <div className="mt-2 space-y-2">
                        <p className="text-[10px] text-muted-foreground leading-relaxed">
                          Lists every recorded change between these dates. Deselect the other
                          sections above for a changes-only review document.
                        </p>
                        <div className="flex flex-wrap gap-2">
                          <div className="flex-1 min-w-[120px]">
                            <label className="block text-[10px] text-muted-foreground mb-0.5">From</label>
                            <input
                              type="date"
                              className="input text-xs h-8"
                              value={changelogFrom}
                              max={changelogTo || undefined}
                              onChange={(e) => setChangelogFrom(e.target.value)}
                            />
                          </div>
                          <div className="flex-1 min-w-[120px]">
                            <label className="block text-[10px] text-muted-foreground mb-0.5">To</label>
                            <input
                              type="date"
                              className="input text-xs h-8"
                              value={changelogTo}
                              min={changelogFrom || undefined}
                              onChange={(e) => setChangelogTo(e.target.value)}
                            />
                          </div>
                        </div>
                        {datesInvalid && (
                          <p className="text-[10px] text-destructive">
                            The start date must not be after the end date.
                          </p>
                        )}
                      </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div>
                    <label className="label">Sections</label>
                    <p className="text-xs text-muted-foreground mt-1">
                      Section selection applies to report formats only. {format === 'reqif' ? 'ReqIF exports all requirements.' : format === 'sysml' ? 'SysML v2 exports all requirements.' : 'Data exports include all requirements in flat table form.'}
                    </p>
                  </div>
                )}

                {/* Subsystems — always shown */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="label">Subsystems</label>
                    <div className="flex gap-2">
                      <button onClick={handleSelectAllGroups} className="text-[10px] text-muted-foreground hover:text-foreground">All</button>
                      <button onClick={handleSelectNoneGroups} className="text-[10px] text-muted-foreground hover:text-foreground">None</button>
                    </div>
                  </div>
                  <div className="space-y-0.5 max-h-48 overflow-y-auto">
                    {tree.length === 0 ? (
                      <p className="text-xs text-muted-foreground py-2">Loading...</p>
                    ) : (
                      tree.map((group) => (
                        <label
                          key={group.id}
                          className={`flex items-center gap-2 px-2 py-1 rounded-md cursor-pointer text-xs transition-colors ${
                            selectedGroups.has(group.id) ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-accent'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={selectedGroups.has(group.id)}
                            onChange={() => toggleGroup(group.id)}
                            className="rounded"
                          />
                          <span className="font-mono text-[10px] opacity-60 w-20 shrink-0 truncate">{group.id}</span>
                          <span className="truncate">{group.name || group.id}</span>
                        </label>
                      ))
                    )}
                  </div>
                  <p className="text-[10px] text-muted-foreground mt-1">
                    {selectedCount} of {totalCount} requirements selected
                  </p>
                </div>
              </div>

              {error && <p className="text-xs text-destructive">{error}</p>}

              {fallbackMessage && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs flex items-start gap-2">
                  <AlertTriangle size={14} className="text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <p className="font-medium text-amber-400">Render fallback</p>
                    <p className="text-muted-foreground mt-0.5">{fallbackMessage}</p>
                  </div>
                </div>
              )}

              {downloading && (
                <div className="flex items-center gap-3 text-sm text-muted-foreground py-1">
                  <Loader size={16} className="animate-spin shrink-0" />
                  <span>{downloadStatus || 'Preparing…'}</span>
                </div>
              )}

              <div className="flex gap-2 pt-2 border-t">
                <button
                  onClick={handleDownload}
                  disabled={downloading || selectedCount === 0 || datesInvalid}
                  className="btn-primary flex-1 justify-center"
                  title={selectedCount === 0 ? 'Select at least one subsystem'
                    : datesInvalid ? 'Fix the changelog date range' : undefined}
                >
                  {downloading ? (
                    <><Loader size={14} className="animate-spin" /> Generating…</>
                  ) : (
                    <><Download size={14} /> Download {allFormats.find(f => f.id === format)?.label.split(' ')[0]}</>
                  )}
                </button>
                <button onClick={onClose} className="btn-secondary">Cancel</button>
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
