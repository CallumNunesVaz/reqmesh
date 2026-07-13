#!/usr/bin/env python3
"""reqmesh CLI - Requirements management using version control."""

import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@click.group()
@click.version_option("0.4.0", prog_name="reqmesh")
def cli():
    """reqmesh - Requirements management using version control."""


@cli.command()
@click.argument("project_path", default=".")
@click.option("--port", "-p", default=8000, help="Port to run on")
@click.option("--host", "-h", default="0.0.0.0", help="Host to bind to")
def serve(project_path, port, host):
    """Start the web UI for a project directory (or a directory of projects)."""
    import os
    root = Path(project_path).resolve()
    # The API's data root is the directory *containing* project dirs, so when
    # pointed at a single project, serve its parent.
    if (root / "_meta.yaml").exists():
        data_root = root.parent
        click.echo(f"Project: {root}")
    else:
        data_root = root
        click.echo(f"Projects root: {root}")
    os.environ["RT_DATA_ROOT"] = str(data_root)
    import uvicorn
    click.echo(f"Starting reqmesh on http://{host}:{port}")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)


@cli.command()
@click.argument("project_path", default=".")
@click.option("--quality", is_flag=True, help="Also run requirement quality linting")
@click.option("--quality-floor", default=60, type=int, show_default=True, help="Minimum acceptable quality score (0-100)")
def validate(project_path, quality, quality_floor):
    """Run integrity checks on a project."""
    project_root = Path(project_path).resolve()
    if not (project_root / "_meta.yaml").exists():
        click.echo(f"Error: {project_path} is not a valid project (missing _meta.yaml)", err=True)
        sys.exit(1)

    from app.services.yaml_store import YamlStore
    from app.services.integrity import IntegrityChecker

    store = YamlStore(project_root)
    checker = IntegrityChecker(store)
    result = checker.check_all()

    click.echo(f"\n  Project: {store.read_meta().get('name', project_root.name)}")
    click.echo(f"  Requirements: {len(store.list_requirements())}")
    click.echo(f"  Verification Cases: {len(store.list_verification_cases())}\n")

    if result["valid"]:
        click.echo(click.style("  ✓ All checks passed", fg="green"))
    else:
        for issue in result["issues"]:
            sev = issue["severity"]
            color = "red" if sev == "error" else "yellow"
            click.echo(click.style(f"  ✗ [{sev.upper()}] {issue['type']}: {issue.get('source',issue.get('id',''))} → {issue.get('target','')}", fg=color))

    if result["suspect_links"]:
        click.echo(f"\n  ⚠ {len(result['suspect_links'])} suspect links detected")
        for sl in result["suspect_links"]:
            click.echo(f"    {sl['source']} → {sl['target']} ({sl['type']}) - {sl.get('reason','')}")

    exit_code = 0 if result["valid"] else 1

    if quality:
        from app.services.quality import project_quality
        q = project_quality(store)
        click.echo(f"\n  ══ Quality Linting ══")
        click.echo(f"  Average score: {q['average']}/100  (floor: {quality_floor})")
        worst = [r for r in q["per_requirement"] if r["score"] < 80][:10]
        if worst:
            click.echo(f"  Top issues:")
            for r in worst:
                color = "red" if r["score"] < quality_floor else "yellow"
                click.echo(click.style(f"    {r['id']}: {r['score']}/100 — {r.get('name','')}", fg=color))
                for f in r.get("findings", [])[:3]:
                    click.echo(f"      [{f['rule']}] {f['message']}")
        if q["average"] < quality_floor:
            click.echo(click.style(f"\n  ✗ Project average {q['average']} is below quality floor {quality_floor}", fg="red"))
            exit_code = 1

    sys.exit(exit_code)


