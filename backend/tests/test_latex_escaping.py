r"""Every user-controlled value must be LaTeX-escaped before interpolation.

The requirement table in ``build_latex`` escapes ``name``, ``description``,
``rationale``, ``source`` and ``allocated_to``, but the relation ``type`` and the
``baselines`` list used to be spliced in raw. A relation type such as
``}\input{/etc/passwd}`` then reached the compiled document. The engine runs
without ``-shell-escape``, so the reachable impact is local-file disclosure into
the exported PDF and broken exports rather than RCE — but any authenticated
editor, or any ReqIF import, can trigger it.

This is the third bug of this exact shape (tasks 118 and 135 were the others),
so alongside the fix this module carries a sweep test driven from the Pydantic
model that fails on any unescaped field — the one that would catch the fourth.
"""
from __future__ import annotations

import datetime
import typing

import app.services.publisher as publisher_module
from app.models.requirement import Requirement
from app.services.publisher import Publisher
from app.services.publishers.latex_helpers import latex_escape
from app.services.yaml_store import YamlStore


# ── fixtures & helpers ─────────────────────────────────────────────────────────

# The reported payload. ``latex_escape`` turns it into
# ``\}\textbackslash{}input\{/etc/passwd\}``, so a live ``\input{`` can no
# longer appear.
RELATION_PAYLOAD = r"}\input{/etc/passwd}"

# Every LaTeX metacharacter plus a distinctive token. The sweep asserts this
# exact string never appears raw. (No ``<``/``>`` — the HTML sanitiser would
# otherwise rewrite the marker for the rich-text fields.)
MARKER = r"SWEEP143\{}%$#&_^~"


def _store(tmp_path, name: str = "proj") -> YamlStore:
    return YamlStore(tmp_path / name)


# ── the two known sites ───────────────────────────────────────────────────────


class TestRelationTypeEscaping:
    def test_relation_type_is_escaped(self, tmp_path):
        store = _store(tmp_path)
        store.create_requirement({
            "id": "REQ-ONE",
            "name": "First requirement",
            "type": "functional",
            "status": "proposed",
            "priority": "medium",
            "relations": [{"type": RELATION_PAYLOAD, "target": "REQ-TWO"}],
        })
        store.create_requirement({
            "id": "REQ-TWO",
            "name": "Second requirement",
            "type": "functional",
            "status": "proposed",
            "priority": "medium",
        })
        latex = Publisher(store).build_latex()

        # The escaped literal is present, in escaped form.
        assert latex_escape(RELATION_PAYLOAD) in latex
        # The raw payload — and the live \input command — are not.
        assert RELATION_PAYLOAD not in latex
        assert r"\input{" not in latex


class TestBaselineEscaping:
    def test_baseline_name_is_escaped(self, tmp_path):
        baseline = r"base\{}%$#&_^~"
        store = _store(tmp_path)
        store.create_requirement({
            "id": "REQ-ONE",
            "name": "First requirement",
            "type": "functional",
            "status": "proposed",
            "priority": "medium",
            "baselines": [baseline],
        })
        latex = Publisher(store).build_latex()

        assert latex_escape(baseline) in latex
        assert baseline not in latex


# ── the sweep: fail on any unescaped field ────────────────────────────────────


# Fields the sweep deliberately does NOT set to the marker. Each entry is the
# documentation of why that field is not part of the sweep, so a field added to
# the model later is either swept automatically or added here with a reason.
SWEEP_ALLOWLIST = {
    # entity ids — safe-id constrained (alphanumeric only), so they cannot carry
    # the marker; they are rendered escaped via _latex_escape / _latex_link.
    "id": "entity id; safe-id constrained, rendered escaped via _latex_escape",
    "verification_cases": "entity ids routed through _latex_link (safe-id constrained)",
    "needs": "entity ids; not rendered in build_latex",
    # not rendered anywhere in build_latex (HTML hierarchy / markdown only)
    "parent": "not rendered in build_latex",
    "cascade_from": "not rendered in build_latex",
    "subject": "not rendered in build_latex (HTML hierarchy only)",
    "reviewed": "not rendered in build_latex",
    "created": "not rendered in build_latex",
    "modified": "not rendered in build_latex",
    "verification_methods": "not rendered in build_latex",
    "attributes": "not rendered in build_latex (HTML hierarchy only)",
    # non-string data
    "normative": "boolean flag, not string data",
    "priorities": "dict[str, int] scores; not rendered in build_latex",
}

