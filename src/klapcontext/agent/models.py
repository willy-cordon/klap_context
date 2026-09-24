"""Small serializable model for the future context compiler."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AgentContextPlan:
    query: str
    intent: str
    confidence: float
    area: str
    detail: str
    max_tokens: int
    capabilities: list[str]
    providers: list[dict]
    sections: list[str]
    strategy: str

    def as_dict(self) -> dict:
        return asdict(self)
