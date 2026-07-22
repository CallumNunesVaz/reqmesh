import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { FileDown, FileText, FileCode, File, Check, Download, Printer } from 'lucide-react';
import { api } from '../api/client';

const formats = [
  { id: 'html', label: 'HTML Report', icon: FileCode, desc: 'Rich colorized web report with tables, charts, and hierarchy', ext: '.html' },
  { id: 'pdf', label: 'PDF Document', icon: File, desc: 'Print-ready document with embedded styles and page breaks', ext: '.pdf' },
  { id: 'md', label: 'Markdown', icon: FileText, desc: 'Plain text markdown for version control and wikis', ext: '.md' },
  { id: 'latex', label: 'LaTeX', icon: FileCode, desc: 'Academic-quality LaTeX source for publications', ext: '.tex' },
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

export default function PublishPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [selectedFormat, setSelectedFormat] = useState('html');
  const [sections, setSections] = useState<string[]>(allSections.map(s => s.id));
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<{ format: string; content: string } | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  const handleGenerate = async () => {
    if (!projectId) return;
    setGenerating(true);
    try {
      const token = (() => { try { return localStorage.getItem('rt-token'); } catch { return null; } })();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const res = await fetch(`/api/projects/${projectId}/publish`, {
        method: 'POST', headers, body: JSON.stringify({ format: selectedFormat, sections }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: 'Failed' }))).detail);
      setResult(await res.json());
    } catch (err: any) {
      alert(err.message);
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = () => {
    if (!projectId) return;
    window.open(`/api/projects/${projectId}/publish/download?format=${selectedFormat}`, '_blank');
  };

  const toggleSection = (id: string) => {
    setSections(prev => prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]);
  };

  return (
    <div className="max-w-5xl mx-auto p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">Publish Report</h1>
        <p className="text-sm text-muted-foreground mt-1">Generate colorized reports from your requirements data</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mb-6">
        {formats.map((fmt) => {
          const Icon = fmt.icon;
          const active = selectedFormat === fmt.id;
          return (
            <motion.button
              key={fmt.id}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => setSelectedFormat(fmt.id)}
              className={`card p-4 text-left transition-all cursor-pointer ${
                active ? 'ring-2 ring-primary border-primary' : 'hover:shadow-md'
              }`}
            >
              <Icon size={24} className={`mb-2 ${active ? 'text-primary' : 'text-muted-foreground'}`} />
              <h3 className="font-semibold text-sm text-card-foreground">{fmt.label}</h3>
              <p className="text-xs text-muted-foreground mt-1">{fmt.desc}</p>
            </motion.button>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="card p-4">
            <h2 className="font-semibold text-sm text-card-foreground mb-3">Sections</h2>
            <div className="space-y-1">
              {allSections.map((sec) => (
                <label key={sec.id} className={`flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer transition-colors text-xs ${sections.includes(sec.id) ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-accent'}`}>
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

            <div className="mt-4 pt-4 border-t space-y-2">
              <button
                onClick={handleGenerate}
                disabled={generating}
                className="btn-primary w-full justify-center"
              >
                {generating ? (
                  <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                ) : (
                  <><Printer size={14} /> Generate Report</>
                )}
              </button>
              {result && (
                <button onClick={handleDownload} className="btn-secondary w-full justify-center">
                  <Download size={14} /> Download File
                </button>
              )}
            </div>
          </motion.div>
        </div>

        <div className="lg:col-span-2">
          {result && result.format === 'html' ? (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="card p-1 overflow-hidden">
              <div className="flex items-center justify-between px-3 py-2 border-b bg-muted/30">
                <span className="text-xs font-medium text-muted-foreground">Preview</span>
                <div className="flex items-center gap-1">
                  <button onClick={() => setPreviewOpen(!previewOpen)} className="text-xs btn-ghost p-1">
                    {previewOpen ? 'Collapse' : 'Expand'}
                  </button>
                  <button onClick={handleDownload} className="text-xs btn-ghost p-1">
                    <Download size={12} />
                  </button>
                </div>
              </div>
              {previewOpen && (
                <iframe
                  srcDoc={result.content}
                  className="w-full h-[600px] border-0"
                  title="Report Preview"
                  sandbox="allow-same-origin"
                />
              )}
            </motion.div>
          ) : result ? (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="card p-5 text-center">
              <Check size={48} className="mx-auto text-emerald-400 mb-4" />
              <p className="text-card-foreground font-medium">Report generated successfully</p>
              <p className="text-sm text-muted-foreground mt-1">Format: {result.format}</p>
              <button onClick={handleDownload} className="btn-primary mt-4">
                <Download size={14} /> Download
              </button>
            </motion.div>
          ) : (
            <div className="card p-12 text-center">
              <FileDown size={48} className="mx-auto text-muted-foreground/40 mb-4" />
              <p className="text-card-foreground font-medium">Select format and sections, then generate</p>
              <p className="text-sm text-muted-foreground mt-1">Choose HTML for a rich colorized report with all sections</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
