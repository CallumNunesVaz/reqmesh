import { useState, useRef, useEffect, type ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, BookOpen, Boxes, FileText, CheckCircle2, GitBranch, Sigma, Sparkles, ShieldCheck, TrendingUp, Keyboard, Terminal, Globe, Search, Info, AlertTriangle, Lightbulb, ArrowUpCircle } from 'lucide-react';

type DocSection = { id: string; icon: typeof BookOpen; title: string; keywords: string; render: () => ReactNode };

/* ── Helper components ──────────────────────────────────────────────────── */

function H2({ children }: { children: ReactNode }) {
  return <h2 className="text-lg font-semibold text-card-foreground mt-8 mb-3 tracking-tight">{children}</h2>;
}
function H3({ children }: { children: ReactNode }) {
  return <h3 className="text-sm font-semibold text-card-foreground mt-6 mb-2">{children}</h3>;
}
function P({ children }: { children: ReactNode }) {
  return <p className="text-sm text-card-foreground/80 leading-relaxed mb-3">{children}</p>;
}
function UL({ children }: { children: ReactNode }) {
  return <ul className="text-sm text-card-foreground/80 space-y-1 mb-3 pl-4">{children}</ul>;
}
function LI({ children }: { children: ReactNode }) {
  return <li className="before:content-['—'] before:text-muted-foreground/40 before:mr-2">{children}</li>;
}
function OL({ children }: { children: ReactNode }) {
  return <ol className="text-sm text-card-foreground/80 space-y-1 mb-3 pl-4 list-decimal">{children}</ol>;
}
function InlineCode({ children }: { children: ReactNode }) {
  return <code className="text-primary bg-primary/10 px-1.5 py-0.5 rounded text-[12px] font-mono">{children}</code>;
}
function Code({ children }: { children: ReactNode }) {
  return (
    <pre className="bg-muted/80 border rounded-lg p-3 mb-3 overflow-x-auto">
      <code className="text-sm text-card-foreground/80 font-mono whitespace-pre">{children}</code>
    </pre>
  );
}
function Kbd({ children }: { children: string }) {
  return <kbd className="inline-flex items-center border rounded px-1.5 py-px text-[11px] font-mono bg-muted text-muted-foreground">{children}</kbd>;
}
function KeyRow({ keys, action }: { keys: ReactNode; action: string }) {
  return (
    <tr className="hover:bg-accent/30">
      <td className="px-3 py-1.5 text-right font-mono text-[11px] text-foreground">{keys}</td>
      <td className="px-3 py-1.5 text-sm text-card-foreground/80">{action}</td>
    </tr>
  );
}
function KeyTable({ children }: { children: ReactNode }) {
  return (
    <table className="w-full text-left mb-4">
      <tbody>{children}</tbody>
    </table>
  );
}
function Callout({ variant, children }: { variant: 'info' | 'warning' | 'tip'; children: ReactNode }) {
  const meta = {
    info:    { icon: Info,          cls: 'border-blue-500/20 bg-blue-500/[0.04]', iconCls: 'text-blue-400' },
    warning: { icon: AlertTriangle, cls: 'border-amber-500/20 bg-amber-500/[0.04]', iconCls: 'text-amber-400' },
    tip:     { icon: Lightbulb,     cls: 'border-emerald-500/20 bg-emerald-500/[0.04]', iconCls: 'text-emerald-400' },
  }[variant];
  const Icon = meta.icon;
  return (
    <div className={`border rounded-lg p-3 mb-3 ${meta.cls}`}>
      <div className="flex items-start gap-2">
        <Icon size={14} className={`${meta.iconCls} shrink-0 mt-0.5`} />
        <div className="text-sm text-card-foreground/80 leading-relaxed">{children}</div>
      </div>
    </div>
  );
}

/* ── Each section is a proper React component ──────────────────────────── */

