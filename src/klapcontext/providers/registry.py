"""Runtime provider registry with external registration and local configuration."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .contracts import Capability


@dataclass
class ProviderRegistration:
    provider: Any
    name: str
    capabilities: frozenset[Capability]
    enabled: bool = True
    priorities: dict[Capability, int] = field(default_factory=dict)
    languages: frozenset[str] = frozenset()
    frameworks: frozenset[str] = frozenset()
    timeout: float | None = None

    def priority(self, capability: Capability) -> int:
        return self.priorities.get(capability, 0)

    def matches(self, language: str | None, framework: str | None) -> bool:
        language_ok = not self.languages or (language is not None and language.casefold() in self.languages)
        framework_ok = not self.frameworks or (framework is not None and framework.casefold() in self.frameworks)
        return language_ok and framework_ok

    def supports(self, capability: Capability, request: Any = None) -> bool:
        if capability not in self.capabilities:
            return False
        dynamic = getattr(self.provider, "capabilities_for", None)
        if not callable(dynamic):
            return True
        try:
            values = dynamic(request)
            return capability in {item if isinstance(item, Capability) else Capability(item) for item in values}
        except Exception:
            return False

    def available(self, request: Any = None) -> bool:
        check = getattr(self.provider, "is_available", None)
        try:
            return bool(check(request)) if callable(check) else True
        except Exception:
            return False


class ProviderRegistry:
    """Mutable composition root; adapters register without changes to core services."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderRegistration] = {}
        self.warnings: list[str] = []

    def register(
        self,
        provider: Any,
        *,
        name: str | None = None,
        capabilities: Iterable[Capability | str] | None = None,
        enabled: bool = True,
        priorities: dict[Capability | str, int] | None = None,
        languages: Iterable[str] = (),
        frameworks: Iterable[str] = (),
        timeout: float | None = None,
        replace: bool = False,
    ) -> ProviderRegistration:
        provider_name = name or getattr(provider, "name", provider.__class__.__name__)
        if provider_name in self._providers and not replace:
            raise ValueError(f"Provider already registered: {provider_name}")
        advertised = capabilities
        if advertised is None:
            value = getattr(provider, "capabilities", ())
            advertised = value() if callable(value) else value
        normalized = frozenset(item if isinstance(item, Capability) else Capability(item) for item in advertised)
        normalized_priorities = {
            key if isinstance(key, Capability) else Capability(key): int(value)
            for key, value in (priorities or {}).items()
        }
        registration = ProviderRegistration(
            provider,
            provider_name,
            normalized,
            enabled,
            normalized_priorities,
            frozenset(item.casefold() for item in languages),
            frozenset(item.casefold() for item in frameworks),
            timeout,
        )
        self._providers[provider_name] = registration
        return registration

    def unregister(self, name: str) -> None:
        self._providers.pop(name, None)

    def enable(self, name: str, enabled: bool = True) -> None:
        self._providers[name].enabled = enabled

    def candidates(self, capability: Capability, *, language: str | None = None, framework: str | None = None, request: Any = None) -> list[ProviderRegistration]:
        values = [item for item in self._providers.values() if item.enabled and item.supports(capability, request) and item.matches(language, framework)]
        return sorted(values, key=lambda item: (-item.priority(capability), item.name))

    def registrations(self) -> tuple[ProviderRegistration, ...]:
        return tuple(self._providers.values())

    def apply_config(self, path: Path) -> list[str]:
        """Apply optional `.klap/providers.json`; unknown providers are warnings."""
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as error:
            warning = f"Provider configuration is invalid: {type(error).__name__}: {error}"
            self.warnings.append(warning)
            return [warning]
        warnings: list[str] = []
        for name, settings in payload.get("providers", {}).items():
            registration = self._providers.get(name)
            if registration is None:
                warnings.append(f"Configured provider is not registered: {name}")
                continue
            if "enabled" in settings:
                registration.enabled = bool(settings["enabled"])
            if "timeout_seconds" in settings:
                registration.timeout = float(settings["timeout_seconds"])
            for key, value in settings.get("priorities", {}).items():
                registration.priorities[Capability(key)] = int(value)
        self.warnings.extend(warnings)
        return warnings
