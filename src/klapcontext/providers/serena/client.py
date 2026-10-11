"""Stateful, read-only MCP stdio client used by the Serena adapter."""
from __future__ import annotations

import asyncio
import concurrent.futures
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import SerenaSettings


READ_ONLY_TOOLS = frozenset({
    "activate_project",
    "find_symbol",
    "get_symbols_overview",
    "find_declaration",
    "find_referencing_symbols",
    "find_implementations",
    "get_current_config",
})


@dataclass
class _Command:
    action: str
    name: str | None
    arguments: dict[str, Any]
    future: concurrent.futures.Future


class SerenaMcpClient:
    """Own one reusable Serena process/session on a dedicated worker thread."""

    def __init__(self, root: Path, settings: SerenaSettings):
        self.root = Path(root).resolve(strict=True)
        self.settings = settings
        self._commands: queue.Queue[_Command] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._tools: dict[str, dict[str, Any]] = {}
        self.server_info: dict[str, Any] = {}

    def _start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=lambda: asyncio.run(self._serve()), name="klap-serena-mcp", daemon=True)
            self._thread.start()

    def _request(self, action: str, name: str | None = None, arguments: dict[str, Any] | None = None) -> Any:
        self._start()
        future: concurrent.futures.Future = concurrent.futures.Future()
        self._commands.put(_Command(action, name, arguments or {}, future))
        try:
            return future.result(timeout=self.settings.timeout_seconds)
        except concurrent.futures.TimeoutError as error:
            future.cancel()
            raise TimeoutError(f"Serena MCP request timed out after {self.settings.timeout_seconds:g}s") from error

    def list_tools(self) -> dict[str, dict[str, Any]]:
        return self._request("list")

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        if name not in READ_ONLY_TOOLS:
            raise PermissionError(f"Serena tool is not authorized: {name}")
        return self._request("call", name, arguments)

    def close(self) -> None:
        thread = self._thread
        if not thread or not thread.is_alive():
            return
        future: concurrent.futures.Future = concurrent.futures.Future()
        self._commands.put(_Command("close", None, {}, future))
        try:
            future.result(timeout=min(self.settings.timeout_seconds, 5.0))
        except Exception:
            pass
        thread.join(timeout=5)

    async def _serve(self) -> None:
        parameters = StdioServerParameters(command=self.settings.command, args=self.settings.launch_args(self.root))
        while True:
            command = await asyncio.to_thread(self._commands.get)
            if command.action == "close":
                command.future.set_result(True)
                return
            try:
                async with stdio_client(parameters) as (reader, writer):
                    async with ClientSession(reader, writer) as session:
                        initialized = await asyncio.wait_for(session.initialize(), self.settings.timeout_seconds)
                        info = getattr(initialized, "serverInfo", None)
                        self.server_info = {
                            "name": getattr(info, "name", None),
                            "version": getattr(info, "version", None),
                        }
                        listing = await asyncio.wait_for(session.list_tools(), self.settings.timeout_seconds)
                        self._tools = {
                            tool.name: {
                                "name": tool.name,
                                "description": tool.description,
                                "inputSchema": tool.inputSchema,
                            }
                            for tool in listing.tools
                        }
                        while True:
                            if command.action == "list":
                                command.future.set_result(dict(self._tools))
                            elif command.action == "call":
                                if command.name not in READ_ONLY_TOOLS:
                                    raise PermissionError(f"Serena tool is not authorized: {command.name}")
                                if command.name not in self._tools:
                                    raise NotImplementedError(f"Serena tool is unavailable: {command.name}")
                                result = await asyncio.wait_for(
                                    session.call_tool(command.name, command.arguments),
                                    self.settings.timeout_seconds,
                                )
                                if getattr(result, "isError", False):
                                    raise RuntimeError(self._text(result) or f"Serena tool failed: {command.name}")
                                command.future.set_result(self._payload(result))
                            command = await asyncio.to_thread(self._commands.get)
                            if command.action == "close":
                                command.future.set_result(True)
                                return
            except BaseException as error:
                if not command.future.done():
                    command.future.set_exception(error)
                # A timeout or protocol error invalidates the session. The next
                # queued request gets a clean process rather than a poisoned one.

    @staticmethod
    def _text(result: Any) -> str:
        return "\n".join(str(getattr(item, "text", "")) for item in getattr(result, "content", []) if getattr(item, "text", None))

    @classmethod
    def _payload(cls, result: Any) -> Any:
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            return structured
        return cls._text(result)
