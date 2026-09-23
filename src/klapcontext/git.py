from __future__ import annotations

import subprocess
from pathlib import Path


def run_git(root: Path, *args: str) -> str | None:
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True)
    return result.stdout.strip() if result.returncode == 0 else None


def is_repository(root: Path) -> bool:
    return run_git(root, "rev-parse", "--is-inside-work-tree") == "true"


def commit(root: Path) -> str | None:
    return run_git(root, "rev-parse", "HEAD")


def dirty_files(root: Path) -> list[str]:
    output = run_git(root, "status", "--porcelain") or ""
    return [line[3:] for line in output.splitlines() if line]


def exclude_klap(root: Path) -> None:
    git_dir = run_git(root, "rev-parse", "--git-dir")
    if not git_dir:
        raise RuntimeError("Not a Git repository")
    exclude = (root / git_dir / "info" / "exclude").resolve()
    exclude.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    additions = [entry for entry in (".klap/", "graphify-out/") if entry not in {line.strip() for line in existing.splitlines()}]
    if additions:
        exclude.write_text(existing.rstrip() + ("\n" if existing.strip() else "") + "\n".join(additions) + "\n", encoding="utf-8")