# Nested-model fields that name another entity rather than holding free text —
# they must stay safe ids or the requirement would be dropped on load.
_NESTED_ID_FIELDS = {"target"}


def _sweep_value(annotation) -> object:
    """Return a marker-bearing value appropriate to a Pydantic field's type."""
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is typing.Union:  # Optional[X] / X | None
        inner = [a for a in args if a is not type(None)]
        if len(inner) == 1:
            return _sweep_value(inner[0])
        return MARKER

    if origin is list:
        (item,) = args
        if item is str:
            return [MARKER]
        return [_sweep_model(item)]

    if origin is dict:
        return {}

    if annotation is str:
        return MARKER
    if isinstance(annotation, type) and issubclass(annotation, str):
        # str-Enums (status, priority, type, …) render their raw value.
        return MARKER
    if annotation is bool:
        return True
    if annotation is int or annotation is float:
        return 1
    return MARKER


def _sweep_model(model_cls) -> dict:
    """One instance of a nested model with every string field set to the marker."""
    out: dict[str, object] = {}
    for name, field in model_cls.model_fields.items():
        if name in _NESTED_ID_FIELDS:
            out[name] = "REQ-SWEEP-TARGET"
            continue
        out[name] = _sweep_value(field.annotation)
    return out


def _sweep_requirement() -> dict:
    """A requirement with every swept field set to the marker."""
    req: dict[str, object] = {"id": "REQ-SWEEP"}
    for name, field in Requirement.model_fields.items():
        if name in SWEEP_ALLOWLIST:
            continue
        req[name] = _sweep_value(field.annotation)
    return req


class TestSweep:
    def test_no_raw_marker_survives(self, tmp_path):
        store = _store(tmp_path)
        store.create_requirement(_sweep_requirement())
        latex = Publisher(store).build_latex()

        # The requirement must actually reach the report — otherwise "no raw
        # marker" would pass trivially because nothing was rendered.
        assert "REQ-SWEEP" in latex
        # The marker value did reach the report, in escaped form.
        assert latex_escape(MARKER) in latex
        # And nowhere does the raw marker survive.
        assert MARKER not in latex

    def test_sweep_covers_every_model_field(self):
        """Every model field is either swept or explicitly allow-listed.

        Drives the field list from the Pydantic model so a field added later is
        covered automatically; this guard makes the *allow-list* the only way a
        field can escape the sweep, and forces a comment for each entry.
        """
        swept = set(Requirement.model_fields) - set(SWEEP_ALLOWLIST)
        assert "id" in SWEEP_ALLOWLIST  # id is always fixed, never swept
        # Sanity: the reported bug's field is swept, not allow-listed.
        assert "relations" in swept
        assert "baselines" in swept


# ── byte-identical output for ordinary text ────────────────────────────────────


class _FrozenDatetime(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 1, 2, 3, 4, 5, tzinfo=tz)


