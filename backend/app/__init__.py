"""reqmesh - Requirements management using version control.

Usage as a library:
    import reqmesh

    proj = reqmesh.open("./my-project")
    reqs = proj.list_requirements()
    result = proj.validate()
    proj.publish("html", "./output/report.html")
"""

from pathlib import Path


def open(project_path: str) -> "Project":
    """Open a project from a directory path."""
    project_root = Path(project_path).resolve()
    if not (project_root / "_meta.yaml").exists():
        raise FileNotFoundError(f"Not a valid project: {project_path}")
    return Project(project_root)


class Project:
    def __init__(self, root: Path):
        self.root = root
        self._store = None

    @property
    def store(self):
        if self._store is None:
            from app.services.yaml_store import YamlStore
            self._store = YamlStore(self.root)
        return self._store

    @property
    def name(self) -> str:
        return self.store.read_meta().get("name", self.root.name)

    def list_requirements(self) -> list[dict]:
        return self.store.list_requirements()

    def get_requirement(self, req_id: str) -> dict | None:
        return self.store.get_requirement(req_id)

    def list_verification_cases(self) -> list[dict]:
        return self.store.list_verification_cases()

    def list_specifications(self) -> list[dict]:
        return self.store.list_specifications()

    def validate(self) -> dict:
        from app.services.integrity import IntegrityChecker
        checker = IntegrityChecker(self.store)
        return checker.check_all()

    def publish(self, format: str = "html", output: str | None = None, sections: list | None = None) -> str:
        from app.services.publisher import Publisher
        pub = Publisher(self.store)
        if format == "html":
            if output:
                pub.to_html_file(output)
                return output
            return pub.to_html_string()
        elif format == "md":
            if output:
                pub.to_markdown_file(output)
                return output
            return pub.build_markdown()
        elif format == "pdf":
            pub.to_pdf_file(output)
            return output
        elif format == "latex":
            if output:
                pub.to_latex_file(output)
                return output
            return pub.build_latex()
        raise ValueError(f"Unknown format: {format}")

    def __repr__(self):
        return f"Project({self.name!r}, {len(self.list_requirements())} reqs)"
