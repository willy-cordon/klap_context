"""Translate Serena's public MCP tools to KlapContext capability contracts."""
from __future__ import annotations

import ast
import atexit
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

from ..contracts import Capability
from ..models import Confidence, Evidence, ProviderIdentity, ProviderResult, ResultState, SourceLocation, SymbolIdentity
from .client import READ_ONLY_TOOLS, SerenaMcpClient
from .config import SerenaSettings


_TOOL_CAPABILITIES = {
    "find_symbol": {Capability.SYMBOL_LOOKUP},
    "get_symbols_overview": {Capability.SYMBOL_LOOKUP},
    "find_declaration": {Capability.SYMBOL_LOOKUP},
    "find_referencing_symbols": {Capability.REFERENCES, Capability.IMPACT_ANALYSIS},
    "find_implementations": {Capability.IMPLEMENTATIONS},
}


class SerenaProvider:
    name = "serena"
    capabilities = frozenset({
        Capability.SYMBOL_LOOKUP,
        Capability.REFERENCES,
        Capability.IMPLEMENTATIONS,
        Capability.IMPACT_ANALYSIS,
    })

    def __init__(self, root: Path, settings: SerenaSettings, *, client: SerenaMcpClient | None = None):
        self.root = Path(root).resolve(strict=True)
        self.settings = settings
        self._client = client or SerenaMcpClient(self.root, settings)
        self._tools: dict[str, dict[str, Any]] | None = None
        self._version: str | None = None
        self.discovery_error: str | None = None
        atexit.register(self.close)

    def close(self) -> None:
        self._client.close()

    def is_available(self, request: Any = None) -> bool:
        return self.settings.eligible

    def capabilities_for(self, request: Any = None) -> set[Capability]:
        try:
            tools = self._discover_tools()
            self.discovery_error = None
        except Exception as error:
            self.discovery_error = f"{type(error).__name__}: {error}"
            return set()
        return {capability for name in tools for capability in _TOOL_CAPABILITIES.get(name, set())}

    def version(self) -> str | None:
        if self._version is not None:
            return self._version
        try:
            completed = subprocess.run(
                [self.settings.command, "--version"],
                cwd=self.root,
                text=True,
                capture_output=True,
                timeout=min(self.settings.timeout_seconds, 5.0),
                check=False,
            )
            output = (completed.stdout or completed.stderr).strip()
            self._version = output.rsplit(" ", 1)[-1] if completed.returncode == 0 and output else None
        except (OSError, subprocess.SubprocessError):
            self._version = None
        return self._version

    def probe(self) -> dict[str, Any]:
        tools = self._discover_tools()
        from ...detector import detect_project
        stack, _ = detect_project(self.root)
        languages = list(dict.fromkeys("TypeScript" if value == "JavaScript" else value for value in stack.get("languages", [])))
        return {
            "startable": True,
            "server": dict(self._client.server_info),
            "tools": sorted(tools),
            "capabilities": sorted(item.value for item in self.capabilities_for()),
            "languages": languages,
            "error": None,
            "missing_dependencies": [],
        }

    def find_symbols(self, request: Any) -> ProviderResult:
        request = request or {}
        operation = request.get("operation", "lookup")
        relative_path = self._relative_path(request.get("path") or request.get("relative_path"), required=operation == "overview")
        if operation == "overview":
            if "get_symbols_overview" not in self._discover_tools():
                return self._unsupported("get_symbols_overview")
            raw = self._call("get_symbols_overview", {
                "relative_path": relative_path,
                "depth": min(max(int(request.get("depth", 1)), 0), 3),
                "max_answer_chars": self._answer_limit(request),
            })
            values = self._normalize_overview(raw, relative_path)
            return self._result(values, limitations=["Overview reports declarations, not runtime reachability."])

        query = request.get("symbol") or request.get("query")
        if not query:
            return ProviderResult(ResultState.UNKNOWN, provider=self._identity(), error="symbol/query is required")
        if "find_symbol" not in self._discover_tools():
            return self._unsupported("find_symbol")
        raw = self._call("find_symbol", {
            "name_path_pattern": str(query),
            "relative_path": relative_path or "",
            "depth": min(max(int(request.get("depth", 0)), 0), 3),
            "include_body": bool(request.get("include_body", operation == "definition")),
            "include_info": True,
            "substring_matching": bool(request.get("substring_matching", True)),
            "max_answer_chars": self._answer_limit(request),
        })
        values = self._normalize_symbols(raw, limit=self._result_limit(request))
        if operation == "definition":
            values = [item for item in values if item.kind.casefold() not in {"file", "module"}]
        return self._result(values)

    def find_references(self, request: Any) -> ProviderResult:
        if "find_referencing_symbols" not in self._discover_tools():
            return self._unsupported("find_referencing_symbols")
        definitions = self._definitions(request)
        if definitions.state not in {ResultState.OK, ResultState.NO_RESULTS}:
            return definitions
        references: list[dict[str, Any]] = []
        for symbol in definitions.data or []:
            location = symbol.location
            if not location:
                continue
            raw = self._call("find_referencing_symbols", {
                "name_path": symbol.qualified_name or symbol.name,
                "relative_path": location.path,
                "include_info": True,
                "max_answer_chars": self._answer_limit(request),
            })
            for item in self._normalize_fact_dicts(raw, "reference", limit=self._result_limit(request)):
                item["referenced_symbol"] = symbol.qualified_name or symbol.name
                item["verified"] = True
                item["impact"] = "inferred_from_verified_reference"
                references.append(item)
        return self._result(
            self._deduplicate(references),
            limitations=["References are verified by Serena/LSP; behavioral impact remains inferred."],
        )

    def find_implementations(self, request: Any) -> ProviderResult:
        if "find_implementations" not in self._discover_tools():
            return self._unsupported("find_implementations")
        definitions = self._definitions(request)
        if definitions.state not in {ResultState.OK, ResultState.NO_RESULTS}:
            return definitions
        implementations: list[dict[str, Any]] = []
        for symbol in definitions.data or []:
            if not symbol.location:
                continue
            raw = self._call("find_implementations", {
                "name_path": symbol.qualified_name or symbol.name,
                "relative_path": symbol.location.path,
                "include_info": True,
                "max_answer_chars": self._answer_limit(request),
            })
            implementations.extend(self._normalize_fact_dicts(raw, "implementation", limit=self._result_limit(request)))
        return self._result(self._deduplicate(implementations))

    def impact(self, request: Any) -> ProviderResult:
        references = self.find_references(request)
        if references.state not in {ResultState.OK, ResultState.NO_RESULTS}:
            return references
        symbol = (request or {}).get("symbol") or (request or {}).get("query")
        value = {
            "symbol": symbol,
            "verified_references": references.data or [],
            "direct_callers": [
                {
                    "source_symbol": item.get("qualified_name") or item.get("name"),
                    "file": item.get("path"),
                    "line": item.get("line"),
                    "confidence": Confidence.CONFIRMED.value,
                    "provider": self.name,
                }
                for item in references.data or []
            ],
            "consumers": references.data or [],
            "relationship_paths": [],
            "indirect_callers": [],
            "related_tests": [item.get("path") for item in references.data or [] if "test" in str(item.get("path", "")).casefold()],
            "impact": [
                {
                    "path": item.get("path"),
                    "line": item.get("line"),
                    "symbol": item.get("qualified_name") or item.get("name"),
                    "status": "INFERRED",
                    "reason": "The symbol contains a Serena-verified reference; runtime breakage is not proven.",
                }
                for item in references.data or []
            ],
        }
        return ProviderResult(
            references.state,
            value,
            self._identity(),
            confidence=Confidence.INFERRED,
            evidence=references.evidence,
            limitations=["Reference existence is verified; impact severity and runtime execution are inferred."],
        )

    def _definitions(self, request: Any) -> ProviderResult:
        scoped = dict(request or {})
        scoped["operation"] = "definition"
        scoped.setdefault("include_body", False)
        result = self.find_symbols(scoped)
        if isinstance(result.data, list):
            result.data = [item for item in result.data if str(getattr(item, "kind", "")).casefold() not in {"file", "module"}]
            result.state = ResultState.OK if result.data else ResultState.NO_RESULTS
        return result

    def _discover_tools(self) -> dict[str, dict[str, Any]]:
        if self._tools is None:
            self._tools = {name: schema for name, schema in self._client.list_tools().items() if name in READ_ONLY_TOOLS}
        return self._tools

    def _call(self, name: str, arguments: dict[str, Any]) -> Any:
        schema = self._discover_tools().get(name, {}).get("inputSchema", {})
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        filtered = {key: value for key, value in arguments.items() if key in properties and value is not None}
        return self._parse(self._client.call(name, filtered))

    @staticmethod
    def _parse(value: Any) -> Any:
        if isinstance(value, dict) and set(value) == {"result"}:
            return SerenaProvider._parse(value["result"])
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return []
        for parser in (json.loads, ast.literal_eval):
            try:
                return parser(text)
            except (ValueError, SyntaxError, json.JSONDecodeError):
                pass
        return {"content": text}

    def _relative_path(self, value: Any, *, required: bool = False) -> str | None:
        if value in {None, ""}:
            if required:
                raise ValueError("A project-relative path is required")
            return None
        candidate = Path(str(value))
        resolved = (self.root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        try:
            relative = resolved.relative_to(self.root)
        except ValueError as error:
            raise ValueError("Path must stay within the project root") from error
        return relative.as_posix()

    def _safe_location(self, item: dict[str, Any]) -> SourceLocation | None:
        path_value = item.get("relative_path") or item.get("path") or item.get("file")
        if not path_value:
            return None
        try:
            path = self._relative_path(path_value, required=True)
        except ValueError:
            return None
        region = item.get("body_location") or item.get("location") or {}
        if not isinstance(region, dict):
            region = {}
        start = region.get("start_line", item.get("line"))
        end = region.get("end_line", item.get("end_line"))
        line = item.get("line_one_based")
        return SourceLocation(path or "", int(line) if line is not None else self._line(start), self._line(end))

    @staticmethod
    def _line(value: Any) -> int | None:
        if value is None:
            return None
        try:
            # Serena/LSP locations are zero-based; KlapContext's public model is
            # one-based like editors and source listings.
            return int(value) + 1
        except (TypeError, ValueError):
            return None

    def _normalize_symbols(self, raw: Any, *, limit: int) -> list[SymbolIdentity]:
        values = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
        symbols: list[SymbolIdentity] = []
        for index, item in enumerate(values[:limit]):
            if not isinstance(item, dict):
                continue
            location = self._safe_location(item)
            if item.get("relative_path") and location is None:
                continue
            qualified = str(item.get("name_path") or item.get("qualified_name") or item.get("name") or "")
            name = qualified.rsplit("/", 1)[-1] if qualified else ""
            if not name:
                continue
            excerpt = item.get("body") or item.get("content") or item.get("info")
            evidence = (Evidence("Serena MCP semantic result", location, str(excerpt)[:2000] if excerpt else None),)
            symbols.append(SymbolIdentity(
                f"serena:{location.path if location else ''}:{qualified}:{location.line if location else index}",
                name,
                str(item.get("kind") or item.get("type") or "symbol"),
                qualified,
                None,
                location,
                self._identity(),
                evidence,
                Confidence.CONFIRMED,
                ("Static language-server result; runtime execution is not implied.",),
            ))
        return symbols

    def _normalize_overview(self, raw: Any, relative_path: str | None) -> list[SymbolIdentity]:
        flattened: list[dict[str, Any]] = []

        def visit(value: Any, parent: str = "") -> None:
            if isinstance(value, list):
                for item in value:
                    visit(item, parent)
            elif isinstance(value, dict):
                if "name_path" in value or "body_location" in value:
                    item = dict(value); item.setdefault("relative_path", relative_path); flattened.append(item)
                else:
                    for kind, children in value.items():
                        if isinstance(children, (list, dict)):
                            visit(children, str(kind))
                        elif isinstance(children, str):
                            flattened.append({"name_path": children, "kind": parent or kind, "relative_path": relative_path})
            elif isinstance(value, str):
                flattened.append({"name_path": value, "kind": parent or "symbol", "relative_path": relative_path})

        visit(raw)
        return self._normalize_symbols(flattened, limit=self.settings.max_results)

    def _normalize_fact_dicts(self, raw: Any, kind: str, *, limit: int) -> list[dict[str, Any]]:
        flattened: list[dict[str, Any]] = []

        def visit(value: Any, path: str | None = None, reported_kind: str | None = None) -> None:
            if isinstance(value, list):
                for child in value:
                    visit(child, path, reported_kind)
                return
            if not isinstance(value, dict):
                return
            if "name_path" in value or "body_location" in value:
                item = dict(value)
                if path:
                    item.setdefault("relative_path", path)
                if reported_kind:
                    item.setdefault("kind", reported_kind)
                excerpt = item.get("content_around_reference")
                if excerpt:
                    item.setdefault("content", excerpt)
                    match = re.search(r"^\s*>\s*(\d+):", str(excerpt), re.MULTILINE)
                    if match:
                        item["line_one_based"] = int(match.group(1))
                flattened.append(item)
                return
            for key, child in value.items():
                next_path = path
                next_kind = reported_kind
                if any(str(key).casefold().endswith(suffix) for suffix in (".php", ".js", ".jsx", ".ts", ".tsx", ".py", ".java", ".go", ".rs")):
                    next_path = str(key)
                else:
                    next_kind = str(key)
                visit(child, next_path, next_kind)

        visit(raw)
        symbols = self._normalize_symbols(flattened, limit=limit)
        return [
            {
                "id": symbol.id,
                "name": symbol.name,
                "qualified_name": symbol.qualified_name,
                "kind": kind,
                "path": symbol.location.path if symbol.location else None,
                "line": symbol.location.line if symbol.location else None,
                "end_line": symbol.location.end_line if symbol.location else None,
                "provider": self.name,
                "confidence": Confidence.CONFIRMED.value,
                "evidence": [
                    {
                        "source": evidence.source,
                        "location": {
                            "path": evidence.location.path,
                            "line": evidence.location.line,
                            "end_line": evidence.location.end_line,
                        } if evidence.location else None,
                        "excerpt": evidence.excerpt,
                    }
                    for evidence in symbol.evidence
                ],
                "limitations": list(symbol.limitations),
            }
            for symbol in symbols
        ]

    def _identity(self) -> ProviderIdentity:
        return ProviderIdentity(self.name, self.version(), self.__class__.__name__)

    def _result(self, values: list[Any], *, limitations: Iterable[str] = ()) -> ProviderResult:
        evidence: list[Evidence] = []
        for value in values:
            if isinstance(value, SymbolIdentity):
                evidence.extend(value.evidence)
        return ProviderResult(
            ResultState.OK if values else ResultState.NO_RESULTS,
            values,
            self._identity(),
            evidence=evidence,
            confidence=Confidence.CONFIRMED,
            limitations=list(limitations),
        )

    def _unsupported(self, tool: str) -> ProviderResult:
        return ProviderResult(
            ResultState.UNSUPPORTED,
            [],
            self._identity(),
            error=f"Serena did not advertise {tool} in tools/list",
            limitations=[f"Capability unavailable because Serena tool {tool} is absent."],
        )

    def _result_limit(self, request: Any) -> int:
        return min(max(int((request or {}).get("max_results", self.settings.max_results)), 1), self.settings.max_results)

    def _answer_limit(self, request: Any) -> int:
        return min(max(int((request or {}).get("max_answer_chars", self.settings.max_answer_chars)), 100), self.settings.max_answer_chars)

    @staticmethod
    def _deduplicate(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[Any, ...]] = set()
        result = []
        for value in values:
            key = (value.get("qualified_name"), value.get("path"), value.get("line"), value.get("kind"))
            if key not in seen:
                seen.add(key); result.append(value)
        return result
