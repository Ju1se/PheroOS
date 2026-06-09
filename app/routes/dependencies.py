from __future__ import annotations

from functools import lru_cache

from runtime.graph import AgentRuntime
from runtime.factory import RuntimeComponents, build_runtime
from runtime.llm import LiteLLMClient, ModelConfig
from runtime.agent_registry import AgentRegistry
from runtime.capability_registry import CapabilityRegistry, CapabilityStateStore
from runtime.connection_control import ConnectionControlPlane
from runtime.os_kernel import OSKernel
from runtime.runtime_context import RuntimeMaterializer
from runtime.skill_loader import SkillLoader


@lru_cache
def get_skill_loader() -> SkillLoader:
    return SkillLoader()


@lru_cache
def get_llm_client() -> LiteLLMClient:
    return LiteLLMClient()


@lru_cache
def get_model_config() -> ModelConfig:
    return ModelConfig.from_env()


@lru_cache
def get_connection_control_plane() -> ConnectionControlPlane:
    return ConnectionControlPlane()


@lru_cache
def get_capability_registry() -> CapabilityRegistry:
    return CapabilityRegistry()


@lru_cache
def get_capability_state_store() -> CapabilityStateStore:
    return CapabilityStateStore()


@lru_cache
def get_agent_registry() -> AgentRegistry:
    return AgentRegistry()


@lru_cache
def get_os_kernel() -> OSKernel:
    return OSKernel(
        registry=get_capability_registry(),
        state_store=get_capability_state_store(),
        control_plane=get_connection_control_plane(),
        agent_registry=get_agent_registry(),
    )


@lru_cache
def get_runtime_materializer() -> RuntimeMaterializer:
    return RuntimeMaterializer(
        control_plane=get_connection_control_plane(),
        workspace_root=".",
        fallback_llm=get_llm_client(),
        capability_registry=get_capability_registry(),
        capability_state_store=get_capability_state_store(),
        agent_registry=get_agent_registry(),
        os_kernel=get_os_kernel(),
    )


def get_agent_runtime() -> AgentRuntime:
    return build_runtime(
        RuntimeComponents(
            model_gateway=get_llm_client(),
            skill_loader=get_skill_loader(),
            model_config=get_model_config(),
            runtime_context_factory=get_runtime_materializer().build_context,
        )
    )
