"""FastAPI conventions translated into the framework-neutral semantic model."""
from __future__ import annotations

import ast
from pathlib import Path

from ..evidence import Evidence
from ..providers.python_intelligence import analyze as analyze_python
from ..semantic import EntryPoint, ExecutionTransition, SemanticModel


class FastAPIAdapter:
    name = "FastAPI"

    def detect(self, root: Path) -> bool:
        return any("fastapi" in path.read_text(encoding="utf-8", errors="ignore").casefold() for path in (root / "pyproject.toml", root / "requirements.txt") if path.exists())

    def analyze(self, root: Path) -> SemanticModel:
        components, transitions = analyze_python(root); entries = []
        for path in root.rglob("*.py"):
            if any(part in {".venv", "venv", ".git", ".klap"} for part in path.relative_to(root).parts): continue
            relative = path.relative_to(root).as_posix()
            try: tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError): continue
            for node in tree.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)): continue
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute): continue
                    if decorator.func.attr.lower() not in {"get", "post", "put", "patch", "delete", "options"}: continue
                    route = decorator.args[0].value if decorator.args and isinstance(decorator.args[0], ast.Constant) else None
                    if not isinstance(route, str): continue
                    method = decorator.func.attr.upper(); name = f"{method} {route}"
                    evidence = [Evidence("code", relative, "Decorador de ruta FastAPI", "CONFIRMED", 1.0, line=node.lineno, symbol=node.name).as_dict()]
                    handler = f"{relative.removesuffix('.py').replace('/', '.')}.{node.name}"
                    entries.append(EntryPoint("HTTP", name, handler, "HTTP", method, route, relative, node.lineno, "FastAPI", "CONFIRMED", evidence))
                    transitions.append(ExecutionTransition(name, handler, "HTTP_ENTRY", relative, node.lineno, "CONFIRMED", "fastapi", evidence))
        return SemanticModel("Python", "FastAPI", "FRAMEWORK", components, entries, transitions)
