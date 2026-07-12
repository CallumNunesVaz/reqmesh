#!/usr/bin/env python3
"""Git pre-commit hook - validates requirements before committing."""

import sys
from pathlib import Path

HOOK_CONTENT = r'''#!/bin/bash
# reqmesh pre-commit hook
# Validates requirement YAML files before commit

PROJECT_ROOT=$(git rev-parse --show-toplevel)
STAGED=$(git diff --cached --name-only --diff-filter=ACM | grep -E "requirements/.*\.yaml$|specifications/.*\.yaml$|verification_cases/.*\.yaml$" || true)

if [ -z "$STAGED" ]; then
    exit 0
fi

echo "reqmesh: Checking staged requirements..."
ERRORS=0

for REQ_FILE in $STAGED; do
    if [ ! -f "$REQ_FILE" ]; then
        continue
    fi

    REQ_ID=$(basename "$REQ_FILE" .yaml)

    # Check for required fields
    if ! grep -q "^id:" "$REQ_FILE" 2>/dev/null; then
        echo "  ERROR: $REQ_ID - missing 'id' field"
        ERRORS=$((ERRORS + 1))
    fi

    # Check for dangling relations (basic check)
    RELS=$(grep -A1 "relations:" "$REQ_FILE" | grep "target:" | sed 's/.*target: //' | tr -d ' ')
    for TARGET in $RELS; do
        if [ ! -f "$(dirname "$REQ_FILE")/$TARGET.yaml" ] && [ ! -f "$PROJECT_ROOT/requirements/$TARGET.yaml" ]; then
            echo "  WARNING: $REQ_ID - links to $TARGET which may not exist"
        fi
    done
done

if [ $ERRORS -gt 0 ]; then
    echo ""
    echo "reqmesh: $ERRORS error(s) found. Commit blocked."
    echo "Run 'reqmesh validate' for details or use --no-verify to bypass."
    exit 1
fi

echo "reqmesh: All checks passed."
exit 0
'''


def install_hook(project_path: str) -> str:
    """Install the pre-commit hook into the project's .git/hooks directory."""
    git_dir = Path(project_path) / ".git"
    if not git_dir.exists():
        raise FileNotFoundError(f"No .git directory found in {project_path}. Run 'git init' first.")

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)

    hook_path = hooks_dir / "pre-commit"
    with open(hook_path, "w") as f:
        f.write(HOOK_CONTENT)

    hook_path.chmod(0o755)
    return str(hook_path)


def uninstall_hook(project_path: str) -> str:
    """Remove the pre-commit hook."""
    hook_path = Path(project_path) / ".git" / "hooks" / "pre-commit"
    if hook_path.exists():
        hook_path.unlink()
        return str(hook_path)
    return ""
