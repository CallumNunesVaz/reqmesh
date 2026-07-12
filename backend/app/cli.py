#!/usr/bin/env python3
"""reqmesh CLI - Requirements management using version control."""

import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@click.group()
@click.version_option("0.3.0", prog_name="reqmesh")
def cli():
    """reqmesh - Requirements management using version control."""


@cli.command()
@click.argument("project_path", default=".")
@click.option("--port", "-p", default=8000, help="Port to run on")
@click.option("--host", "-h", default="0.0.0.0", help="Host to bind to")
def serve(project_path, port, host):
    """Start the web UI for a project directory."""
    import os
    os.environ["RT_DATA_ROOT"] = str(Path(project_path).resolve())
    import uvicorn
    click.echo(f"Starting reqmesh on http://{host}:{port}")
    click.echo(f"Project: {Path(project_path).resolve()}")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)


@cli.command()
@click.argument("project_path", default=".")
def validate(project_path):
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

    sys.exit(0 if result["valid"] else 1)


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
def export(project_path):
    """Export a project (placeholder - ReqIF/SysML coming soon)."""
    click.echo("Export to ReqIF/SysML formats coming in a future release.")


@cli.command()
@click.argument("project_path", default=".")
def import_(project_path):
    """Import a project (placeholder - ReqIF/SysML coming soon)."""
    click.echo("Import from ReqIF/SysML formats coming in a future release.")


if __name__ == "__main__":
    cli()
