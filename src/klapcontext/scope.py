"""Central, explainable repository scope used before every analysis provider."""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

RULES_VERSION = "2"
CODE_EXTENSIONS = {
    ".py", ".php", ".cs", ".js", ".jsx", ".ts", ".tsx", ".java", ".go",
    ".rs", ".rb", ".kt", ".kts", ".vue", ".swift", ".cpp", ".cc", ".c",
    ".h", ".hpp", ".fs", ".fsx", ".scala", ".sh", ".ps1",
}
METADATA_NAMES = {
    "composer.json", "composer.lock", "package.json", "package-lock.json",
    "yarn.lock", "pnpm-lock.yaml", "pyproject.toml", "poetry.lock",
    "requirements.txt", "pipfile", "pipfile.lock", "cargo.toml", "cargo.lock",
    "go.mod", "go.sum", "pom.xml", "build.gradle", "build.gradle.kts",
    "global.json", "directory.build.props", "directory.packages.props",
}
METADATA_SUFFIXES = {".csproj", ".fsproj", ".vbproj", ".sln"}
HARD_EXCLUDED_DIRS = {".git", ".klap", "graphify-out"}
DEFAULT_EXCLUDED_DIRS = {
    "node_modules", "vendor", ".next", ".nuxt", ".output", "dist", "build",
    "coverage", ".coverage", ".venv", ".test-venv", "venv", "env", "site-packages", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", ".nox", "bin", "obj", "target", ".gradle", ".idea",
}
VENDOR_PATHS = {"public/assets/vendor", "public/assets_admin/vendors"}
STATIC_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".woff",
    ".woff2", ".ttf", ".eot", ".mp3", ".wav", ".mp4", ".mov", ".pdf",
    ".zip", ".gz", ".tar", ".7z", ".map",
}
DEFAULT_CONFIG = {"version": 1, "include": [], "exclude": []}


