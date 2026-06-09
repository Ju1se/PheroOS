from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from runtime.agent_registry import AgentRegistry
from runtime.capability_registry import (
    CapabilityManifest,
    CapabilityRegistry,
    CapabilityStateStore,
    DEFAULT_TENANT_ID,
)
from runtime.connection_control import ConnectionControlPlane
from runtime.legacy_os_intents import (
    infer_legacy_intent,
    is_legacy_investment_intent,
    is_short_entity_query as legacy_is_short_entity_query,
    legacy_intent_reason as compatibility_legacy_intent_reason,
    legacy_required_capability_types,
    legacy_unknown_committee_member_warning,
    looks_like_public_company_reference as legacy_looks_like_public_company_reference,
    needs_public_financial_data as legacy_needs_public_financial_data,
)
from runtime.permission_policy import evaluate_capability_permissions
from runtime.swarm.goal_router import build_goal_routed_swarm_plan
from runtime.swarm.protocol_loader import load_protocol_from_capability


@dataclass(frozen=True)
class OSKernel:
    registry: CapabilityRegistry
    state_store: CapabilityStateStore
    control_plane: ConnectionControlPlane
    agent_registry: AgentRegistry | None = None

    def plan(
        self,
        *,
        task: str,
        tenant_id: str = DEFAULT_TENANT_ID,
        auto_enable: bool = True,
        selected_agent_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        static_intent = infer_intent(task)
        protocol_intent = self.protocol_declared_intent(task=task, fallback_intent=static_intent)
        intent = str(protocol_intent.get("intent") or static_intent)
        protocol_selected = protocol_intent.get("source") == "capability_protocol_intent"
        selected_protocol_capability_ids = selected_protocol_ids(protocol_intent) if protocol_selected else None
        protocol_required_types = self.protocol_required_capability_types(
            intent=intent,
            capability_ids=selected_protocol_capability_ids,
        )
        protocol_requirement_gap = protocol_selected and not protocol_required_types
        required_types = required_capability_types(
            task=task,
            intent=intent,
            protocol_required_capability_types=protocol_required_types,
            suppress_legacy_static_fallback=protocol_selected,
        )
        os_routing_trace = build_os_routing_trace(
            task=task,
            static_intent=static_intent,
            protocol_intent=protocol_intent,
            selected_intent=intent,
            protocol_required_capability_types=protocol_required_types,
            required_capability_types=required_types,
            protocol_requirement_gap=protocol_requirement_gap,
        )
        active_ids_before = set(self.state_store.enabled_ids(tenant_id=tenant_id))
        disabled_ids = set(self.state_store.disabled_ids(tenant_id=tenant_id))
        active_manifests = manifests_by_ids(self.registry, active_ids_before)
        connection_index = self.control_plane.capability_index(tenant_id=tenant_id)
        active_types = capability_types(active_manifests).union(connection_capability_types(connection_index))
        missing_types = [item for item in required_types if item not in active_types]

        candidates = self.registry.resolve_required(missing_types)
        auto_enabled: list[str] = []
        needs_confirmation: list[dict[str, Any]] = []
        missing_capabilities: list[str] = []
        permission_grants: list[dict[str, Any]] = []
        planned_capability_ids: set[str] = set()

        for required_type in missing_types:
            matching = [manifest for manifest in candidates if required_type in manifest.capability_types]
            if not matching:
                missing_capabilities.append(required_type)
                continue
            disabled_matching = [manifest for manifest in matching if manifest.id in disabled_ids]
            matching = [manifest for manifest in matching if manifest.id not in disabled_ids]
            if not matching:
                manifest = disabled_matching[0]
                if manifest.id in planned_capability_ids:
                    continue
                planned_capability_ids.add(manifest.id)
                decision = evaluate_capability_permissions(manifest)
                needs_confirmation.append(
                    {
                        "capability": manifest.to_public_dict(),
                        "permission_decision": decision.to_dict(),
                        "reason": "disabled_by_user",
                    }
                )
                continue
            manifest = matching[0]
            if manifest.id in planned_capability_ids:
                continue
            planned_capability_ids.add(manifest.id)
            decision = evaluate_capability_permissions(manifest)
            if auto_enable and decision.auto_enable:
                self.state_store.enable(
                    capability_id=manifest.id,
                    tenant_id=tenant_id,
                    reason=f"os:auto-enable:{intent}",
                    permission_grants=decision.permission_grants,
                )
                auto_enabled.append(manifest.id)
                permission_grants.append(decision.to_dict())
            else:
                needs_confirmation.append(
                    {
                        "capability": manifest.to_public_dict(),
                        "permission_decision": decision.to_dict(),
                        "reason": "permission_confirmation_required"
                        if decision.needs_confirmation
                        else "manual_confirmation_required",
                    }
                )

        enabled_manifests = manifests_by_ids(
            self.registry,
            set(self.state_store.enabled_ids(tenant_id=tenant_id)),
        )
        enabled_capability_ids = {manifest.id for manifest in enabled_manifests}
        available_types = capability_types(enabled_manifests).union(connection_capability_types(connection_index))
        connection_requirements = required_connections(enabled_manifests, self.control_plane, tenant_id=tenant_id)
        still_missing_types = [item for item in required_types if item not in available_types]
        capability_runtime_ready = (
            not protocol_requirement_gap
            and not still_missing_types
            and not connection_requirements
            and not needs_confirmation
        )

        swarm_plan = self.swarm_plan(
            task=task,
            intent=intent,
            required_capability_types=required_types,
            enabled_capability_ids=enabled_capability_ids,
            extra_protocol_capability_ids=selected_protocol_capability_ids if protocol_requirement_gap else set(),
            selected_agent_ids=selected_agent_ids,
        )
        protocol_target_gap = swarm_protocol_target_gap(swarm_plan)
        runtime_ready = capability_runtime_ready and not protocol_target_gap

        return {
            "tenant_id": tenant_id,
            "intent": intent,
            "intent_source": protocol_intent.get("source") or "legacy_infer_intent",
            "protocol_intent_matches": protocol_intent.get("matches", []),
            "required_capabilities": required_types,
            "os_routing_trace": os_routing_trace,
            "available_capabilities": sorted(available_types),
            "missing_capabilities": sorted(set(missing_capabilities + still_missing_types)),
            "auto_enabled": sorted(set(auto_enabled)),
            "needs_confirmation": needs_confirmation,
            "needs_capability": bool(protocol_requirement_gap or protocol_target_gap),
            "connection_requirements": connection_requirements,
            "permission_grants": permission_grants,
            "enabled_capabilities": [manifest.to_public_dict() for manifest in enabled_manifests],
            "disabled_capabilities": sorted(disabled_ids),
            "agent_plan": self.agent_plan(
                enabled_capability_ids=enabled_capability_ids,
                selected_agent_ids=selected_agent_ids,
                swarm_plan=swarm_plan,
            ),
            "committee_plan": self.committee_plan(
                intent=intent,
                enabled_capability_ids=enabled_capability_ids,
                selected_agent_ids=selected_agent_ids,
                swarm_plan=swarm_plan,
            ),
            "swarm_plan": swarm_plan,
            "runtime_ready": runtime_ready,
        }

    def protocol_declared_intent(self, *, task: str, fallback_intent: str) -> dict[str, Any]:
        manifests, _diagnostics = self.registry.load()
        matches: list[dict[str, Any]] = []
        for manifest in manifests:
            protocol = load_protocol_from_capability(manifest.to_public_dict())
            if protocol.generated_legacy_protocol:
                continue
            declared_intents = protocol.intents
            for declared_intent in declared_intents:
                match = protocol_intent_match_details(task, declared_intent, manifest, protocol=protocol)
                if match and protocol_intent_match_allowed(match, declared_intent, fallback_intent):
                    matches.append(
                        {
                            "capability_id": manifest.id,
                            "intent": declared_intent,
                            "source": protocol.source,
                            "generated_legacy_protocol": protocol.generated_legacy_protocol,
                            "score": match["score"],
                            "matched_markers": match["matched_markers"],
                            "identity_match_count": match["identity_match_count"],
                            "keyword_match_count": match["keyword_match_count"],
                        }
                    )
        if matches:
            matches.sort(
                key=lambda item: (
                    str(item.get("intent")) != str(fallback_intent),
                    -float(item.get("score") or 0),
                    bool(item.get("generated_legacy_protocol")),
                    str(item.get("capability_id")),
                )
            )
            return {
                "intent": matches[0]["intent"],
                "source": "capability_protocol_intent",
                "selected_capability_id": matches[0]["capability_id"],
                "matches": matches,
            }
        return {"intent": fallback_intent, "source": "legacy_infer_intent", "matches": []}

    def protocol_required_capability_types(
        self,
        *,
        intent: str,
        capability_ids: set[str] | None = None,
    ) -> list[str]:
        manifests, _diagnostics = self.registry.load()
        required: list[str] = []
        for manifest in manifests:
            if capability_ids is not None and manifest.id not in capability_ids:
                continue
            protocol = load_protocol_from_capability(manifest.to_public_dict())
            if protocol.generated_legacy_protocol:
                continue
            if intent in set(protocol.intents):
                required.extend(manifest.capability_types)
                required.extend(protocol_required_types_for_intent(protocol, intent))
        return unique(required)

    def agent_plan(
        self,
        *,
        enabled_capability_ids: set[str],
        selected_agent_ids: list[str] | None = None,
        swarm_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.agent_registry is None:
            return {
                "required": False,
                "selection_mode": "unavailable",
                "agents": [],
                "available_agent_count": 0,
                "warnings": [],
            }
        selected = [str(item) for item in selected_agent_ids or [] if str(item).strip()]
        catalog = self.agent_registry.catalog(enabled_capability_ids=enabled_capability_ids or None)
        agents = catalog.get("agents", []) if isinstance(catalog, dict) else []
        valid_keys = {str(item.get("key")) for item in agents if isinstance(item, dict)}
        unknown = [key for key in selected if key not in valid_keys]
        if selected:
            planned = [item for item in agents if str(item.get("key")) in set(selected)]
            selection_mode = "user_selected"
        elif isinstance(swarm_plan, dict) and swarm_plan.get("activated_agents"):
            activated = {str(item) for item in swarm_plan.get("activated_agents") or []}
            planned = [item for item in agents if str(item.get("key")) in activated]
            selection_mode = "pheromone_response_threshold" if planned else "none"
        else:
            planned = [item for item in agents if item.get("default_enabled")]
            selection_mode = "auto_default" if planned else "none"
        return {
            "required": bool(agents),
            "selection_mode": selection_mode,
            "agents": planned,
            "available_agent_count": len(agents),
            "swarm_targets": (swarm_plan or {}).get("target_signals", []),
            "swarm_allocation": (swarm_plan or {}).get("agent_allocation", []),
            "diagnostics": catalog.get("diagnostics", []) if isinstance(catalog, dict) else [],
            "warnings": [f"unknown agent ignored: {key}" for key in unknown],
        }

    def committee_plan(
        self,
        *,
        intent: str,
        enabled_capability_ids: set[str],
        selected_agent_ids: list[str] | None = None,
        swarm_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.agent_registry is None:
            return {"required": False, "members": [], "selection_mode": "not_required", "warnings": []}
        selected = [str(item) for item in selected_agent_ids or [] if str(item).strip()]
        if not selected and isinstance(swarm_plan, dict):
            selected = [str(item) for item in swarm_plan.get("activated_agents") or [] if str(item).strip()]
        members = self.agent_registry.committee_specs(
            selected_keys=selected,
            enabled_capability_ids=enabled_capability_ids or None,
        )
        all_agents = self.agent_registry.catalog(enabled_capability_ids=enabled_capability_ids or None).get("agents", [])
        valid_keys = {str(item.get("key")) for item in all_agents if isinstance(item, dict)}
        unknown = [key for key in selected if key not in valid_keys]
        if selected and not members:
            members = self.agent_registry.committee_specs(enabled_capability_ids=enabled_capability_ids or None)
        if not members:
            return {
                "required": False,
                "selection_mode": "not_required",
                "members": [],
                "member_count": 0,
                "available_member_count": 0,
                "intent": intent,
                "warnings": [legacy_unknown_committee_member_warning(key) for key in unknown],
            }
        return {
            "required": True,
            "selection_mode": "user_selected"
            if selected_agent_ids
            else "pheromone_response_threshold"
            if selected
            else "auto_default",
            "members": members,
            "member_count": len(members),
            "available_member_count": len(all_agents),
            "intent": intent,
            "warnings": [legacy_unknown_committee_member_warning(key) for key in unknown],
        }

    def swarm_plan(
        self,
        *,
        task: str,
        intent: str,
        required_capability_types: list[str],
        enabled_capability_ids: set[str],
        extra_protocol_capability_ids: set[str] | None = None,
        selected_agent_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if self.agent_registry is None:
            return {
                "schema_version": "pheroos.goal_router.v1",
                "intent": intent,
                "target_signals": [],
                "agent_allocation": [],
                "activated_agents": [],
                "selection_mode": "unavailable",
            }
        catalog = self.agent_registry.catalog(enabled_capability_ids=enabled_capability_ids or None)
        agents = catalog.get("agents", []) if isinstance(catalog, dict) else []
        protocol_capability_ids = set(enabled_capability_ids)
        protocol_capability_ids.update(extra_protocol_capability_ids or set())
        return build_goal_routed_swarm_plan(
            task=task,
            intent=intent,
            required_capability_types=required_capability_types,
            agents=agents,
            capabilities=[manifest.to_public_dict() for manifest in manifests_by_ids(self.registry, protocol_capability_ids)],
            selected_agent_ids=selected_agent_ids,
        )


def infer_intent(task: str) -> str:
    return infer_legacy_intent(task)


def build_os_routing_trace(
    *,
    task: str,
    static_intent: str,
    protocol_intent: dict[str, Any],
    selected_intent: str,
    protocol_required_capability_types: list[str],
    required_capability_types: list[str],
    protocol_requirement_gap: bool = False,
) -> list[dict[str, Any]]:
    protocol_source = str(protocol_intent.get("source") or "").strip()
    protocol_matches = protocol_intent.get("matches") if isinstance(protocol_intent.get("matches"), list) else []
    static_intent_used = protocol_source != "capability_protocol_intent"
    protocol_requirements_used = bool(protocol_required_capability_types)
    if protocol_requirements_used:
        requirement_source = "capability_protocol"
    elif protocol_requirement_gap:
        requirement_source = "capability_protocol_missing_requirements"
    else:
        requirement_source = "legacy_static_fallback"
    trace = [
        {
            "event_type": "os.intent.legacy_inferred",
            "intent": static_intent,
            "used": static_intent_used,
            "reason": legacy_intent_reason(task, static_intent),
        },
        {
            "event_type": "os.intent.selected",
            "intent": selected_intent,
            "source": protocol_source or "legacy_infer_intent",
            "protocol_match_count": len(protocol_matches),
            "legacy_fallback": static_intent_used,
        },
        {
            "event_type": "os.required_capabilities.selected",
            "source": requirement_source,
            "protocol_required_capability_types": list(protocol_required_capability_types),
            "required_capability_types": list(required_capability_types),
            "legacy_fallback": not protocol_requirements_used and not protocol_requirement_gap,
            "needs_capability": bool(protocol_requirement_gap),
        },
    ]
    if protocol_requirement_gap:
        trace.append(
            {
                "event_type": "os.required_capabilities.needs_capability",
                "intent": selected_intent,
                "reason": "selected capability protocol declared an intent but no capability types or required_capability_types",
                "selected_capability_id": protocol_intent.get("selected_capability_id"),
                "protocol_match_count": len(protocol_matches),
            }
        )
    return trace


def selected_protocol_ids(protocol_intent: dict[str, Any]) -> set[str]:
    capability_id = str(protocol_intent.get("selected_capability_id") or "").strip()
    return {capability_id} if capability_id else set()


def protocol_required_types_for_intent(protocol: Any, intent: str) -> list[str]:
    by_intent = getattr(protocol, "required_capability_types_by_intent", {}) or {}
    if isinstance(by_intent, dict) and intent in by_intent:
        return [str(item).strip() for item in by_intent.get(intent) or [] if str(item).strip()]
    return [
        str(item).strip()
        for item in getattr(protocol, "required_capability_types", []) or []
        if str(item).strip()
    ]


def swarm_protocol_target_gap(swarm_plan: dict[str, Any]) -> bool:
    trace = swarm_plan.get("routing_trace") if isinstance(swarm_plan, dict) else []
    if not isinstance(trace, list):
        return False
    return any(
        isinstance(item, dict) and item.get("event_type") == "goal_router.protocol_targets_missing"
        for item in trace
    )


def legacy_intent_reason(task: str, intent: str) -> dict[str, Any]:
    return dict(compatibility_legacy_intent_reason(task, intent))


def matched_hints(lowered_text: str, hints: tuple[str, ...]) -> list[str]:
    return [hint for hint in hints if contains_hint(lowered_text, hint)]


def is_investment_intent(task: str) -> bool:
    return is_legacy_investment_intent(task)


def looks_like_public_company_reference(task: str) -> bool:
    return legacy_looks_like_public_company_reference(task)


def contains_any_hint(lowered_text: str, hints: tuple[str, ...]) -> bool:
    return any(contains_hint(lowered_text, hint) for hint in hints)


def contains_hint(lowered_text: str, hint: str) -> bool:
    needle = hint.lower()
    if re.fullmatch(r"[a-z0-9][a-z0-9 .:/&+-]*", needle):
        return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", lowered_text) is not None
    return needle in lowered_text


def protocol_intent_marker_matches_task(
    task: str,
    declared_intent: str,
    manifest: CapabilityManifest,
    *,
    protocol: Any | None = None,
) -> bool:
    return bool(protocol_intent_match_details(task, declared_intent, manifest, protocol=protocol))


def protocol_intent_match_details(
    task: str,
    declared_intent: str,
    manifest: CapabilityManifest,
    *,
    protocol: Any | None = None,
) -> dict[str, Any]:
    lowered = str(task or "").lower()
    identity_markers, keyword_markers = protocol_intent_marker_groups(declared_intent, manifest, protocol=protocol)
    identity_matches = sorted({marker for marker in identity_markers if contains_hint(lowered, marker)})
    keyword_matches = sorted({marker for marker in keyword_markers if contains_hint(lowered, marker)})
    if not identity_matches and not keyword_matches:
        return {}
    return {
        "score": (3.0 * len(identity_matches)) + len(keyword_matches),
        "matched_markers": (identity_matches + keyword_matches)[:12],
        "identity_match_count": len(identity_matches),
        "keyword_match_count": len(keyword_matches),
    }


def protocol_intent_match_allowed(match: dict[str, Any], declared_intent: str, fallback_intent: str) -> bool:
    if str(declared_intent) == str(fallback_intent):
        return True
    if str(fallback_intent) in {"", "general_chat"}:
        return True
    if int(match.get("identity_match_count") or 0) > 0:
        return True
    return int(match.get("keyword_match_count") or 0) >= 2


def protocol_intent_markers(
    declared_intent: str,
    manifest: CapabilityManifest,
    *,
    protocol: Any | None = None,
) -> tuple[str, ...]:
    identity_markers, keyword_markers = protocol_intent_marker_groups(declared_intent, manifest, protocol=protocol)
    return tuple(marker for marker in [*identity_markers, *keyword_markers] if marker.strip())


def protocol_intent_marker_groups(
    declared_intent: str,
    manifest: CapabilityManifest,
    *,
    protocol: Any | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    intent = str(declared_intent or "").strip()
    if not intent:
        return (), ()
    identity_markers = {
        intent,
        intent.replace("_", " "),
        intent.replace("_", "-"),
        str(manifest.id or ""),
        str(manifest.id or "").replace("-", " "),
        str(manifest.name or ""),
    }
    keyword_markers: set[str] = set()
    if protocol is not None:
        intent_keywords = getattr(protocol, "intent_keywords", {}) or {}
        if isinstance(intent_keywords, dict):
            keyword_markers.update(str(keyword) for keyword in intent_keywords.get(intent, []) or [])
        for target in getattr(protocol, "targets", []) or []:
            if protocol_target_applies_to_intent(target, intent):
                keyword_markers.update(str(keyword) for keyword in getattr(target, "keywords", []) or [])
    return (
        tuple(expand_marker_variants(identity_markers)),
        tuple(expand_marker_variants(keyword_markers)),
    )


def protocol_target_applies_to_intent(target: Any, intent: str) -> bool:
    compatible = [str(item).strip() for item in getattr(target, "compatible_intents", []) or [] if str(item).strip()]
    return not compatible or str(intent) in compatible


def expand_marker_variants(markers: set[str]) -> tuple[str, ...]:
    output: set[str] = set()
    for marker in markers:
        value = str(marker or "").strip()
        if not value:
            continue
        output.add(value)
        output.add(value.replace("_", " "))
        output.add(value.replace("_", "-"))
        output.add(value.replace("-", " "))
        output.add(value.replace("-", "_"))
    return tuple(marker for marker in output if marker.strip())


def is_short_entity_query(task: str) -> bool:
    return legacy_is_short_entity_query(task)


def required_capability_types(
    *,
    task: str,
    intent: str,
    protocol_required_capability_types: list[str] | None = None,
    suppress_legacy_static_fallback: bool = False,
) -> list[str]:
    return legacy_required_capability_types(
        task=task,
        intent=intent,
        protocol_required_capability_types=protocol_required_capability_types,
        suppress_legacy_static_fallback=suppress_legacy_static_fallback,
    )


def needs_public_financial_data(task: str) -> bool:
    return legacy_needs_public_financial_data(task)


def manifests_by_ids(registry: CapabilityRegistry, capability_ids: set[str]) -> list[CapabilityManifest]:
    manifests, _diagnostics = registry.load()
    return [manifest for manifest in manifests if manifest.id in capability_ids]


def capability_types(manifests: list[CapabilityManifest]) -> set[str]:
    output: set[str] = set()
    for manifest in manifests:
        output.update(manifest.capability_types)
    return output


def required_connections(
    manifests: list[CapabilityManifest],
    control_plane: ConnectionControlPlane,
    *,
    tenant_id: str,
) -> list[dict[str, Any]]:
    active_connections = control_plane.list_active_connections(tenant_id=tenant_id)
    kinds = {str(item.get("kind") or "") for item in active_connections}
    providers = {str(item.get("provider") or item.get("provider_key") or "") for item in active_connections}
    provider_keys = {str(item.get("provider_key") or "") for item in active_connections}
    requirements = []
    for manifest in manifests:
        for connection in manifest.connections:
            if connection == "model_provider" and "model_provider" in kinds:
                continue
            if connection in providers or connection in provider_keys:
                continue
            requirements.append(
                {
                    "capability_id": manifest.id,
                    "connection": connection,
                    "status": "missing",
                }
            )
    return requirements


def connection_capability_types(capability_index: dict[str, Any]) -> set[str]:
    output = set()
    for capability in capability_index.get("capabilities") or []:
        if isinstance(capability, dict) and capability.get("type"):
            output.add(str(capability["type"]))
    if capability_index.get("model_providers"):
        output.add("chat_model")
    return output


def unique(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
