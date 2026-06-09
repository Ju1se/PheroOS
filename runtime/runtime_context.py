from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.agent_registry import AgentRegistry
from runtime.capability_runtime import load_capability_runtime_descriptors
from runtime.capability_registry import CapabilityRegistry, CapabilityStateStore
from runtime.connection_control import DEFAULT_TENANT_ID, ConnectionControlPlane
from runtime.data_sources import data_provider_descriptors_from_capability
from runtime.financial_data_sources import WRDSFinancialDataSource
from runtime.legacy_agent_registry import selected_agent_ids_from_metadata
from runtime.legacy_model_roles import (
    legacy_scoped_agent_field,
    model_roles_for_provider_mix,
    model_roles_for_single_provider,
)
from runtime.legacy_runtime_validation import (
    legacy_wrds_capability_enabled,
    legacy_wrds_missing_connection_issue,
    legacy_wrds_status_tool_name,
    legacy_wrds_tools_not_registered_issue,
)
from runtime.llm import LiteLLMClient, ModelConfig
from runtime.model_gateway import ConnectionAwareModelGateway, capability_model_names
from runtime.os_kernel import OSKernel
from runtime.tool_registry import ToolRegistry
from tools.public_financial_tools import PublicFinancialDataTools


@dataclass(frozen=True)
class RuntimeContext:
    tenant_id: str
    model_gateway: ConnectionAwareModelGateway
    model_routing_policy: dict[str, Any]
    tool_registry: ToolRegistry
    capability_index: dict[str, Any]
    enabled_capabilities: list[dict[str, Any]]
    permission_grants: list[dict[str, Any]]
    os_plan: dict[str, Any] | None = None
    data_source_registry: dict[str, Any] | None = None
    skill_registry: dict[str, Any] | None = None
    agent_registry: dict[str, Any] | None = None
    capability_runtime: dict[str, Any] | None = None
    validation_issues: list[dict[str, Any]] | None = None

    def validate(self) -> list[dict[str, Any]]:
        return validate_runtime_context(self)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "model_routing_policy": self.model_routing_policy,
            "capability_index": self.capability_index,
            "enabled_capabilities": self.enabled_capabilities,
            "permission_grants": self.permission_grants,
            "os_plan": self.os_plan,
            "data_source_registry": self.data_source_registry,
            "skill_registry": self.skill_registry,
            "agent_registry": self.agent_registry,
            "capability_runtime": self.capability_runtime,
            "validation_issues": self.validation_issues or [],
            "tools": self.tool_registry.manifest(),
        }


