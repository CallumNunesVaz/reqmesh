import { useState, useEffect } from 'react';
import { X, FileDown, FileText, FileCode, File, Download, Loader, FileSpreadsheet, Globe, FileType, AlertTriangle, History } from 'lucide-react';
import { api, baselineNames, type Component, type RequirementTreeNode } from '../api/client';
import Modal from './Modal';

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
  const [components, setComponents] = useState<Component[]>([]);
  const [selectedComponents, setSelectedComponents] = useState<Set<string>>(new Set());
  const [componentSelectAll, setComponentSelectAll] = useState(true);
  const [baselines, setBaselines] = useState<string[]>([]);
  const [selectedBaselines, setSelectedBaselines] = useState<Set<string>>(new Set());
  const [baselineSelectAll, setBaselineSelectAll] = useState(true);
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
    api.listComponents(projectId).then(cs => {
      setComponents(cs);
      setSelectedComponents(new Set(cs.map(c => c.id)));
      setComponentSelectAll(true);
    }).catch(console.error);
    api.getProject(projectId).then(p => {
      const names = baselineNames(p.baselines);
      setBaselines(names);
      setSelectedBaselines(new Set(names));
      setBaselineSelectAll(true);
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

  const toggleComponent = (id: string) => {
    setSelectedComponents(prev => {
      const next = new Set(prev);
      if (next.has(id)) { next.delete(id); } else { next.add(id); }
      setComponentSelectAll(next.size === components.length);
      return next;
    });
  };

  const handleSelectAllComponents = () => {
    setSelectedComponents(new Set(components.map(c => c.id)));
    setComponentSelectAll(true);
  };

  const handleSelectNoneComponents = () => {
    setSelectedComponents(new Set());
    setComponentSelectAll(false);
  };

  const toggleBaseline = (name: string) => {
    setSelectedBaselines(prev => {
      const next = new Set(prev);
      if (next.has(name)) { next.delete(name); } else { next.add(name); }
      setBaselineSelectAll(next.size === baselines.length);
      return next;
    });
  };

  const handleSelectAllBaselines = () => {
    setSelectedBaselines(new Set(baselines));
    setBaselineSelectAll(true);
  };

  const handleSelectNoneBaselines = () => {
    setSelectedBaselines(new Set());
    setBaselineSelectAll(false);
  };

  const selectedCount = subtreeIds.size;
  const totalCount = flatTree.length;
  const scoped = isReportFormat(format);
  // An explicit empty scope filter exports nothing — worth a disabled button
  // rather than a silently empty download.
  const emptyScope =
    selectedCount === 0 ||
    (!componentSelectAll && selectedComponents.size === 0) ||
    (!baselineSelectAll && selectedBaselines.size === 0);

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
      // to silently export everything when the user picked "None". The same
      // distinction applies to the component and baseline filters.
      const hasGroupFilter = !groupSelectAll;
      const hasComponentFilter = !componentSelectAll;
      const hasBaselineFilter = !baselineSelectAll;
      const wanted = changelogOn ? [...sections, CHANGELOG_SECTION] : sections;
      const secsParam = isReportFormat(format) ? `&sections=${encodeURIComponent(wanted.join(','))}` : '';
      const logParam = (isReportFormat(format) && changelogOn)
        ? `&changelog_from=${encodeURIComponent(changelogFrom)}&changelog_to=${encodeURIComponent(changelogTo)}`
        : '';
      // Scope filters (subsystems/components/baselines) only apply to report
      // formats; for data/interchange formats the backend exports everything,
      // so the pickers are greyed out and no scope param is sent.
      const subParam = (scoped && hasGroupFilter) ? `&subsystems=${encodeURIComponent([...selectedGroups].join(','))}` : '';
      const compParam = (scoped && hasComponentFilter) ? `&components=${encodeURIComponent([...selectedComponents].join(','))}` : '';
      const baseParam = (scoped && hasBaselineFilter) ? `&baselines=${encodeURIComponent([...selectedBaselines].join(','))}` : '';
      const qs = `?format=${format}${subParam}${compParam}${baseParam}${secsParam}${logParam}`;
      // Auth is an HttpOnly cookie now — no bearer token to attach.
      const res = await fetch(`/api/projects/${projectId}/publish/download${qs}`, { credentials: 'include' });
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
    <Modal open={open} onClose={onClose} panelClassName="w-full max-w-2xl p-6 max-h-[85vh] overflow-y-auto">
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
                  <span className="label">Reports</span>
                  <span className="text-3xs text-muted-foreground">— formatted documents with section selection</span>
                </div>
                <div className="grid grid-cols-4 gap-2">
                  {reportFormats.map((fmt) => {
                    const Icon = fmt.icon;
                    const active = format === fmt.id;
                    return (
                      <button
                        key={fmt.id}
                        onClick={() => setFormat(fmt.id)}
                        className={`flex flex-col items-center gap-1 p-3 rounded-lg border text-xs transition-colors ${
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
                  <span className="label">Data Exports</span>
                  <span className="text-3xs text-muted-foreground">— tabular data for spreadsheets and analysis tools</span>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {dataFormats.map((fmt) => {
                    const Icon = fmt.icon;
                    const active = format === fmt.id;
                    return (
                      <button
                        key={fmt.id}
                        onClick={() => setFormat(fmt.id)}
                        className={`flex flex-col items-center gap-1 p-3 rounded-lg border text-xs transition-colors ${
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
                  <span className="label">Interchange Formats</span>
                  <span className="text-3xs text-muted-foreground">— industry standards for tool-to-tool exchange</span>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {interchangeFormats.map((fmt) => {
                    const Icon = fmt.icon;
                    const active = format === fmt.id;
                    return (
                      <button
                        key={fmt.id}
                        onClick={() => setFormat(fmt.id)}
                        className={`flex flex-col items-center gap-1 p-3 rounded-lg border text-xs transition-colors ${
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
                <div className="rounded-lg border border-cs-amber/30 bg-cs-amber/5 p-3 text-xs">
                  <p className="font-medium text-cs-amber">LaTeX engine not detected — PDF quality reduced</p>
                  <p className="text-muted-foreground mt-0.5">
                    Install <code className="bg-muted px-1 rounded-md">tectonic</code> (<code>curl -L https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-x86_64-unknown-linux-gnu.tar.gz | tar xz -C ~/.local/bin</code>) for full-quality PDF with coloured badges and table of contents.
                  </p>
                </div>
              )}

              <div className="grid grid-cols-2 gap-5">
                {/* Sections — only for report formats */}
                {isReportFormat(format) ? (
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span className="label">Sections</span>
                      <div className="flex gap-2">
                        <button onClick={selectAllSections} className="text-3xs text-muted-foreground hover:text-foreground">All</button>
                        <button onClick={selectNoneSections} className="text-3xs text-muted-foreground hover:text-foreground">None</button>
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
                            className="rounded-md"
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
                          className="rounded-md"
                        />
                        <History size={12} className="shrink-0" />
                        <span className="font-medium">Changelog (diff report)</span>
                      </label>

                      {changelogOn && (
                      <div className="mt-2 space-y-2">
                        <p className="text-3xs text-muted-foreground leading-relaxed">
                          Lists every recorded change between these dates. Deselect the other
                          sections above for a changes-only review document.
                        </p>
                        <div className="flex flex-wrap gap-2">
                          <div className="flex-1 min-w-[120px]">
                            <label className="block text-3xs text-muted-foreground mb-0.5">From
                              <input
                                type="date"
                                className="input text-xs h-8"
                                value={changelogFrom}
                                max={changelogTo || undefined}
                                onChange={(e) => setChangelogFrom(e.target.value)}
                              />
                            </label>
                          </div>
                          <div className="flex-1 min-w-[120px]">
                            <label className="block text-3xs text-muted-foreground mb-0.5">To
                              <input
                                type="date"
                                className="input text-xs h-8"
                                value={changelogTo}
                                min={changelogFrom || undefined}
                                onChange={(e) => setChangelogTo(e.target.value)}
                              />
                            </label>
                          </div>
                        </div>
                        {datesInvalid && (
                          <p className="text-3xs text-destructive">
                            The start date must not be after the end date.
                          </p>
                        )}
                      </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div>
                    <span className="label">Sections</span>
                    <p className="text-xs text-muted-foreground mt-1">
                      Section selection and the Subsystems / Components / Baselines filters apply to report formats only. {format === 'reqif' ? 'ReqIF exports all requirements.' : format === 'sysml' ? 'SysML v2 exports all requirements.' : 'Data exports include all requirements in flat table form.'}
                    </p>
                  </div>
                )}

                {/* Subsystems — greyed out for non-report formats, which ignore
                    scope filters and always export everything. */}
                <div className={scoped ? '' : 'opacity-50 pointer-events-none'}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="label">Subsystems</span>
                    <div className="flex gap-2">
                      <button onClick={handleSelectAllGroups} className="text-3xs text-muted-foreground hover:text-foreground">All</button>
                      <button onClick={handleSelectNoneGroups} className="text-3xs text-muted-foreground hover:text-foreground">None</button>
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
                            className="rounded-md"
                          />
                          <span className="font-mono text-3xs opacity-60 w-20 shrink-0 truncate">{group.id}</span>
                          <span className="truncate">{group.name || group.id}</span>
                        </label>
                      ))
                    )}
                  </div>
                  <p className="text-3xs text-muted-foreground mt-1">
                    {selectedCount} of {totalCount} requirements selected
                  </p>
                </div>

                {/* Components */}
                <div className={scoped ? '' : 'opacity-50 pointer-events-none'}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="label">Components</span>
                    <div className="flex gap-2">
                      <button onClick={handleSelectAllComponents} title="Select all components" className="text-3xs text-muted-foreground hover:text-foreground">All</button>
                      <button onClick={handleSelectNoneComponents} title="Select no components" className="text-3xs text-muted-foreground hover:text-foreground">None</button>
                    </div>
                  </div>
                  <div className="space-y-0.5 max-h-48 overflow-y-auto">
                    {components.length === 0 ? (
                      <p className="text-xs text-muted-foreground py-2">Loading...</p>
                    ) : (
                      components.map((comp) => (
                        <label
                          key={comp.id}
                          className={`flex items-center gap-2 px-2 py-1 rounded-md cursor-pointer text-xs transition-colors ${
                            selectedComponents.has(comp.id) ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-accent'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={selectedComponents.has(comp.id)}
                            onChange={() => toggleComponent(comp.id)}
                            className="rounded-md"
                          />
                          <span className="font-mono text-3xs opacity-60 w-20 shrink-0 truncate">{comp.id}</span>
                          <span className="truncate">{comp.name || comp.id}</span>
                        </label>
                      ))
                    )}
                  </div>
                  <p className="text-3xs text-muted-foreground mt-1">
                    {selectedComponents.size} of {components.length} components selected
                  </p>
                </div>

                {/* Baselines */}
                <div className={scoped ? '' : 'opacity-50 pointer-events-none'}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="label">Baselines</span>
                    <div className="flex gap-2">
                      <button onClick={handleSelectAllBaselines} title="Select all baselines" className="text-3xs text-muted-foreground hover:text-foreground">All</button>
                      <button onClick={handleSelectNoneBaselines} title="Select no baselines" className="text-3xs text-muted-foreground hover:text-foreground">None</button>
                    </div>
                  </div>
                  <div className="space-y-0.5 max-h-48 overflow-y-auto">
                    {baselines.length === 0 ? (
                      <p className="text-xs text-muted-foreground py-2">No baselines defined</p>
                    ) : (
                      baselines.map((name) => (
                        <label
                          key={name}
                          className={`flex items-center gap-2 px-2 py-1 rounded-md cursor-pointer text-xs transition-colors ${
                            selectedBaselines.has(name) ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-accent'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={selectedBaselines.has(name)}
                            onChange={() => toggleBaseline(name)}
                            className="rounded-md"
                          />
                          <span className="font-mono text-3xs opacity-60 w-20 shrink-0 truncate">{name}</span>
                        </label>
                      ))
                    )}
                  </div>
                  <p className="text-3xs text-muted-foreground mt-1">
                    {selectedBaselines.size} of {baselines.length} baselines selected
                  </p>
                </div>
              </div>

              {error && <p className="text-xs text-destructive">{error}</p>}

              {fallbackMessage && (
                <div className="rounded-lg border border-cs-amber/30 bg-cs-amber/5 p-3 text-xs flex items-start gap-2">
                  <AlertTriangle size={14} className="text-cs-amber shrink-0 mt-0.5" />
                  <div>
                    <p className="font-medium text-cs-amber">Render fallback</p>
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
                  disabled={downloading || emptyScope || datesInvalid}
                  className="btn-primary flex-1 justify-center"
                  title={emptyScope ? 'Select at least one of each scope filter'
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
    </Modal>
  );
}
