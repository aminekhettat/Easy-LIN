"""Block commits and pushes that leak confidential LDF assets.

Rules:
- No tracked or staged ``.ldf`` files.
- No mention of local ``.ldf`` filenames in tracked text files.

Local confidentiality is derived at runtime from local ``*.ldf`` files and is
never stored in repository sources.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.5.2
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
    in LICENSE.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _git(args: list[str], cwd: Path) -> str:
    """Run a git command in the repository and return its standard output."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


def _repo_root() -> Path:
    """Return the repository root directory."""
    here = Path(__file__).resolve().parent
    return here.parent


def _local_ldf_names(root: Path) -> set[str]:
    """Collect confidential local LDF filenames from the working tree."""
    names: set[str] = set()
    for path in root.rglob("*.ldf"):
        names.add(path.name.lower())
    return names


def _tracked_files(root: Path) -> list[Path]:
    """Return the tracked repository files as absolute paths."""
    out = _git(["ls-files"], root)
    files: list[Path] = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            files.append(root / line)
    return files


def _staged_paths(root: Path) -> list[str]:
    """Return staged paths that would be part of the next commit."""
    out = _git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"], root)
    return [line.strip() for line in out.splitlines() if line.strip()]


def _is_text_file(path: Path) -> bool:
    """Conservatively decide whether a tracked file should be scanned as text."""
    # conservative extension-based text detection for repository files
    text_ext = {
        ".py",
        ".md",
        ".txt",
        ".ini",
        ".yml",
        ".yaml",
        ".toml",
        ".json",
        ".cfg",
        ".gitignore",
        ".gitattributes",
        ".ps1",
        ".sh",
    }
    return path.suffix.lower() in text_ext or path.name in {
        "README",
        "README.md",
        "LICENSE",
    }


def _scan_for_name_leaks(root: Path, confidential_names: set[str]) -> list[str]:
    """Scan tracked text files for confidential local LDF filenames."""
    leaks: list[str] = []
    for tracked in _tracked_files(root):
        if not tracked.exists() or not _is_text_file(tracked):
            continue
        try:
            text = tracked.read_text(encoding="utf-8", errors="ignore").lower()
        except Exception:
            continue
        for name in confidential_names:
            if name and name in text:
                rel = tracked.relative_to(root).as_posix()
                leaks.append(f"{rel}: contains confidential LDF filename '{name}'")
                break
    return leaks


def main() -> int:
    """Run the confidentiality checks for the configured git hook mode."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=["pre-commit", "pre-push"], default="pre-commit"
    )
    args = parser.parse_args()

    root = _repo_root()
    confidential_names = _local_ldf_names(root)

    violations: list[str] = []

    staged = _staged_paths(root)
    for rel in staged:
        if rel.lower().endswith(".ldf"):
            violations.append(f"Staged .ldf file is forbidden: {rel}")

    tracked_ldf = [
        path.relative_to(root).as_posix()
        for path in _tracked_files(root)
        if path.suffix.lower() == ".ldf"
    ]
    for rel in tracked_ldf:
        violations.append(f"Tracked .ldf file is forbidden: {rel}")

    if confidential_names:
        violations.extend(_scan_for_name_leaks(root, confidential_names))

    if violations:
        print("\nLDF confidentiality guard blocked this operation:\n")
        for item in violations:
            print(f"- {item}")
        print(
            "\nFix: remove confidential names/content from tracked files and keep .ldf files untracked."
        )
        return 1

    print(f"LDF confidentiality guard ({args.mode}) passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

