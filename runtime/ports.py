from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol

from tools.safe_tools import ToolResult


Message = dict[str, str]
ToolCallable = Callable[..., ToolResult]
AsyncToolCallable = Callable[..., Awaitable[ToolResult]]
ProviderWebSearchCallable = Callable[..., Awaitable[dict[str, Any]]]


class ChatModelClient(Protocol):
    """Minimal model gateway interface used by the runtime."""

    async def chat(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float = 0.0,
    ) -> str:
        """Return assistant text from a chat completion backend."""


class ToolExecutor(Protocol):
    """Tool registry boundary used by the executor node."""

    def names(self) -> list[str]:
        """Return available tool names."""

    def manifest(self) -> list[dict[str, Any]]:
        """Return serializable tool metadata."""

    def run(self, name: str, args: dict[str, Any] | None = None) -> ToolResult:
        """Run a synchronous tool."""

    async def arun(self, name: str, args: dict[str, Any] | None = None) -> ToolResult:
        """Run a synchronous or asynchronous tool."""


class SkillRegistry(Protocol):
    """Skill lookup boundary used by the orchestrator."""

    def match(self, task: str, explicit_names: list[str] | None = None) -> list[Any]:
        """Return matching skill objects for a task."""

    def all(self) -> list[Any]:
        """Return all available skill objects."""


class AuditSink(Protocol):
    """Optional audit sink boundary for external persistence adapters."""

    def append(self, run: dict[str, Any]) -> None:
        """Persist a completed or failed run summary."""
