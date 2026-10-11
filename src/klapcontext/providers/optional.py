"""Composition boundary for optional third-party provider adapters."""
from __future__ import annotations

from pathlib import Path

from .contracts import Capability
from .registry import ProviderRegistry


def register_optional_providers(registry: ProviderRegistry, root: Path) -> None:
    """Register bundled optional adapters without leaking them into core services."""
    try:
        from .serena import SerenaProvider, load_serena_settings

        settings = load_serena_settings(Path(root))
        if settings.configured or settings.detected:
            registry.register(
                SerenaProvider(Path(root), settings),
                priorities={
                    Capability.SYMBOL_LOOKUP: 80,
                    Capability.REFERENCES: 80,
                    Capability.IMPLEMENTATIONS: 80,
                    Capability.IMPACT_ANALYSIS: 80,
                },
                timeout=settings.timeout_seconds,
            )
    except Exception as error:
        registry.warnings.append(f"Optional provider configuration ignored: {type(error).__name__}: {error}")


def optional_provider_diagnostics(root: Path, *, probe: bool = False) -> dict[str, dict]:
    """Return diagnostics keyed by adapter name for generic CLI presentation."""
    from .serena import serena_diagnostics

    return {"serena": serena_diagnostics(Path(root), probe=probe)}
