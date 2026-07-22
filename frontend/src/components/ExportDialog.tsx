import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, FileDown, FileText, FileCode, File, Download, Loader } from 'lucide-react';
import { api, type RequirementTreeNode } from '../api/client';

interface ExportDialogProps {
  open: boolean;
  onClose: () => void;
  projectId: string;
}

const formats = [
  { id: 'html', label: 'HTML Report', icon: FileCode, desc: 'Rich colorized report with tables, charts and hierarchy', ext: '.html' },
  { id: 'pdf', label: 'PDF Document', icon: File, desc: 'Print-ready PDF with embedded styles and page breaks', ext: '.pdf' },
  { id: 'md', label: 'Markdown', icon: FileText, desc: 'Plain text for version control and wikis', ext: '.md' },
  { id: 'latex', label: 'LaTeX', icon: FileCode, desc: 'Academic-quality source for publications', ext: '.tex' },
  { id: 'reqif', label: 'ReqIF 1.2', icon: File, desc: 'Requirements Interchange Format for DOORS/Polarion import', ext: '.xml' },
  { id: 'sysml', label: 'SysML v2', icon: FileCode, desc: 'SysML v2 textual notation for MBSE tools', ext: '.sysml' },
  { id: 'csv', label: 'CSV', icon: FileText, desc: 'Spreadsheet for Excel/Numbers import', ext: '.csv' },
  { id: 'tsv', label: 'TSV', icon: FileText, desc: 'Tab-separated for data tools', ext: '.tsv' },
  { id: 'xlsx', label: 'Excel (XLSX)', icon: FileText, desc: 'Microsoft Excel worksheet', ext: '.xlsx' },
];

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

export default function ExportDialog({ open, onClose, projectId }: ExportDialogProps) {
  const [format, setFormat] = useState('html');
  const [sections, setSections] = useState<string[]>(allSections.map(s => s.id));
  const [generating, setGenerating] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewContent, setPreviewContent] = useState('');
  const [error, setError] = useState('');
  const [tree, setTree] = useState<RequirementTreeNode[]>([]);
  const [selectedGroups, setSelectedGroups] = useState<Set<string>>(new Set());
  const [groupSelectAll, setGroupSelectAll] = useState(true);

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

  const handleGenerate = async () => {
    if (format === 'pdf' || format === 'reqif' || format === 'sysml' || format === 'csv' || format === 'tsv' || format === 'xlsx') {
      handleDownload();
      return;
    }
    setError('');
    setGenerating(true);
    try {
      const token = (() => { try { return localStorage.getItem('rt-token'); } catch { return null; } })();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const subsystems = groupSelectAll ? null : [...selectedGroups];
      const res = await fetch(`/api/projects/${projectId}/publish`, {
        method: 'POST', headers,
        body: JSON.stringify({ format, sections, subsystems }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: 'Failed' }))).detail);
      const data = await res.json();
      if (format === 'html') {
        setPreviewContent(data.content);
        setPreviewOpen(true);
      }
    } catch (err: any) {
      setError(err.message || 'Export failed');
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = () => {
    const subsystems = groupSelectAll ? '' : [...selectedGroups].join(',');
    const qs = subsystems ? `?format=${format}&subsystems=${encodeURIComponent(subsystems)}` : `?format=${format}`;
    window.open(`/api/projects/${projectId}/publish/download${qs}`, '_blank');
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

            <h2 className="text-lg font-bold text-foreground mb-1">Export Document</h2>
            <p className="text-xs text-muted-foreground mb-5">Generate a formatted report from your requirements</p>

            <div className="space-y-5">
              <div>
                <label className="label">Format</label>
                <div className="grid grid-cols-4 gap-2 mt-1">
                  {formats.map((fmt) => {
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

              <div className="grid grid-cols-2 gap-5">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="label">Sections</label>
                    <div className="flex gap-2">
                      <button onClick={selectAllSections} className="text-[10px] text-muted-foreground hover:text-foreground">All</button>
                      <button onClick={selectNoneSections} className="text-[10px] text-muted-foreground hover:text-foreground">None</button>
                    </div>
                  </div>
                  <div className="space-y-0.5">
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
                </div>

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

              <div className="flex gap-2 pt-2 border-t">
                <button onClick={handleGenerate} disabled={generating} className="btn-primary flex-1 justify-center">
                  {generating ? (
                    <><Loader size={14} className="animate-spin" /> Generating...</>
                  ) : (
                    <><FileText size={14} /> {format === 'pdf' ? 'Download PDF' : 'Generate'}</>
                  )}
                </button>
                <button onClick={handleDownload} className="btn-secondary justify-center">
                  <Download size={14} />
                </button>
              </div>

              {previewOpen && previewContent && (
                <div className="border rounded-lg overflow-hidden">
                  <div className="flex items-center justify-between px-3 py-2 border-b bg-muted/30">
                    <span className="text-[10px] font-medium text-muted-foreground">Preview</span>
                    <button onClick={() => setPreviewOpen(false)} className="text-[10px] text-muted-foreground hover:text-foreground">Hide</button>
                  </div>
                  <iframe srcDoc={previewContent} className="w-full h-[400px] border-0" title="Preview" />
                </div>
              )}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
