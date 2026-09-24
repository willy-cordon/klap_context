"""Framework-neutral semantic facts consumed by flows and agent intelligence.

Framework adapters translate conventions into this vocabulary.  Nothing above
this layer needs to know whether an HTTP endpoint came from Laravel, FastAPI,
or a generic executable script.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class SemanticComponent:
    name: str
    type: str
    file: str | None = None
    symbol: str | None = None
    status: str = "CONFIRMED"
    evidence: list[dict] = field(default_factory=list)


@dataclass
class EntryPoint:
    type: str
    name: str
    handler: str | None = None
    protocol: str | None = None
    method: str | None = None
    path: str | None = None
    file: str | None = None
    line: int | None = None
    framework: str | None = None
    status: str = "CONFIRMED"
    evidence: list[dict] = field(default_factory=list)


@dataclass
class ExecutionTransition:
    source: str
    target: str
    type: str
    file: str | None = None
    line: int | None = None
    status: str = "CONFIRMED"
    provider: str = "klap-native"
    evidence: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class Flow:
    """A framework-neutral execution path reconstructed from transitions."""
    name: str
    entry_point: str
    steps: list[str]
    status: str = "INFERRED"
    evidence: list[dict] = field(default_factory=list)


@dataclass
class BackgroundTask:
    name: str
    type: str
    schedule: str | None = None
    handler: str | None = None
    file: str | None = None
    status: str = "CONFIRMED"
    evidence: list[dict] = field(default_factory=list)


@dataclass
class Event:
    name: str
    file: str | None = None
    status: str = "CONFIRMED"
    evidence: list[dict] = field(default_factory=list)


@dataclass
class EventHandler:
    name: str
    event: str | None = None
    file: str | None = None
    status: str = "INFERRED"
    evidence: list[dict] = field(default_factory=list)


@dataclass
class ExternalIntegration:
    name: str
    type: str
    file: str | None = None
    status: str = "INFERRED"
    evidence: list[dict] = field(default_factory=list)


@dataclass
class DataStore:
    name: str
    type: str | None = None
    file: str | None = None
    status: str = "INFERRED"
    evidence: list[dict] = field(default_factory=list)


@dataclass
class Configuration:
    name: str
    file: str
    status: str = "CONFIRMED"
    evidence: list[dict] = field(default_factory=list)


@dataclass
class Dependency:
    name: str
    version: str | None = None
    category: str | None = None
    status: str = "CONFIRMED"
    evidence: list[dict] = field(default_factory=list)


@dataclass
class Test:
    name: str
    file: str
    subject: str | None = None
    status: str = "INFERRED"
    evidence: list[dict] = field(default_factory=list)


@dataclass
class SemanticModel:
    language: str | None
    framework: str | None = None
    analysis_mode: str = "GENERIC"
    components: list[SemanticComponent] = field(default_factory=list)
    entry_points: list[EntryPoint] = field(default_factory=list)
    transitions: list[ExecutionTransition] = field(default_factory=list)
    flows: list[Flow] = field(default_factory=list)
    background_tasks: list[BackgroundTask] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    event_handlers: list[EventHandler] = field(default_factory=list)
    integrations: list[ExternalIntegration] = field(default_factory=list)
    datastores: list[DataStore] = field(default_factory=list)
    configurations: list[Configuration] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)
    tests: list[Test] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "language": self.language,
            "framework": self.framework,
            "analysis_mode": self.analysis_mode,
            "components": [asdict(item) for item in self.components],
            "entry_points": [asdict(item) for item in self.entry_points],
            "transitions": [asdict(item) for item in self.transitions],
            "flows": [asdict(item) for item in self.flows],
            "background_tasks": [asdict(item) for item in self.background_tasks],
            "events": [asdict(item) for item in self.events],
            "event_handlers": [asdict(item) for item in self.event_handlers],
            "integrations": [asdict(item) for item in self.integrations],
            "datastores": [asdict(item) for item in self.datastores],
            "configurations": [asdict(item) for item in self.configurations],
            "dependencies": [asdict(item) for item in self.dependencies],
            "tests": [asdict(item) for item in self.tests],
            "metadata": self.metadata,
        }
