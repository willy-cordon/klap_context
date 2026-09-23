from __future__ import annotations
from dataclasses import asdict, dataclass

@dataclass(frozen=True)
class Evidence:
    source_type: str
    path: str
    reason: str
    status: str = "CONFIRMED"
    confidence: float = 1.0
    def as_dict(self): return asdict(self)