@cli.command()
@click.argument("project_path", default=".")
@click.option("--format", "-f", default="html", type=click.Choice(["html", "pdf", "md", "latex"]))
@click.option("--output", "-o", default=None, help="Output file path")
@click.option("--sections", "-s", multiple=True, help="Sections to include")
def publish(project_path, format, output, sections):
    """Publish a project as a formatted document."""
    project_root = Path(project_path).resolve()
    if not (project_root / "_meta.yaml").exists():
        click.echo(f"Error: {project_path} is not a valid project", err=True)
        sys.exit(1)

    from app.services.yaml_store import YamlStore
    from app.services.publisher import Publisher

    store = YamlStore(project_root)
    pub = Publisher(store)
    project_name = store.read_meta().get("name", project_root.name)

    if output is None:
        ext_map = {"html": "html", "pdf": "pdf", "md": "md", "latex": "tex"}
        output = f"{project_name.replace(' ','_')}_report.{ext_map[format]}"

    if format == "html":
        pub.to_html_file(output)
    elif format == "pdf":
        pub.to_pdf_file(output)
    elif format == "md":
        pub.to_markdown_file(output)
    elif format == "latex":
        pub.to_latex_file(output)

    click.echo(click.style(f"  ✓ Report published to: {output}", fg="green"))


@cli.command()
@click.argument("project_id")
@click.option("--name", "-n", default=None, help="Project display name")
@click.option("--path", "-p", default=None, help="Custom project directory path")
def create(project_id, name, path):
    """Create a new requirements project."""
    from app.core.config import settings
    proj_path = Path(path) if path else Path(settings.data_root) / project_id
    if proj_path.exists():
        click.echo(f"Error: Project directory already exists: {proj_path}", err=True)
        sys.exit(1)

    from app.services.yaml_store import YamlStore
    store = YamlStore(proj_path)
    store.ensure_dirs()
    store.write_meta({"name": name or project_id})
    click.echo(click.style(f"  ✓ Project created: {proj_path}", fg="green"))


@cli.command()
@click.argument("project_path", default=".")
@click.option("--item", "-i", default=None, help="Review specific requirement ID (default: review all)")
def review(project_path, item):
    """Mark requirements as reviewed (fingerprint baseline)."""
    project_root = Path(project_path).resolve()
    if not (project_root / "_meta.yaml").exists():
        click.echo(f"Error: {project_path} is not a valid project", err=True)
        sys.exit(1)

    from app.services.yaml_store import YamlStore
    from app.services.fingerprint import review_item, review_all

    store = YamlStore(project_root)
    if item:
        result = review_item(store, item)
        if result is None:
            click.echo(f"Error: requirement '{item}' not found", err=True)
            sys.exit(1)
        click.echo(click.style(f"  ✓ Reviewed {item}", fg="green"))
    else:
        r = review_all(store)
        click.echo(click.style(f"  ✓ Reviewed {r['reviewed']}/{r['total']} requirements", fg="green"))


@cli.command()
@click.argument("project_path", default=".")
@click.option("--code", "-c", default=None, help="Path to source code root")
@click.option("--dry-run", is_flag=True, help="Report discovered links without writing")
def scan(project_path, code, dry_run):
    """Scan source files for coverage tags and link them to requirements."""
    project_root = Path(project_path).resolve()
    if not (project_root / "_meta.yaml").exists():
        click.echo(f"Error: {project_path} is not a valid project", err=True)
        sys.exit(1)

    from app.services.yaml_store import YamlStore
    from app.services.code_scan import scan_tree, merge_references

    store = YamlStore(project_root)
    code_root = Path(code).resolve() if code else project_root.parent
    hits = scan_tree(code_root)

    if not hits:
        click.echo("  No coverage tags found in source files.")
        return

    click.echo(f"\n  Scanned: {code_root}")
    click.echo(f"  Tags found: {len(hits)}\n")

    req_map = {r["id"]: r["name"] for r in store.list_requirements()}
    for h in hits[:20]:
        name = req_map.get(h["req_id"], "")
        click.echo(f"  [{h['kind']} -> {h['req_id']}]  {h['path']}:{h['line']}  {name}")

    if dry_run:
        click.echo(click.style("\n  Dry-run: no changes written.", fg="yellow"))
    else:
        summary = merge_references(store, hits)
        click.echo(click.style(
            f"\n  ✓ Merged: {summary['created']} created, {summary['updated']} updated, "
            f"{summary['requirements_touched']} requirements touched",
            fg="green",
        ))


