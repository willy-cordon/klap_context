"""Local PHP code intelligence backed by Tree-sitter, never an external MCP."""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..scope import IndexScope


EXCLUDED = {".git", ".klap", "vendor", "node_modules", "build", "dist", ".venv", "venv", ".test-venv"}
INDEX_VERSION = 7


@dataclass(frozen=True)
class CodeSymbol:
    id: str
    name: str
    qualified_name: str
    type: str
    file: str
    start_line: int
    end_line: int
    namespace: str | None = None
    parent: str | None = None
    visibility: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CodeRelation:
    source_symbol: str
    target_symbol: str
    relation: str
    file: str
    line: int
    confidence: str
    provider: str = "php-tree-sitter"
    metadata: dict = field(default_factory=dict)


def available() -> bool:
    try:
        import tree_sitter  # noqa: F401
        import tree_sitter_php  # noqa: F401
        return True
    except ImportError:
        return False


def _line(source: bytes, offset: int) -> int:
    return source.count(b"\n", 0, offset) + 1


def _text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _descendants(node):
    yield node
    for child in node.children:
        yield from _descendants(child)


def _first(node, kind: str):
    return next((child for child in node.children if child.type == kind), None)


def _field_text(node, field: str, source: bytes) -> str | None:
    child = node.child_by_field_name(field)
    return _text(child, source) if child else None


def _imports(values: list[str]) -> dict[str, str]:
    result = {}
    for value in values:
        cleaned = value.strip().lstrip("\\")
        alias_match = re.match(r"(.+?)\s+as\s+(\w+)$", cleaned, re.I)
        qualified = alias_match.group(1).strip() if alias_match else cleaned
        alias = alias_match.group(2) if alias_match else qualified.rsplit("\\", 1)[-1]
        result[alias] = qualified
    return result


def _qualify(value: str, namespace: str | None, imports: dict[str, str]) -> str:
    value = value.strip().lstrip("\\")
    if not value or value.casefold() in {"self", "static", "parent"}:
        return value
    first, *rest = value.split("\\")
    if first in imports:
        return "\\".join([imports[first], *rest])
    return f"{namespace}\\{value}" if namespace and "\\" not in value else value


