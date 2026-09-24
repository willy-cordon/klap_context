"""Tree-sitter structural facts for JavaScript and TypeScript."""
from __future__ import annotations

from pathlib import Path

from ..semantic import ExecutionTransition, SemanticComponent


def _walk(node):
    yield node
    for child in node.children: yield from _walk(child)


def _text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def analyze(root: Path) -> tuple[list[SemanticComponent], list[ExecutionTransition]]:
    from tree_sitter import Language, Parser
    import tree_sitter_javascript, tree_sitter_typescript
    components, transitions = [], []
    for path in sorted([*root.rglob("*.js"), *root.rglob("*.ts")]):
        if any(part in {".git", ".klap", "node_modules", "dist", "build"} for part in path.relative_to(root).parts): continue
        source = path.read_bytes(); relative = path.relative_to(root).as_posix()
        grammar = tree_sitter_typescript.language_typescript() if path.suffix == ".ts" else tree_sitter_javascript.language()
        tree = Parser(Language(grammar)).parse(source); module = relative.rsplit(".", 1)[0].replace("/", ".")
        for node in _walk(tree.root_node):
            if node.type not in {"class_declaration", "function_declaration", "method_definition"}: continue
            name_node = node.child_by_field_name("name") or next((item for item in node.children if item.type in {"identifier", "property_identifier", "type_identifier"}), None)
            if not name_node: continue
            name = _text(name_node, source); qualified = f"{module}.{name}"
            kind = "class" if node.type == "class_declaration" else ("method" if node.type == "method_definition" else "function")
            components.append(SemanticComponent(qualified, kind, relative, qualified, evidence=[]))
            for call in _walk(node):
                if call.type != "call_expression": continue
                function = call.child_by_field_name("function")
                if function: transitions.append(ExecutionTransition(qualified, _text(function, source), "CALL", relative, call.start_point[0] + 1, "INFERRED", "js-tree-sitter"))
    return components, transitions