def _golden_store(tmp_path) -> YamlStore:
    store = _store(tmp_path)
    store.write_meta({"name": "Golden Project"})
    store.create_requirement({
        "id": "REQ-GOLD",
        "name": "Ordinary requirement",
        "description": "Ordinary description text",
        "rationale": "Ordinary rationale",
        "source": "Ordinary source",
        "allocated_to": "Ordinary owner",
        "type": "functional",
        "status": "proposed",
        "priority": "medium",
        "baselines": ["SRR"],
        "relations": [{"type": "depends", "target": "REQ-GOLD-2"}],
        "verification_cases": [],
        "verification_status": "pending",
    })
    store.create_requirement({
        "id": "REQ-GOLD-2",
        "name": "Ordinary target requirement",
        "description": "",
        "rationale": "",
        "source": "",
        "type": "functional",
        "status": "proposed",
        "priority": "medium",
        "baselines": [],
        "relations": [],
        "verification_cases": [],
    })
    return store


def _freeze_branding(monkeypatch) -> None:
    """Pin the branding/report settings the golden depends on.

    ``_header_config`` reads a singleton ``settings`` object shared with the
    rest of the suite; other tests mutate it. Freeze the values the golden was
    captured with so the byte-identical assertion never depends on test order.
    """
    settings = publisher_module.global_settings
    monkeypatch.setattr(settings, "instance_name", "reqmesh")
    for key in (
        "report_company_name",
        "report_department",
        "report_document_title",
        "report_logo_url",
        "report_document_number",
        "report_revision",
        "report_classification",
        "report_status",
        "report_prepared_by",
        "report_reviewed_by",
        "report_approved_by",
    ):
        monkeypatch.setattr(settings, key, "")
    monkeypatch.setattr(settings, "report_show_git_commit", False)
    monkeypatch.setattr(settings, "report_distribution", [])
    monkeypatch.setattr(settings, "report_color", "#2094f3")


class TestOrdinaryTextIsByteIdentical:
    def test_output_matches_golden(self, tmp_path, monkeypatch):
        monkeypatch.setattr(publisher_module, "datetime", _FrozenDatetime)
        _freeze_branding(monkeypatch)
        latex = Publisher(_golden_store(tmp_path)).build_latex()
        assert latex == GOLDEN