class RuntimeMaterializer:
    """Build a fresh runtime context from active tenant connections per run."""

    def __init__(
        self,
        *,
        control_plane: ConnectionControlPlane,
        workspace_root: str | Path = ".",
        fallback_llm: LiteLLMClient | None = None,
        capability_registry: CapabilityRegistry | None = None,
        capability_state_store: CapabilityStateStore | None = None,
        agent_registry: AgentRegistry | None = None,
        os_kernel: OSKernel | None = None,
    ) -> None:
        self.control_plane = control_plane
        self.workspace_root = workspace_root
        self.fallback_llm = fallback_llm or LiteLLMClient()
        self.capability_registry = capability_registry
        self.capability_state_store = capability_state_store
        self.agent_registry = agent_registry
        self.os_kernel = os_kernel

    def build_context(
        self,
        *,
        tenant_id: str = DEFAULT_TENANT_ID,
        task: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeContext:
        os_plan = (
            self.os_kernel.plan(
                task=task or "",
                tenant_id=tenant_id,
                selected_agent_ids=selected_agent_ids_from_metadata(metadata),
            )
            if self.os_kernel is not None and task
            else None
        )
        capability_index = self.control_plane.capability_index(tenant_id=tenant_id)
        active_connections = self.control_plane.list_active_connections(tenant_id=tenant_id)
        enabled_capabilities = self._enabled_capabilities(tenant_id=tenant_id)
        enabled_manifests = self._enabled_manifests(tenant_id=tenant_id)
        enabled_capability_ids = {str(item.get("id")) for item in enabled_capabilities if item.get("id")}
        permission_grants = [
            *list((os_plan or {}).get("permission_grants") or []),
            *[
                {"capability_id": capability.get("id"), "permission_grants": capability.get("permission_grants") or []}
                for capability in enabled_capabilities
                if capability.get("permission_grants")
            ],
        ]
        gateway = ConnectionAwareModelGateway(
            control_plane=self.control_plane,
            tenant_id=tenant_id,
            fallback=self.fallback_llm,
        )
        wrds_tools = self._wrds_tools(tenant_id=tenant_id)
        tool_registry = ToolRegistry(
            workspace_root=self.workspace_root,
            provider_web_search=gateway.provider_web_search if has_model_provider(active_connections) else None,
            provider_web_search_enabled=has_model_provider(active_connections),
            wrds_enabled=wrds_tools is not None,
            wrds_tools=wrds_tools,
            public_financial_tools=PublicFinancialDataTools(fred_api_key=self._fred_api_key(tenant_id=tenant_id)),
            permission_grants=permission_grants,
            active_connections=active_connection_keys(active_connections),
            allowed_tool_names=self._allowed_tool_names(enabled_capabilities),
        )
        context = RuntimeContext(
            tenant_id=tenant_id,
            model_gateway=gateway,
            model_routing_policy=default_model_routing_policy(capability_index),
            tool_registry=tool_registry,
            capability_index=capability_index,
            enabled_capabilities=enabled_capabilities,
            permission_grants=permission_grants,
            os_plan=os_plan,
            data_source_registry=self._data_source_registry(enabled_capabilities),
            skill_registry=self._skill_registry(enabled_capabilities),
            agent_registry=self._agent_registry(enabled_capability_ids, os_plan=os_plan),
            capability_runtime=load_capability_runtime_descriptors(enabled_manifests) if enabled_manifests else {"capabilities": {}, "diagnostics": []},
        )
        return RuntimeContext(
            **{
                **context.__dict__,
                "validation_issues": context.validate(),
            }
        )

    def _wrds_tools(self, *, tenant_id: str):
        if self.capability_registry is not None and self.capability_state_store is not None:
            active = self.capability_state_store.active_capabilities(
                registry=self.capability_registry,
                tenant_id=tenant_id,
            )
            has_wrds_capability = any(
                "wrds" in capability.get("connections", [])
                or any(str(tool).startswith("wrds_") for tool in capability.get("tools", []))
                for capability in active
            )
            if not has_wrds_capability:
                return None
        for record in self.control_plane.list_active_connections(tenant_id=tenant_id):
            if record.get("kind") == "financial_data_source" and record.get("provider") == "wrds":
                return WRDSFinancialDataSource.from_connection(
                    control_plane=self.control_plane,
                    record=record,
                ).tools
        return None

    def _fred_api_key(self, *, tenant_id: str) -> str | None:
        for record in self.control_plane.list_active_connections(tenant_id=tenant_id):
            if record.get("kind") == "financial_data_source" and record.get("provider") == "fred":
                return self.control_plane.secret_value(record, "api_key")
        return None

    def _enabled_capabilities(self, *, tenant_id: str) -> list[dict[str, Any]]:
        if self.capability_registry is None or self.capability_state_store is None:
            return []
        return self.capability_state_store.active_capabilities(
            registry=self.capability_registry,
            tenant_id=tenant_id,
        )

    def _enabled_manifests(self, *, tenant_id: str):
        if self.capability_registry is None or self.capability_state_store is None:
            return []
        enabled_ids = set(self.capability_state_store.enabled_ids(tenant_id=tenant_id))
        manifests, _diagnostics = self.capability_registry.load()
        return [manifest for manifest in manifests if manifest.id in enabled_ids]

    def _data_source_registry(self, capabilities: list[dict[str, Any]]) -> dict[str, Any]:
        data_sources = []
        provider_descriptors = []
        for capability in capabilities:
            descriptors = data_provider_descriptors_from_capability(capability)
            provider_descriptors.extend(descriptor.to_dict() for descriptor in descriptors)
            if descriptors or capability.get("data_packages"):
                primary = descriptors[0].to_dict() if descriptors else {}
                data_sources.append(
                    {
                        "capability_id": capability.get("id"),
                        "provider_id": primary.get("provider_id") or capability.get("id"),
                        "source_kind": primary.get("source_kind") or "capability_declared_source",
                        "dataset_kind": primary.get("dataset_kind") or "declared_data_packages",
                        "connections": capability.get("connections", []),
                        "data_packages": capability.get("data_packages", []),
                        "descriptor_schema": primary.get("schema_version"),
                    }
                )
        return {
            "schema_version": "open-multi-agent.data_source_registry.v0.1",
            "sources": data_sources,
            "provider_descriptors": provider_descriptors,
            "descriptors": provider_descriptors,
        }

    def _skill_registry(self, capabilities: list[dict[str, Any]]) -> dict[str, Any]:
        skills = []
        for capability in capabilities:
            for skill in capability.get("skills", []) or []:
                skills.append({"skill": skill, "capability_id": capability.get("id")})
        return {"skills": skills}

    def _agent_registry(self, enabled_capability_ids: set[str], *, os_plan: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.agent_registry is None:
            return {"agents": [], "diagnostics": []}
        catalog = self.agent_registry.catalog(enabled_capability_ids=enabled_capability_ids)
        active_keys = runtime_agent_keys_from_plan(os_plan)
        if not active_keys:
            return catalog
        agents = catalog.get("agents") if isinstance(catalog.get("agents"), list) else []
        return {
            **catalog,
            "agents": [agent for agent in agents if str(agent.get("key") or "") in active_keys],
            "selection_mode": nested_get(os_plan, "agent_plan", "selection_mode") or nested_get(os_plan, "swarm_plan", "selection_mode"),
            "available_agent_count": len(agents),
        }

    def _allowed_tool_names(self, capabilities: list[dict[str, Any]]) -> list[str] | None:
        if self.capability_registry is None or self.capability_state_store is None:
            return None
        names: set[str] = set()
        for capability in capabilities:
            for tool in capability.get("tools") or []:
                text = str(tool).strip()
                if text:
                    names.add(text)
        return sorted(names)


def default_model_routing_policy(capability_index: dict[str, Any]) -> dict[str, Any]:
    providers = [item.get("provider") for item in capability_index.get("model_providers", [])]
    model_config = model_config_from_capabilities(capability_index)
    return {
        "judgment_roles": ["zhipu", "anthropic", "openai", "moonshot", "openai_compatible", "minimax"],
        "execution_roles": ["minimax", "openai", "anthropic", "moonshot", "zhipu", "openai_compatible"],
        "available_providers": [provider for provider in providers if provider],
        "fallback": "single-provider" if len(providers) == 1 else "provider-priority",
        "selected_models": {
            "judgment": model_config.orchestrator,
            "execution": model_config.executor,
            "critic": model_config.critic,
            "writer": model_config.writer,
            "final_judge": model_config.final_judge,
        },
        "fallback_chains": {
            "glm": model_config.glm_fallback_models,
            "minimax": model_config.minimax_fallback_models,
            "default": model_config.default_fallback_models,
        },
    }


def model_config_from_capabilities(capability_index: dict[str, Any]) -> ModelConfig:
    scoped_overrides = scoped_model_overrides(capability_index)
    provider_models = provider_model_catalog(capability_index, include_scoped=False)
    providers = set(provider_models)
    if providers == {"minimax"}:
        minimax_model = select_provider_model(provider_models, "minimax")
        fallbacks = fallback_chain_for_primary(primary_provider="minimax", provider_models=provider_models)
        return apply_model_overrides(ModelConfig(
            **model_roles_for_single_provider(minimax_model),
            minimax_fallback_models=",".join(fallbacks),
            default_fallback_models=",".join(fallbacks),
        ), scoped_overrides)
    if providers == {"zhipu"}:
        glm_model = select_provider_model(provider_models, "zhipu")
        fallbacks = fallback_chain_for_primary(primary_provider="zhipu", provider_models=provider_models)
        return apply_model_overrides(ModelConfig(
            **model_roles_for_single_provider(glm_model),
            glm_fallback_models=",".join(fallbacks),
            default_fallback_models=",".join(fallbacks),
        ), scoped_overrides)
    if providers == {"openai"}:
        openai_model = select_provider_model(provider_models, "openai")
        fallbacks = fallback_chain_for_primary(primary_provider="openai", provider_models=provider_models)
        return apply_model_overrides(
            ModelConfig(**model_roles_for_single_provider(openai_model), default_fallback_models=",".join(fallbacks)),
            scoped_overrides,
        )
    if providers == {"anthropic"}:
        claude_model = select_provider_model(provider_models, "anthropic")
        fallbacks = fallback_chain_for_primary(primary_provider="anthropic", provider_models=provider_models)
        return apply_model_overrides(
            ModelConfig(**model_roles_for_single_provider(claude_model), default_fallback_models=",".join(fallbacks)),
            scoped_overrides,
        )
    if providers == {"moonshot"}:
        kimi_model = select_provider_model(provider_models, "moonshot")
        fallbacks = fallback_chain_for_primary(primary_provider="moonshot", provider_models=provider_models)
        return apply_model_overrides(
            ModelConfig(**model_roles_for_single_provider(kimi_model), default_fallback_models=",".join(fallbacks)),
            scoped_overrides,
        )
    if providers:
        judgment_provider = first_available_provider(
            providers,
            ["zhipu", "anthropic", "openai", "moonshot", "openai_compatible", "openrouter", "deepseek", "gemini", "minimax"],
        )
        execution_provider = first_available_provider(
            providers,
            ["minimax", "openai", "anthropic", "moonshot", "zhipu", "openai_compatible", "openrouter", "deepseek", "gemini"],
        )
        judgment_model = select_provider_model(provider_models, judgment_provider)
        execution_model = select_provider_model(provider_models, execution_provider)
        fallback_models = unique_models(
            [
                *fallback_chain_for_primary(primary_provider=judgment_provider, provider_models=provider_models),
                *fallback_chain_for_primary(primary_provider=execution_provider, provider_models=provider_models),
            ]
        )
        first_fallback = first_model_not_in(fallback_models, {judgment_model, execution_model}) or execution_model
        return apply_model_overrides(ModelConfig(
            **model_roles_for_provider_mix(
                judgment_model=judgment_model,
                execution_model=execution_model,
                fallback_model=first_fallback,
            ),
            glm_fallback_models=",".join(fallback_models),
            minimax_fallback_models=",".join(fallback_models),
            default_fallback_models=",".join(fallback_models),
        ), scoped_overrides)
    return apply_model_overrides(ModelConfig.from_env(), scoped_overrides)


def provider_model_catalog(capability_index: dict[str, Any], *, include_scoped: bool = False) -> dict[str, list[str]]:
    catalog: dict[str, list[str]] = {}
    for record in capability_index.get("model_providers") or []:
        if not isinstance(record, dict):
            continue
        if not include_scoped and scoped_agent_fields(record):
            continue
        provider = str(record.get("provider") or record.get("provider_key") or "").strip()
        if not provider:
            continue
        models = capability_model_names(record)
        if not models:
            models = default_models_for_provider(provider)
        catalog[provider] = unique_models([*catalog.get(provider, []), *models])
    return catalog


def default_models_for_provider(provider: str) -> list[str]:
    defaults = {
        "zhipu": ["glm-5.1", "glm-5.1-standard"],
        "minimax": ["minimax-m2.7"],
        "openai": ["gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4.1-mini"],
        "anthropic": ["claude-sonnet-4-5", "claude-opus-4-1", "claude-3-5-sonnet-latest"],
        "moonshot": ["kimi-k2.6", "kimi-k2.5", "moonshot-v1-auto", "kimi-k2-thinking", "kimi-k2-turbo-preview", "kimi-k2-0905-preview", "moonshot-v1-128k"],
        "openai_compatible": ["openai-compatible-default"],
        "openrouter": ["openrouter/auto"],
        "deepseek": ["deepseek-chat"],
        "gemini": ["gemini-2.5-pro", "gemini-2.5-flash"],
    }
    return defaults.get(provider, [provider])


def select_provider_model(provider_models: dict[str, list[str]], provider: str) -> str:
    models = provider_models.get(provider) or default_models_for_provider(provider)
    preferences = {
        "zhipu": ("glm-5.1", "glm-5.1-standard", "glm"),
        "minimax": ("minimax-m2.7", "MiniMax-M2.7", "minimax"),
        "openai": ("gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4o", "o3", "o4"),
        "anthropic": ("claude-sonnet-4-5", "claude-opus-4-1", "claude-3-5-sonnet", "claude-3-5-haiku", "claude"),
        "moonshot": ("kimi-k2.6", "kimi-k2.5", "moonshot-v1-auto", "kimi-k2-thinking", "kimi-k2-turbo-preview", "kimi-k2-0905-preview", "kimi-k2", "moonshot-v1"),
        "openrouter": ("openrouter/auto",),
        "deepseek": ("deepseek-chat", "deepseek-reasoner", "deepseek"),
        "gemini": ("gemini-2.5-pro", "gemini-2.5-flash", "gemini"),
    }
    lowered = [(model, model.lower()) for model in models]
    for preferred in preferences.get(provider, ()):
        preferred_lower = preferred.lower()
        for original, lower in lowered:
            if lower == preferred_lower or lower.startswith(preferred_lower):
                return original
    return models[0]


def fallback_chain_for_primary(*, primary_provider: str, provider_models: dict[str, list[str]]) -> list[str]:
    provider_order = {
        "zhipu": ["zhipu", "anthropic", "openai", "minimax", "openai_compatible", "openrouter", "deepseek", "gemini"],
        "minimax": ["minimax", "openai", "anthropic", "zhipu", "openai_compatible", "openrouter", "deepseek", "gemini"],
        "openai": ["openai", "anthropic", "moonshot", "minimax", "zhipu", "openai_compatible", "openrouter", "deepseek", "gemini"],
        "anthropic": ["anthropic", "openai", "moonshot", "minimax", "zhipu", "openai_compatible", "openrouter", "deepseek", "gemini"],
        "moonshot": ["moonshot", "openai", "anthropic", "minimax", "zhipu", "openai_compatible", "openrouter", "deepseek", "gemini"],
    }.get(primary_provider, [primary_provider, "openai", "anthropic", "moonshot", "minimax", "zhipu"])
    models = []
    for provider in provider_order:
        if provider not in provider_models:
            continue
        models.append(select_provider_model(provider_models, provider))
    return unique_models(models)


def scoped_model_overrides(capability_index: dict[str, Any]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for record in capability_index.get("model_providers") or []:
        if not isinstance(record, dict):
            continue
        fields = scoped_agent_fields(record)
        if not fields:
            continue
        config = record.get("config") if isinstance(record.get("config"), dict) else {}
        explicit_overrides = config.get("model_overrides") if isinstance(config.get("model_overrides"), dict) else {}
        for field, model in explicit_overrides.items():
            field_name = str(field).strip()
            if field_name and field_name != "agent_model_overrides" and str(model).strip():
                overrides[field_name] = str(model).strip()
        provider = str(record.get("provider") or record.get("provider_key") or "").strip()
        model = str(config.get("preferred_model") or "").strip()
        if not model:
            models = capability_model_names(record) or default_models_for_provider(provider)
            model = select_provider_model({provider: models}, provider) if provider else (models[0] if models else "")
        for field in fields:
            if field and field != "agent_model_overrides" and model:
                overrides.setdefault(field, model)
    return overrides


def scoped_agent_fields(record: dict[str, Any]) -> list[str]:
    config = record.get("config") if isinstance(record.get("config"), dict) else {}
    scope = config.get("agent_scope")
    if isinstance(scope, str):
        raw_fields = [item.strip() for item in scope.split(",") if item.strip()]
    elif isinstance(scope, list):
        raw_fields = [str(item).strip() for item in scope if str(item).strip()]
    else:
        raw_fields = []
    fields = []
    for field in raw_fields:
        normalized = legacy_scoped_agent_field(field)
        if normalized and normalized != "agent_model_overrides":
            fields.append(normalized)
    return fields


def apply_model_overrides(config: ModelConfig, overrides: dict[str, str]) -> ModelConfig:
    if not overrides:
        return config
    values = {field: getattr(config, field) for field in ModelConfig.__dataclass_fields__}
    agent_model_overrides = dict(config.agent_model_overrides)
    for field, model in overrides.items():
        if field in values and str(model).strip():
            values[field] = str(model).strip()
        elif str(field or "").strip() and str(model).strip():
            agent_model_overrides[str(field).strip()] = str(model).strip()
    values["agent_model_overrides"] = agent_model_overrides
    fallback_models = unique_models(
        [
            values.get("default_fallback_models", ""),
            *[model for model in overrides.values() if str(model).strip()],
        ]
    )
    if fallback_models and not values.get("default_fallback_models"):
        values["default_fallback_models"] = ",".join(fallback_models)
    return ModelConfig(**values)


def first_available_provider(providers: set[str], preference: list[str]) -> str:
    for provider in preference:
        if provider in providers:
            return provider
    return sorted(providers)[0]


def first_model_not_in(models: list[str], excluded: set[str]) -> str | None:
    excluded_lower = {item.lower() for item in excluded}
    for model in models:
        if model.lower() not in excluded_lower:
            return model
    return None


def unique_models(models: list[str]) -> list[str]:
    seen: set[str] = set()
    output = []
    for model in models:
        key = str(model).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(str(model).strip())
    return output


def runtime_agent_keys_from_plan(os_plan: dict[str, Any] | None) -> set[str]:
    if not isinstance(os_plan, dict):
        return set()
    agent_plan = os_plan.get("agent_plan") if isinstance(os_plan.get("agent_plan"), dict) else {}
    agents = agent_plan.get("agents") if isinstance(agent_plan.get("agents"), list) else []
    keys = {str(agent.get("key") or "") for agent in agents if isinstance(agent, dict) and agent.get("key")}
    if keys:
        return keys
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    return {str(key) for key in swarm_plan.get("activated_agents") or [] if str(key).strip()}


def nested_get(payload: dict[str, Any] | None, *path: str) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def active_connection_keys(records: list[dict[str, Any]]) -> list[str]:
    keys: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        for key in ("kind", "provider", "id", "connection_key"):
            value = str(record.get(key) or "").strip()
            if value:
                keys.add(value)
        if record.get("kind") == "model_provider":
            keys.update({"model-provider", "model_provider", "chat_model"})
        if record.get("kind") == "financial_data_source" and record.get("provider") == "wrds":
            keys.update({"wrds", "financial_data_source", "professional_financial_database"})
    return sorted(keys)


def has_model_provider(records: list[dict[str, Any]]) -> bool:
    return any(isinstance(record, dict) and record.get("kind") == "model_provider" for record in records)


def validate_runtime_context(context: RuntimeContext) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    os_plan = context.os_plan if isinstance(context.os_plan, dict) else {}
    required = set(os_plan.get("required_capabilities") or [])
    if "chat_model" in required and not context.capability_index.get("model_providers"):
        issues.append(
            {
                "code": "missing_model_provider",
                "severity": "blocking",
                "message": "No active model provider connection is available for a model-backed run.",
            }
        )
    for requirement in os_plan.get("connection_requirements") or []:
        if isinstance(requirement, dict):
            issues.append(
                {
                    "code": "missing_connection",
                    "severity": "blocking",
                    "message": f"Missing required connection: {requirement.get('connection')}",
                    "details": {
                        "capability_id": requirement.get("capability_id"),
                        "connection": requirement.get("connection"),
                    },
                }
            )
    if os_plan.get("needs_confirmation"):
        issues.append(
            {
                "code": "permission_confirmation_required",
                "severity": "pending_confirmation",
                "message": "One or more capabilities require explicit user confirmation before runtime use.",
            }
        )
    if os_plan and not os_plan.get("runtime_ready", False):
        issues.append(
            {
                "code": "runtime_not_ready",
                "severity": "blocking",
                "message": "The OS plan is not runtime-ready; inspect missing capabilities and connections.",
            }
        )
    tool_names = set(context.tool_registry.names())
    if legacy_wrds_capability_enabled(context.enabled_capabilities):
        if not context.capability_index.get("financial_data_sources"):
            issues.append(legacy_wrds_missing_connection_issue())
        if legacy_wrds_status_tool_name() not in tool_names:
            issues.append(legacy_wrds_tools_not_registered_issue())
    return dedupe_issues(issues)


def dedupe_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for issue in issues:
        key = (
            issue.get("code"),
            issue.get("message"),
            str(issue.get("details") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(issue)
    return output
