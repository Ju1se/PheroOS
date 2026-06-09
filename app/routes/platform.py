from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.routes.dependencies import (
    get_agent_registry,
    get_capability_registry,
    get_capability_state_store,
    get_connection_control_plane,
    get_os_kernel,
)
from runtime.agent_registry import AgentRegistry
from runtime.capability_registry import CapabilityRegistry, CapabilityStateStore
from runtime.connection_control import DEFAULT_TENANT_ID, ConnectionControlPlane
from runtime.connection_inference import infer_connection
from runtime.legacy_agent_registry import selected_agent_ids_from_metadata
from runtime.os_kernel import OSKernel
from runtime.platform_config import PlatformConfigStore
from runtime.permission_policy import evaluate_capability_permissions
from runtime.swarm.agent_profile import AgentProfileStore
from runtime.swarm.pheromone_store import read_events, read_signals
from runtime.swarm.trace_store import SwarmTraceStore


router = APIRouter(prefix="/platform", tags=["platform"])


class ConnectionPayload(BaseModel):
    name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    base_url: str | None = None
    api_key: str | None = None
    username: str | None = None
    password: str | None = None
    access_token: str | None = None
    account: str | None = None
    database: str | None = None
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class AutoConfigurePayload(BaseModel):
    raw: str = Field(min_length=1)


class InferConnectionPayload(BaseModel):
    raw: str = Field(min_length=1)
    tenant_id: str = DEFAULT_TENANT_ID


class ConfirmConnectionPayload(BaseModel):
    raw: str = Field(min_length=1)
    tenant_id: str = DEFAULT_TENANT_ID
    validate_connection: bool = Field(default=True, alias="validate")
    discover: bool = True


class CapabilityResolvePayload(BaseModel):
    task: str = Field(min_length=1)
    tenant_id: str = DEFAULT_TENANT_ID
    committee_member_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapabilityEnablePayload(BaseModel):
    capability_id: str = Field(min_length=1)
    tenant_id: str = DEFAULT_TENANT_ID
    confirmed: bool = False


def get_platform_config_store() -> PlatformConfigStore:
    return PlatformConfigStore()


@router.get("/config")
def get_platform_config(
    tenant_id: str = DEFAULT_TENANT_ID,
    store: PlatformConfigStore = Depends(get_platform_config_store),
    control_plane: ConnectionControlPlane = Depends(get_connection_control_plane),
) -> dict[str, Any]:
    legacy_config = store.public_config()
    if legacy_config["model_providers"] or legacy_config["data_sources"]:
        return legacy_config
    control_config = control_plane.legacy_public_config(tenant_id=tenant_id)
    if control_config["model_providers"] or control_config["data_sources"]:
        return control_config
    return legacy_config


@router.post("/auto-configure")
def auto_configure_connection(
    payload: AutoConfigurePayload,
    store: PlatformConfigStore = Depends(get_platform_config_store),
) -> dict[str, Any]:
    try:
        inferred = infer_connection(payload.raw)
        if inferred.kind == "model_provider":
            connection = store.upsert_model_provider(inferred.connection_id, inferred.payload)
        else:
            connection = store.upsert_data_source(inferred.connection_id, inferred.payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "kind": inferred.kind,
        "connection_id": inferred.connection_id,
        "connection": connection,
        "confidence": inferred.confidence,
        "reason": inferred.reason,
        "warnings": inferred.warnings,
    }


