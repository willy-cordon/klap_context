from __future__ import annotations

import json
from pathlib import Path

from .evidence import Evidence


def detect_project(root: Path) -> tuple[dict, list[Evidence]]:
    evidence: list[Evidence] = []
    stack = {"languages": [], "frameworks": [], "databases": [], "runtime": [], "infrastructure": []}
    def add(bucket: str, value: str, path: str, reason: str) -> None:
        if value not in stack[bucket]: stack[bucket].append(value)
        evidence.append(Evidence("file", path, reason, "CONFIRMED", 1.0))
    composer = root / "composer.json"
    if composer.exists():
        add("languages", "PHP", "composer.json", "Composer manifest detected")
        try: deps = {**json.loads(composer.read_text(encoding="utf-8")).get("require", {}), **json.loads(composer.read_text(encoding="utf-8")).get("require-dev", {})}
        except json.JSONDecodeError: deps = {}
        if "laravel/framework" in deps: add("frameworks", "Laravel", "composer.json", "laravel/framework dependency detected")
    elif any(root.rglob("*.php")):
        # A standalone PHP repository has no Composer manifest to identify it,
        # but language analysis can still provide a useful generic model.
        first_php = next(root.rglob("*.php"))
        add("languages", "PHP", str(first_php.relative_to(root)).replace("\\", "/"), "PHP source file detected")
    package = root / "package.json"
    if package.exists():
        add("languages", "JavaScript", "package.json", "npm manifest detected")
        try: deps = {**json.loads(package.read_text(encoding="utf-8")).get("dependencies", {}), **json.loads(package.read_text(encoding="utf-8")).get("devDependencies", {})}
        except json.JSONDecodeError: deps = {}
        for name, label in (("next", "Next.js"), ("vue", "Vue"), ("react", "React"), ("express", "Express"), ("@nestjs/core", "NestJS")):
            if name in deps: add("frameworks", label, "package.json", f"{name} dependency detected")
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
        python_manifest = root / "pyproject.toml" if (root / "pyproject.toml").exists() else root / "requirements.txt"
        add("languages", "Python", python_manifest.name, "Python manifest detected")
        if "fastapi" in python_manifest.read_text(encoding="utf-8", errors="ignore").casefold(): add("frameworks", "FastAPI", python_manifest.name, "FastAPI dependency detected")
    if (root / "manage.py").exists(): add("frameworks", "Django", "manage.py", "Django entry point detected")
    if list(root.glob("*.csproj")): add("languages", "C#", next(root.glob("*.csproj")).name, ".NET project detected")
    if (root / "Dockerfile").exists(): add("infrastructure", "Docker", "Dockerfile", "Dockerfile detected")
    if list(root.glob("docker-compose*")) or list(root.glob("compose*")): add("infrastructure", "Docker Compose", "docker-compose", "Compose configuration detected")
    if (root / ".github" / "workflows").exists(): add("infrastructure", "GitHub Actions", ".github/workflows", "GitHub Actions workflows detected")
    return stack, evidence


def detect_components(root: Path) -> list[dict]:
    """Find independent project boundaries without assuming a monorepo layout."""
    result = []
    for manifest in [*root.rglob("composer.json"), *root.rglob("package.json"), *root.rglob("pyproject.toml"), *root.rglob("requirements.txt")]:
        if any(part in {".git", ".klap", "node_modules", "vendor", ".venv", "venv"} for part in manifest.relative_to(root).parts): continue
        directory = manifest.parent
        if directory == root: continue
        stack, _ = detect_project(directory)
        result.append({"name": directory.name, "path": directory.relative_to(root).as_posix(), "languages": stack["languages"], "frameworks": stack["frameworks"], "manifest": manifest.name, "status": "CONFIRMED"})
    return result
