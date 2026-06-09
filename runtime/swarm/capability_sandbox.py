from __future__ import annotations

from typing import Any

from runtime.capability_manifest_security import (
    BLOCKING_SIGNAL_TYPES,
    DANGEROUS_IMPORTS,
    UNTRUSTED_LEVELS,
    build_manifest_security_report,
    normalize_sandbox_policy,
    normalize_trust_level,
)
from runtime.permission_policy import CONFIRMATION_REQUIRED_PERMISSIONS
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState


def build_capability_sandbox_auditor_report(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    enabled = metadata.get("enabled_capabilities") or metadata.get("capabilities")
    capability_index = metadata.get("capability_index") if isinstance(metadata.get("capability_index"), dict) else {}
    catalog_caps = capability_index.get("capabilities") if isinstance(capability_index.get("capabilities"), list) else []
    capabilities = normalize_capabilities(enabled) + normalize_capabilities(catalog_caps)
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for capability in capabilities:
        cap_id = str(capability.get("id") or capability.get("capability_id") or "").strip()
        if not cap_id or cap_id in seen:
            continue
        seen.add(cap_id)
        unique.append(capability)

    findings: list[dict[str, Any]] = []
    for capability in unique:
        cap_id = str(capability.get("id") or capability.get("capability_id") or "")
        trust_level = normalize_trust_level(capability.get("trust_level") or capability.get("provider"))
        permissions = [str(item) for item in capability.get("permissions") or []]
        swarm = capability.get("swarm") if isinstance(capability.get("swarm"), dict) else {}
        sandbox = normalize_sandbox_policy(capability.get("sandbox"))
        security_report = capability.get("security_diagnostics")
        if not isinstance(security_report, dict):
            security_report = build_manifest_security_report(capability)
        for item in security_report.get("findings") or []:
            if not isinstance(item, dict):
                continue
            findings.append(
                finding(
                    cap_id,
                    str(item.get("code") or "security_finding"),
                    str(item.get("severity") or "medium"),
                    str(item.get("message") or "Capability security finding."),
                )
            )
        dangerous = sorted(set(permissions).intersection(CONFIRMATION_REQUIRED_PERMISSIONS))
        if dangerous:
            findings.append(
                finding(cap_id, "dangerous_permission", "high", f"Capability requests confirmation-required permissions: {', '.join(dangerous)}")
            )
        dangerous_imports = sorted(set(str(item) for item in capability.get("allowed_imports") or []).intersection(DANGEROUS_IMPORTS))
        if dangerous_imports:
            severity = "high" if trust_level in UNTRUSTED_LEVELS else "medium"
            findings.append(
                finding(cap_id, "dangerous_allowed_import", severity, f"Capability declares dangerous imports: {', '.join(dangerous_imports)}")
            )
        if sandbox.get("secrets") != "no_direct_access":
            findings.append(finding(cap_id, "secret_access_policy_violation", "high", "Capability requests direct secret access."))
        if sandbox.get("model_calls") != "gateway_only":
            findings.append(finding(cap_id, "model_gateway_bypass", "high", "Capability must call models through ModelGateway."))
        if sandbox.get("tools") != "registry_only":
            findings.append(finding(cap_id, "tool_registry_bypass", "high", "Capability must execute tools through ToolRegistry."))
        if trust_level in UNTRUSTED_LEVELS:
            findings.append(finding(cap_id, "untrusted_capability", "medium", "Capability is not trusted first-party code."))
            allowed = set(str(item) for item in swarm.get("allowed_signal_types") or [])
            if BLOCKING_SIGNAL_TYPES.intersection(allowed):
                findings.append(
                    finding(cap_id, "untrusted_blocking_signal", "high", "Untrusted capability must not emit blocking or verified governance signals.")
                )
            if sandbox.get("network") in {"arbitrary", "open", "unrestricted", "network:arbitrary"}:
                findings.append(finding(cap_id, "untrusted_arbitrary_network", "high", "Untrusted capability cannot use arbitrary network access."))
            if sandbox.get("filesystem") in {"write", "read_write", "workspace_write", "filesystem:write"}:
                findings.append(finding(cap_id, "untrusted_filesystem_write", "high", "Untrusted capability cannot write to the filesystem."))

    findings = dedupe_findings(findings)

    high_count = len([item for item in findings if item.get("severity") == "high"])
    status = "blocked" if high_count else "watch" if findings else "clear"
    return {
        "schema_version": "pheroos.capability_sandbox_auditor.v1",
        "status": status,
        "capability_count": len(unique),
        "findings": findings,
        "high_risk_count": high_count,
        "sandbox_policy": {
            "third_party_default_lane": "inspection",
            "untrusted_can_emit_blocking": False,
            "model_access": "model_gateway_only",
            "tool_access": "tool_registry_only",
            "secret_access": "secret_ref_only",
            "filesystem": "read_only_by_default",
        },
    }


def capability_sandbox_auditor_signals(state: dict[str, Any], report: dict[str, Any]) -> list[PheromoneSignal]:
    run_id = str(state.get("run_id") or "unknown")
    tenant_id = str((state.get("metadata") or {}).get("tenant_id") or "default")
    signals: list[PheromoneSignal] = []
    for item in report.get("findings") or []:
        high = item.get("severity") == "high"
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.QUARANTINE if high else SignalType.RISK,
                target=f"capability:{item.get('capability_id')}",
                content=str(item.get("message") or "Capability sandbox finding."),
                strength=0.9 if high else 0.58,
                confidence=0.84,
                priority="hard" if high else "normal",
                blocking=high,
                verification_state=VerificationState.BLOCKING if high else VerificationState.VERIFIED,
                source_module="capability_sandbox_auditor",
                metadata=item,
            )
        )
    return signals


def normalize_capabilities(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if isinstance(value.get("capabilities"), list):
            return normalize_capabilities(value.get("capabilities"))
        return [value]
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def finding(capability_id: str, code: str, severity: str, message: str) -> dict[str, Any]:
    return {"capability_id": capability_id, "code": code, "severity": severity, "message": message}


def dedupe_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for item in findings:
        key = (str(item.get("capability_id")), str(item.get("code")), str(item.get("message")))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