@router.post("/connections/infer")
def infer_platform_connection(
    payload: InferConnectionPayload,
    control_plane: ConnectionControlPlane = Depends(get_connection_control_plane),
) -> dict[str, Any]:
    try:
        return control_plane.infer(raw=payload.raw, tenant_id=payload.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/connections/confirm")
def confirm_platform_connection(
    payload: ConfirmConnectionPayload,
    control_plane: ConnectionControlPlane = Depends(get_connection_control_plane),
) -> dict[str, Any]:
    try:
        connection = control_plane.confirm(
            raw=payload.raw,
            tenant_id=payload.tenant_id,
            validate=payload.validate_connection,
            discover=payload.discover,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"connection": connection}


@router.get("/connections")
def list_platform_connections(
    tenant_id: str = DEFAULT_TENANT_ID,
    control_plane: ConnectionControlPlane = Depends(get_connection_control_plane),
) -> dict[str, Any]:
    return {"tenant_id": tenant_id, "connections": control_plane.list_connections(tenant_id=tenant_id)}


@router.post("/connections/{connection_id}/test")
def test_platform_connection(
    connection_id: str,
    tenant_id: str = DEFAULT_TENANT_ID,
    control_plane: ConnectionControlPlane = Depends(get_connection_control_plane),
) -> dict[str, Any]:
    try:
        return control_plane.test_connection(connection_id=connection_id, tenant_id=tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/connections/{connection_id}/discover")
def discover_platform_connection(
    connection_id: str,
    tenant_id: str = DEFAULT_TENANT_ID,
    control_plane: ConnectionControlPlane = Depends(get_connection_control_plane),
) -> dict[str, Any]:
    try:
        return control_plane.discover_connection(connection_id=connection_id, tenant_id=tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/connections/{connection_id}/disable")
def disable_platform_connection(
    connection_id: str,
    tenant_id: str = DEFAULT_TENANT_ID,
    control_plane: ConnectionControlPlane = Depends(get_connection_control_plane),
) -> dict[str, Any]:
    try:
        return {"connection": control_plane.disable_connection(connection_id=connection_id, tenant_id=tenant_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/connections/{connection_id}/revoke")
def revoke_platform_connection(
    connection_id: str,
    tenant_id: str = DEFAULT_TENANT_ID,
    control_plane: ConnectionControlPlane = Depends(get_connection_control_plane),
) -> dict[str, Any]:
    try:
        return {"connection": control_plane.revoke_connection(connection_id=connection_id, tenant_id=tenant_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/connections/{connection_id}")
def delete_platform_connection(
    connection_id: str,
    tenant_id: str = DEFAULT_TENANT_ID,
    control_plane: ConnectionControlPlane = Depends(get_connection_control_plane),
) -> dict[str, Any]:
    try:
        return control_plane.delete_connection(connection_id=connection_id, tenant_id=tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/capabilities")
def get_platform_capabilities(
    tenant_id: str = DEFAULT_TENANT_ID,
    control_plane: ConnectionControlPlane = Depends(get_connection_control_plane),
) -> dict[str, Any]:
    return control_plane.capability_index(tenant_id=tenant_id)


@router.get("/capability-catalog")
def get_capability_catalog(
    registry: CapabilityRegistry = Depends(get_capability_registry),
) -> dict[str, Any]:
    try:
        return registry.catalog()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/capabilities/resolve")
def resolve_platform_capabilities(
    payload: CapabilityResolvePayload,
    kernel: OSKernel = Depends(get_os_kernel),
) -> dict[str, Any]:
    return kernel.plan(
        task=payload.task,
        tenant_id=payload.tenant_id,
        auto_enable=False,
        selected_agent_ids=selected_agent_ids_from_payload(payload),
    )


@router.post("/os/plan")
def plan_platform_os(
    payload: CapabilityResolvePayload,
    kernel: OSKernel = Depends(get_os_kernel),
) -> dict[str, Any]:
    return kernel.plan(
        task=payload.task,
        tenant_id=payload.tenant_id,
        auto_enable=True,
        selected_agent_ids=selected_agent_ids_from_payload(payload),
    )


def selected_agent_ids_from_payload(payload: CapabilityResolvePayload) -> list[str]:
    if payload.committee_member_ids:
        return [str(item) for item in payload.committee_member_ids if str(item).strip()]
    return selected_agent_ids_from_metadata(payload.metadata)


@router.post("/capabilities/enable")
def enable_platform_capability(
    payload: CapabilityEnablePayload,
    registry: CapabilityRegistry = Depends(get_capability_registry),
    state_store: CapabilityStateStore = Depends(get_capability_state_store),
) -> dict[str, Any]:
    manifest = registry.get(payload.capability_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="capability not found")
    decision = evaluate_capability_permissions(manifest)
    if decision.needs_confirmation and not payload.confirmed:
        return {
            "enabled": False,
            "status": "needs_confirmation",
            "capability": manifest.to_public_dict(),
            "permission_decision": decision.to_dict(),
        }
    state = state_store.enable(
        capability_id=manifest.id,
        tenant_id=payload.tenant_id,
        reason="manual-confirmed" if payload.confirmed else "manual",
        permission_grants=decision.permission_grants,
    )
    return {
        "enabled": True,
        "status": "enabled",
        "capability": manifest.to_public_dict(),
        "state": state,
        "permission_decision": decision.to_dict(),
    }


@router.post("/capabilities/{capability_id}/disable")
def disable_platform_capability(
    capability_id: str,
    tenant_id: str = DEFAULT_TENANT_ID,
    state_store: CapabilityStateStore = Depends(get_capability_state_store),
) -> dict[str, Any]:
    was_enabled = state_store.disable(capability_id=capability_id, tenant_id=tenant_id)
    return {
        "capability_id": capability_id,
        "status": "disabled",
        "was_enabled": was_enabled,
    }


@router.get("/capabilities/active")
def get_active_platform_capabilities(
    tenant_id: str = DEFAULT_TENANT_ID,
    registry: CapabilityRegistry = Depends(get_capability_registry),
    state_store: CapabilityStateStore = Depends(get_capability_state_store),
) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "capabilities": state_store.active_capabilities(registry=registry, tenant_id=tenant_id),
    }


@router.get("/agents")
def get_platform_agents(
    tenant_id: str = DEFAULT_TENANT_ID,
    registry: AgentRegistry = Depends(get_agent_registry),
    capability_registry: CapabilityRegistry = Depends(get_capability_registry),
    state_store: CapabilityStateStore = Depends(get_capability_state_store),
) -> dict[str, Any]:
    active_capabilities = state_store.active_capabilities(registry=capability_registry, tenant_id=tenant_id)
    active_ids = {str(item.get("id")) for item in active_capabilities if item.get("id")}
    return {
        "tenant_id": tenant_id,
        **registry.catalog(enabled_capability_ids=active_ids or None),
    }


@router.get("/swarm/signals")
def list_swarm_signals(
    run_id: str | None = None,
    limit: int = 200,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> dict[str, Any]:
    return {"tenant_id": tenant_id, "data": read_signals(run_id=run_id, tenant_id=tenant_id, limit=limit)}


@router.get("/swarm/events")
def list_swarm_events(
    run_id: str | None = None,
    limit: int = 200,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> dict[str, Any]:
    return {"tenant_id": tenant_id, "data": read_events(run_id=run_id, tenant_id=tenant_id, limit=limit)}


@router.get("/swarm/agent-profiles")
def list_swarm_agent_profiles(tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
    profiles = AgentProfileStore().load_all(tenant_id=tenant_id)
    return {"tenant_id": tenant_id, "data": [profile.to_dict() for profile in profiles.values()]}


@router.get("/swarm/runs/{run_id}/timeline")
def get_swarm_run_timeline(run_id: str, limit: int = 500, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
    return {"data": SwarmTraceStore().timeline(run_id=run_id, limit=limit, tenant_id=tenant_id)}


@router.get("/swarm/runs/{run_id}/why-blocked/{target}")
def get_swarm_run_why_blocked(run_id: str, target: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
    return SwarmTraceStore().why_blocked(run_id=run_id, target=target, tenant_id=tenant_id)


@router.get("/swarm/runs/{run_id}/why-committed")
def get_swarm_run_why_committed(run_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
    return SwarmTraceStore().why_committed(run_id=run_id, tenant_id=tenant_id)


@router.get("/swarm/runs/{run_id}/evidence-graph")
def get_swarm_run_evidence_graph(run_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
    return SwarmTraceStore().evidence_graph(run_id=run_id, tenant_id=tenant_id)


@router.get("/swarm/runs/{run_id}/agent-allocation")
def get_swarm_run_agent_allocation(run_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
    return SwarmTraceStore().agent_allocation(run_id=run_id, tenant_id=tenant_id)


@router.get("/swarm/runs/{run_id}/why-agent/{agent_id}")
def get_swarm_run_why_agent(run_id: str, agent_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
    return SwarmTraceStore().why_agent(run_id=run_id, agent_id=agent_id, tenant_id=tenant_id)


@router.get("/swarm/runs/{run_id}/tool-events")
def get_swarm_run_tool_events(run_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
    return SwarmTraceStore().tool_events(run_id=run_id, tenant_id=tenant_id)


@router.get("/swarm/runs/{run_id}/permission-events")
def get_swarm_run_permission_events(run_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
    return SwarmTraceStore().permission_events(run_id=run_id, tenant_id=tenant_id)


@router.get("/swarm/runs/{run_id}/pheromone-snapshot")
def get_swarm_run_pheromone_snapshot(run_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
    return SwarmTraceStore().reconstruct_pheromone_snapshot(run_id=run_id, tenant_id=tenant_id)


@router.get("/swarm/runs/{run_id}/recovery-lineage/{target}")
def get_swarm_run_recovery_lineage(run_id: str, target: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
    return SwarmTraceStore().recovery_lineage(run_id=run_id, target=target, tenant_id=tenant_id)


@router.get("/swarm/runs/{run_id}/capability-protocol")
def get_swarm_run_capability_protocol(run_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
    return SwarmTraceStore().capability_protocol(run_id=run_id, tenant_id=tenant_id)


@router.put("/model-providers/{connection_id}")
def upsert_model_provider(
    connection_id: str,
    payload: ConnectionPayload,
    store: PlatformConfigStore = Depends(get_platform_config_store),
) -> dict[str, Any]:
    try:
        return store.upsert_model_provider(connection_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/data-sources/{connection_id}")
def upsert_data_source(
    connection_id: str,
    payload: ConnectionPayload,
    store: PlatformConfigStore = Depends(get_platform_config_store),
) -> dict[str, Any]:
    try:
        return store.upsert_data_source(connection_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/model-providers/{connection_id}")
def delete_model_provider(
    connection_id: str,
    store: PlatformConfigStore = Depends(get_platform_config_store),
) -> dict[str, Any]:
    return {"deleted": store.delete_model_provider(connection_id)}


@router.delete("/data-sources/{connection_id}")
def delete_data_source(
    connection_id: str,
    store: PlatformConfigStore = Depends(get_platform_config_store),
) -> dict[str, Any]:
    return {"deleted": store.delete_data_source(connection_id)}
