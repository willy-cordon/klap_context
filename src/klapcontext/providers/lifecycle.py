"""Managed, project-local lifecycle for optional analysis providers.

The registry decides *how* to use providers.  This module only detects,
installs and verifies their runtime tools.  It never changes a user's PATH,
global agent configuration, or Python environment.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any


GRAPHIFY = {"package": "graphifyy", "version": "0.9.66", "command": "graphify", "series": (0, 9)}
SERENA = {"package": "serena-agent", "version": "1.7.0", "command": "serena", "series": (1, 7)}
# Serena's Python language-server backend invokes uv/uvx.  Keep this
# prerequisite in the same project-local runtime and pin it independently.
SERENA_UV_VERSION = "0.13.0"
TIMEOUT_SECONDS = 120


@dataclass
class ProviderRuntime:
    name: str
    required_version: str
    state: str
    installed_version: str | None = None
    source: str | None = None
    executable: str | None = None
    connection: str = "UNAVAILABLE"
    capabilities: list[str] | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def runtime_root(root: Path) -> Path:
    return Path(root) / ".klap" / "provider-runtime"


def state_path(root: Path) -> Path:
    return Path(root) / ".klap" / "provider-state.json"


def write_provider_state(root: Path, values: dict[str, Any]) -> None:
    """Persist lifecycle facts after preparation or analysis completion."""
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "providers": values}, indent=2) + "\n", encoding="utf-8")


def managed_command(root: Path, name: str) -> str | None:
    folder = runtime_root(root) / name
    scripts = folder / ("Scripts" if os.name == "nt" else "bin")
    candidate = scripts / (f"{name}.exe" if os.name == "nt" else name)
    return str(candidate) if candidate.is_file() else None


def managed_tool(root: Path, provider: str, tool: str) -> str | None:
    folder = runtime_root(root) / provider
    scripts = folder / ("Scripts" if os.name == "nt" else "bin")
    candidate = scripts / (f"{tool}.exe" if os.name == "nt" else tool)
    return str(candidate) if candidate.is_file() else None


def managed_home(root: Path, name: str) -> Path:
    return runtime_root(root) / name / "home"


def _read_config(root: Path) -> dict[str, Any]:
    path = Path(root) / ".klap" / "providers.json"
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def explicitly_disabled(root: Path, name: str) -> bool:
    provider = _read_config(root).get("providers", {}).get(name, {})
    return isinstance(provider, dict) and provider.get("enabled") is False


def _version(command: str, root: Path) -> str | None:
    try:
        completed = subprocess.run([command, "--version"], cwd=root, text=True, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode:
        return None
    match = re.search(r"(\d+\.\d+(?:\.\d+)?)", (completed.stdout or completed.stderr or ""))
    return match.group(1) if match else None


def _compatible(value: str | None, spec: dict[str, Any]) -> bool:
    if not value:
        return False
    parts = tuple(int(item) for item in value.split(".")[:2] if item.isdigit())
    return parts == spec["series"]


class ProviderLifecycle:
    """Prepare standard providers in isolated per-project virtual environments."""

    def __init__(self, root: Path, *, timeout_seconds: int = TIMEOUT_SECONDS):
        self.root = Path(root).resolve()
        self.timeout_seconds = timeout_seconds

    def prepare(self, *, no_graphify: bool = False, no_serena: bool = False, repair: bool = False) -> dict[str, dict[str, Any]]:
        values = {
            "graphify": self._ensure("graphify", GRAPHIFY, skip=no_graphify, repair=repair),
            "serena": self._ensure("serena", SERENA, skip=no_serena, repair=repair),
        }
        self._write(values)
        return {name: value.as_dict() for name, value in values.items()}

    def _ensure(self, name: str, spec: dict[str, Any], *, skip: bool, repair: bool) -> ProviderRuntime:
        if explicitly_disabled(self.root, name):
            return ProviderRuntime(name, spec["version"], "SKIPPED", source="project configuration", error="Disabled by .klap/providers.json")
        if skip:
            return ProviderRuntime(name, spec["version"], "SKIPPED", source="CLI flag", error=f"Skipped by --no-{name}")
        managed = managed_command(self.root, name)
        system = shutil.which(spec["command"])
        for executable, source in ((managed, "managed"), (system, "system")):
            installed = _version(executable, self.root) if executable else None
            if executable and _compatible(installed, spec) and not repair:
                if name == "graphify" and not self._graphify_healthy(executable):
                    # A console entry point can exist while its native/runtime
                    # dependencies are incompatible with the current Python.
                    # Prefer an isolated runtime over modifying that install.
                    continue
                if name == "serena" and not self._serena_has_uv(source):
                    # A system Serena without uv cannot start several official
                    # language servers.  Provision an isolated complete runtime
                    # rather than altering the user's installation or PATH.
                    continue
                runtime = ProviderRuntime(name, spec["version"], "READY", installed, source, executable)
                return self._verify(runtime)
        runtime = self._install(name, spec)
        return self._verify(runtime) if runtime.state == "READY" else runtime

    def _install(self, name: str, spec: dict[str, Any]) -> ProviderRuntime:
        folder = runtime_root(self.root) / name
        python = folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        try:
            folder.parent.mkdir(parents=True, exist_ok=True)
            if not python.is_file():
                subprocess.run([*self._base_python(name), "-m", "venv", str(folder)], cwd=self.root, text=True, capture_output=True, timeout=self.timeout_seconds, check=True)
            packages = [f"{spec['package']}=={spec['version']}"]
            if name == "serena":
                packages.append(f"uv=={SERENA_UV_VERSION}")
            subprocess.run([str(python), "-m", "pip", "install", "--no-input", "--disable-pip-version-check", *packages], cwd=self.root, text=True, capture_output=True, timeout=self.timeout_seconds, check=True)
        except (OSError, subprocess.SubprocessError) as error:
            detail = getattr(error, "stderr", None) or str(error)
            return ProviderRuntime(name, spec["version"], "FAILED", source="managed", error=detail[-1000:])
        executable = managed_command(self.root, name)
        installed = _version(executable, self.root) if executable else None
        if not executable or not _compatible(installed, spec):
            return ProviderRuntime(name, spec["version"], "FAILED", installed, "managed", executable, error="Installed executable is missing or incompatible")
        if name == "serena":
            try:
                home = managed_home(self.root, name)
                home.mkdir(parents=True, exist_ok=True)
                subprocess.run([executable, "init"], cwd=self.root, text=True, capture_output=True, timeout=self.timeout_seconds, check=True, env={**os.environ, "SERENA_HOME": str(home)})
            except (OSError, subprocess.SubprocessError) as error:
                detail = getattr(error, "stderr", None) or str(error)
                return ProviderRuntime(name, spec["version"], "PARTIAL", installed, "managed", executable, error=f"Serena installed but init failed: {detail[-800:]}")
        return ProviderRuntime(name, spec["version"], "READY", installed, "managed", executable)

    def _serena_has_uv(self, source: str) -> bool:
        if source == "managed":
            return bool(managed_tool(self.root, "serena", "uv") or managed_tool(self.root, "serena", "uvx"))
        return bool(shutil.which("uv") or shutil.which("uvx"))

    def _graphify_healthy(self, executable: str) -> bool:
        try:
            return subprocess.run([executable, "extract", "--help"], cwd=self.root, text=True, capture_output=True, timeout=15, check=False).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    @staticmethod
    def _base_python(name: str) -> list[str]:
        """Pick a compatible interpreter without changing the global one."""
        if name != "graphify" or sys.version_info < (3, 14):
            return [sys.executable]
        if os.name == "nt":
            for version in ("3.13", "3.12", "3.11"):
                candidate = ["py", f"-{version}"]
                try:
                    if subprocess.run([*candidate, "-c", "import sys; print(sys.version_info[:2])"], text=True, capture_output=True, timeout=5, check=False).returncode == 0:
                        return candidate
                except (OSError, subprocess.SubprocessError):
                    pass
        return [sys.executable]

    def _verify(self, runtime: ProviderRuntime) -> ProviderRuntime:
        if runtime.name == "graphify":
            runtime.connection = "VERIFIED"
            return runtime
        try:
            from .serena import SerenaProvider, load_serena_settings
            from ..scope import IndexScope

            # First-run language-server provisioning can exceed the regular
            # interactive query timeout.  The lifecycle has its own bounded
            # installation/health timeout and leaves normal queries unchanged.
            settings = replace(load_serena_settings(self.root), timeout_seconds=float(self.timeout_seconds))
            provider = SerenaProvider(self.root, settings)
            try:
                details = provider.probe()
                tools = set(details.get("tools", []))
                source_files = sorted(IndexScope.load(self.root).included_paths)
                if "get_symbols_overview" in tools and source_files:
                    # Exercise the public adapter with one bounded, read-only
                    # overview.  This proves more than MCP discovery without
                    # turning initialization into semantic repository search.
                    result = provider.find_symbols({
                        "operation": "overview",
                        "relative_path": source_files[0],
                        "depth": 0,
                        "max_answer_chars": 256,
                    })
                    if result.state.value not in {"OK", "NO_RESULTS"}:
                        raise RuntimeError(result.error or "Serena read-only health check failed")
                else:
                    raise RuntimeError("No eligible read-only Serena health check is available for this project")
                runtime.capabilities = details.get("capabilities", [])
                runtime.connection = "VERIFIED"
            finally:
                provider.close()
        except Exception as error:
            runtime.state = "PARTIAL"
            runtime.connection = "FAILED"
            runtime.error = f"{type(error).__name__}: {error}"
        return runtime

    def _write(self, values: dict[str, ProviderRuntime]) -> None:
        write_provider_state(self.root, {name: value.as_dict() for name, value in values.items()})


def prepare_standard_providers(root: Path, **kwargs: Any) -> dict[str, dict[str, Any]]:
    return ProviderLifecycle(Path(root)).prepare(**kwargs)
