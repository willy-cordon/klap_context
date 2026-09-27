"""Express and NestJS conventions mapped to generic HTTP entries."""
from __future__ import annotations

import re
from pathlib import Path

from ..evidence import Evidence
from ..providers.javascript_intelligence import analyze as analyze_js
from ..semantic import EntryPoint, ExecutionTransition, SemanticModel
from ..scope import IndexScope


def _inactive_spans(path: Path, text: str) -> list[tuple[int, int]]:
    try:
        from tree_sitter import Language, Parser
        if path.suffix in {".ts", ".tsx"}:
            import tree_sitter_typescript
            language = tree_sitter_typescript.language_tsx() if path.suffix == ".tsx" else tree_sitter_typescript.language_typescript()
        else:
            import tree_sitter_javascript
            language = tree_sitter_javascript.language()
        source = text.encode("utf-8")
        tree = Parser(Language(language)).parse(source)
        spans, stack = [], [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type in {"comment", "string", "template_string"}:
                spans.append((len(source[:node.start_byte].decode("utf-8", errors="replace")), len(source[:node.end_byte].decode("utf-8", errors="replace"))))
                continue
            stack.extend(node.children)
        return spans
    except (ImportError, ValueError):
        return [(match.start(), match.end()) for match in re.finditer(r"//[^\n]*|/\*.*?\*/", text, re.S)]


class NodeAdapter:
    def __init__(self, framework: str, scope: IndexScope | None = None):
        self.name = framework
        self.scope = scope

    def detect(self, root: Path) -> bool:
        package = root / "package.json"
        return package.exists() and self.name.casefold() in package.read_text(encoding="utf-8", errors="ignore").casefold()

    def analyze(self, root: Path) -> SemanticModel:
        components, transitions = analyze_js(root, self.scope); entries = []
        for path in [*root.rglob("*.js"), *root.rglob("*.ts")]:
            if "node_modules" in path.parts: continue
            relative, text = path.relative_to(root).as_posix(), path.read_text(encoding="utf-8", errors="ignore")
            if self.scope is not None and relative not in self.scope.included_paths: continue
            if self.name == "Express":
                pattern = r"(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*([A-Za-z_$][\w$]*)"
            else:
                pattern = r"@(Get|Post|Put|Patch|Delete)\s*\(\s*['\"]?([^'\")]+)['\"]?\s*\)\s*(?:async\s+)?([A-Za-z_$][\w$]*)"
            inactive = _inactive_spans(path, text)
            for match in re.finditer(pattern, text):
                if any(start <= match.start() < end for start, end in inactive):
                    continue
                method, route, handler = match.groups(); name = f"{method.upper()} {route}"
                line = text.count("\n", 0, match.start()) + 1; evidence = [Evidence("code", relative, f"Ruta {self.name}", "CONFIRMED", 1.0, line=line, symbol=handler).as_dict()]
                entries.append(EntryPoint("HTTP", name, handler, "HTTP", method.upper(), route, relative, line, self.name, "CONFIRMED", evidence)); transitions.append(ExecutionTransition(name, handler, "HTTP_ENTRY", relative, line, "CONFIRMED", self.name.casefold(), evidence))
        return SemanticModel("TypeScript/JavaScript", self.name, "FRAMEWORK", components, entries, transitions)
