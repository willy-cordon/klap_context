"""Provider-neutral analysis values and explicit result states."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar


class ResultState(str, Enum):
    """The semantic outcome of a provider call, independent of transport errors."""

    OK = "OK"
    NO_RESULTS = "NO_RESULTS"
    UNSUPPORTED = "UNSUPPORTED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    UNKNOWN = "UNKNOWN"


class Confidence(str, Enum):
    CONFIRMED = "CONFIRMED"
    HIGH = "HIGH"
    INFERRED = "INFERRED"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ProviderIdentity:
    name: str
    version: str | None = None
    adapter: str | None = None


@dataclass(frozen=True)
class SourceLocation:
    path: str
    line: int | None = None
    end_line: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class Evidence:
    source: str
    location: SourceLocation | None = None
    excerpt: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class SymbolIdentity:
    id: str
    name: str
    kind: str
    qualified_name: str | None = None
    language: str | None = None
    location: SourceLocation | None = None
    provider: ProviderIdentity | None = None
    evidence: tuple[Evidence, ...] = ()
    confidence: Confidence = Confidence.UNKNOWN
    limitations: tuple[str, ...] = ()
    state: ResultState = ResultState.OK


@dataclass(frozen=True)
class StructuralRelation:
    source: str
    target: str
    kind: str
    location: SourceLocation | None = None
    provider: ProviderIdentity | None = None
    evidence: tuple[Evidence, ...] = ()
    confidence: Confidence = Confidence.UNKNOWN
    limitations: tuple[str, ...] = ()
    state: ResultState = ResultState.OK


T = TypeVar("T")


@dataclass
class ProviderResult(Generic[T]):
    state: ResultState
    data: T | None = None
    provider: ProviderIdentity | None = None
    evidence: list[Evidence] = field(default_factory=list)
    confidence: Confidence = Confidence.UNKNOWN
    limitations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    elapsed_ms: float | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return self.state in {ResultState.OK, ResultState.NO_RESULTS}

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["state"] = self.state.value
        value["confidence"] = self.confidence.value
        return value

    @classmethod
    def no_results(cls, provider: ProviderIdentity, data: T | None = None, *, limitation: str | None = None) -> "ProviderResult[T]":
        return cls(ResultState.NO_RESULTS, data, provider, limitations=[limitation] if limitation else [])
