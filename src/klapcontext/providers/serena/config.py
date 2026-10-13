"""Portable project-local configuration and non-invasive Serena discovery."""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ARGS = ("start-mcp-server", "--context=ide", "--enable-web-dashboard=false", "--open-web-dashboard=false")


@dataclass(frozen=True)
class SerenaSettings:
    command: str = "serena"
    args: tuple[str, ...] = DEFAULT_ARGS
    enabled: bool = True
    mode: str = "auto"
    timeout_seconds: float = 30.0
    configured: bool = False
    max_results: int = 50
    max_answer_chars: int = 20_000

    def __post_init__(self) -> None:
        if self.mode not in {"auto", "configured"}:
            raise ValueError("Serena mode must be 'auto' or 'configured'")
        if not self.command.strip():
            raise ValueError("Serena command cannot be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("Serena timeout_seconds must be positive")
        if self.max_results < 1 or self.max_answer_chars < 100:
            raise ValueError("Serena result limits must be positive")
        # KlapContext owns project activation so a portable config cannot point
        # Serena at an unrelated/personal directory.
        if any(arg == "--project" or arg.startswith("--project=") or arg == "--project-from-cwd" for arg in self.args):
            raise ValueError("Serena args must not set a project; KlapContext injects the validated root")

    @property
    def detected(self) -> bool:
        command = os.path.expandvars(os.path.expanduser(self.command))
        return bool(shutil.which(command) or (Path(command).is_file() and Path(command).suffix.casefold() in {".exe", ".cmd", ".bat", ".com", ".py", ""}))

    @property
    def eligible(self) -> bool:
        return self.enabled and self.detected and (self.mode == "auto" or self.configured)

    def launch_args(self, root: Path) -> list[str]:
        root = Path(root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Serena project root must be a directory")
        return [*self.args, "--project", str(root)]


def _provider_payload(root: Path) -> tuple[dict[str, Any], str | None]:
    path = Path(root) / ".klap" / "providers.json"
    if not path.exists():
        return {}, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        value = payload.get("providers", {}).get("serena", {})
        return (value if isinstance(value, dict) else {}), None
    except (OSError, json.JSONDecodeError) as error:
        return {}, f"Invalid .klap/providers.json: {type(error).__name__}: {error}"


def load_serena_settings(root: Path) -> SerenaSettings:
    payload, error = _provider_payload(root)
    if error:
        raise ValueError(error)
    args = payload.get("args", list(DEFAULT_ARGS))
    if not isinstance(args, (list, tuple)) or not all(isinstance(item, str) for item in args):
        raise ValueError("Serena args must be an array of strings")
    from ..lifecycle import managed_command
    managed = managed_command(Path(root), "serena")
    return SerenaSettings(
        command=str(payload.get("command", managed or "serena")),
        args=tuple(args),
        enabled=bool(payload.get("enabled", True)),
        mode=str(payload.get("mode", "auto")),
        timeout_seconds=float(payload.get("timeout_seconds", 30.0)),
        configured=bool(payload),
        max_results=int(payload.get("max_results", 50)),
        max_answer_chars=int(payload.get("max_answer_chars", 20_000)),
    )


def serena_diagnostics(root: Path, *, probe: bool = False) -> dict[str, Any]:
    """Report installed/configured/startable separately; probing is explicit."""
    try:
        settings = load_serena_settings(root)
    except Exception as error:
        return {
            "enabled": False, "configured": True, "detected": False,
            "startable": False, "capabilities": [], "languages": [],
            "error": f"{type(error).__name__}: {error}", "missing_dependencies": [],
        }
    try:
        from ...detector import detect_project
        stack, _ = detect_project(Path(root))
        languages = list(dict.fromkeys("TypeScript" if value == "JavaScript" else value for value in stack.get("languages", [])))
    except Exception:
        languages = []
    result: dict[str, Any] = {
        "enabled": settings.enabled,
        "mode": settings.mode,
        "configured": settings.configured,
        "detected": settings.detected,
        "startable": None,
        "command": settings.command,
        "capabilities": [],
        "capabilities_status": "not probed; capabilities require MCP tools/list",
        "tools": [],
        "languages": languages,
        "error": None,
        "missing_dependencies": [] if settings.detected else [settings.command],
        "probe": "not requested",
    }
    if not probe or not settings.enabled or not settings.detected:
        return result
    from .adapter import SerenaProvider
    provider = SerenaProvider(Path(root), settings)
    try:
        details = provider.probe()
        result.update(details)
        result["capabilities_status"] = "discovered from MCP tools/list"
        result["probe"] = "completed"
    except Exception as error:
        result.update(startable=False, error=f"{type(error).__name__}: {error}", probe="failed")
    finally:
        provider.close()
    return result