@cli.command()
@click.argument("project_path", default=".")
def trace(project_path):
    """Run a full traceability report (shallow + deep coverage)."""
    project_root = Path(project_path).resolve()
    if not (project_root / "_meta.yaml").exists():
        click.echo(f"Error: {project_path} is not a valid project", err=True)
        sys.exit(1)

    from app.services.yaml_store import YamlStore
    from app.services.tracing import trace_all

    store = YamlStore(project_root)
    items = trace_all(store)

    exit_code = 0
    for item in items:
        status = "ok" if item["deep"] else "not ok"
        n_uncovered = len(item["uncovered_types"])
        n_needs = len(item["needs"])
        color = "green" if item["deep"] else "red"
        click.echo(click.style(
            f"  {status} [ in: {n_needs - n_uncovered}/{n_needs} ] {item['id']} "
            f"({', '.join(item.get('covered_types', []))})",
            fg=color,
        ))
        if not item["deep"]:
            exit_code = 1

    sys.exit(exit_code)


@cli.command()
@click.argument("project_path", default=".")
@click.option("--format", "-f", default="reqif", type=click.Choice(["reqif", "sysml"]))
@click.option("--output", "-o", default=None, help="Output file path")
def export(project_path, format, output):
    """Export a project to ReqIF 1.2 or SysML v2 textual notation."""
    project_root = Path(project_path).resolve()
    if not (project_root / "_meta.yaml").exists():
        click.echo(f"Error: {project_path} is not a valid project", err=True)
        sys.exit(1)

    from app.services.yaml_store import YamlStore

    store = YamlStore(project_root)
    if format == "reqif":
        from app.services.reqif_export import export_reqif
        content, ext = export_reqif(store), "reqif"
    else:
        from app.services.sysml_export import export_sysml_v2
        content, ext = export_sysml_v2(store), "sysml"

    if output is None:
        project_name = store.read_meta().get("name", project_root.name)
        output = f"{project_name.replace(' ', '_')}.{ext}"
    Path(output).write_text(content)
    click.echo(click.style(f"  ✓ Exported to: {output}", fg="green"))


@cli.command("import")
@click.argument("project_path", default=".")
@click.option("--input", "-i", "input_file", required=True, help="ReqIF (.xml) or SysML (.sysml) file to import")
@click.option("--format", "-f", "fmt", default="auto", type=click.Choice(["auto", "reqif", "sysml"]))
@click.option("--mode", "-m", default="merge", type=click.Choice(["merge", "replace"]),
              help="merge: create/update; replace: wipe existing requirements first")
def import_(project_path, input_file, fmt, mode):
    """Import requirements from a ReqIF 1.2 or SysML v2 file."""
    project_root = Path(project_path).resolve()
    if not (project_root / "_meta.yaml").exists():
        click.echo(f"Error: {project_path} is not a valid project", err=True)
        sys.exit(1)
    src = Path(input_file)
    if not src.exists():
        click.echo(f"Error: input file not found: {input_file}", err=True)
        sys.exit(1)

    from app.services.yaml_store import YamlStore
    from app.services.importer import parse_and_import

    store = YamlStore(project_root)
    try:
        summary = parse_and_import(store, src.read_bytes(), fmt=fmt, mode=mode)
    except ValueError as exc:
        click.echo(click.style(f"  ✗ Import failed: {exc}", fg="red"), err=True)
        sys.exit(1)

    click.echo(click.style(
        f"  ✓ Imported ({summary['format']}): "
        f"{summary['created']} created, {summary['updated']} updated, "
        f"{summary['verification_cases']} verification cases, "
        f"{summary['traces_added']} traces, {summary['skipped']} skipped",
        fg="green",
    ))


if __name__ == "__main__":
    cli()
