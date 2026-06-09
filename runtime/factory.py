from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from runtime.graph import AgentRuntime
from runtime.llm import LiteLLMClient, ModelConfig
from runtime.ports import ChatModelClient, ProviderWebSearchCallable, SkillRegistry, ToolCallable
from runtime.skill_loader import SkillLoader
from runtime.tool_registry import ToolRegistry


@dataclass(frozen=True)
class RuntimeComponents:
    """Composable dependencies for building an AgentRuntime.

    External apps and OSS contributors should prefer constructing this object
    over importing concrete adapters inside their API or CLI layer.
    """

    model_gateway: ChatModelClient | None = None
    llm: ChatModelClient | None = None
    skill_loader: SkillRegistry | None = None
    model_config: ModelConfig | None = None
    tool_registry: ToolRegistry | None = None
    workspace_root: str | Path = "."
    provider_web_search: ProviderWebSearchCallable | None = None
    extra_tools: dict[str, ToolCallable] = field(default_factory=dict)
    extra_tool_manifest: list[dict[str, Any]] = field(default_factory=list)
    runtime_context_factory: Any | None = None


def build_runtime(components: RuntimeComponents | None = None) -> AgentRuntime:
    """Build the default runtime from swappable components."""

    components = components or RuntimeComponents()
    model_config = components.model_config or ModelConfig.from_env()
    model_gateway = components.model_gateway or components.llm or LiteLLMClient()
    skill_loader = components.skill_loader or SkillLoader()
    tool_registry = components.tool_registry or ToolRegistry(
        workspace_root=components.workspace_root,
        provider_web_search=components.provider_web_search,
        extra_tools=components.extra_tools,
        extra_tool_manifest=components.extra_tool_manifest,
    )
    return AgentRuntime(
        model_gateway=model_gateway,
        skill_loader=skill_loader,
        model_config=model_config,
        tool_registry=tool_registry,
        runtime_context_factory=components.runtime_context_factory,
    )