class PhpCodeIntelligenceProvider:
    """Indexes declarations and conservative structural relationships in PHP."""
    name = "php-tree-sitter"

    def __init__(self, root: Path, scope: IndexScope | None = None):
        self.root = root.resolve()
        self.scope = scope
        self.cache_file = self.root / ".klap" / "code-intelligence" / "php-index.json"
        self._index: dict | None = None

    def _files(self) -> list[Path]:
        if self.scope is not None:
            return sorted(self.root / path for path in self.scope.included_paths if path.casefold().endswith(".php"))
        files = []
        for directory, children, names in os.walk(self.root):
            children[:] = [child for child in children if child not in EXCLUDED]
            files.extend(Path(directory) / name for name in names if name.endswith(".php"))
        return sorted(files)

    def _fingerprint(self, files: list[Path]) -> str:
        value = "|".join(f"{path.relative_to(self.root)}:{path.stat().st_mtime_ns}:{path.stat().st_size}" for path in files)
        return hashlib.sha256(value.encode()).hexdigest()

    def index(self) -> dict:
        files = self._files()
        fingerprint = self._fingerprint(files)
        if self.cache_file.exists():
            try:
                cached = json.loads(self.cache_file.read_text(encoding="utf-8"))
                if cached.get("fingerprint") == fingerprint and cached.get("index_version") == INDEX_VERSION:
                    self._index = cached
                    return cached
            except (OSError, json.JSONDecodeError):
                pass
        parsed = [self._parse(path) for path in files]
        symbols = [symbol for item in parsed for symbol in item["symbols"]]
        relations = [relation for item in parsed for relation in item["relations"]]
        result = {"provider": self.name, "index_version": INDEX_VERSION, "fingerprint": fingerprint, "symbols": symbols, "relations": relations}
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        self._index = result
        return result

    def _parse(self, path: Path) -> dict:
        from tree_sitter import Language, Parser
        import tree_sitter_php

        source = path.read_bytes()
        tree = Parser(Language(tree_sitter_php.language_php())).parse(source)
        relative = path.relative_to(self.root).as_posix()
        namespace = next((_text(node.child_by_field_name("name"), source) for node in _descendants(tree.root_node) if node.type == "namespace_definition" and node.child_by_field_name("name")), None)
        imports = [_text(node, source).replace("use ", "").replace(";", "").strip() for node in _descendants(tree.root_node) if node.type == "namespace_use_clause"]
        import_map = _imports(imports)
        symbols, relations = [], []
        for declaration in _descendants(tree.root_node):
            if declaration.type not in {"class_declaration", "interface_declaration", "trait_declaration"}:
                continue
            name = _field_text(declaration, "name", source)
            if not name:
                continue
            kind = {"class_declaration": "class", "interface_declaration": "interface", "trait_declaration": "trait"}[declaration.type]
            qualified = f"{namespace}\\{name}" if namespace else name
            symbol = CodeSymbol(qualified, name, qualified, kind, relative, _line(source, declaration.start_byte), _line(source, declaration.end_byte), namespace, metadata={"imports": imports})
            symbols.append(asdict(symbol))
            for child in declaration.children:
                if child.type == "base_clause":
                    relations.append(asdict(CodeRelation(qualified, _qualify(_text(child, source).replace("extends", "").strip(), namespace, import_map), "EXTENDS", relative, _line(source, child.start_byte), "CONFIRMED")))
                if child.type == "class_interface_clause":
                    for target in [part.strip() for part in _text(child, source).replace("implements", "").split(",")]:
                        relations.append(asdict(CodeRelation(qualified, _qualify(target, namespace, import_map), "IMPLEMENTS", relative, _line(source, child.start_byte), "CONFIRMED")))
            properties = self._properties(declaration, source)
            properties.update(self._constructor_properties(declaration, source))
            properties = {name: _qualify(type_name, namespace, import_map) for name, type_name in properties.items()}
            for property_name, type_name in properties.items():
                relations.append(asdict(CodeRelation(qualified, type_name, "INJECTS", relative, _line(source, declaration.start_byte), "CONFIRMED", metadata={"property": property_name})))
            for method in (node for node in _descendants(declaration) if node.type == "method_declaration"):
                method_name = _field_text(method, "name", source)
                if not method_name:
                    continue
                method_id = f"{qualified}::{method_name}"
                visibility = next((_text(child, source) for child in method.children if child.type == "visibility_modifier"), None)
                method_symbol = CodeSymbol(method_id, method_name, method_id, "constructor" if method_name == "__construct" else "method", relative, _line(source, method.start_byte), _line(source, method.end_byte), namespace, qualified, visibility)
                symbols.append(asdict(method_symbol))
                if method_name == "handle":
                    event_type = re.search(r"function\s+handle\s*\(\s*([A-Za-z_]\w*(?:\\[A-Za-z_]\w*)*)\s+\$", _text(method, source))
                    if event_type:
                        relations.append(asdict(CodeRelation(qualified, _qualify(event_type.group(1), namespace, import_map), "LISTENS_TO", relative, _line(source, method.start_byte), "CONFIRMED")))
                relations.extend(self._calls(method, source, method_id, relative, properties, namespace, import_map))
        for function in (node for node in _descendants(tree.root_node) if node.type == "function_definition"):
            name = _field_text(function, "name", source)
            if name:
                qualified = f"{namespace}\\{name}" if namespace else name
                symbols.append(asdict(CodeSymbol(qualified, name, qualified, "function", relative, _line(source, function.start_byte), _line(source, function.end_byte), namespace)))
                relations.extend(self._calls(function, source, qualified, relative, {}, namespace, import_map))
        return {"symbols": symbols, "relations": relations}

    def _properties(self, declaration, source: bytes) -> dict[str, str]:
        values = {}
        for node in _descendants(declaration):
            if node.type != "property_promotion_parameter":
                continue
            variable = _field_text(node, "name", source)
            type_name = _field_text(node, "type", source)
            if variable and type_name:
                values[variable.lstrip("$")] = type_name.split("\\")[-1]
        return values

    def _constructor_properties(self, declaration, source: bytes) -> dict[str, str]:
        """Map classic constructor injection (``$this->x = $x``) to its type.

        Lumen and older Laravel applications commonly use this form instead of
        PHP 8 property promotion.  It is deliberately conservative: only a
        typed constructor parameter assigned directly to a ``$this`` property
        is resolved.
        """
        text = _text(declaration, source)
        constructor = re.search(r"function\s+__construct\s*\((.*?)\)\s*\{(.*?)\}", text, re.S)
        if not constructor:
            return {}
        parameters = {
            variable: type_name.split("\\")[-1]
            for type_name, variable in re.findall(r"(?:public|protected|private)?\s*([A-Za-z_]\w*(?:\\[A-Za-z_]\w*)*)\s+\$(\w+)", constructor.group(1))
        }
        return {
            property_name: parameters[variable]
            for property_name, variable in re.findall(r"\$this->(\w+)\s*=\s*\$(\w+)\s*;", constructor.group(2))
            if variable in parameters
        }

    def _calls(self, method, source: bytes, source_id: str, file: str, properties: dict[str, str], namespace: str | None, imports: dict[str, str]) -> list[dict]:
        relations = []
        for node in _descendants(method):
            target, relation, confidence = None, "CALLS", "INFERRED"
            if node.type == "scoped_call_expression":
                scope = _field_text(node, "scope", source) or ""
                scope = source_id.rsplit("::", 1)[0] if scope.casefold() in {"self", "static"} else _qualify(scope, namespace, imports)
                called = _field_text(node, "name", source)
                if called in {"dispatch", "dispatchSync", "dispatchNow"}:
                    target = scope
                    relation = "DISPATCHES"
                else:
                    target = f"{scope}::{called}"
                confidence = "CONFIRMED"
            elif node.type == "member_call_expression":
                name = _field_text(node, "name", source)
                object_node = node.child_by_field_name("object")
                object_text = _text(object_node, source) if object_node else ""
                if object_text == "$this":
                    target = f"{source_id.rsplit('::', 1)[0]}::{name}"
                elif object_text.startswith("$this->"):
                    service = object_text.split("->", 1)[1]
                    target = f"{properties.get(service, service)}::{name}"
                elif object_text.startswith("$"):
                    target = f"{object_text[1:]}::{name}"
                confidence = "INFERRED"
            elif node.type == "object_creation_expression":
                target = _field_text(node, "name", source) or (_text(_first(node, "name"), source) if _first(node, "name") else None)
                target = _qualify(target, namespace, imports) if target else None
                relation = "INSTANTIATES"; confidence = "CONFIRMED"
            elif node.type == "function_call_expression":
                function = _field_text(node, "function", source) or _field_text(node, "name", source)
                expression = _text(node, source)
                if function and function.casefold() in {"event", "dispatch"}:
                    created = re.search(r"new\s+([A-Za-z_]\w*(?:\\[A-Za-z_]\w*)*)", expression)
                    if created:
                        target = _qualify(created.group(1), namespace, imports)
                        relation = "DISPATCHES"
                        confidence = "CONFIRMED"
            if target and "None" not in target:
                relations.append(asdict(CodeRelation(source_id, target, relation, file, _line(source, node.start_byte), confidence, metadata={"expression": _text(node, source)[:240]})))
        return relations

    def _symbols(self) -> list[dict]: return self.index()["symbols"]
    def _relations(self) -> list[dict]: return self.index()["relations"]

    def find_symbol(self, query: str) -> list[dict]:
        value = query.replace("\\", "\\").casefold()
        return [symbol for symbol in self._symbols() if symbol["qualified_name"].casefold().endswith(value) or symbol["name"].casefold() == value][:20]

    def callers(self, symbol: str) -> list[dict]:
        return [relation for relation in self._relations() if relation["relation"] == "CALLS" and relation["target_symbol"].endswith(symbol)][:100]

    def consumers(self, symbol: str) -> list[dict]:
        classes = {"CALLS": "direct", "INSTANTIATES": "direct", "DISPATCHES": "event", "LISTENS_TO": "event", "INJECTS": "dependency", "EXTENDS": "dependency", "IMPLEMENTS": "dependency"}
        result = []
        for relation in self._relations():
            if relation["target_symbol"].endswith(symbol):
                item = dict(relation)
                item["consumer_type"] = classes.get(item["relation"], "possible")
                item["explanation"] = f"{item['source_symbol']} --{item['relation']}--> {item['target_symbol']}"
                result.append(item)
        return result[:100]

    @staticmethod
    def _same_symbol(candidate: str, symbol: str) -> bool:
        return candidate == symbol or candidate.endswith("\\" + symbol) or candidate.endswith("::" + symbol) or symbol.endswith(candidate)

    def relationship_paths(self, symbol: str, *, depth: int = 4, max_paths: int = 50) -> list[dict]:
        """Trace evidence-backed reverse dependencies with event semantics."""
        relations = self._relations()
        paths, queue = [], [(symbol, [], 0, {symbol})]
        while queue and len(paths) < max_paths:
            current, path, level, visited = queue.pop(0)
            if level >= depth:
                continue
            # Normal reverse dependency: source relies on current target.
            candidates = [item for item in relations if self._same_symbol(item["target_symbol"], current)]
            # LISTENS_TO is represented listener -> event. Once a listener is a
            # consumer, walk to its event so dispatchers can be found next.
            candidates += [item for item in relations if item["relation"] == "LISTENS_TO" and self._same_symbol(item["source_symbol"], current)]
            for relation in candidates:
                next_symbol = relation["target_symbol"] if relation["relation"] == "LISTENS_TO" and self._same_symbol(relation["source_symbol"], current) else relation["source_symbol"]
                if any(self._same_symbol(next_symbol, item) for item in visited):
                    continue
                step = {"source": relation["source_symbol"], "target": relation["target_symbol"], "relation": relation["relation"], "file": relation["file"], "line": relation["line"], "confidence": relation["confidence"]}
                next_path = [*path, step]
                paths.append({"from": next_symbol, "to": symbol, "classification": "direct" if level == 0 else "transitive", "relations": next_path})
                queue.append((next_symbol, next_path, level + 1, {*visited, next_symbol}))
        return paths

    def callees(self, symbol: str) -> list[dict]:
        return [relation for relation in self._relations() if relation["source_symbol"].endswith(symbol)][:100]

    def call_graph(self, symbol: str, *, depth: int = 3, max_nodes: int = 50) -> dict:
        root = next((item["qualified_name"] for item in self.find_symbol(symbol)), symbol)
        edges, visited, queue = [], {root}, [(root, 0)]
        while queue and len(visited) < max_nodes:
            current, level = queue.pop(0)
            if level >= depth: continue
            for relation in self.callees(current):
                edges.append(relation)
                target = relation["target_symbol"]
                if target not in visited:
                    visited.add(target); queue.append((target, level + 1))
        return {"root": root, "nodes": sorted(visited), "edges": edges, "depth": depth, "truncated": len(visited) >= max_nodes}

    def impact(self, symbol: str) -> dict:
        consumers = self.consumers(symbol)
        direct = [item for item in consumers if item["consumer_type"] == "direct"]
        indirect, seen, queue = [], {symbol}, [item["source_symbol"] for item in direct]
        while queue and len(indirect) < 50:
            current = queue.pop(0)
            if current in seen: continue
            seen.add(current); indirect.append(current)
            queue.extend(item["source_symbol"] for item in self.callers(current))
        name = symbol.split("::")[0].split("\\")[-1]
        source_files = {item["source_symbol"] for item in self._relations() if item["target_symbol"].endswith(name)}
        tests = [item["file"] for item in self._symbols() if item["qualified_name"] in source_files and "test" in item["file"].casefold()]
        return {"symbol": symbol, "direct_callers": direct, "consumers": consumers, "relationship_paths": self.relationship_paths(symbol), "indirect_callers": indirect, "related_tests": sorted(set(tests)), "statement": "Relaciones estructurales potencialmente afectadas; no es una predicción de fallas."}

    def minimal_edit_context(self, symbol: str, *, max_tokens: int = 1200) -> dict:
        match = next(iter(self.find_symbol(symbol)), None)
        if not match: return {"symbol": symbol, "status": "UNKNOWN", "reason": "Símbolo no encontrado"}
        path = self.root / match["file"]
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        source = "\n".join(lines[match["start_line"] - 1:match["end_line"]])[:max_tokens * 4]
        parent = next((item for item in self._symbols() if item["qualified_name"] == match.get("parent")), None)
        return {"symbol": match, "source": source, "class": parent, "imports": (parent or {}).get("metadata", {}).get("imports", []), "callees": self.callees(match["qualified_name"]), "callers": self.callers(match["qualified_name"]), "impact": self.impact(match["qualified_name"]), "token_budget": max_tokens}
