import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { FileDown, FileText, FileCode, File, Download, Loader, AlertTriangle } from 'lucide-react';
import { api } from '../api/client';
import EmptyState from '../components/EmptyState';
import Reveal from '../components/Reveal';

const formats = [
  { id: 'html', label: 'HTML Report', icon: FileCode, desc: 'Rich colorized web report with tables, charts, and hierarchy', ext: '.html' },
  { id: 'pdf', label: 'PDF Document', icon: File, desc: 'Print-ready document with embedded styles and page breaks', ext: '.pdf' },
  { id: 'md', label: 'Markdown', icon: FileText, desc: 'Plain text markdown for version control and wikis', ext: '.md' },
  { id: 'latex', label: 'LaTeX', icon: FileCode, desc: 'Academic-quality LaTeX source for publications', ext: '.tex' },
];

const dataFormats = [
  { id: 'csv', label: 'CSV', icon: FileText, desc: 'Comma-separated values for spreadsheet import', ext: '.csv' },
  { id: 'tsv', label: 'TSV', icon: FileText, desc: 'Tab-separated values for data processing', ext: '.tsv' },
  { id: 'xlsx', label: 'Excel (XLSX)', icon: FileText, desc: 'Microsoft Excel workbook', ext: '.xlsx' },
];

const interchangeFormats = [
  { id: 'reqif', label: 'ReqIF 1.2', icon: FileCode, desc: 'Requirements Interchange Format for DOORS/Polarion', ext: '.xml' },
  { id: 'sysml', label: 'SysML v2', icon: FileCode, desc: 'SysML v2 textual notation for MBSE tools', ext: '.sysml' },
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

const reportFormatIds = new Set(['html', 'pdf', 'md', 'latex']);
const allFormats = [...formats, ...dataFormats, ...interchangeFormats];

export default function PublishPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [selectedFormat, setSelectedFormat] = useState('html');
  const [sections, setSections] = useState<string[]>(allSections.map(s => s.id));
  const [downloading, setDownloading] = useState(false);
  const [downloadStatus, setDownloadStatus] = useState('');
  const [fallbackMessage, setFallbackMessage] = useState('');
  // Tri-state on purpose: null = not yet known. This started as `false`, with
  // the failure swallowed, so an unanswered probe rendered as a confident
  // "LaTeX engine not detected" — on every page load before the request
  // resolved, and permanently if it ever failed. The endpoint needs auth, so
  // an expired session was enough to tell a working deployment that its PDFs
  // were being downgraded. Claim nothing until the server has actually said.
  const [latexAvail, setLatexAvail] = useState<boolean | null>(null);

  useEffect(() => {
    api.getLatexStatus()
      .then(s => setLatexAvail(s.available))
      .catch(() => setLatexAvail(null));
  }, []);

  const handleDownload = async () => {
    if (!projectId) return;
    setFallbackMessage('');
    setDownloading(true);
    const isPdf = selectedFormat === 'pdf';
    setDownloadStatus(isPdf ? 'Building report…' : 'Preparing download…');
    // These are elapsed-time hints, so they may only describe what is *likely*
    // still happening — never claim an outcome. The previous phase-3 message
    // announced "Rendering PDF via HTML fallback…" on a timer, so every report
    // that took longer than 8 s looked like it had fallen back, including the
    // ones where LaTeX succeeded (a full Cessna report compiles in ~11 s). The
    // real answer arrives in the X-Render-Fallback header below.
    const phase2 = setTimeout(() => {
      setDownloadStatus(isPdf ? 'Compiling LaTeX to PDF…' : 'Still working…');
    }, 2500);
    const phase3 = setTimeout(() => {
      if (isPdf) setDownloadStatus('Still compiling — large reports take a while…');
    }, 8000);
    try {
      const secsParam = reportFormatIds.has(selectedFormat) ? `&sections=${encodeURIComponent(sections.join(','))}` : '';
      // Auth is an HttpOnly cookie now — no bearer token to attach.
      const res = await fetch(`/api/projects/${projectId}/publish/download?format=${selectedFormat}${secsParam}`, { credentials: 'include' });
      if (res.status === 429) {
        throw new Error('Export limit reached — reports are capped per minute because each one is expensive to build. Wait a moment and try again.');
      }
      if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: 'Export failed' }))).detail || 'Export failed');
      const fb = res.headers.get('X-Render-Fallback');
      if (fb) setFallbackMessage(fb);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const fmt = allFormats.find(f => f.id === selectedFormat);
      a.download = `${projectId}_${selectedFormat}.${fmt?.ext || selectedFormat}`;
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(url);
      a.remove();
    } catch (err: any) {
      alert(err.message || 'Download failed');
    } finally {
      clearTimeout(phase2);
      clearTimeout(phase3);
      setDownloading(false);
      setDownloadStatus('');
    }
  };

  const toggleSection = (id: string) => {
    setSections(prev => prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]);
  };

  const selectAllSections = () => setSections(allSections.map(s => s.id));
  const selectNoneSections = () => setSections([]);

  return (
    <div className="max-w-5xl mx-auto p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Publish &amp; Export</h1>
        <p className="text-sm text-muted-foreground mt-1">Generate reports and export requirements in interchange formats</p>
      </div>

      {/* Reports */}
      <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">Reports</h2>
      <div className="grid grid-cols-1 @2xl:grid-cols-2 @4xl:grid-cols-4 gap-4 mb-6">
        {formats.map((fmt) => {
          const Icon = fmt.icon;
          const active = selectedFormat === fmt.id;
          return (
            <motion.button
              key={fmt.id}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => setSelectedFormat(fmt.id)}
              className={`card p-4 text-left transition-[border-color,box-shadow] cursor-pointer ${
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

      {/* Data Exports */}
      <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">Data Exports</h2>
      <div className="grid grid-cols-1 @3xl:grid-cols-3 gap-4 mb-6">
        {dataFormats.map((fmt) => {
          const Icon = fmt.icon;
          const active = selectedFormat === fmt.id;
          return (
            <motion.button
              key={fmt.id}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => setSelectedFormat(fmt.id)}
              className={`card p-4 text-left transition-[border-color,box-shadow] cursor-pointer ${
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

      {/* Interchange Formats */}
      <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">Interchange Formats</h2>
      <div className="grid grid-cols-1 @3xl:grid-cols-2 gap-4 mb-6">
        {interchangeFormats.map((fmt) => {
          const Icon = fmt.icon;
          const active = selectedFormat === fmt.id;
          return (
            <motion.button
              key={fmt.id}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => setSelectedFormat(fmt.id)}
              className={`card p-4 text-left transition-[border-color,box-shadow] cursor-pointer ${
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

      {latexAvail === false && selectedFormat === 'pdf' && (
        <div className="card p-4 mb-6 border-cs-amber/30 bg-cs-amber/5">
          <p className="text-sm font-medium text-cs-amber">LaTeX engine not detected</p>
          <p className="text-xs text-muted-foreground mt-1">
            PDF reports will be rendered from the HTML version (basic formatting, no coloured badges or table of contents).
            Install a LaTeX engine for full-quality PDF output:
          </p>
          <code className="block mt-2 text-xs bg-muted rounded-md px-3 py-2">
            # Option 1 — single binary (recommended)<br />
            curl -L https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-x86_64-unknown-linux-gnu.tar.gz | tar xz -C ~/.local/bin<br />
            <br />
            # Option 2 — system package<br />
            sudo apt install texlive-latex-base
          </code>
        </div>
      )}

      <div className="grid grid-cols-1 @4xl:grid-cols-3 gap-6">
        <div className="@4xl:col-span-1">
          <Reveal className="card p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold text-sm text-card-foreground">
                {reportFormatIds.has(selectedFormat) ? 'Sections' : 'Format Info'}
              </h2>
              {reportFormatIds.has(selectedFormat) && (
                <div className="flex gap-2">
                  <button onClick={selectAllSections} className="text-3xs text-muted-foreground hover:text-foreground">All</button>
                  <button onClick={selectNoneSections} className="text-3xs text-muted-foreground hover:text-foreground">None</button>
                </div>
              )}
            </div>
            {reportFormatIds.has(selectedFormat) ? (
              <div className="space-y-1">
                {allSections.map((sec) => (
                  <label key={sec.id} className={`flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer transition-colors text-xs ${sections.includes(sec.id) ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-accent'}`}>
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
            ) : (
              <p className="text-xs text-muted-foreground">
                This format exports all requirements in a single file. Section selection applies to report formats only.
              </p>
            )}

            <div className="mt-4 pt-4 border-t space-y-3">
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
                <div className="flex items-center gap-3 text-sm text-muted-foreground">
                  <Loader size={16} className="animate-spin shrink-0" />
                  <span>{downloadStatus || 'Preparing…'}</span>
                </div>
              )}
              <button
                onClick={handleDownload}
                disabled={downloading}
                className="btn-primary w-full justify-center"
              >
                {downloading ? (
                  <><Loader size={14} className="animate-spin" /> Generating…</>) : (
                  <><Download size={14} /> Download {allFormats.find(f => f.id === selectedFormat)?.label.split(' ')[0]}</>
                )}
              </button>
            </div>
          </Reveal>
        </div>

        <div className="@4xl:col-span-2">
          <EmptyState
            icon={FileDown}
            title="Select format and sections, then download"
            hint={selectedFormat === 'html' ? 'HTML opens in a new browser tab' :
               selectedFormat === 'pdf' ? 'PDF downloads as a print-ready document' :
               selectedFormat === 'md' ? 'Markdown downloads as plain text' :
               selectedFormat === 'latex' ? 'LaTeX source downloads for compilation' :
               selectedFormat === 'reqif' ? 'ReqIF downloads as XML for DOORS/Polarion import' :
               selectedFormat === 'sysml' ? 'SysML v2 downloads for MBSE tools' :
               'Downloads as a file for external tools'}
          />
        </div>
      </div>
    </div>
  );
}
