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


def branch(root: Path) -> str | None:
    return run_git(root, "branch", "--show-current")


def recent_changes(root: Path, paths: list[str] | None = None, limit: int = 8) -> list[dict]:
    args = ["log", f"--max-count={limit}", "--format=%H%x1f%ad%x1f%s", "--date=short"]
    if paths: args.extend(["--", *paths])
    output = run_git(root, *args) or ""
    return [{"commit": parts[0], "date": parts[1], "subject": parts[2], "status": "CONFIRMED"} for line in output.splitlines() if len(parts := line.split("\x1f", 2)) == 3]


def co_changes(root: Path, path: str, limit: int = 30) -> list[dict]:
    output = run_git(root, "log", f"--max-count={limit}", "--name-only", "--format=") or ""
    counts: dict[str, int] = {}
    for group in output.split("\n\n"):
        files = {line.strip().replace("\\", "/") for line in group.splitlines() if line.strip()}
        if path.replace("\\", "/") in files:
            for other in files - {path.replace("\\", "/")}:
                counts[other] = counts.get(other, 0) + 1
    return [{"path": other, "co_change_count": count, "status": "INFERRED", "reason": "Cambió en el mismo commit histórico; no implica causalidad."} for other, count in sorted(counts.items(), key=lambda item: item[1], reverse=True) if count > 1][:10]


def intelligence(root: Path, paths: list[str] | None = None) -> dict:
    return {"branch": branch(root), "commit": commit(root), "modified_files": dirty_files(root), "recent_changes": recent_changes(root, paths), "co_changes": co_changes(root, paths[0]) if paths else []}


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
