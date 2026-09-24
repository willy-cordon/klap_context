"""Useful PHP semantics when no framework adapter applies."""
from __future__ import annotations

from pathlib import Path

from ..evidence import Evidence
from ..providers.code_intelligence import PhpCodeIntelligenceProvider
from ..semantic import EntryPoint, ExecutionTransition, SemanticComponent, SemanticModel


def _evidence(file: str, line: int, symbol: str, reason: str, status: str = "CONFIRMED") -> list[dict]:
    return [Evidence("code", file, reason, status, 1.0 if status == "CONFIRMED" else .7, line=line, symbol=symbol).as_dict()]


class GenericPhpAdapter:
    """Language fallback: symbols and structural calls remain valuable alone."""

    name = "generic-php"

    def detect(self, root: Path) -> bool:
        return any(root.rglob("*.php"))

    def analyze(self, root: Path) -> SemanticModel:
        provider = PhpCodeIntelligenceProvider(root)
        index = provider.index()
        components = [SemanticComponent(item["qualified_name"], item["type"], item["file"], item["qualified_name"], evidence=_evidence(item["file"], item["start_line"], item["qualified_name"], "Símbolo PHP detectado")) for item in index["symbols"]]
        transitions = [ExecutionTransition(item["source_symbol"], item["target_symbol"], "CALL" if item["relation"] == "CALLS" else item["relation"], item["file"], item["line"], item["confidence"], item["provider"], _evidence(item["file"], item["line"], item["source_symbol"], "Relación estructural PHP", item["confidence"]), item.get("metadata", {})) for item in index["relations"]]
        entries = []
        for item in index["symbols"]:
            if item["type"] == "function" and item["name"].casefold() == "main":
                entries.append(EntryPoint("FUNCTION", item["qualified_name"], item["qualified_name"], file=item["file"], line=item["start_line"], status="INFERRED", evidence=_evidence(item["file"], item["start_line"], item["qualified_name"], "Función main heurística", "INFERRED")))
        return SemanticModel("PHP", None, "GENERIC", components, entries, transitions, metadata={"provider": provider.name})