const DOCS: DocSection[] = [
  {
    id: 'overview', icon: BookOpen, title: 'Getting Started',
    keywords: 'welcome introduction iso 15288 tour getting started yaml git-native processes',
    render: () => (
      <>
        <H2>Welcome to reqmesh</H2>
        <P>Reqmesh is a git-native requirements management tool. All your data lives in human-readable YAML files alongside your source code — no databases, no lock-in.</P>

        <Callout variant="tip">New here? Press <Kbd>F1</Kbd> any time to open this documentation. Press <Kbd>Ctrl+K</Kbd> to jump to any entity by name or ID.</Callout>

        <H3>ISO 15288 Alignment</H3>
        <P>Reqmesh follows <strong className="text-card-foreground">ISO/IEC 15288:2023</strong>. The matrix below shows the current support level for each of the ~30 technical and management processes.</P>
        <div className="flex items-center gap-4 mb-3 text-[10px]">
          <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-emerald-500/30 border border-emerald-500/40" /> Full</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-amber-500/30 border border-amber-500/40" /> Partial</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-muted border border-border" /> Not addressed</span>
        </div>
        <table className="w-full text-left mb-4">
          <thead>
            <tr className="border-b"><th className="px-3 py-2 text-xs font-medium text-muted-foreground">Process Group / Clause</th><th className="px-3 py-2 text-xs font-medium text-muted-foreground">ISO 15288 Process</th><th className="px-3 py-2 text-xs font-medium text-muted-foreground">Reqmesh Support</th><th className="px-3 py-2 text-xs font-medium text-muted-foreground">Notes</th></tr>
          </thead>
          <tbody>{[
            ['Agreement', '§6.1.1', 'Acquisition', 0, '—'],
            ['Agreement', '§6.1.2', 'Supply', 0, '—'],
            ['Project-Enabling', '§6.2.1', 'Life Cycle Model Mgmt', 1, 'Status workflow (artifact-level only; no system stages)'],
            ['Project-Enabling', '§6.2.2', 'Infrastructure Mgmt', 0, '—'],
            ['Project-Enabling', '§6.2.3', 'Portfolio Mgmt', 0, '—'],
            ['Project-Enabling', '§6.2.4', 'Human Resource Mgmt', 0, '—'],
            ['Project-Enabling', '§6.2.5', 'Quality Mgmt', 1, 'Quality linting (partial process coverage)'],
            ['Project-Enabling', '§6.2.6', 'Knowledge Mgmt', 0, '—'],
            ['Technical Mgmt', '§6.3.1', 'Project Planning', 1, 'Effort + backlog (no schedule/WBS)'],
            ['Technical Mgmt', '§6.3.2', 'Assessment & Control', 1, 'Metrics dashboard'],
            ['Technical Mgmt', '§6.3.3', 'Decision Mgmt', 2, 'Decision Records'],
            ['Technical Mgmt', '§6.3.4', 'Risk Mgmt', 2, 'Risks (severity × probability, linked to requirements)'],
            ['Technical Mgmt', '§6.3.5', 'Configuration Mgmt', 2, 'Baselines + Change Requests + Git integration'],
            ['Technical Mgmt', '§6.3.6', 'Information Mgmt', 1, 'YAML store + git versioning'],
            ['Technical Mgmt', '§6.3.7', 'Measurement', 1, 'Parametrics + evaluation (no formal measurement plan)'],
            ['Technical Mgmt', '§6.3.8', 'Quality Assurance', 2, 'Quality linting (INCOSE / EARS / ISO 29148)'],
            ['Technical', '§6.4.1', 'Business/Mission Analysis', 0, '—'],
            ['Technical', '§6.4.2.1', 'Stakeholder Needs Definition', 1, 'RequirementKind (stakeholder_need); no separate Stakeholder entity'],
            ['Technical', '§6.4.2.2', 'System Requirements Definition', 2, 'Full requirement model with types, priorities, traceability'],
            ['Technical', '§6.4.3', 'Architecture Definition', 1, 'Component tree (physical only; no logical architecture layer)'],
            ['Technical', '§6.4.4', 'Design Definition', 2, 'Component parameters + constraints + budget rollups'],
            ['Technical', '§6.4.5', 'System Analysis', 1, 'Parametric evaluation (no trade studies or sensitivity analysis)'],
            ['Technical', '§6.4.6', 'Implementation', 0, '—'],
            ['Technical', '§6.4.7', 'Integration', 0, '—'],
            ['Technical', '§6.4.8', 'Transition', 0, '—'],
            ['Technical', '§6.4.9', 'Verification', 2, 'Verification Cases (test, analysis, demo, inspection) + Run Test + measurements'],
            ['Technical', '§6.4.10', 'Transition to Operation', 0, '—'],
            ['Technical', '§6.4.11', 'Validation', 1, 'Measured verdicts + CaseType (validation cases); no stakeholder validation framework'],
            ['Technical', '§6.4.12', 'Operation', 0, '—'],
            ['Technical', '§6.4.13', 'Maintenance', 0, '—'],
            ['Technical', '§6.4.14', 'Disposal', 0, '—'],
          ].map(([group, clause, process, level, notes], i) => {
            const ck = String(clause).replace(/\./g, '-');
            return (
              <tr key={`${ck}-${i}`} className="hover:bg-accent/30">
                <td className="px-3 py-1.5 text-[10px] text-muted-foreground">{group}</td>
                <td className="px-3 py-1.5 text-[10px]"><span className="font-mono text-muted-foreground">{clause}</span> <span className="text-card-foreground">{process}</span></td>
                <td className="px-3 py-1.5"><span className={`inline-block w-3 h-3 rounded-sm border ${level === 2 ? 'bg-emerald-500/30 border-emerald-500/40' : level === 1 ? 'bg-amber-500/30 border-amber-500/40' : 'bg-muted border-border'}`} /></td>
                <td className="px-3 py-1.5 text-[10px] text-card-foreground/60">{notes}</td>
              </tr>
            );
          })}</tbody></table>

        <H3>What you can do</H3>
        <UL>
          <LI><strong className="text-card-foreground">Write requirements</strong> with rich text, structured properties, and traceability links</LI>
          <LI><strong className="text-card-foreground">Model physical design</strong> as a hierarchy of components mapped to requirements</LI>
          <LI><strong className="text-card-foreground">Verify</strong> that requirements are met with linked verification cases</LI>
          <LI><strong className="text-card-foreground">Evaluate constraints</strong> with a SysML-style parametric engine</LI>
          <LI><strong className="text-card-foreground">Track quality</strong> with automated linting against INCOSE / EARS guidelines</LI>
          <LI><strong className="text-card-foreground">Review and baseline</strong> with content-fingerprint change control</LI>
          <LI><strong className="text-card-foreground">Import/export</strong> via ReqIF 1.2, SysML v2, CSV, TSV, and XLSX</LI>
          <LI><strong className="text-card-foreground">Collaborate</strong> in real-time with live change streaming and presence</LI>
        </UL>

        <H3>Quick tour</H3>
        <OL>
          <LI>Click <strong className="text-card-foreground">Requirements</strong> in the left nav to see the requirements tree</LI>
          <LI>Click any requirement to open its detail page</LI>
          <LI>The <strong className="text-card-foreground">Graph</strong> pane (right side) shows a visual traceability diagram</LI>
          <LI>Use <Kbd>Ctrl+K</Kbd> to jump to anything by name or ID</LI>
          <LI>Press <Kbd>?</Kbd> or <Kbd>Ctrl+/</Kbd> to see keyboard shortcuts</LI>
        </OL>
      </>
    ),
  },
  {
    id: 'keyboard', icon: Keyboard, title: 'Keyboard Shortcuts',
    keywords: 'shortcuts keys hotkeys ctrl alt navigation palette f1',
    render: () => (
      <>
        <H2>Keyboard Shortcuts</H2>
        <P>Reqmesh can be used entirely via keyboard.</P>

        <Callout variant="info">Shortcuts do not fire when you are typing in a text field (except <Kbd>Ctrl+S</Kbd> for save).</Callout>

        <H3>Global</H3>
        <KeyTable>
          <KeyRow keys={<Kbd>Ctrl+K</Kbd>} action="Open command palette" />
          <KeyRow keys={<Kbd>Ctrl+E</Kbd>} action="Toggle edit / view mode" />
          <KeyRow keys={<Kbd>Ctrl+G</Kbd>} action="Toggle graph pane" />
          <KeyRow keys={<Kbd>Ctrl+H</Kbd>} action="Toggle guided mode (helpers)" />
          <KeyRow keys={<Kbd>F1</Kbd>} action="Open this documentation" />
          <KeyRow keys={<Kbd>Ctrl+/</Kbd>} action="Show keyboard shortcut reference" />
          <KeyRow keys={<Kbd>Escape</Kbd>} action="Close dialog, deselect, or go back" />
        </KeyTable>

        <H3>Quick Navigation</H3>
        <KeyTable>
          <KeyRow keys={<><Kbd>Alt+R</Kbd></>} action="Go to Requirements" />
          <KeyRow keys={<><Kbd>Alt+C</Kbd></>} action="Go to Components" />
          <KeyRow keys={<><Kbd>Alt+S</Kbd></>} action="Go to Specifications" />
          <KeyRow keys={<><Kbd>Alt+V</Kbd></>} action="Go to Verification Cases" />
          <KeyRow keys={<><Kbd>Alt+T</Kbd></>} action="Go to Trace Matrix" />
          <KeyRow keys={<><Kbd>Alt+H</Kbd></>} action="Go to Change Requests" />
          <KeyRow keys={<><Kbd>Alt+K</Kbd></>} action="Go to Risks" />
          <KeyRow keys={<><Kbd>Alt+M</Kbd></>} action="Go to Metrics" />
          <KeyRow keys={<><Kbd>Alt+P</Kbd></>} action="Go to Publish" />
        </KeyTable>

        <H3>List Pages</H3>
        <KeyTable>
          <KeyRow keys={<><Kbd>j</Kbd> or <Kbd>↓</Kbd></>} action="Select next item" />
          <KeyRow keys={<><Kbd>k</Kbd> or <Kbd>↑</Kbd></>} action="Select previous item" />
          <KeyRow keys={<Kbd>Enter</Kbd>} action="Open selected item" />
          <KeyRow keys={<Kbd>/</Kbd>} action="Focus the search field" />
          <KeyRow keys={<Kbd>n</Kbd>} action="Create a new item" />
          <KeyRow keys={<Kbd>Escape</Kbd>} action="Clear selection" />
        </KeyTable>

        <H3>Detail Pages</H3>
        <KeyTable>
          <KeyRow keys={<Kbd>Ctrl+S</Kbd>} action="Save changes" />
          <KeyRow keys={<Kbd>Escape</Kbd>} action="Back to list" />
          <KeyRow keys={<Kbd>Delete</Kbd>} action="Delete this item" />
        </KeyTable>
      </>
    ),
  },
  {
    id: 'requirements', icon: FileText, title: 'Requirements Management',
    keywords: 'requirement properties status priority traceability relations refines satisfies derives conflicts coverage needs',
    render: () => (
      <>
        <H2>Requirements</H2>
        <P>Requirements are the core entity. Each requirement is one YAML file in your project's <InlineCode>requirements/</InlineCode> directory.</P>

        <H3>Properties</H3>
        <UL>
          <LI><strong className="text-card-foreground">ID</strong> — unique identifier (validated as filename-safe)</LI>
          <LI><strong className="text-card-foreground">Type</strong> — <span className="text-blue-400">functional</span>, <span className="text-teal-400">non-functional</span>, <span className="text-purple-400">interface</span>, <span className="text-pink-400">design</span>, or <span className="text-orange-400">constraint</span></LI>
          <LI><strong className="text-card-foreground">Status</strong> — proposed → approved → implemented → verified → rejected → deprecated</LI>
          <LI><strong className="text-card-foreground">Priority</strong> — low, medium, high, or critical</LI>
          <LI><strong className="text-card-foreground">Verification method</strong> — test, analysis, demonstration, or inspection</LI>
        </UL>

        <H3>Traceability</H3>
        <P>Create <strong className="text-card-foreground">relations</strong> between requirements to build a traceability graph:</P>
        <UL>
          <LI><strong className="text-card-foreground">refines</strong> — this requirement details another</LI>
          <LI><strong className="text-card-foreground">satisfies</strong> — this requirement meets a higher-level need</LI>
          <LI><strong className="text-card-foreground">derives</strong> — this requirement is derived from another</LI>
          <LI><strong className="text-card-foreground">conflicts</strong> — these requirements are in tension</LI>
          <LI><strong className="text-card-foreground">verified_by</strong> — a verification case proves this requirement</LI>
        </UL>

        <H3>Coverage</H3>
        <P>Each requirement can declare <strong className="text-card-foreground">needs</strong> — the artifact types that must cover it. For example, a system requirement with <InlineCode>needs: [design, test]</InlineCode> requires coverage from at least one design artifact and one test. The coverage engine computes <strong className="text-card-foreground">shallow</strong> (immediate) and <strong className="text-card-foreground">deep</strong> (transitive) status.</P>

        <Callout variant="tip">Relations are bidirectional — when you link A → B, B automatically shows that A links to it.</Callout>
      </>
    ),
  },
  {
    id: 'components', icon: Boxes, title: 'Components — the Design',
    keywords: 'component hierarchy system subsystem assembly part software interface satisfies quantity rollup budget mass',
    render: () => (
      <>
        <H2>Components</H2>
        <P>Requirements describe what the system must <strong className="text-card-foreground">do</strong>. Components describe what the system <strong className="text-card-foreground">is</strong> — the synthesised design.</P>

        <H3>Hierarchy</H3>
        <P>Components form a tree:</P>
        <UL>
          <LI><span className="text-blue-400 font-medium">system</span> — the whole product</LI>
          <LI><span className="text-purple-400 font-medium">subsystem</span> — a major functional grouping</LI>
          <LI><span className="text-orange-400 font-medium">assembly</span> — a group of parts</LI>
          <LI><span className="text-green-400 font-medium">part</span> — the smallest replaceable unit</LI>
          <LI><span className="text-teal-400 font-medium">software</span> — a software module</LI>
          <LI><span className="text-pink-400 font-medium">interface</span> — a connection point</LI>
        </UL>
        <P>Each component has a <strong className="text-card-foreground">quantity</strong> — parts with quantity &gt; 1 are multiplied in budget rollups.</P>

        <H3>Mapping to Requirements</H3>
        <P>Components carry two links to the functional side:</P>
        <UL>
          <LI><strong className="text-card-foreground">satisfies</strong> — the requirements this component exists to deliver</LI>
          <LI><strong className="text-card-foreground">verification_cases</strong> — the tests that exercise this component</LI>
        </UL>
        <P>Both are validated: linking to a non-existent requirement or VC is rejected. Deleting a component promotes its children to the deleted component's parent.</P>

        <H3>Parameters & Rollups</H3>
        <P>Components carry numeric parameters (mass, current draw, cost…) that participate in <strong className="text-card-foreground">budget rollups</strong>:</P>
        <Code>rollup('C172', 'mass')  →  sums mass across every component under C172</Code>
        <P>Quantity is multiplied automatically — 2× SPAR each at 19 kg contributes 38 kg.</P>
      </>
    ),
  },
  {
    id: 'parametrics', icon: Sigma, title: 'Parametrics & Constraints',
    keywords: 'parameter constraint expression derived margin verdict pass fail unknown rollup evaluate sysml units dimension value type constraint def calc def definition binding analysis case what-if subject interchange round-trip',
    render: () => (
      <>
        <H2>Parametric Evaluation</H2>
        <P>Requirements can carry typed parameters and evaluable constraints — they are not just prose, they can be computed.</P>

        <H3>Parameters</H3>
        <P>Parameters are named numbers with a unit:</P>
        <Code>name: mtow,  value: 1157,  unit: kg</Code>
        <P>A parameter can also be <strong className="text-card-foreground">derived</strong> via an expression:</P>
        <Code>name: useful_load,  unit: kg,  expr: "mtow - AFRM0000.empty_mass"</Code>

        <H3>Constraints</H3>
        <P>Constraints are boolean pass/fail checks:</P>
        <Code>{'expr: "useful_load >= 380"'}</Code>
        <P>Add an <strong className="text-card-foreground">assume</strong> clause to gate a constraint:</P>
        <Code>{'expr: "cabin_temp >= 18",  assume: "OAT >= -20"'}</Code>
        <P>If the assumption fails, the constraint is "not applicable" instead of "failed".</P>

        <H3>Verdicts & Margins</H3>
        <P>Every constraint evaluates to one of:</P>
        <div className="flex flex-wrap gap-2 mb-3 text-xs">
          <span className="badge bg-emerald-500/10 text-emerald-400 border-emerald-500/30">pass</span>
          <span className="badge bg-red-500/10 text-red-400 border-red-500/30">fail</span>
          <span className="badge bg-amber-500/10 text-amber-400 border-amber-500/30">unknown</span>
          <span className="badge bg-red-500/10 text-red-400 border-red-500/30">error</span>
          <span className="badge bg-muted text-muted-foreground">not applicable</span>
        </div>
        <P>Single-comparison constraints report a <strong className="text-card-foreground">margin</strong>: how far you are from the boundary (e.g. <InlineCode>+3.0 (+0.26%)</InlineCode>).</P>

        <H3>Expression Language</H3>
        <P>Arithmetic: <InlineCode>+ - * / ** %</InlineCode>  ·  Comparisons: <InlineCode>&lt; &lt;= &gt; &gt;= == !=</InlineCode> (chainable: <InlineCode>5 &lt; x &lt; 10</InlineCode>)</P>
        <P>Logic: <InlineCode>and or not</InlineCode>  ·  Functions: <InlineCode>min(a,b) max(a,b) abs(x) sqrt(x) floor(x) ceil(x) round(x)</InlineCode></P>
        <P>References: <InlineCode>REQ_ID.param_name</InlineCode>  ·  Rollups: <InlineCode>rollup('COMP_ID', 'param')</InlineCode></P>

        <Callout variant="info">All expressions are parsed against a strict whitelist — YAML content can never execute arbitrary code.</Callout>

        <H3>Units &amp; Dimensional Checking</H3>
        <P>Units are more than labels. reqmesh recognises common SI and aerospace units (<InlineCode>kg, m, N, W, A, kt, psi…</InlineCode>) and their dimensions. If a derived parameter or comparison mixes incompatible quantities (say a mass plus a length), an amber <strong className="text-card-foreground">units</strong> warning appears next to it.</P>
        <Callout variant="info">Dimensional checks are advisory — they never change a pass/fail verdict, and unknown or blank units are simply not checked (so ad-hoc units never warn).</Callout>

        <H3>Reusable Definitions (SysML v2 constraint / calc def)</H3>
        <P>Write a rule once and reuse it. A <strong className="text-card-foreground">constraint def</strong> declares formal parameters and an expression; requirements apply it by <strong className="text-card-foreground">binding</strong> each formal to a real parameter reference:</P>
        <Code>{'MassBudget(actual, limit) = actual <= limit\n→ bind: actual = AFRM0000.design_mass, limit = AFRM0000.empty_mass'}</Code>
        <P>A <strong className="text-card-foreground">calc def</strong> (e.g. <InlineCode>Area(w, h) = w * h</InlineCode>) derives a parameter's value the same way. Manage definitions on the <strong className="text-card-foreground">Metrics &amp; Analysis</strong> page; bind them on a requirement under "Use a definition".</P>

        <H3>Analysis Cases (what-if)</H3>
        <P>An analysis case runs the evaluation over a chosen <strong className="text-card-foreground">scope</strong> with hypothetical parameter <strong className="text-card-foreground">overrides</strong>, without touching the model — e.g. "does the mass budget still hold at <InlineCode>empty_mass = 779</InlineCode>?". Create and run them on the Metrics &amp; Analysis page.</P>

        <H3>Requirement Subject</H3>
        <P>A requirement can name the component it constrains via its <strong className="text-card-foreground">subject</strong> (a SysML v2 concept), set in the requirement's properties panel.</P>

        <H3>SysML v2 Interchange</H3>
        <P>Parameters, constraints (with assume/require), measure kinds, subjects, and the component tree all <strong className="text-card-foreground">round-trip</strong> through SysML v2 export and import — so the parametric model survives a trip to and from other SysML v2 tooling.</P>
      </>
    ),
  },
  {
    id: 'verification', icon: CheckCircle2, title: 'Verification Cases',
    keywords: 'verification case test analysis demonstration inspection measurement execution run bulk',
    render: () => (
      <>
        <H2>Verification Cases</H2>
        <P>Verification cases prove that requirements are met. They can be <strong className="text-card-foreground">tests</strong>, <strong className="text-card-foreground">analyses</strong>, <strong className="text-card-foreground">demonstrations</strong>, or <strong className="text-card-foreground">inspections</strong>.</P>

        <H3>Measurements</H3>
        <P>Record numeric measurements against requirement parameters:</P>
        <Code>parameter: "AFRM0005.max_load"    value: 5.92    unit: g</Code>
        <P>The auto-complete suggests parameters from linked requirements. The <strong className="text-card-foreground">unit field auto-fills</strong> when you select a parameter.</P>

        <H3>Execution</H3>
        <P>Each VC tracks an execution history: timestamp, status, notes, and executor. The <strong className="text-card-foreground">Run Test</strong> button logs a new execution entry and shows a spinner while the API call is in flight.</P>

        <H3>Bulk Operations</H3>
        <P>Select multiple VCs via their checkboxes (visible in edit mode), choose a target status from the bulk action bar, and click <strong className="text-card-foreground">Apply</strong> to update all selected cases at once.</P>
      </>
    ),
  },
  {
    id: 'coverage', icon: GitBranch, title: 'Traceability & Coverage',
    keywords: 'traceability shallow deep coverage broken chain scan tags openfasttrace report ci trace',
    render: () => (
      <>
        <H2>Deep Traceability</H2>
        <P>Reqmesh provides both <strong className="text-card-foreground">shallow</strong> and <strong className="text-card-foreground">deep</strong> coverage analysis, inspired by OpenFastTrace.</P>

        <H3>Shallow Coverage</H3>
        <P>For each entry in a requirement's <InlineCode>needs</InlineCode> list, is there at least one covering item of that type? Shallow coverage checks immediate, one-hop coverage.</P>

        <H3>Deep Coverage</H3>
        <P>Is the requirement covered, AND are all of its coverers themselves deeply covered (recursively)? Deep coverage checks the entire chain from requirements through design to implementation and test.</P>

        <H3>Broken Chains</H3>
        <P>A requirement that is shallow-covered but not deep-covered has a <strong className="text-card-foreground">broken chain</strong> — one of its coverers is missing its own coverage. The Metrics page identifies these gaps.</P>

        <H3>Code Scanning</H3>
        <P>Run <InlineCode>POST /api/projects/{'{id}'}/scan</InlineCode> or the CLI <InlineCode>scan</InlineCode> command to scan source files for coverage tags:</P>
        <Code>[impl-&gt;dsn~validate-request~1]{"\n"}@covers REQ-AUTH-001</Code>
        <P>Discovered links are merged into requirement references with SHA-256 staleness detection.</P>

        <H3>Reports</H3>
        <P>Use <InlineCode>GET /api/projects/{'{id}'}/trace?format=text</InlineCode> or the CLI <InlineCode>trace</InlineCode> command for an OFT-style plaintext coverage report. The command exits non-zero when deep coverage is incomplete — suitable for CI gates.</P>
      </>
    ),
  },
  {
    id: 'review', icon: ShieldCheck, title: 'Review & Fingerprints',
    keywords: 'fingerprint review suspect link doorstop sha-256 unreviewed normative derived baseline',
    render: () => (
      <>
        <H2>Fingerprint-Based Review</H2>
        <P>Inspired by Doorstop, requirements and their links carry content-hash fingerprints that automatically detect when re-review is needed.</P>

        <H3>How it works</H3>
        <OL>
          <LI>Each requirement has a <strong className="text-card-foreground">reviewed</strong> field — a SHA-256 hash of its normative content</LI>
          <LI>When you click <strong className="text-card-foreground">Review</strong>, the current fingerprint is stored</LI>
          <LI>If any normative field changes, the fingerprint no longer matches and the requirement is flagged as <strong className="text-amber-400">unreviewed</strong></LI>
          <LI>Each relation stores the target's fingerprint at review time. If the target changes, the link becomes <strong className="text-amber-400">suspect</strong></LI>
        </OL>

        <Callout variant="warning">Changing the description, type, priority, source, or rationale triggers re-review. Changing <InlineCode>allocated_to</InlineCode> or <InlineCode>baselines</InlineCode> does not.</Callout>

        <H3>Derived & Non-normative</H3>
        <UL>
          <LI><strong className="text-card-foreground">derived: true</strong> — no parent link needed (e.g. external regulatory mandate)</LI>
          <LI><strong className="text-card-foreground">normative: false</strong> — excluded from coverage and gap analysis; rendered as section headings in published output</LI>
        </UL>
      </>
    ),
  },
  {
    id: 'quality', icon: Sparkles, title: 'Quality Linting',
    keywords: 'linting incose ears iso 29148 weak words vague placeholder passive voice atomic guided mode score',
    render: () => (
      <>
        <H2>Requirement Quality Linting</H2>
        <P>Reqmesh automatically checks requirement text against writing guidelines based on INCOSE, EARS, and ISO 29148.</P>

        <H3>Rules</H3>
        <table className="w-full text-left mb-4">
          <thead>
            <tr className="border-b">
              <th className="px-3 py-2 text-xs font-medium text-muted-foreground">Rule</th>
              <th className="px-3 py-2 text-xs font-medium text-muted-foreground">Detects</th>
              <th className="px-3 py-2 text-xs font-medium text-muted-foreground">Severity</th>
            </tr>
          </thead>
          <tbody>
            <tr className="hover:bg-accent/30">
              <td className="px-3 py-1.5 text-xs font-medium text-card-foreground">Weak words</td>
              <td className="px-3 py-1.5 text-xs text-card-foreground/70">"should", "may", "appropriate", "user-friendly"</td>
              <td className="px-3 py-1.5 text-xs"><span className="badge bg-amber-500/10 text-amber-400">warning</span></td>
            </tr>
            <tr className="hover:bg-accent/30">
              <td className="px-3 py-1.5 text-xs font-medium text-card-foreground">Vague quantifiers</td>
              <td className="px-3 py-1.5 text-xs text-card-foreground/70">"several", "minimal", "a lot of"</td>
              <td className="px-3 py-1.5 text-xs"><span className="badge bg-amber-500/10 text-amber-400">warning</span></td>
            </tr>
            <tr className="hover:bg-accent/30">
              <td className="px-3 py-1.5 text-xs font-medium text-card-foreground">Placeholders</td>
              <td className="px-3 py-1.5 text-xs text-card-foreground/70">"TODO", "TBD", "FIXME"</td>
              <td className="px-3 py-1.5 text-xs"><span className="badge bg-red-500/10 text-red-400">error</span></td>
            </tr>
            <tr className="hover:bg-accent/30">
              <td className="px-3 py-1.5 text-xs font-medium text-card-foreground">Non-atomic</td>
              <td className="px-3 py-1.5 text-xs text-card-foreground/70">Multiple "and" conjunctions</td>
              <td className="px-3 py-1.5 text-xs"><span className="badge bg-muted text-muted-foreground">info</span></td>
            </tr>
            <tr className="hover:bg-accent/30">
              <td className="px-3 py-1.5 text-xs font-medium text-card-foreground">Word count</td>
              <td className="px-3 py-1.5 text-xs text-card-foreground/70">Too short (&lt; 5) or too long (&gt; 200)</td>
              <td className="px-3 py-1.5 text-xs"><span className="badge bg-amber-500/10 text-amber-400">warning</span></td>
            </tr>
            <tr className="hover:bg-accent/30">
              <td className="px-3 py-1.5 text-xs font-medium text-card-foreground">Untestable</td>
              <td className="px-3 py-1.5 text-xs text-card-foreground/70">Test-verified with no measurable criteria</td>
              <td className="px-3 py-1.5 text-xs"><span className="badge bg-amber-500/10 text-amber-400">warning</span></td>
            </tr>
            <tr className="hover:bg-accent/30">
              <td className="px-3 py-1.5 text-xs font-medium text-card-foreground">Passive voice</td>
              <td className="px-3 py-1.5 text-xs text-card-foreground/70">"is processed by"</td>
              <td className="px-3 py-1.5 text-xs"><span className="badge bg-muted text-muted-foreground">info</span></td>
            </tr>
          </tbody>
        </table>

        <H3>Configuration</H3>
        <P>Customise thresholds in <InlineCode>_meta.yaml</InlineCode>:</P>
        <Code>{`quality:
  min_words: 5
  max_words: 300
  rules:
    weak_words: true
    passive_voice: false
  weights:
    weak_words: 5
    placeholders: 10`}</Code>

        <H3>Live Feedback</H3>
        <P>Enable <strong className="text-card-foreground">Guided Mode</strong> (<Kbd>Ctrl+H</Kbd>) to see live quality feedback as you type, including a guideline reference panel explaining each rule.</P>

        <Callout variant="tip">Run <InlineCode>python -m app.cli validate &lt;project&gt; --quality --quality-floor 60</InlineCode> to enforce a quality gate in CI. Exits non-zero if the project average drops below the floor.</Callout>
      </>
    ),
  },
  {
    id: 'planning', icon: TrendingUp, title: 'Planning & Estimation',
    keywords: 'effort story points backlog stakeholder priorities burndown decision records estimation',
    render: () => (
      <>
        <H2>Planning & Estimation</H2>
        <P>Lightweight project-planning signals on top of requirements.</P>

        <H3>Effort</H3>
        <P>Set <strong className="text-card-foreground">story points</strong> on requirements to track implementation effort. The <strong className="text-card-foreground">Metrics</strong> dashboard shows total, completed, and remaining effort by status — a simple burndown view.</P>

        <H3>Stakeholder Priorities</H3>
        <P>Assign per-stakeholder scores:</P>
        <Code>{`priorities:
  development: 5
  customers: 8
  safety: 10`}</Code>

        <H3>Backlog</H3>
        <P><InlineCode>GET /api/projects/{'{id}'}/backlog</InlineCode> returns requirements sorted by a combined priority function. Filter by status, sort by effort or priority.</P>

        <H3>Decision Records</H3>
        <P>Record architectural and engineering decisions with context, alternatives, rationale, and linked requirements. Decisions appear on the documentation section of each linked requirement's detail page.</P>
      </>
    ),
  },
  {
    id: 'git', icon: GitBranch, title: 'Git Integration',
    keywords: 'git auto-commit push remote offline air-gapped history commits version control',
    render: () => (
      <>
        <H2>Git Integration</H2>
        <P>Reqmesh is git-native — your project is a git repository.</P>

        <H3>Auto-Commit</H3>
        <P>Every mutation through the API is committed automatically with a descriptive message like <InlineCode>rt: put requirements/SYST0001</InlineCode>. Disable with <InlineCode>RT_GIT_AUTOCOMMIT=false</InlineCode>.</P>

        <H3>Push to Remote</H3>
        <P>Set <InlineCode>RT_GIT_REMOTE_URL</InlineCode> and <InlineCode>RT_GIT_PUSH_ON_COMMIT=true</InlineCode> to push after every auto-commit. Useful for off-server backup and audit logging.</P>

        <H3>Offline Mode</H3>
        <P>Set <InlineCode>RT_OFFLINE_MODE=true</InlineCode> to suppress all outbound network calls (git push, SMTP). The application works fully air-gapped.</P>

        <H3>Change History</H3>
        <P>Every entity (requirements, components, specifications, verification cases) tracks field-level changes in <InlineCode>history/</InlineCode>. <InlineCode>GET /api/projects/{'{id}'}/git/log</InlineCode> shows git commits. Both work independently — history works without git.</P>
      </>
    ),
  },
  {
    id: 'interchange', icon: FileText, title: 'Import & Export',
    keywords: 'import export reqif sysml csv tsv xlsx excel doors polarion jama merge replace interchange',
    render: () => (
      <>
        <H2>Interchange Formats</H2>
        <P>Reqmesh supports round-trip interchange through five formats:</P>

        <div className="space-y-2 mb-4">
          <Callout variant="info"><strong className="text-card-foreground">ReqIF 1.2</strong> — Standard requirements interchange format used by DOORS, Polarion, and Jama. Both import and export preserve types, attributes, relations, and verification links.</Callout>
          <Callout variant="info"><strong className="text-card-foreground">SysML v2</strong> — Textual MBSE notation. Import and export preserve the requirement hierarchy and constraints.</Callout>
          <Callout variant="tip"><strong className="text-card-foreground">CSV / TSV / XLSX</strong> — Spreadsheet formats for stakeholder review. Export creates a flat table with all fields. Import maps common header names (e.g. "Requirement ID" → id). XLSX export includes styled headers. Dry-run mode previews changes before applying.</Callout>
        </div>

        <H3>Import Modes</H3>
        <UL>
          <LI><strong className="text-card-foreground">merge</strong> (default) — creates new entities, updates matching IDs</LI>
          <LI><strong className="text-card-foreground">replace</strong> — wipes existing requirements first, then imports</LI>
        </UL>

        <H3>Export</H3>
        <P>Access via the <strong className="text-card-foreground">Export</strong> button in the header, or:</P>
        <Code>python -m app.cli export &lt;project&gt; -f reqif{"\n"}python -m app.cli export &lt;project&gt; -f sysml</Code>
      </>
    ),
  },
  {
    id: 'cli', icon: Terminal, title: 'CLI Reference',
    keywords: 'command line cli terminal validate trace review scan publish export import serve create',
    render: () => (
      <>
        <H2>Command-Line Interface</H2>
        <P>All commands run from the <InlineCode>backend/</InlineCode> directory:</P>
        <Code>cd backend{"\n"}.venv/bin/python -m app.cli &lt;command&gt;</Code>

        <H3>Project Management</H3>
        <KeyTable>
          <KeyRow keys={<InlineCode>create &lt;id&gt;</InlineCode>} action="Create a new project" />
          <KeyRow keys={<InlineCode>serve [path]</InlineCode>} action="Start the web server" />
        </KeyTable>

        <H3>Validation & Analysis</H3>
        <KeyTable>
          <KeyRow keys={<InlineCode>validate [path]</InlineCode>} action="Integrity checks (dangling links, cycles, cascades)" />
          <KeyRow keys={<InlineCode>validate [path] --quality</InlineCode>} action="Integrity checks + requirement quality linting" />
          <KeyRow keys={<InlineCode>trace [path]</InlineCode>} action="Coverage report (exits non-zero on gaps)" />
          <KeyRow keys={<InlineCode>review [path]</InlineCode>} action="Fingerprint-baseline all requirements" />
          <KeyRow keys={<InlineCode>review [path] --item REQ-001</InlineCode>} action="Baseline a single requirement" />
          <KeyRow keys={<InlineCode>scan [path] --code ../src</InlineCode>} action='Scan for [impl→ID] coverage tags' />
        </KeyTable>

        <H3>Publishing & Interchange</H3>
        <KeyTable>
          <KeyRow keys={<InlineCode>publish [path] -f html</InlineCode>} action="Generate HTML report" />
          <KeyRow keys={<InlineCode>publish [path] -f pdf</InlineCode>} action="Generate PDF report" />
          <KeyRow keys={<InlineCode>export [path] -f reqif</InlineCode>} action="Export to ReqIF 1.2" />
          <KeyRow keys={<InlineCode>export [path] -f sysml</InlineCode>} action="Export to SysML v2" />
          <KeyRow keys={<InlineCode>import [path] -i file.reqif</InlineCode>} action="Import ReqIF file" />
          <KeyRow keys={<InlineCode>import [path] -i file.csv -m replace</InlineCode>} action="Replace all with CSV data" />
        </KeyTable>
      </>
    ),
  },
  {
    id: 'deployment', icon: Globe, title: 'Deployment',
    keywords: 'deploy docker server electron desktop environment variables tls https smtp production secret admin',
    render: () => (
      <>
        <H2>Deployment</H2>
        <P>Reqmesh can be deployed as a web server, Docker container, or desktop app.</P>

        <H3>Server (development)</H3>
        <Code>./start.sh server</Code>
        <P>Backend on :8000, frontend on :5173.</P>

        <H3>Docker (production)</H3>
        <Code>export RT_SECRET=$(openssl rand -hex 32){"\n"}export RT_ADMIN_PASSWORD=$(openssl rand -base64 16){"\n"}docker compose -f docker-compose.prod.yml up -d</Code>
        <P>Serves on a single origin (backend serves the built SPA). See <InlineCode>DEPLOYMENT.md</InlineCode> for TLS configuration with Caddy or nginx, email notifications, git push to remote, and air-gapped deployment.</P>

        <H3>Desktop (Electron)</H3>
        <Code>./start.sh desktop</Code>
        <P>Builds the frontend and launches a native window. The backend is spawned and torn down automatically.</P>

        <H3>Key Environment Variables</H3>
        <table className="w-full text-left mb-4">
          <thead>
            <tr className="border-b">
              <th className="px-3 py-2 text-xs font-medium text-muted-foreground">Variable</th>
              <th className="px-3 py-2 text-xs font-medium text-muted-foreground">Purpose</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['RT_DATA_ROOT', 'Where projects are stored'],
              ['RT_SECRET', 'JWT signing key'],
              ['RT_ADMIN_PASSWORD', 'Initial admin password'],
              ['RT_GIT_AUTOCOMMIT', 'Auto-commit changes'],
              ['RT_GIT_REMOTE_URL', 'Remote to push commits'],
              ['RT_OFFLINE_MODE', 'Suppress all outbound calls'],
              ['RT_SMTP_HOST', 'SMTP server for email notifications'],
              ['RT_BASE_URL', 'Public URL for email links'],
              ['RT_SEED_DEMO', 'Seed Cessna 172S example'],
              ['RT_LOG_LEVEL', 'Python log level'],
            ].map(([k, v]) => (
              <tr key={k} className="hover:bg-accent/30">
                <td className="px-3 py-1.5 text-xs font-mono text-primary">{k}</td>
                <td className="px-3 py-1.5 text-xs text-card-foreground/70">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </>
    ),
  },
  {
    id: 'releases', icon: GitBranch, title: 'Releases',
    keywords: 'release version vX.Y.Z semver tag github bundle tarball docker ghcr deploy install manifest changelog',
    render: () => (
      <>
        <H2>Releases</H2>
        <P>A release is a version-controlled <InlineCode>vX.Y.Z</InlineCode> build of reqmesh, bundled for deployment on a server. Each release ships the backend, the built frontend, and the pre-seeded Cessna 172S example project, plus deployment configs and an installer.</P>

        <H3>Version source of truth</H3>
        <P>The repo-root <InlineCode>VERSION</InlineCode> file is authoritative; <InlineCode>scripts/set_version.py</InlineCode> propagates it to the backend and the frontend/desktop <InlineCode>package.json</InlineCode>. The running version is served at <InlineCode>/version</InlineCode> and shown next to the reqmesh logo.</P>

        <H3>Cutting a release</H3>
        <Code>scripts/release.sh minor    # 0.4.0 -&gt; 0.5.0 (also: patch | major | X.Y.Z)</Code>
        <P>This bumps the version everywhere, writes release notes from the commits since the last tag, builds the bundle as a smoke test, commits, tags <InlineCode>vX.Y.Z</InlineCode>, and pushes. Pushing the tag runs the GitHub Actions workflow, which publishes a GitHub Release (tarball + checksum) and pushes the Docker image to <InlineCode>ghcr.io</InlineCode>.</P>

        <H3>Artifacts</H3>
        <UL>
          <LI><InlineCode>reqmesh-vX.Y.Z.tar.gz</InlineCode> — unpack and run <InlineCode>./install.sh</InlineCode> (Docker if present, else a Python venv).</LI>
          <LI><InlineCode>ghcr.io/&lt;owner&gt;/reqmesh:X.Y.Z</InlineCode> — <InlineCode>docker compose -f docker-compose.prod.yml up -d</InlineCode>.</LI>
        </UL>
        <Callout variant="tip">See <InlineCode>RELEASING.md</InlineCode> in the repo for the full process, including <InlineCode>--dry-run</InlineCode> and <InlineCode>--no-push</InlineCode> options.</Callout>
      </>
    ),
  },
  {
    id: 'updates', icon: ArrowUpCircle, title: 'Updates',
    keywords: 'update self-update upgrade new version admin system settings docker sidecar rollback migration backup latest github release',
    render: () => (
      <>
        <H2>Updates</H2>
        <P>Administrators can check for and apply new versions from the <InlineCode>System</InlineCode> page (top bar &rarr; System). reqmesh compares its running version to the latest release on GitHub and shows when a newer one is available, with its release notes.</P>

        <H3>One-click update (Docker)</H3>
        <P>When deployed with Docker and the <InlineCode>self-update</InlineCode> profile, an admin can update in place. reqmesh backs up every project (a <InlineCode>pre-update-&lt;version&gt;</InlineCode> git tag), then a small updater sidecar pulls the new image and recreates the app. The app container never holds the Docker socket &mdash; only the sidecar does.</P>
        <Code>docker compose -f docker-compose.prod.yml --profile self-update up -d</Code>

        <H3>Clean transition</H3>
        <UL>
          <LI>Project data lives on its own volume and is preserved across the update.</LI>
          <LI>Data-schema migrations run automatically on the new version's first start.</LI>
          <LI>A pre-update backup tag per project allows rollback if a migration misbehaves.</LI>
        </UL>

        <H3>Offline / air-gapped (update from a file)</H3>
        <P>When the server can't reach GitHub, an admin can upload an image archive instead (System &rarr; <InlineCode>Update from a file</InlineCode>). Download the <InlineCode>reqmesh-v&lt;version&gt;-image.tar.gz</InlineCode> asset from a release on a connected machine, transfer it across, and upload it &mdash; reqmesh backs up data and the sidecar loads the image and recreates the app, with no network access. This still uses the self-update sidecar.</P>

        <H3>Other deployments</H3>
        <P>Without the self-update profile (or on bare-metal), the System page shows the exact manual commands instead &mdash; typically <InlineCode>docker compose pull &amp;&amp; up -d</InlineCode>, or downloading the new release tarball and re-running <InlineCode>install.sh</InlineCode>.</P>
        <Callout variant="info">See <InlineCode>DEPLOYMENT.md</InlineCode> &sect;12b for enabling self-update and the related environment variables.</Callout>
      </>
    ),
  },
  {
    id: 'administration', icon: ShieldCheck, title: 'Administration',
    keywords: 'admin settings application settings smtp email test feature toggle self-registration email verification offline branding instance name lockout disable suspend invite session force logout bulk csv import export users roles security',
    render: () => (
      <>
        <H2>Administration</H2>
        <P>Administrators get three admin surfaces in the top bar: <strong className="text-card-foreground">Settings</strong> (instance configuration), <strong className="text-card-foreground">Users</strong> (accounts), and <strong className="text-card-foreground">System</strong> (version &amp; updates).</P>

        <H3>Application Settings</H3>
        <P>Instance-wide configuration you can change at runtime without editing <InlineCode>.env</InlineCode> or restarting — grouped into branding, features, email, security, limits, and updates. Saved values override the environment defaults and apply immediately.</P>
        <UL>
          <LI><strong className="text-card-foreground">Branding</strong> — instance name (shown by the logo) and support email.</LI>
          <LI><strong className="text-card-foreground">Features</strong> — allow self-registration, require email verification, offline mode, self-update.</LI>
          <LI><strong className="text-card-foreground">Email</strong> — SMTP host/port/credentials plus a <strong className="text-card-foreground">Send test email</strong> button that reports success or the exact SMTP error.</LI>
          <LI><strong className="text-card-foreground">Security</strong> — session length and failed-login lockout threshold/duration.</LI>
        </UL>
        <Callout variant="info">A setting pinned by an environment variable (<InlineCode>RT_*</InlineCode>) shows a lock icon and is read-only in the UI — deployment config always wins.</Callout>

        <H3>User Management</H3>
        <UL>
          <LI><strong className="text-card-foreground">Invite</strong> — create an account and email a set-password link (the link is shown to copy when email isn't configured).</LI>
          <LI><strong className="text-card-foreground">Disable / enable</strong> — block sign-in without deleting the account (attribution and data are kept).</LI>
          <LI><strong className="text-card-foreground">Lockout</strong> — accounts auto-lock after too many failed logins; an admin can unlock early.</LI>
          <LI><strong className="text-card-foreground">Force sign-out</strong> — revoke every active session for a user; you can also sign yourself out everywhere.</LI>
          <LI><strong className="text-card-foreground">Bulk actions</strong> — select rows to disable, enable, delete, or set the role in one go.</LI>
          <LI><strong className="text-card-foreground">CSV</strong> — export all users, or import <InlineCode>username,full_name,email,role</InlineCode> rows as invitations.</LI>
        </UL>
        <Callout variant="info">Guard rails prevent disabling/deleting the last administrator or your own account.</Callout>
      </>
    ),
  },
  {
    id: 'glossary', icon: BookOpen, title: 'Glossary',
    keywords: 'glossary terms definitions dictionary terminology',
    render: () => (
      <>
        <H2>Glossary of Terms</H2>
        <P>Key terminology used across reqmesh, listed alphabetically.</P>

        <dl className="space-y-4 mt-4">
          {[
            { term: 'Baseline', def: 'A frozen snapshot of all requirements at a point in time. Baselines can be compared with the current state to identify changes.' },
            { term: 'Budget Rollup', def: 'A parametric expression (rollup(\'C172\', \'mass\')) that sums a parameter across an entire component hierarchy, multiplying by each component\'s quantity.' },
            { term: 'Cascade', def: 'Automatic propagation of field changes from a parent requirement to its cascaded children. Break the link via "Break Cascade".' },
            { term: 'Change Request', def: 'A formal proposal to modify one or more requirements. Tracks status from submission through review, approval, and implementation.' },
            { term: 'Component', def: 'A physical element of the design — part, assembly, subsystem, or system. Components satisfy requirements and carry parameters for budget rollups.' },
            { term: 'Constraint', def: 'A boolean pass/fail check over parameters. Example: "useful_load >= 380". Evaluated by the parametric engine to produce verdicts and margins.' },
            { term: 'Coverage', def: 'Measures whether requirements have the required artifact types covering them. Shallow coverage checks immediate coverage; deep coverage checks the entire chain transitively.' },
            { term: 'Decision Record', def: 'A documented architectural or engineering decision with context, alternatives considered, rationale, and linked requirements.' },
            { term: 'Deep Coverage', def: 'A requirement is deeply covered when it is shallow-covered AND all of its covering items are themselves deeply covered (recursive). Broken chains are flagged in the Metrics page.' },
            { term: 'Derived Requirement', def: 'A requirement with derived: true — has an external source (e.g., an airworthiness directive) and does not require a parent link.' },
            { term: 'Fingerprint', def: 'A SHA-256 hash of a requirement\'s normative content. When the "Review" action is performed, the fingerprint is stored. If any normative field later changes, the requirement is flagged as unreviewed.' },
            { term: 'Gap Analysis', def: 'Checks requirements for missing fields — description, rationale, source, and traceability links. Visible on the Metrics page.' },
            { term: 'Measurement', def: 'A recorded numeric value from a verification case, overriding a modelled parameter with empirical evidence. Produces a separate "measured" verdict in the parametric engine.' },
            { term: 'Needs', def: 'The artifact types that must provide coverage for a requirement. Example: needs: [design, verification_case]. An empty needs list means the requirement is a terminating (leaf) item.' },
            { term: 'Non-normative', def: 'A requirement with normative: false — excluded from coverage analysis, gap analysis, and verification checks. Used for section headings or decision records in published output.' },
            { term: 'Parameter', def: 'A typed numeric quantity on a requirement or component. Parameters have a name, value, unit, and optional derivation expression.' },
            { term: 'Refines', def: 'A traceability relation indicating one requirement provides more detail for another. Forms the basis of the requirements hierarchy.' },
            { term: 'Relation', def: 'A directed link between two requirements. Types include: refines, satisfies, derives, conflicts, and verified_by. Relations are bidirectional — both ends always see the link.' },
            { term: 'Review', def: 'The action of fingerprint-baselining a requirement. Stores the current content hash so future changes are detected. Available per-requirement or for all via "Review All".' },
            { term: 'Risk', def: 'A potential threat to the project with severity, probability, impact, and mitigation. Linked to the requirements it threatens.' },
            { term: 'Satisfies', def: 'A link from a component to a requirement, indicating the component exists to deliver that requirement. Also used as a relation type between requirements.' },
            { term: 'Shallow Coverage', def: 'Checks whether, for each entry in a requirement\'s needs list, at least one covering item of that type exists. A prerequisite for deep coverage.' },
            { term: 'Specification', def: 'A document grouping requirements. Specifications form a hierarchy with children, and can be referenced from multiple requirements.' },
            { term: 'Suspect Link', def: 'A relation whose target has changed since the link was last reviewed (the stored fingerprint no longer matches). Flagged in the integrity check.' },
            { term: 'Trace Link', def: 'An entry in the traceability matrix connecting a source entity to a target entity with a type (refines, satisfies, derives, etc.). Shown on the Trace Matrix page.' },
            { term: 'Trace Matrix', def: 'The complete set of trace links in a project. Displayed as a filterable list or grid view on the Trace Matrix page.' },
            { term: 'Verification Case', def: 'A test, analysis, demonstration, or inspection that proves one or more requirements are met. Can record measurements for parametric evaluation and track execution history.' },
            { term: 'Verification Method', def: 'How a requirement will be proven — test (physical testing), analysis (modelling/simulation), demonstration (showing it works), or inspection (review/examination).' },
            { term: 'Verdict', def: 'The result of evaluating a constraint — pass, fail, unknown, error, or not applicable. Shown as color-coded badges on the requirement detail page and Metrics dashboard.' },
            { term: 'Workflow', def: 'The allowed status transitions for requirements, configured per project in _meta.yaml. Example: proposed → in_review → approved → implemented → verified.' },
            { term: 'ISO 15288', def: 'ISO/IEC 15288:2023 — the international standard for system life cycle processes. Reqmesh aligns its terminology and process model with this standard. See the Getting Started page for a mapping table.' },
            { term: 'Stakeholder Requirement', def: '(ISO 15288 §6.4.2.3) A requirement expressing a stakeholder need or expectation. In reqmesh, captured as a Requirement with stakeholder priority scores and an optional source field referencing the originating stakeholder document.' },
            { term: 'System Requirement', def: '(ISO 15288 §6.4.2.3) A requirement derived from stakeholder requirements, expressed in technical terms suitable for design. In reqmesh, represented by functional, interface, and constraint type requirements with verification methods.' },
            { term: 'Validation', def: '(ISO 15288 §6.4.11) Confirmation that the system meets stakeholder needs. In reqmesh, measured verdicts from the parametric engine provide ongoing validation evidence — the actual system behaviour compared against modelled expectations.' },
            { term: 'System Element', def: '(ISO 15288 §4.48) A member of a system. In reqmesh, represented by Components — discrete parts, assemblies, subsystems, or the complete system forming the design hierarchy.' },
            { term: 'Architecture Definition', def: '(ISO 15288 §6.4.3) The process of identifying and structuring system elements and their relationships. In reqmesh, the Component tree with satisfies links to requirements represents the architecture definition.' },
            { term: 'Design Definition', def: '(ISO 15288 §6.4.4) The process of providing detailed design characteristics for system elements. In reqmesh, component parameters (mass, current draw, cost) and budget rollups represent the design definition.' },
            { term: 'Configuration Baseline', def: '(ISO 15288 §6.3.5) An approved snapshot of product configuration information. In reqmesh, the Baseline freeze operation captures all requirement states, with diff showing changes from the baseline.' },
          ].map(({ term, def }) => (
            <div key={term}>
              <dt className="text-sm font-semibold text-card-foreground">{term}</dt>
              <dd className="text-sm text-card-foreground/70 leading-relaxed pl-0">{def}</dd>
            </div>
          ))}
        </dl>
      </>
    ),
  },
];

/* ── Documentation panel ────────────────────────────────────────────────── */

export default function DocumentationPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [activeId, setActiveId] = useState('overview');
  const [query, setQuery] = useState('');
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) contentRef.current?.scrollTo(0, 0);
  }, [open, activeId]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); onClose(); } };
    document.addEventListener('keydown', onKey, true);
    return () => document.removeEventListener('keydown', onKey, true);
  }, [open, onClose]);

  const activeTopic = DOCS.find((t) => t.id === activeId);

  // Match titles first, then section keywords, so a search for "reqif" or
  // "docker" lands on the right topic even though no title mentions it.
  const q = query.trim().toLowerCase();
  const matches = (t: DocSection) =>
    t.title.toLowerCase().includes(q) || t.keywords.toLowerCase().includes(q);
  const filteredResults = q ? DOCS.filter(matches) : DOCS;

  return (
    <AnimatePresence>
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 backdrop-blur-sm pt-[8vh]"
          onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 20 }}
            className="bg-card border rounded-2xl shadow-2xl w-full max-w-5xl max-h-[82vh] mx-4 flex flex-col overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-3 border-b shrink-0">
              <div className="flex items-center gap-2">
                <BookOpen size={16} className="text-primary" />
                <h2 className="text-sm font-semibold text-card-foreground">Documentation</h2>
                <span className="text-[10px] text-muted-foreground/50">— press F1 to open</span>
              </div>
              <div className="flex items-center gap-2 flex-1 max-w-xs ml-4">
                <div className="relative flex-1">
                  <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <input
                    className="pl-7 pr-2.5 py-1.5 w-full rounded-lg bg-muted/50 border text-xs text-foreground outline-none focus:ring-1 focus:ring-ring/20"
                    placeholder="Search topics…"
                    value={query}
                    onChange={(e) => {
                      const next = e.target.value;
                      setQuery(next);
                      const nq = next.trim().toLowerCase();
                      if (!nq) return;
                      const match = DOCS.find((t) =>
                        t.title.toLowerCase().includes(nq) || t.keywords.toLowerCase().includes(nq));
                      if (match) setActiveId(match.id);
                    }}
                  />
                </div>
              </div>
              <button onClick={onClose} className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent ml-2">
                <X size={16} />
              </button>
            </div>

            {/* Body: sidebar + content */}
            <div className="flex flex-1 min-h-0 overflow-hidden">
              {/* Sidebar TOC */}
              <div className="w-56 shrink-0 border-r overflow-auto p-3 space-y-0.5">
                {filteredResults.map((topic) => {
                  const Icon = topic.icon || BookOpen;
                  return (
                    <button
                      key={topic.id}
                      onClick={() => { setActiveId(topic.id); setQuery(''); }}
                      className={`flex items-center gap-2 text-xs w-full text-left px-2 py-1.5 rounded-md transition-colors ${
                        activeId === topic.id ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground hover:bg-accent'
                      }`}
                    >
                      <Icon size={13} className="shrink-0" />
                      <span className="truncate">{topic.title}</span>
                    </button>
                  );
                })}
                {filteredResults.length === 0 && (
                  <p className="text-xs text-muted-foreground px-2 py-3">No matching topics.</p>
                )}
              </div>

              {/* Content area */}
              <div ref={contentRef} className="flex-1 overflow-auto">
                <div className="p-6">
                  {activeTopic?.render()}
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
