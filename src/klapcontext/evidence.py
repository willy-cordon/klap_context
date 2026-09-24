"""Small, serializable evidence records shared by every analyzer."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Evidence:
    source_type: str
    path: str
    reason: str
    status: str = "CONFIRMED"
    confidence: float = 1.0
    line: int | None = None
    symbol: str | None = None
    snippet: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def from_match(root: Path, path: Path, match_start: int, reason: str, *, symbol: str | None = None, status: str = "CONFIRMED", confidence: float | None = None) -> Evidence:
    """Create evidence anchored to one source line; snippets never include env files."""
    text = path.read_text(encoding="utf-8", errors="replace")
    line = text.count("\n", 0, match_start) + 1
    snippet = None
    if not path.name.startswith(".env"):
        snippet = text.splitlines()[line - 1].strip()[:240]
    return Evidence(
        "source",
        str(path.relative_to(root)),
        reason,
        status,
        confidence if confidence is not None else (1.0 if status == "CONFIRMED" else 0.7),
        line,
        symbol,
        snippet,
    )
