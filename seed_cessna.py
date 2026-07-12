#!/usr/bin/env python3
"""Seed the Cessna 172 example project.

Writes the project directly into the data root — no running server or
credentials required. The backend also does this automatically on first
launch when the data root has no projects (disable with RT_SEED_DEMO=false),
so this script is only needed to re-seed or to seed a custom location.

Usage:
    backend/.venv/bin/python seed_cessna.py            # seed if missing
    backend/.venv/bin/python seed_cessna.py --force    # delete and re-seed
    backend/.venv/bin/python seed_cessna.py --data-root /path/to/projects
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.core.config import settings  # noqa: E402
from app.services.demo_seed import PROJECT_ID, seed_demo_project  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default=settings.data_root,
                        help=f"Projects directory (default: {settings.data_root})")
    parser.add_argument("--force", action="store_true",
                        help="Delete an existing cessna-172 project and re-seed")
    args = parser.parse_args()

    data_root = Path(args.data_root)
    data_root.mkdir(parents=True, exist_ok=True)
    if seed_demo_project(data_root, force=args.force):
        print(f"Seeded {PROJECT_ID} into {data_root}")
    else:
        print(f"{PROJECT_ID} already exists in {data_root} (use --force to re-seed)")


if __name__ == "__main__":
    main()
