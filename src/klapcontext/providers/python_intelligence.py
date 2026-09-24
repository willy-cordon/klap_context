"""Small deterministic Python structural index built on the standard AST."""
from __future__ import annotations

import ast
from pathlib import Path

from ..semantic import ExecutionTransition, SemanticComponent


EXCLUDED = {".git", ".klap", ".venv", "venv", "node_modules", "build", "dist", "__pycache__"}


def analyze(root: Path) -> tuple[list[SemanticComponent], list[ExecutionTransition]]:
    components, transitions = [], []
    for path in sorted(root.rglob("*.py")):
        if any(part in EXCLUDED for part in path.relative_to(root).parts):
            continue
        relative = path.relative_to(root).as_posix()
        try: tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except (OSError, SyntaxError): continue
        module = relative.removesuffix(".py").replace("/", ".")
        for node in tree.body:
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)): continue
            name = f"{module}.{node.name}"
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            components.append(SemanticComponent(name, kind, relative, name, evidence=[]))
            body = node.body if isinstance(node, ast.ClassDef) else [node]
            methods = [item for item in body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))] if isinstance(node, ast.ClassDef) else []
            for method in methods:
                method_name = f"{name}.{method.name}"
                components.append(SemanticComponent(method_name, "method", relative, method_name, evidence=[]))
                _calls(method, method_name, relative, transitions)
            if not isinstance(node, ast.ClassDef): _calls(node, name, relative, transitions)
    return components, transitions


def _calls(node: ast.AST, source: str, file: str, transitions: list[ExecutionTransition]) -> None:
    for item in ast.walk(node):
        if not isinstance(item, ast.Call): continue
        target = None
        if isinstance(item.func, ast.Name): target = item.func.id
        elif isinstance(item.func, ast.Attribute): target = item.func.attr
        if target:
            transitions.append(ExecutionTransition(source, target, "CALL", file, item.lineno, "INFERRED", "python-ast", metadata={"expression": ast.unparse(item)[:240]}))