def _match(path: str, pattern: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    pattern = pattern.replace("\\", "/").lstrip("./")
    return fnmatch.fnmatch(normalized, pattern) or Path(normalized).match(pattern)


def _git_lines(root: Path, *args: str) -> list[str] | None:
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True)
    if result.returncode != 0:
        return None
    return [line.replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


@dataclass
class ScopeEntry:
    path: str
    kind: str
    reason: str
    tracked: bool = False
    explicit: bool = False

    def as_dict(self) -> dict:
        return {"path": self.path, "kind": self.kind, "reason": self.reason, "tracked": self.tracked, "explicit": self.explicit}


@dataclass
class IndexScope:
    root: Path
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    included: list[ScopeEntry] = field(default_factory=list)
    metadata: list[ScopeEntry] = field(default_factory=list)
    excluded: list[ScopeEntry] = field(default_factory=list)
    ignored_by_git: int = 0

    @classmethod
    def load(cls, root: Path, *, write_default: bool = True) -> "IndexScope":
        root = root.resolve()
        config_path = root / ".klap" / "scope.json"
        config = DEFAULT_CONFIG.copy()
        if config_path.exists():
            try:
                loaded = json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    config.update(loaded)
            except (OSError, json.JSONDecodeError):
                # Invalid configuration is represented in the scope summary and
                # never silently replaced.
                config["configuration_error"] = "Invalid .klap/scope.json"
        elif write_default:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")
        scope = cls(root, list(config.get("include", [])), list(config.get("exclude", [])))
        scope._scan()
        if config.get("configuration_error"):
            scope.excluded.append(ScopeEntry(".klap/scope.json", "configuration", config["configuration_error"]))
        return scope

    def _scan(self) -> None:
        tracked = set(_git_lines(self.root, "ls-files") or [])
        visible = _git_lines(self.root, "ls-files", "--cached", "--others", "--exclude-standard")
        if visible is None:
            candidates = []
            for directory, children, names in os.walk(self.root):
                children[:] = [name for name in children if name not in HARD_EXCLUDED_DIRS]
                for name in names:
                    candidates.append((Path(directory) / name).relative_to(self.root).as_posix())
        else:
            candidates = visible
            ignored = _git_lines(self.root, "ls-files", "--others", "--ignored", "--exclude-standard") or []
            for relative in ignored:
                classified = self.classify(relative, tracked=False)
                explicitly_included = any(_match(relative, pattern) for pattern in self.include_patterns)
                if explicitly_included:
                    candidates.append(relative)
                elif classified.kind == "code":
                    self.ignored_by_git += 1
        seen = set()
        for relative in sorted(candidates):
            relative = relative.strip("/")
            if not relative or relative in seen:
                continue
            seen.add(relative)
            path = self.root / relative
            if not path.is_file():
                continue
            entry = self.classify(relative, tracked=relative in tracked)
            if entry.kind == "code":
                self.included.append(entry)
            elif entry.kind == "metadata":
                self.metadata.append(entry)
            else:
                self.excluded.append(entry)

    def classify(self, relative: str, *, tracked: bool = False) -> ScopeEntry:
        normalized = relative.replace("\\", "/").strip("/")
        parts = normalized.split("/")
        explicit_include = any(_match(normalized, pattern) for pattern in self.include_patterns)
        explicit_exclude = any(_match(normalized, pattern) for pattern in self.exclude_patterns)
        if any(part in HARD_EXCLUDED_DIRS for part in parts):
            return ScopeEntry(normalized, "excluded", "KlapContext/Git generated artifact", tracked, explicit_exclude)
        if explicit_exclude and not explicit_include:
            return ScopeEntry(normalized, "excluded", "Explicit scope exclusion", tracked, True)
        if explicit_include:
            return ScopeEntry(normalized, "code", "Explicit scope inclusion", tracked, True)
        lowered = normalized.casefold()
        if any(lowered == prefix or lowered.startswith(prefix + "/") for prefix in VENDOR_PATHS):
            return ScopeEntry(normalized, "excluded", "Vendored public asset", tracked)
        excluded_dir = next((part for part in parts[:-1] if part.casefold() in DEFAULT_EXCLUDED_DIRS), None)
        if excluded_dir:
            return ScopeEntry(normalized, "excluded", f"Generated, cache or dependency directory: {excluded_dir}", tracked)
        name = parts[-1].casefold()
        suffix = Path(name).suffix.casefold()
        if name in METADATA_NAMES or suffix in METADATA_SUFFIXES:
            return ScopeEntry(normalized, "metadata", "Dependency/build metadata", tracked)
        if name == "artisan" or parts[0].casefold() == ".husky":
            return ScopeEntry(normalized, "code", "Repository executable script", tracked)
        if not suffix:
            try:
                first_line = (self.root / normalized).open("rb").readline(256)
                if first_line.startswith(b"#!"):
                    return ScopeEntry(normalized, "code", "Repository executable script", tracked)
            except OSError:
                pass
        if name.endswith((".min.js", ".min.css", ".bundle.js", ".bundle.css")):
            return ScopeEntry(normalized, "excluded", "Minified or bundled output", tracked)
        if suffix in STATIC_SUFFIXES:
            return ScopeEntry(normalized, "excluded", "Static/binary resource", tracked)
        if suffix in CODE_EXTENSIONS:
            return ScopeEntry(normalized, "code", "Repository source code", tracked)
        return ScopeEntry(normalized, "excluded", "Non-code project resource", tracked)

    def includes(self, path: str | Path) -> bool:
        try:
            relative = Path(path).resolve().relative_to(self.root).as_posix() if Path(path).is_absolute() else Path(path).as_posix()
        except (OSError, ValueError):
            return False
        return any(entry.path == relative for entry in self.included)

    @property
    def included_paths(self) -> set[str]:
        return {entry.path for entry in self.included}

    @property
    def relevant_paths(self) -> set[str]:
        return self.included_paths | {entry.path for entry in self.metadata} | {".klap/scope.json"}

    def graphify_excludes(self) -> list[str]:
        patterns = [f"**/{name}/**" for name in sorted(DEFAULT_EXCLUDED_DIRS | HARD_EXCLUDED_DIRS)]
        patterns += [f"{path}/**" for path in sorted(VENDOR_PATHS)]
        patterns += ["**/*.min.js", "**/*.min.css", "**/*.bundle.js", "**/*.bundle.css", "**/*.map"]
        patterns += self.exclude_patterns
        # Explicit includes negate compatible gitignore-style exclusions.
        patterns += ["!" + pattern for pattern in self.include_patterns]
        return patterns

    def snapshot_hash(self) -> str:
        digest = hashlib.sha256()
        digest.update(f"scope-rules:{RULES_VERSION}\n".encode())
        digest.update(json.dumps({"include": self.include_patterns, "exclude": self.exclude_patterns}, sort_keys=True).encode())
        for relative in sorted(self.relevant_paths):
            path = self.root / relative
            digest.update(relative.encode("utf-8", errors="replace"))
            if path.exists() and path.is_file():
                try:
                    with path.open("rb") as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            digest.update(chunk)
                except OSError:
                    digest.update(b"<unreadable>")
            else:
                digest.update(b"<missing>")
        return digest.hexdigest()

    def summary(self, *, graph: dict | None = None) -> dict:
        reasons = Counter(entry.reason for entry in self.excluded)
        graph_nodes = (graph or {}).get("nodes", [])
        if not isinstance(graph_nodes, list):
            graph_nodes = (graph or {}).get("graph", {}).get("nodes", []) if isinstance((graph or {}).get("graph"), dict) else []
        nodes_in_scope = 0
        nodes_metadata = 0
        nodes_without_source = 0
        nodes_outside = 0
        metadata_paths = {entry.path for entry in self.metadata}
        for node in graph_nodes if isinstance(graph_nodes, list) else []:
            raw = node.get("source_file") or node.get("file") or node.get("path") if isinstance(node, dict) else None
            if not raw:
                nodes_without_source += 1
                continue
            try:
                relative = Path(raw).resolve().relative_to(self.root).as_posix() if Path(raw).is_absolute() else Path(raw).as_posix()
            except (OSError, ValueError):
                nodes_outside += 1
                continue
            if relative in self.included_paths:
                nodes_in_scope += 1
            elif relative in metadata_paths:
                nodes_metadata += 1
            else:
                nodes_outside += 1
        warnings = []
        if nodes_outside:
            warnings.append(f"{nodes_outside} graph node(s) reference files outside the selected code scope.")
        if self.ignored_by_git:
            warnings.append(f"{self.ignored_by_git} untracked path(s) are ignored by Git and were not analyzed unless explicitly made visible.")
        return {
            "rules_version": RULES_VERSION,
            "configuration": ".klap/scope.json",
            "hash": self.snapshot_hash(),
            "included_code_files": len(self.included),
            "metadata_files": len(self.metadata),
            "excluded_files": len(self.excluded),
            "ignored_by_git": self.ignored_by_git,
            "included_roots": self._top_roots(self.included),
            "excluded_reasons": dict(reasons.most_common()),
            "graph_nodes_in_scope": nodes_in_scope,
            "graph_nodes_metadata": nodes_metadata,
            "graph_nodes_without_source": nodes_without_source,
            "graph_nodes_outside_scope": nodes_outside,
            "warnings": warnings,
            "included": [entry.as_dict() for entry in self.included],
            "metadata": [entry.as_dict() for entry in self.metadata],
            "excluded": [entry.as_dict() for entry in self.excluded],
        }

    def filter_graph(self, graph: dict) -> dict:
        """Defensive filter using the same scope; providers should already comply."""
        if not isinstance(graph, dict):
            return {}
        nested = graph.get("graph") if isinstance(graph.get("graph"), dict) else None
        container = nested or graph
        nodes = container.get("nodes", [])
        if not isinstance(nodes, list):
            return graph
        kept_ids: set[str] = set()
        unresolved: set[str] = set()
        kept_nodes = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            identifier = str(node.get("id", ""))
            raw = node.get("source_file") or node.get("file") or node.get("path")
            if not raw:
                unresolved.add(identifier)
                continue
            try:
                relative = Path(raw).resolve().relative_to(self.root).as_posix() if Path(raw).is_absolute() else Path(raw).as_posix()
            except (OSError, ValueError):
                continue
            if relative in self.included_paths:
                kept_ids.add(identifier)
                kept_nodes.append(node)
        edges_key = "links" if isinstance(container.get("links"), list) else "edges"
        edges = container.get(edges_key, []) if isinstance(container.get(edges_key), list) else []
        # Keep source-less semantic nodes only when directly connected to scoped code.
        connected = set()
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("source", edge.get("from", "")))
            target = str(edge.get("target", edge.get("to", "")))
            if source in kept_ids and target in unresolved:
                connected.add(target)
            if target in kept_ids and source in unresolved:
                connected.add(source)
        if connected:
            kept_nodes.extend(node for node in nodes if isinstance(node, dict) and str(node.get("id", "")) in connected)
            kept_ids.update(connected)
        kept_edges = [edge for edge in edges if isinstance(edge, dict) and str(edge.get("source", edge.get("from", ""))) in kept_ids and str(edge.get("target", edge.get("to", ""))) in kept_ids]
        result = dict(graph)
        target = dict(container)
        target["nodes"] = kept_nodes
        target[edges_key] = kept_edges
        if nested is not None:
            result["graph"] = target
        else:
            result = target
        return result

    @staticmethod
    def _top_roots(entries: list[ScopeEntry]) -> list[dict]:
        counts = Counter(entry.path.split("/", 1)[0] for entry in entries)
        return [{"path": path, "files": count} for path, count in counts.most_common(20)]
