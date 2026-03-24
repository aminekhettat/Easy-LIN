"""Audit Python files for missing module, class, and function docstrings.

This helper is used during documentation work to identify symbols that still
need Sphinx-style documentation.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.5.2
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
    in LICENSE.
"""

import ast
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent


def iter_python_files(root: Path) -> list[Path]:
    """Return repository Python files excluding virtualenv and git metadata."""
    return sorted(
        path
        for path in root.rglob("*.py")
        if ".venv" not in path.parts and ".git" not in path.parts
    )


def audit_python_file(path: Path, root: Path) -> dict[str, Any] | None:
    """Return missing-docstring metadata for one Python file if needed."""
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    try:
        module = ast.parse(text)
    except SyntaxError as exc:
        return {"file": path.relative_to(root).as_posix(), "syntax_error": str(exc)}

    module_doc = ast.get_docstring(module) is not None
    missing = []
    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if ast.get_docstring(node) is None:
                missing.append(
                    {
                        "type": type(node).__name__,
                        "name": node.name,
                        "line": node.lineno,
                    }
                )

    if module_doc and not missing:
        return None

    return {
        "file": path.relative_to(root).as_posix(),
        "module_doc": module_doc,
        "missing": missing,
    }


def build_summary(root: Path = ROOT) -> list[dict[str, Any]]:
    """Collect the documentation audit summary for the repository."""
    summary = []
    for path in iter_python_files(root):
        result = audit_python_file(path, root)
        if result is not None:
            summary.append(result)
    return summary


def main() -> None:
    """Print the repository docstring audit report as JSON."""
    print(json.dumps(build_summary(), indent=2))


if __name__ == "__main__":
    main()
