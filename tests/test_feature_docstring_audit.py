"""
Atomic features covered:
- Audit files with UTF-8 BOM without raising false syntax errors
- Report missing module and function docstrings with stable metadata
"""

from __future__ import annotations

from pathlib import Path

from tools.audit_docstrings import audit_python_file, build_summary


def test_audit_python_file_accepts_utf8_bom_module(tmp_path: Path) -> None:
    """Ensure BOM-prefixed Python files are parsed and ignored when fully documented."""
    module_path = tmp_path / "bom_module.py"
    module_path.write_text(
        '"""Documented module."""\n\n'
        "def documented() -> None:\n"
        '    """Documented function."""\n'
        "    return None\n",
        encoding="utf-8-sig",
    )

    result = audit_python_file(module_path, tmp_path)

    assert result is None


def test_audit_python_file_reports_missing_docstrings(tmp_path: Path) -> None:
    """Ensure missing module and nested function docstrings are reported."""
    module_path = tmp_path / "undocumented.py"
    module_path.write_text(
        "def outer() -> None:\n"
        '    """Outer function docstring."""\n'
        "    def inner() -> None:\n"
        "        return None\n"
        "    inner()\n",
        encoding="utf-8",
    )

    result = audit_python_file(module_path, tmp_path)

    assert result == {
        "file": "undocumented.py",
        "module_doc": False,
        "missing": [
            {"type": "FunctionDef", "name": "inner", "line": 3},
        ],
    }


def test_build_summary_collects_only_files_with_gaps(tmp_path: Path) -> None:
    """Ensure the repository summary includes only files that need documentation work."""
    (tmp_path / "documented.py").write_text(
        '"""Documented module."""\n\n'
        "class Documented:\n"
        '    """Documented class."""\n\n'
        "    def method(self) -> None:\n"
        '        """Documented method."""\n'
        "        return None\n",
        encoding="utf-8",
    )
    (tmp_path / "missing.py").write_text(
        '"""Module docstring."""\n\ndef undocumented() -> None:\n    return None\n',
        encoding="utf-8",
    )

    summary = build_summary(tmp_path)

    assert summary == [
        {
            "file": "missing.py",
            "module_doc": True,
            "missing": [
                {"type": "FunctionDef", "name": "undocumented", "line": 3},
            ],
        }
    ]
