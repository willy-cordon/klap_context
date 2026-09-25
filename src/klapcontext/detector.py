from __future__ import annotations

import json
import fnmatch
import os
from pathlib import Path

from .evidence import Evidence


EXCLUDED = {".git", ".klap", "graphify-out", "node_modules", "vendor", ".venv", "venv", ".test-venv", "build", "dist"}


def _sources(root: Path, pattern: str):
    for directory, children, names in os.walk(root):
        children[:] = [child for child in children if child not in EXCLUDED]
        for name in names:
            if fnmatch.fnmatch(name, pattern):
                yield Path(directory) / name


def detect_project(root: Path) -> tuple[dict, list[Evidence]]:
    evidence: list[Evidence] = []
    stack = {"languages": [], "frameworks": [], "databases": [], "runtime": [], "infrastructure": [], "package_managers": [], "project_type": "unknown"}
    def add(bucket: str, value: str, path: str, reason: str) -> None:
        if value not in stack[bucket]: stack[bucket].append(value)
        evidence.append(Evidence("file", path, reason, "CONFIRMED", 1.0))
    composer = root / "composer.json"
    if not composer.exists():
        composer = next(_sources(root, "composer.json"), composer)
    if composer.exists():
        composer_path = composer.relative_to(root).as_posix()
        add("languages", "PHP", composer_path, "Composer manifest detected")
        stack["runtime"].append("PHP"); stack["package_managers"].append("composer")
        try: deps = {**json.loads(composer.read_text(encoding="utf-8")).get("require", {}), **json.loads(composer.read_text(encoding="utf-8")).get("require-dev", {})}
        except json.JSONDecodeError: deps = {}
        if "laravel/framework" in deps: add("frameworks", "Laravel", composer_path, "laravel/framework dependency detected")
        if "laravel/lumen-framework" in deps:
            add("frameworks", "Lumen", composer_path, "laravel/lumen-framework dependency detected")
            stack["project_type"] = "backend-api"
    elif any(_sources(root, "*.php")):
        # A standalone PHP repository has no Composer manifest to identify it,
        # but language analysis can still provide a useful generic model.
        first_php = next(_sources(root, "*.php"))
        add("languages", "PHP", str(first_php.relative_to(root)).replace("\\", "/"), "PHP source file detected")
    package = root / "package.json"
    if not package.exists():
        package = next(_sources(root, "package.json"), package)
    if package.exists():
        package_path = package.relative_to(root).as_posix()
        add("languages", "JavaScript", package_path, "npm manifest detected")
        stack["runtime"].append("Node.js"); stack["package_managers"].append("npm")
        try: deps = {**json.loads(package.read_text(encoding="utf-8")).get("dependencies", {}), **json.loads(package.read_text(encoding="utf-8")).get("devDependencies", {})}
        except json.JSONDecodeError: deps = {}
        for name, label in (("next", "Next.js"), ("vue", "Vue"), ("react", "React"), ("express", "Express"), ("@nestjs/core", "NestJS")):
            if name in deps: add("frameworks", label, package_path, f"{name} dependency detected")
        if any(_sources(root, "*.ts")) or any(_sources(root, "*.tsx")): add("languages", "TypeScript", package_path, "TypeScript source detected")
    python_manifest = next((path for pattern in ("pyproject.toml", "requirements.txt") if (path := next(_sources(root, pattern), None))), None)
    if python_manifest:
        python_path = python_manifest.relative_to(root).as_posix()
        add("languages", "Python", python_path, "Python manifest detected")
        stack["runtime"].append("Python"); stack["package_managers"].append("pip")
        if "fastapi" in python_manifest.read_text(encoding="utf-8", errors="ignore").casefold(): add("frameworks", "FastAPI", python_path, "FastAPI dependency detected")
    if (root / "manage.py").exists(): add("frameworks", "Django", "manage.py", "Django entry point detected")
    projects = list(_sources(root, "*.csproj"))
    if projects:
        project = projects[0]; relative = project.relative_to(root).as_posix()
        add("languages", "C#", relative, ".NET project detected"); stack["runtime"].append(".NET"); stack["package_managers"].append("NuGet")
        if "Microsoft.NET.Sdk.Web" in project.read_text(encoding="utf-8", errors="ignore"):
            add("frameworks", "ASP.NET", relative, "Web SDK detected")
    if (root / "go.mod").exists():
        add("languages", "Go", "go.mod", "Go module detected"); stack["runtime"].append("Go"); stack["package_managers"].append("go modules")
    if (root / "Cargo.toml").exists():
        add("languages", "Rust", "Cargo.toml", "Rust manifest detected"); stack["runtime"].append("Rust"); stack["package_managers"].append("cargo")
    if (root / "pom.xml").exists() or (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        manifest = "pom.xml" if (root / "pom.xml").exists() else "build.gradle" if (root / "build.gradle").exists() else "build.gradle.kts"
        add("languages", "Java", manifest, "Java build manifest detected"); stack["runtime"].append("JVM"); stack["package_managers"].append("maven" if manifest == "pom.xml" else "gradle")
    # Keep generic analysis useful for small repositories without a manifest.
    for suffix, language in (("*.py", "Python"), ("*.cs", "C#"), ("*.js", "JavaScript"), ("*.ts", "TypeScript"), ("*.java", "Java"), ("*.go", "Go"), ("*.rs", "Rust")):
        if language not in stack["languages"] and any(_sources(root, suffix)):
            first = next(_sources(root, suffix)); add("languages", language, first.relative_to(root).as_posix(), f"{language} source file detected")
    if any(name in stack["frameworks"] for name in ("Laravel", "Lumen", "FastAPI", "Express", "NestJS", "ASP.NET")): stack["project_type"] = "backend-api"
    if (root / "Dockerfile").exists(): add("infrastructure", "Docker", "Dockerfile", "Dockerfile detected")
    if list(root.glob("docker-compose*")) or list(root.glob("compose*")): add("infrastructure", "Docker Compose", "docker-compose", "Compose configuration detected")
    if (root / ".github" / "workflows").exists(): add("infrastructure", "GitHub Actions", ".github/workflows", "GitHub Actions workflows detected")
    return stack, evidence


def detect_components(root: Path) -> list[dict]:
    """Find independent project boundaries without assuming a monorepo layout."""
    result = []
    manifests = [path for pattern in ("composer.json", "package.json", "pyproject.toml", "requirements.txt", "*.csproj", "go.mod", "Cargo.toml", "pom.xml") for path in _sources(root, pattern)]
    for manifest in manifests:
        directory = manifest.parent
        if directory == root: continue
        stack, _ = detect_project(directory)
        result.append({"name": directory.name, "path": directory.relative_to(root).as_posix(), "languages": stack["languages"], "frameworks": stack["frameworks"], "manifest": manifest.name, "status": "CONFIRMED"})
    return result
