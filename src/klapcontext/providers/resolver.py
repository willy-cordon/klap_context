"""Capability-based provider selection, execution, fallback and tracing."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any

from .contracts import Capability
from .models import Confidence, ProviderIdentity, ProviderResult, ResultState
from .registry import ProviderRegistration, ProviderRegistry


_METHODS = {
    Capability.FRAMEWORK_ANALYSIS: "framework_analysis",
    Capability.SYMBOL_LOOKUP: "find_symbols",
    Capability.REFERENCES: "find_references",
    Capability.IMPLEMENTATIONS: "find_implementations",
    Capability.CALL_GRAPH: "call_graph",
    Capability.CALLERS: "callers",
    Capability.CALLEES: "callees",
    Capability.ENTRY_POINT_DISCOVERY: "entry_points",
    Capability.STRUCTURAL_RELATIONS: "structural_relations",
    Capability.DEPENDENCY_GRAPH: "dependency_graph",
    Capability.DEPENDENCIES: "dependencies",
    Capability.EVIDENCE_PROVENANCE: "provenance",
    Capability.IMPACT_ANALYSIS: "impact",
    Capability.MINIMAL_EDIT_CONTEXT: "minimal_edit_context",
    Capability.FLOW_RECONSTRUCTION: "flows",
    Capability.PATH_SEARCH: "path_search",
    Capability.TEST_DISCOVERY: "tests",
    Capability.INTEGRATION_DISCOVERY: "integrations",
    Capability.AUTOMATION_DISCOVERY: "automations",
    Capability.CONFIG_DISCOVERY: "configurations",
}

# Capabilities returning independent facts are additive. Query-shaped graphs and
# derived answers must remain single-provider so incompatible graph models are
# never silently spliced together.
AGGREGATE_CAPABILITIES = frozenset({
    Capability.SYMBOL_LOOKUP,
    Capability.REFERENCES,
    Capability.IMPLEMENTATIONS,
    Capability.ENTRY_POINT_DISCOVERY,
    Capability.STRUCTURAL_RELATIONS,
    Capability.DEPENDENCIES,
    Capability.EVIDENCE_PROVENANCE,
    Capability.TEST_DISCOVERY,
    Capability.INTEGRATION_DISCOVERY,
    Capability.AUTOMATION_DISCOVERY,
    Capability.CONFIG_DISCOVERY,
})
SINGLE_PROVIDER_CAPABILITIES = frozenset(set(Capability) - set(AGGREGATE_CAPABILITIES))


@dataclass(frozen=True)
class CapabilitySelection:
    capability: Capability
    provider: str | None
    status: str
    fallbacks: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class CapabilityResolver:
    def __init__(self, registry: ProviderRegistry, *, default_timeout: float = 30.0):
        self.registry = registry
        self.default_timeout = default_timeout

    def select(self, capability: Capability, *, language: str | None = None, framework: str | None = None, request: Any = None) -> CapabilitySelection:
        registered = [item for item in self.registry.registrations() if capability in item.capabilities]
        candidates = self.registry.candidates(capability, language=language, framework=framework, request=request)
        ready = next((item for item in candidates if item.available(request)), None)
        if ready:
            fallback_names = tuple(item.name for item in candidates if item.name != ready.name)
            return CapabilitySelection(capability, ready.name, "READY", fallback_names)
        reason = "UNSUPPORTED" if registered else "UNAVAILABLE"
        return CapabilitySelection(capability, None, reason, tuple(item.name for item in registered))

    def resolve(
        self,
        capability: Capability,
        request: Any = None,
        *,
        language: str | None = None,
        framework: str | None = None,
        timeout: float | None = None,
        fallback: bool = True,
    ) -> ProviderResult:
        candidates = self.registry.candidates(capability, language=language, framework=framework, request=request)
        trace: list[dict[str, Any]] = [
            {"provider": item.name, "state": ResultState.PROVIDER_ERROR.value, "error": getattr(item.provider, "discovery_error")}
            for item in self.registry.registrations()
            if capability in item.capabilities and item.enabled and getattr(item.provider, "discovery_error", None)
        ]
        if not candidates:
            registered = [item for item in self.registry.registrations() if capability in item.capabilities]
            discovery_failures = [
                (item.name, getattr(item.provider, "discovery_error", None))
                for item in registered
                if item.enabled and item.available(request) and getattr(item.provider, "discovery_error", None)
            ]
            if discovery_failures:
                name, error = discovery_failures[-1]
                return ProviderResult(
                    ResultState.PROVIDER_ERROR,
                    provider=ProviderIdentity(name),
                    error=f"Provider discovery failed: {error}",
                    limitations=["Provider tools could not be discovered; no capability was assumed."],
                    trace=[{"provider": name, "state": ResultState.PROVIDER_ERROR.value, "error": error}],
                )
            message = "No enabled provider matches the requested language/framework" if registered else "No provider registered for capability"
            return ProviderResult(ResultState.UNSUPPORTED, error=message, limitations=[message], trace=trace)
        for index, registration in enumerate(candidates):
            if not registration.available(request):
                trace.append({"provider": registration.name, "state": ResultState.UNSUPPORTED.value, "reason": "provider unavailable"})
                continue
            result = self._invoke(registration, capability, request, timeout)
            provider_trace = list(result.trace)
            trace.append({"provider": registration.name, "state": result.state.value, "elapsed_ms": result.elapsed_ms, "error": result.error})
            result.trace = [*trace, *provider_trace]
            if result.state in {ResultState.OK, ResultState.NO_RESULTS}:
                if index > 0 or any(item["state"] != ResultState.OK.value for item in trace[:-1]):
                    result.warnings.append(f"Degraded analysis: using fallback provider {registration.name} for {capability.value}.")
                return result
            if not fallback:
                return result
        failures = [item for item in trace if item["state"] == ResultState.PROVIDER_ERROR.value]
        unknowns = [item for item in trace if item["state"] == ResultState.UNKNOWN.value]
        state = ResultState.PROVIDER_ERROR if failures else ResultState.UNKNOWN if unknowns else ResultState.UNSUPPORTED
        error = failures[-1].get("error") if failures else unknowns[-1].get("error") if unknowns else "All matching providers are unavailable"
        return ProviderResult(state, error=error, limitations=["No provider produced a usable result."], warnings=[f"Analysis quality degraded: {capability.value} is unavailable."], trace=trace)

    def resolve_all(
        self,
        capability: Capability,
        request: Any = None,
        *,
        language: str | None = None,
        framework: str | None = None,
        timeout: float | None = None,
    ) -> ProviderResult:
        """Run every usable provider for additive capabilities and deduplicate facts.

        Single-provider capabilities deliberately retain priority/fallback
        semantics. Each combined fact carries its provider metadata; typed
        provider values already carry that metadata in their contract.
        """
        if capability not in AGGREGATE_CAPABILITIES:
            return self.resolve(capability, request, language=language, framework=framework, timeout=timeout)
        candidates = self.registry.candidates(capability, language=language, framework=framework, request=request)
        trace: list[dict[str, Any]] = [
            {"provider": item.name, "state": ResultState.PROVIDER_ERROR.value, "error": getattr(item.provider, "discovery_error")}
            for item in self.registry.registrations()
            if capability in item.capabilities and item.enabled and getattr(item.provider, "discovery_error", None)
        ]
        values: list[Any] = []
        warnings: list[str] = [f"Provider {item['provider']} discovery failed; additive results are degraded." for item in trace]
        limitations: list[str] = []
        contributors: list[str] = []
        states: list[ResultState] = [ResultState.PROVIDER_ERROR for _ in trace]
        for registration in candidates:
            if not registration.available(request):
                trace.append({"provider": registration.name, "state": ResultState.UNSUPPORTED.value, "reason": "provider unavailable"})
                continue
            result = self._invoke(registration, capability, request, timeout)
            states.append(result.state)
            trace.append({"provider": registration.name, "state": result.state.value, "elapsed_ms": result.elapsed_ms, "error": result.error})
            trace.extend(result.trace)
            warnings.extend(result.warnings)
            limitations.extend(result.limitations)
            if result.state not in {ResultState.OK, ResultState.NO_RESULTS}:
                continue
            contributors.append(registration.name)
            payload = result.data if isinstance(result.data, list) else ([] if result.data is None else [result.data])
            for item in payload:
                import dataclasses
                if dataclasses.is_dataclass(item):
                    item = dataclasses.asdict(item)
                if isinstance(item, dict):
                    item = dict(item)
                    item.setdefault("provider", registration.name)
                    item.setdefault("confidence", result.confidence.value)
                    if result.evidence:
                        item.setdefault("evidence", [evidence.__dict__ for evidence in result.evidence])
                    provider_value = item.get("provider")
                    provider_name = provider_value.get("name") if isinstance(provider_value, dict) else provider_value
                    item.setdefault("provenance", [{
                        "provider": provider_name or registration.name,
                        "confidence": item.get("confidence", result.confidence.value),
                        "evidence": item.get("evidence", []),
                    }])
                values.append(item)
        unique: list[Any] = []
        seen: dict[str, int] = {}
        for item in values:
            key = self._fact_key(item)
            if key not in seen:
                seen[key] = len(unique)
                unique.append(item)
            elif isinstance(item, dict) and isinstance(unique[seen[key]], dict):
                retained = unique[seen[key]]
                retained["provenance"] = [*retained.get("provenance", []), *item.get("provenance", [])]
                merged_evidence = [*retained.get("evidence", []), *item.get("evidence", [])]
                retained["evidence"] = [value for index, value in enumerate(merged_evidence) if repr(value) not in {repr(previous) for previous in merged_evidence[:index]}]
        if contributors:
            state = ResultState.OK if unique else ResultState.NO_RESULTS
            identity = ProviderIdentity("combined:" + "+".join(contributors), adapter="CapabilityResolver")
            return ProviderResult(state, unique, identity, confidence=Confidence.INFERRED, limitations=list(dict.fromkeys(limitations)), warnings=list(dict.fromkeys(warnings)), trace=trace)
        state = ResultState.PROVIDER_ERROR if ResultState.PROVIDER_ERROR in states else ResultState.UNKNOWN if ResultState.UNKNOWN in states else ResultState.UNSUPPORTED
        return ProviderResult(state, [], error="No additive provider produced a usable result.", limitations=list(dict.fromkeys(limitations)) or ["No provider produced a usable result."], warnings=list(dict.fromkeys(warnings)), trace=trace)

    @staticmethod
    def _fact_key(item: Any) -> str:
        if isinstance(item, dict):
            # Provider/confidence/evidence describe a fact; they do not define
            # entity identity. Normalize equivalent provider schemas first.
            location = item.get("location") if isinstance(item.get("location"), dict) else {}
            path = item.get("path") or item.get("file") or location.get("path")
            line = item.get("line") or location.get("line")
            if item.get("source") is not None and item.get("target") is not None:
                return repr(("relation", item.get("source"), item.get("target"), item.get("kind") or item.get("type") or item.get("relation"), path, line))
            if item.get("id") is not None:
                return repr(("id", item.get("id")))
            if item.get("qualified_name") is not None:
                return repr(("qualified_name", item.get("qualified_name"), path, line))
            if item.get("symbol") is not None:
                return repr(("symbol", item.get("symbol"), path, line))
            if item.get("name") is not None:
                return repr(("name", item.get("name"), item.get("type") or item.get("kind"), path, line))
        try:
            import dataclasses
            if dataclasses.is_dataclass(item):
                value = dataclasses.asdict(item)
                value.pop("provider", None); value.pop("evidence", None); value.pop("confidence", None); value.pop("limitations", None)
                return repr(sorted(value.items()))
        except (TypeError, ValueError):
            pass
        return repr(item)

    def _invoke(self, registration: ProviderRegistration, capability: Capability, request: Any, timeout: float | None) -> ProviderResult:
        identity = ProviderIdentity(registration.name, self._version(registration.provider), registration.provider.__class__.__name__)
        method_name = _METHODS.get(capability)
        method = getattr(registration.provider, method_name, None) if method_name else None
        if not callable(method):
            return ProviderResult(ResultState.UNSUPPORTED, provider=identity, error=f"Provider does not implement {capability.value}")
        started = time.perf_counter()
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"klap-{registration.name}")
        future = executor.submit(method, request)
        try:
            value = future.result(timeout=timeout or registration.timeout or self.default_timeout)
            result = self._normalize(value, identity)
        except FutureTimeout:
            future.cancel()
            result = ProviderResult(ResultState.PROVIDER_ERROR, provider=identity, error=f"Provider timed out after {timeout or registration.timeout or self.default_timeout:g}s", limitations=["Provider execution timed out."])
        except Exception as error:
            result = ProviderResult(ResultState.PROVIDER_ERROR, provider=identity, error=f"{type(error).__name__}: {error}", limitations=["Provider failed; result is incomplete."])
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        result.elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        return result

    @staticmethod
    def _version(provider: Any) -> str | None:
        value = getattr(provider, "version", None)
        try:
            return value() if callable(value) else value
        except Exception:
            return None

    @staticmethod
    def _normalize(value: Any, identity: ProviderIdentity) -> ProviderResult:
        if isinstance(value, ProviderResult):
            value.provider = value.provider or identity
            return value
        empty = value is None or value == [] or value == {} or value == ()
        return ProviderResult(ResultState.NO_RESULTS if empty else ResultState.OK, value, identity, confidence=Confidence.UNKNOWN)
