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

from pathlib import Path
import ast
import json

root = Path(__file__).resolve().parent.parent
files = sorted(
    p for p in root.rglob("*.py") if ".venv" not in p.parts and ".git" not in p.parts
)
summary = []
for path in files:
    text = path.read_text(encoding="utf-8", errors="ignore")
    try:
        mod = ast.parse(text)
    except SyntaxError as exc:
        summary.append(
            {"file": path.relative_to(root).as_posix(), "syntax_error": str(exc)}
        )
        continue
    module_doc = ast.get_docstring(mod) is not None
    missing = []
    for node in ast.walk(mod):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if ast.get_docstring(node) is None:
                missing.append(
                    {
                        "type": type(node).__name__,
                        "name": node.name,
                        "line": node.lineno,
                    }
                )
    if (not module_doc) or missing:
        summary.append(
            {
                "file": path.relative_to(root).as_posix(),
                "module_doc": module_doc,
                "missing": missing,
            }
        )
print(json.dumps(summary, indent=2))