GOLDEN = r"""\documentclass[11pt,a4paper]{article}
\usepackage{iftex}
\ifPDFTeX
  \usepackage[utf8]{inputenc}
  \usepackage[T1]{fontenc}
  \IfFileExists{helvet.sty}{\usepackage[scaled=0.92]{helvet}}{}
  \renewcommand{\familydefault}{\sfdefault}
  \IfFileExists{courier.sty}{\usepackage{courier}}{}
\else
  \usepackage{fontspec}
  \IfFileExists{inter.sty}{\usepackage[default]{inter}}{}
  \IfFileExists{sourcecodepro.sty}{\usepackage{sourcecodepro}}{}
\fi
\usepackage{geometry}
\geometry{margin=2.6cm, includehead, includefoot, headsep=14pt, footskip=28pt}
\usepackage[table]{xcolor}
\usepackage{fancyhdr}
\usepackage{lastpage}
\usepackage{longtable}
\usepackage{booktabs}
\usepackage{array}
\usepackage{tabularx}
\usepackage{ragged2e}
\usepackage{enumitem}
\usepackage{titlesec}
\usepackage{titletoc}
\usepackage{parskip}
\usepackage{ifthen}
\usepackage{makecell}
\usepackage{xstring}
\usepackage{graphicx}
\IfFileExists{tikz.sty}{\usepackage{tikz}\newcommand{\rmhaspill}{1}}{}
\definecolor{accent}{RGB}{32,148,243}
\definecolor{accentdark}{RGB}{20,96,157}
\definecolor{ink}{RGB}{31,39,51}
\definecolor{muted}{RGB}{104,119,141}
\definecolor{rule}{RGB}{220,224,229}
\definecolor{prop}{RGB}{32,148,243}
\definecolor{appr}{RGB}{34,160,86}
\definecolor{impl}{RGB}{119,62,234}
\definecolor{veri}{RGB}{0,143,140}
\definecolor{rej}{RGB}{237,44,44}
\definecolor{depr}{RGB}{133,144,147}
\definecolor{prihigh}{RGB}{255,119,0}
\definecolor{pricrit}{RGB}{237,44,44}
\definecolor{prlow}{RGB}{133,144,147}
\definecolor{primed}{RGB}{32,148,243}
\definecolor{tabhead}{RGB}{237,246,254}
\definecolor{rowalt}{RGB}{250,251,252}
\usepackage{hyperref}
\hypersetup{colorlinks=true,linkcolor=accent,urlcolor=accent,citecolor=accent}
\titleformat{\section}{\Large\bfseries\color{accentdark}}{\thesection}{0.6em}{}[{\vspace{2pt}\color{accent}\titlerule[1.2pt]}]
\titleformat{\subsection}{\large\bfseries\color{accent}}{\thesubsection}{0.6em}{}
\titlespacing*{\section}{0pt}{22pt}{10pt}
\titlespacing*{\subsection}{0pt}{14pt}{6pt}
\setlength{\tabcolsep}{7pt}
\renewcommand{\arraystretch}{1.15}
\setlength{\LTpre}{6pt}
\setlength{\LTpost}{10pt}
\setlength{\extrarowheight}{1pt}
\setlength{\arrayrulewidth}{0.5pt}
\arrayrulecolor{rule}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\footnotesize\sffamily\color{muted}reqmesh}
\fancyhead[R]{\footnotesize\sffamily\color{muted}Rev 1.0}
\fancyfoot[L]{\footnotesize\sffamily\color{muted}reqmesh}
\fancyfoot[C]{\footnotesize\sffamily\color{muted}Page \thepage\ of \pageref{LastPage}}
\renewcommand{\headrulewidth}{0.4pt}
\renewcommand{\footrulewidth}{0.4pt}
\renewcommand{\headrule}{\color{rule}\hrule width\headwidth height\headrulewidth}
\renewcommand{\footrule}{\color{rule}\hrule width\headwidth height\footrulewidth}
\newcommand{\pill}[2]{%
  \ifdefined\rmhaspill
    \tikz[baseline=(P.base)]{\node[fill=#1!13,rounded corners=4.5pt,inner xsep=6pt,inner ysep=2.2pt,text=#1,font=\bfseries\footnotesize] (P) {#2};}%
  \else
    \colorbox{#1!18}{\textcolor{#1}{\textbf{\footnotesize #2}}}%
  \fi
}
\newcommand{\statcard}[2]{%
  \ifdefined\rmhaspill
    \tikz[baseline=(S.base)]{\node[fill=accent!5,rounded corners=6pt,inner sep=10pt,align=center,minimum width=3.0cm] (S) {\shortstack{{\fontsize{26}{30}\selectfont\bfseries\color{accent} #1}\\[3pt]{\footnotesize\color{muted} #2}}};}%
  \else
    \makecell{{\fontsize{26}{30}\selectfont\bfseries\color{accent} #1}\\[3pt]{\footnotesize\color{muted} #2}}%
  \fi
}
\newcommand{\distbar}[3]{%
  \ifdefined\rmhaspill
    \begin{tikzpicture}[baseline=-0.5ex, x=1cm]
      \draw[rule,line width=9pt,line cap=round] (0,0) -- (#3,0);
      \draw[#1,line width=9pt,line cap=round] (0,0) -- (#2,0);
    \end{tikzpicture}%
  \else
    \textcolor{#1}{\rule{#2cm}{9pt}}%
  \fi
}
\newcommand{\statusbadge}[1]{%
  \IfStrEqCase{#1}{%
    {proposed}{\pill{prop}{proposed}}%
    {approved}{\pill{appr}{approved}}%
    {implemented}{\pill{impl}{implemented}}%
    {verified}{\pill{veri}{verified}}%
    {rejected}{\pill{rej}{rejected}}%
    {passed}{\pill{appr}{passed}}%
    {failed}{\pill{rej}{failed}}%
    {pending}{\pill{depr}{pending}}%
    {in_progress}{\pill{prop}{in progress}}%
    {submitted}{\pill{prop}{submitted}}%
    {in_review}{\pill{prop}{in review}}%
    {open}{\pill{prop}{open}}%
    {closed}{\pill{depr}{closed}}%
    {mitigated}{\pill{appr}{mitigated}}%
    {deprecated}{\pill{depr}{deprecated}}%
    {create}{\pill{appr}{created}}%
    {update}{\pill{prop}{updated}}%
    {delete}{\pill{rej}{deleted}}%
    {review}{\pill{impl}{reviewed}}%
  }[\pill{depr}{#1}]%
}
\newcommand{\prioritybadge}[1]{%
  \IfStrEqCase{#1}{%
    {critical}{\pill{pricrit}{critical}}%
    {high}{\pill{prihigh}{high}}%
    {medium}{\pill{primed}{medium}}%
    {low}{\pill{prlow}{low}}%
  }[\pill{prlow}{#1}]%
}
\begin{document}
\color{ink}
\begin{titlepage}
\thispagestyle{empty}
\centering
\vspace*{2.4cm}
\vspace{0.4cm}
{\color{accent}\rule{\textwidth}{2.5pt}}\par
\vspace{0.9cm}
{\fontsize{34}{40}\selectfont\bfseries\color{accentdark} Golden Project}\par
\vspace{0.7cm}
{\LARGE\color{accent} Requirements Specification Report}\par
\vspace{0.9cm}
{\color{accent}\rule{\textwidth}{2.5pt}}\par
\vspace{1.5cm}
{\Large\bfseries reqmesh}\par
\vspace{0.2cm}
{\large\color{muted} }\par
\vfill
{\color{rule}\rule{0.7\textwidth}{0.5pt}}\par\vspace{0.5cm}
\renewcommand{\arraystretch}{1.5}
{\normalsize\begin{tabular}{r@{\hskip 1.2em}l}
{\color{muted} Revision} & 1.0 \\
{\color{muted} Project} & \texttt{proj} \\
{\color{muted} Date} & 2026-01-02 03:04 UTC \\
{\color{muted} Requirements} & 2 \\
{\color{muted} Verification cases} & 0 \\
\end{tabular}}\par
\renewcommand{\arraystretch}{1.2}
\vspace{1.0cm}
\end{titlepage}
\thispagestyle{fancy}
{\color{accentdark}\Large\bfseries Document Control}\par\vspace{2pt}
{\color{accent}\rule{\textwidth}{1.2pt}}\par\vspace{12pt}
{\large\bfseries\color{accent} Revision History}\par\vspace{4pt}
\begin{tabularx}{\textwidth}{l l >{\raggedright\arraybackslash}X l}
\toprule
\rowcolor{tabhead}\textbf{Revision} & \textbf{Date} & \textbf{Description} & \textbf{Author} \\
\midrule
1.0 & 2026-01-02 03:04 UTC & Initial issue & -- \\
\bottomrule
\end{tabularx}
\vspace{16pt}
{\large\bfseries\color{accent} Approvals}\par\vspace{4pt}
\begin{tabularx}{\textwidth}{l >{\raggedright\arraybackslash}X >{\raggedright\arraybackslash}p{\dimexpr0.18\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.14\textwidth-2\tabcolsep\relax}}
\toprule
\rowcolor{tabhead}\textbf{Role} & \textbf{Name} & \textbf{Signature} & \textbf{Date} \\
\midrule
\textbf{Prepared by} &  & \rule{3.6cm}{0.4pt} & \rule{2cm}{0.4pt} \\
\rowcolor{rowalt}\textbf{Reviewed by} &  & \rule{3.6cm}{0.4pt} & \rule{2cm}{0.4pt} \\
\textbf{Approved by} &  & \rule{3.6cm}{0.4pt} & \rule{2cm}{0.4pt} \\
\bottomrule
\end{tabularx}
\clearpage
\newpage
\begingroup\hypersetup{linkcolor=ink}\tableofcontents\endgroup
\clearpage
\section{Introduction}
\subsection{Purpose}
This document specifies the requirements for the \textbf{Golden Project}
system. It defines the functional, performance, interface and constraint
requirements that the system shall satisfy, together with the verification
approach and supporting engineering data. The keyword \textbf{shall} denotes a
mandatory requirement; each requirement carries a unique identifier for
traceability.
\subsection{Scope}
The scope covers the 2 requirements of the
\textbf{Golden Project} system across all requirement types, the
0 components of the synthesised
design, 0 verification cases, and the
associated risk register. Requirements engineering follows the
ISO/IEC/IEEE~15288 and 29148 frameworks for stakeholder needs and system
requirements definition.
\subsection{Definitions, Acronyms, and Abbreviations}
Terms, acronyms and abbreviations used in this document are defined in the
Glossary (Appendix).
\subsection{Applicable and Reference Documents}
\textbf{Applicable documents} — sources cited by requirements in this specification:
\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.14\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.86\textwidth-2\tabcolsep\relax}@{}}
\toprule\rowcolor{tabhead}\textbf{Ref} & \textbf{Document} \\ \midrule
\endfirsthead
\toprule\rowcolor{tabhead}\textbf{Ref} & \textbf{Document} \\ \midrule
\endhead\bottomrule\endfoot
\texttt{AD-01} & Ordinary source \\
\end{longtable}
\subsection{Document Overview}
The remainder of this document provides a project overview and metrics
(Section~\ref{sec:overview}), the requirements organised by type, the
component inventory, verification cases and the risk register, a
requirements verification traceability matrix, and supporting engineering
data. Reference material is provided in the appendices.
\section{Project Overview}\label{sec:overview}
\begin{tabularx}{\textwidth}{*{4}{>{\centering\arraybackslash}X}}
\toprule
\statcard{2}{REQUIREMENTS} & \statcard{0}{VERIFICATION} & \statcard{0}{COMPONENTS} & \statcard{0}{RISKS} \\
\bottomrule
\end{tabularx}
\vspace{0.6em}
\subsection{Status Distribution}
\begin{tabularx}{\textwidth}{X r r >{\raggedright\arraybackslash}p{\dimexpr0.40\textwidth-2\tabcolsep\relax}}
\toprule
\rowcolor{tabhead}\textbf{Status} & \textbf{Count} & \textbf{\%} & \textbf{Share} \\
\midrule
Proposed & 2 & 100\% & \distbar{prop}{5.5}{5.5} \\
\bottomrule
\end{tabularx}
\subsection{Priority Distribution}
\begin{tabularx}{\textwidth}{X r r >{\raggedright\arraybackslash}p{\dimexpr0.40\textwidth-2\tabcolsep\relax}}
\toprule
\rowcolor{tabhead}\textbf{Priority} & \textbf{Count} & \textbf{\%} & \textbf{Share} \\
\midrule
Medium & 2 & 100\% & \distbar{primed}{5.5}{5.5} \\
\bottomrule
\end{tabularx}
\subsection{Type Distribution}
\begin{tabularx}{\textwidth}{X r r >{\raggedright\arraybackslash}p{\dimexpr0.40\textwidth-2\tabcolsep\relax}}
\toprule
\rowcolor{tabhead}\textbf{Type} & \textbf{Count} & \textbf{\%} & \textbf{Share} \\
\midrule
Functional & 2 & 100\% & \distbar{accent}{5.5}{5.5} \\
\bottomrule
\end{tabularx}
\newpage
\section{Requirements by Type}
\subsection{Functional}
\textbf{2} requirements of this type.
\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.18\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.46\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.18\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.18\textwidth-2\tabcolsep\relax}@{}}
\toprule
\rowcolor{tabhead}
\textbf{ID} & \textbf{Name} & \textbf{Status} & \textbf{Priority} \\
\midrule
\endfirsthead
\toprule
\rowcolor{tabhead}
\textbf{ID} & \textbf{Name} & \textbf{Status} & \textbf{Priority} \\
\midrule
\endhead
\bottomrule
\endfoot
\hypertarget{req-REQ-GOLD-2}{}\texttt{REQ-GOLD-2} & Ordinary target requirement & \statusbadge{proposed} & \prioritybadge{medium} \\[-2pt]
\midrule
\hypertarget{req-REQ-GOLD}{}\texttt{REQ-GOLD} & Ordinary requirement & \statusbadge{proposed} & \prioritybadge{medium} \\[-2pt]
\multicolumn{4}{@{}p{\dimexpr\textwidth-2\tabcolsep\relax}@{}}{\small Ordinary description text \newline \textbf{Rationale:} Ordinary rationale \newline \textbf{Source:} Ordinary source \newline \textbf{Allocated to:} Ordinary owner \newline \textbf{Baselines:} SRR \newline \textbf{Links:} depends \textrightarrow\ \hyperlink{req-REQ-GOLD-2}{REQ-GOLD-2}} \\[-3pt]
\midrule
\end{longtable}
\newpage
\section{Requirements Verification Traceability Matrix}
Each requirement is mapped to its verification method, the verification
case(s) that discharge it, and its current verification status. A
requirement with no verification case is a coverage gap, flagged
\textcolor{rej}{\textbf{none}} below.
\begin{longtable}{@{}>{\ttfamily}p{\dimexpr0.12\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.28\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.12\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.28\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.20\textwidth-2\tabcolsep\relax}@{}}
\toprule\rowcolor{tabhead}\normalfont\textbf{ID} & \normalfont\textbf{Requirement} & \normalfont\textbf{Method} & \normalfont\textbf{Verified By} & \normalfont\textbf{Status} \\\midrule\endfirsthead
\toprule\rowcolor{tabhead}\normalfont\textbf{ID} & \normalfont\textbf{Requirement} & \normalfont\textbf{Method} & \normalfont\textbf{Verified By} & \normalfont\textbf{Status} \\\midrule\endhead\bottomrule\endfoot
REQ-GOLD-2 & Ordinary target requirement & test & \textcolor{rej}{\textbf{none}} & \statusbadge{pending} \\
\rowcolor{rowalt}REQ-GOLD & Ordinary requirement & test & \textcolor{rej}{\textbf{none}} & \statusbadge{pending} \\
\end{longtable}
\newpage
\section{Specifications}
\section{Baselines}
\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.28\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.14\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.58\textwidth-2\tabcolsep\relax}@{}}
\toprule
\rowcolor{tabhead}
\textbf{Baseline} & \textbf{Count} & \textbf{Requirements} \\
\midrule
\endfirsthead
\toprule
\rowcolor{tabhead}
\textbf{Baseline} & \textbf{Count} & \textbf{Requirements} \\
\midrule
\endhead
\bottomrule
\endfoot
SRR & 1 & REQ-GOLD \\
\midrule
\end{longtable}
\section{Quality Metrics}
\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.38\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.31\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.31\textwidth-2\tabcolsep\relax}@{}}
\toprule
\rowcolor{tabhead}
\textbf{Metric} & \textbf{Count} & \textbf{Percentage} \\
\midrule
\endfirsthead
\toprule
\rowcolor{tabhead}
\textbf{Metric} & \textbf{Count} & \textbf{Percentage} \\
\midrule
\endhead
\bottomrule
\endfoot
Description & 1 / 2 & 50\% \\
\midrule
Rationale & 1 / 2 & 50\% \\
\midrule
Source & 1 / 2 & 50\% \\
\midrule
Allocation & 1 / 2 & 50\% \\
\midrule
Traceability & 1 / 2 & 50\% \\
\midrule
\end{longtable}
\section{Gap Analysis}
1 requirements with issues.
\vspace{1em}
\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.14\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.30\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.56\textwidth-2\tabcolsep\relax}@{}}
\toprule
\rowcolor{tabhead}
\textbf{ID} & \textbf{Name} & \textbf{Issues} \\
\midrule
\endfirsthead
\toprule
\rowcolor{tabhead}
\textbf{ID} & \textbf{Name} & \textbf{Issues} \\
\midrule
\endhead
\bottomrule
\endfoot
\texttt{REQ-GOLD-2} & Ordinary target requirement & no description, no rationale, no source, unlinked \\
\midrule
\end{longtable}
\clearpage
\appendix
\titleformat{\section}{\Large\bfseries\color{accentdark}}{Appendix~\thesection}{0.6em}{}[{\vspace{2pt}\color{accent}\titlerule[1.2pt]}]
\section{Glossary}
\begin{longtable}{@{}>{\raggedright\arraybackslash}p{\dimexpr0.25\textwidth-2\tabcolsep\relax} >{\raggedright\arraybackslash}p{\dimexpr0.75\textwidth-2\tabcolsep\relax}@{}}
\toprule
\rowcolor{tabhead}
\textbf{Term} & \textbf{Definition} \\
\midrule
\endfirsthead
\toprule
\rowcolor{tabhead}
\textbf{Term} & \textbf{Definition} \\
\midrule
\endhead
\bottomrule
\endfoot
\textbf{Requirement} & A statement that identifies a product or process operational, functional, or design characteristic or constraint, which is unambiguous, testable or measurable, and necessary for product or process acceptability. \\
\midrule
\textbf{Verification Case} & A defined set of actions, conditions, and expected results used to confirm that a requirement has been correctly implemented. \\
\midrule
\textbf{Component} & A discrete element of a system that can be implemented, tested, and maintained independently. \\
\midrule
\textbf{Specification} & A detailed description of the requirements, design, behavior, or characteristics of a system or component. \\
\midrule
\textbf{Baseline} & A formally approved version of a configuration item that serves as the basis for further development. \\
\midrule
\textbf{Traceability} & The ability to link requirements to their sources, derived requirements, and related verification cases throughout the project lifecycle. \\
\midrule
\textbf{Stakeholder Need} & A capability or condition that a stakeholder expects a system to provide or satisfy, per ISO/IEC 15288:2023. \\
\midrule
\textbf{System Requirement} & A formal statement that defines what a system must do, how it must perform, and the constraints it must satisfy. \\
\midrule
\textbf{MoE} & Measure of Effectiveness -- operational measures that reflect how well the system achieves its intended purpose in its intended environment. \\
\midrule
\textbf{MoP} & Measure of Performance -- physical or engineering measures that characterize system performance attributes. \\
\midrule
\textbf{TPM} & Technical Performance Measure -- quantitative metrics used to track technical progress and predict achievement of requirements. \\
\midrule
\textbf{Verification} & Confirmation through objective evidence that specified requirements have been fulfilled. \\
\midrule
\textbf{Validation} & Confirmation through objective evidence that the system meets the needs of its intended users and stakeholders. \\
\midrule
\textbf{PDR} & Preliminary Design Review -- a technical review held early in development to assess design maturity and alignment with requirements. \\
\midrule
\textbf{CDR} & Critical Design Review -- a technical review confirming the design is sufficiently mature to proceed to implementation. \\
\midrule
\textbf{TRR} & Test Readiness Review -- a review held to verify that the system is ready to enter formal testing. \\
\midrule
\end{longtable}
\section{Parameters \& Constraints}
No requirements with parameters or constraints defined.
\newpage
\section{Verification Details}
\newpage
\section{System States}
No system states defined.
\newpage
\end{document}"""
