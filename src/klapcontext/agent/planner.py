"""Choose the smallest evidence plan that can answer an agent's task."""
from __future__ import annotations

from .capabilities import Capability, CapabilityRouter, default_providers
from .intents import detect
from .models import AgentContextPlan


PLANS = {
    "UNDERSTAND": ([Capability.FRAMEWORK_ANALYSIS, Capability.ENTRY_POINT_DISCOVERY, Capability.FLOW_RECONSTRUCTION, Capability.INTEGRATION_DISCOVERY, Capability.AUTOMATION_DISCOVERY], ["purpose", "entry_points", "flows", "integrations", "automations", "uncertainties"]),
    "CHANGE": ([Capability.ENTRY_POINT_DISCOVERY, Capability.FLOW_RECONSTRUCTION, Capability.SYMBOL_LOOKUP, Capability.CALLERS, Capability.IMPACT_ANALYSIS, Capability.CONFIG_DISCOVERY, Capability.TEST_DISCOVERY], ["entry_points", "flows", "files", "symbols", "configuration", "tests", "impact", "evidence", "uncertainties"]),
    "DEBUG": ([Capability.ENTRY_POINT_DISCOVERY, Capability.FLOW_RECONSTRUCTION, Capability.INTEGRATION_DISCOVERY, Capability.CONFIG_DISCOVERY, Capability.TEST_DISCOVERY], ["entry_points", "flows", "configuration", "tests", "investigation_points", "evidence", "uncertainties"]),
    "TEST": ([Capability.TEST_DISCOVERY, Capability.ENTRY_POINT_DISCOVERY, Capability.FLOW_RECONSTRUCTION], ["tests", "related_code", "entry_points", "flows", "uncertainties"]),
    "REFACTOR": ([Capability.SYMBOL_LOOKUP, Capability.CALLERS, Capability.CALLEES, Capability.IMPACT_ANALYSIS, Capability.TEST_DISCOVERY], ["symbols", "callers", "callees", "impact", "tests", "evidence"]),
    "IMPACT": ([Capability.SYMBOL_LOOKUP, Capability.CALLERS, Capability.IMPACT_ANALYSIS, Capability.TEST_DISCOVERY], ["symbols", "callers", "impact", "tests", "uncertainties"]),
}


class ContextPlanner:
    def __init__(self, router: CapabilityRouter | None = None):
        self.router = router or CapabilityRouter(default_providers())

    def plan(self, query: str, *, detail: str = "standard", max_tokens: int = 5000) -> AgentContextPlan:
        if detail not in {"minimal", "standard", "deep"}:
            raise ValueError("detail must be minimal, standard or deep")
        if max_tokens < 200:
            raise ValueError("max_tokens must be at least 200")
        match = detect(query)
        capabilities, sections = PLANS[match.intent]
        if detail == "minimal": sections = sections[:max(3, len(sections) // 2)]
        resolutions = [self.router.resolve(capability) for capability in capabilities]
        return AgentContextPlan(query, match.intent, match.confidence, match.area, detail, max_tokens, [capability.value for capability in capabilities], [{"capability": resolution.capability.value, "provider": resolution.provider, "status": resolution.status, "fallbacks": list(resolution.fallbacks)} for resolution in resolutions], sections, "Prioriza evidencia directa, luego relaciones de flujo y finalmente contexto periférico hasta agotar el presupuesto.")
