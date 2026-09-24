"""Express and NestJS conventions mapped to generic HTTP entries."""
from __future__ import annotations

import re
from pathlib import Path

from ..evidence import Evidence
from ..providers.javascript_intelligence import analyze as analyze_js
from ..semantic import EntryPoint, ExecutionTransition, SemanticModel


class NodeAdapter:
    def __init__(self, framework: str): self.name = framework

    def detect(self, root: Path) -> bool:
        package = root / "package.json"
        return package.exists() and self.name.casefold() in package.read_text(encoding="utf-8", errors="ignore").casefold()

    def analyze(self, root: Path) -> SemanticModel:
        components, transitions = analyze_js(root); entries = []
        for path in [*root.rglob("*.js"), *root.rglob("*.ts")]:
            if "node_modules" in path.parts: continue
            relative, text = path.relative_to(root).as_posix(), path.read_text(encoding="utf-8", errors="ignore")
            if self.name == "Express":
                pattern = r"(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*([A-Za-z_$][\w$]*)"
            else:
                pattern = r"@(Get|Post|Put|Patch|Delete)\s*\(\s*['\"]?([^'\")]+)['\"]?\s*\)\s*(?:async\s+)?([A-Za-z_$][\w$]*)"
            for match in re.finditer(pattern, text):
                method, route, handler = match.groups(); name = f"{method.upper()} {route}"
                line = text.count("\n", 0, match.start()) + 1; evidence = [Evidence("code", relative, f"Ruta {self.name}", "CONFIRMED", 1.0, line=line, symbol=handler).as_dict()]
                entries.append(EntryPoint("HTTP", name, handler, "HTTP", method.upper(), route, relative, line, self.name, "CONFIRMED", evidence)); transitions.append(ExecutionTransition(name, handler, "HTTP_ENTRY", relative, line, "CONFIRMED", self.name.casefold(), evidence))
        return SemanticModel("TypeScript/JavaScript", self.name, "FRAMEWORK", components, entries, transitions)
