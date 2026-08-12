"""Publishing and export endpoints. Extracted from ``extra_routes.py``.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from app.core.config import settings
from app.core.dependencies import get_store, require_maintain, get_current_user
from app.core.rate_limit import rate_limit
from app.services.publisher import Publisher, compile_latex_to_pdf

router = APIRouter()


class PublishRequest(BaseModel):
    subsystems: Optional[list[str]] = None
    components: Optional[list[str]] = None
    format: str = "html"
    sections: Optional[list[str]] = None


@router.post("/projects/{project_id}/publish")
def publish_project(project_id: str, data: PublishRequest, user: dict = Depends(require_maintain), _rate: None = Depends(rate_limit(5, 60))):
    store = get_store(project_id)
    pub = Publisher(store, data.subsystems, data.components)
    fmt = data.format
    sections = data.sections

    if fmt == "html":
        return {"format": "html", "content": pub.build_html(sections)}
    elif fmt == "md":
        return {"format": "md", "content": pub.build_markdown()}
    elif fmt == "latex":
        return {"format": "latex", "content": pub.build_latex()}
    elif fmt in ("csv", "tsv"):
        from app.services.table_io import export_table
        return {"format": fmt, "content": export_table(store, fmt)}
    raise HTTPException(status_code=400, detail=f"Unknown format: {fmt} (use html, md, latex, csv, or tsv; pdf and xlsx are available on the download route)")


@router.get("/projects/{project_id}/publish/download")
def download_report(project_id: str, format: str = "html", subsystems: str | None = None,
                          components: str | None = None,
                          sections: str | None = None, changelog_from: str = "", changelog_to: str = "",
                          # Buckets are keyed by path, and every format shares this
                          # one — so the old budget of 5 blocked a user who simply
                          # tried each of the nine offered formats once. 15 still
                          # bounds the cost (a PDF is ~11 s of CPU) while leaving
                          # room to work through the format list and retry.
                          _rate: None = Depends(rate_limit(15, 60))):
    store = get_store(project_id)
    sub_list = [s.strip() for s in subsystems.split(",") if s.strip()] if subsystems is not None else None
    comp_list = [s.strip() for s in components.split(",") if s.strip()] if components is not None else None
    pub = Publisher(store, sub_list, comp_list)
    ext_map = {"html": "html", "pdf": "pdf", "md": "md", "latex": "tex", "reqif": "xml", "sysml": "sysml", "csv": "csv", "tsv": "tsv", "xlsx": "xlsx"}
    if format not in ext_map:
        raise HTTPException(status_code=400, detail=f"Unknown format: {format}")
    ext = ext_map[format]

    fd, path = tempfile.mkstemp(suffix=f".{ext}")
    os.close(fd)
    sec_list = [s.strip() for s in sections.split(",") if s.strip()] if sections is not None else None
    fallback = None
    try:
        if format == "reqif":
            from app.services.reqif_export import export_reqif
            Path(path).write_text(export_reqif(store))
        elif format == "sysml":
            from app.services.sysml_export import export_sysml_v2
            Path(path).write_text(export_sysml_v2(store))
        elif format == "html":
            Path(path).write_text(pub.build_html(sec_list, changelog_from, changelog_to))
        elif format == "pdf":
            latex = pub.build_latex(sec_list, changelog_from, changelog_to)
            if not compile_latex_to_pdf(latex, path):
                # Loud on purpose. The fallback produces a visibly worse report,
                # and the only previous signal was a response header the browser
                # threw away — so a deployment could render degraded PDFs for
                # months with nothing in the logs to say why.
                import logging
                logging.getLogger(__name__).error(
                    "PDF report for %s fell back to weasyprint: no working LaTeX engine. "
                    "Reports will omit tables, badges and the table of contents until "
                    "tectonic is installed and its package cache warmed "
                    "(backend/scripts/warm_tectonic.py).", project_id)
                from weasyprint import HTML as WHTML
                from app.services.sanitize import safe_url_fetcher
                WHTML(
                    string=pub.build_html(sec_list, changelog_from, changelog_to),
                    url_fetcher=safe_url_fetcher({getattr(settings, "report_logo_url", "")}),
                ).write_pdf(path)
                fallback = "LaTeX\u2192PDF (tectonic/pdflatex) not available \u2014 rendered via HTML\u2192PDF weasyprint (tables, badges, and table-of-contents omitted)"
        elif format == "md":
            pub.to_markdown_file(path)
        elif format == "latex":
            Path(path).write_text(pub.build_latex(sec_list, changelog_from, changelog_to))
        elif format in ("csv", "tsv"):
            from app.services.table_io import export_table
            Path(path).write_text(export_table(store, format))
        elif format == "xlsx":
            from app.services.table_io import export_xlsx
            export_xlsx(store, path)
    except BaseException:
        os.unlink(path)
        raise

    project_name = store.read_meta().get("name", project_id)
    response = FileResponse(
        path,
        filename=f"{project_name.replace(' ', '_')}_report.{ext}",
        media_type="application/octet-stream",
        background=BackgroundTask(os.unlink, path),
    )
    if fallback:
        response.headers["X-Render-Fallback"] = fallback.replace(",", ";")
    return response


# ── Code & Test Traceability ─────────────────────────────────────────────────

@router.post("/projects/{project_id}/scan")
def scan_code(project_id: str, code_root: str = Form(""), user: dict = Depends(require_maintain), _rate: None = Depends(rate_limit(20, 60))):
    from app.services.code_scan import scan_tree, merge_references
    store = get_store(project_id)

    if code_root:
        root = Path(code_root).resolve()
        project_root = store.root.resolve()
        try:
            root.relative_to(project_root)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"code_root must be inside the project directory: {project_root}",
            ) from None
    else:
        root = store.root

    hits = scan_tree(root)
    summary = merge_references(store, hits)
    return summary


@router.get("/projects/{project_id}/references/freshness")
def reference_freshness(project_id: str, user: dict = Depends(get_current_user)):
    from app.services.references import check_reference_freshness
    store = get_store(project_id)
    return check_reference_freshness(store, store.root)
