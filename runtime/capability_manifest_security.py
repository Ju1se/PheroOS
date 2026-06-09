from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


KNOWN_TRUST_LEVELS = {
    "core_system",
    "first_party_reviewed",
    "trusted_first_party",
    "user_installed",
    "third_party_untrusted",
    "external_content",
}

TRUST_ALIASES = {
    "first_party": "first_party_reviewed",
    "trusted": "trusted_first_party",
    "third_party": "third_party_untrusted",
    "untrusted": "third_party_untrusted",
}

DEFAULT_SANDBOX_POLICY = {
    "network": "deny_by_default",
    "filesystem": "read_only",
    "secrets": "no_direct_access",
    "model_calls": "gateway_only",
    "tools": "registry_only",
}

DANGEROUS_IMPORTS = {
    "anthropic",
    "boto3",
    "httpx",
    "openai",
    "os",
    "requests",
    "socket",
    "subprocess",
    "urllib",
    "wrds",
    "zhipuai",
}

UNTRUSTED_LEVELS = {"third_party_untrusted", "external_content"}
BLOCKING_SIGNAL_TYPES = {"stop_signal", "quarantine", "trust_badge"}


def normalize_trust_level(value: Any) -> str:
    raw = str(value or "first_party_reviewed").strip().lower()
    if not raw:
        return "first_party_reviewed"
    return TRUST_ALIASES.get(raw, raw)


def normalize_sandbox_policy(value: Any) -> dict[str, str]:
    policy = dict(DEFAULT_SANDBOX_POLICY)
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).strip()
            if key_text:
                policy[key_text] = str(item).strip() if str(item).strip() else policy.get(key_text, "")
    return policy


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def string_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def build_manifest_security_report(payload: dict[str, Any], *, capability_dir: Path | None = None) -> dict[str, Any]:
    trust_level = normalize_trust_level(payload.get("trust_level"))
    sandbox = normalize_sandbox_policy(payload.get("sandbox"))
    allowed_imports = string_list(payload.get("allowed_imports"))
    network_allowlist = string_list(payload.get("network_allowlist"))
    signature = string_dict(payload.get("signature"))
    declared_checksum = str(payload.get("checksum") or "").strip() or None
    computed_checksum = compute_capability_checksum(capability_dir) if capability_dir else None
    findings: list[dict[str, str]] = []

    raw_trust = str(payload.get("trust_level") or "").strip().lower()
    if raw_trust and normalize_trust_level(raw_trust) not in KNOWN_TRUST_LEVELS:
        findings.append(
            finding("unknown_trust_level", "high", f"Unknown trust level: {raw_trust}")
        )

    unknown_sandbox_keys = sorted(set(sandbox) - set(DEFAULT_SANDBOX_POLICY))
    for key in unknown_sandbox_keys:
        findings.append(finding("unknown_sandbox_key", "medium", f"Unknown sandbox policy key: {key}"))

    if sandbox.get("secrets") != "no_direct_access":
        findings.append(
            finding(
                "secret_access_policy_violation",
                "high",
                "Capabilities must use SecretStore handles only; direct secret access is forbidden.",
            )
        )
    if sandbox.get("model_calls") != "gateway_only":
        findings.append(
            finding(
                "model_gateway_bypass",
                "high",
                "Capabilities must route all model calls through ModelGateway.",
            )
        )
    if sandbox.get("tools") != "registry_only":
        findings.append(
            finding(
                "tool_registry_bypass",
                "high",
                "Capabilities must route all tool execution through ToolRegistry.",
            )
        )

    if trust_level in UNTRUSTED_LEVELS:
        if sandbox.get("network") in {"arbitrary", "open", "unrestricted", "network:arbitrary"}:
            findings.append(
                finding("untrusted_arbitrary_network", "high", "Untrusted capabilities cannot request arbitrary network access.")
            )
        if sandbox.get("filesystem") in {"write", "read_write", "workspace_write", "filesystem:write"}:
            findings.append(
                finding("untrusted_filesystem_write", "high", "Untrusted capabilities cannot request filesystem write access.")
            )
        if not signature and not declared_checksum:
            findings.append(
                finding("untrusted_unsigned_capability", "high", "Untrusted capabilities require a signature or checksum before activation.")
            )

    dangerous_imports = sorted(set(allowed_imports).intersection(DANGEROUS_IMPORTS))
    if dangerous_imports:
        severity = "high" if trust_level in UNTRUSTED_LEVELS else "medium"
        findings.append(
            finding(
                "dangerous_allowed_import",
                severity,
                f"Capability declares dangerous imports: {', '.join(dangerous_imports)}",
            )
        )

    if sandbox.get("network") == "allowlisted_domains" and not network_allowlist:
        findings.append(
            finding("missing_network_allowlist", "medium", "allowlisted_domains requires network_allowlist entries.")
        )

    swarm = payload.get("swarm") if isinstance(payload.get("swarm"), dict) else {}
    allowed_signals = {str(item) for item in swarm.get("allowed_signal_types") or []}
    if trust_level in UNTRUSTED_LEVELS and BLOCKING_SIGNAL_TYPES.intersection(allowed_signals):
        findings.append(
            finding(
                "untrusted_blocking_signal",
                "high",
                "Untrusted capabilities cannot emit blocking or verified governance signals.",
            )
        )

    signature_status = verify_signature_status(
        signature=signature,
        declared_checksum=declared_checksum,
        computed_checksum=computed_checksum,
    )
    if signature_status["status"] == "checksum_mismatch":
        findings.append(
            finding("checksum_mismatch", "high", "Capability checksum does not match the manifest declaration.")
        )

    high_count = len([item for item in findings if item.get("severity") == "high"])
    medium_count = len([item for item in findings if item.get("severity") == "medium"])
    return {
        "schema_version": "capability.security.v1",
        "status": "blocked" if high_count else "warning" if medium_count else "ok",
        "trust_level": trust_level,
        "sandbox": sandbox,
        "allowed_imports": allowed_imports,
        "network_allowlist": network_allowlist,
        "signature": signature,
        "checksum": declared_checksum,
        "computed_checksum": computed_checksum,
        "signature_status": signature_status,
        "roadmap": capability_security_roadmap(),
        "findings": findings,
        "high_risk_count": high_count,
        "medium_risk_count": medium_count,
    }


def capability_security_roadmap() -> dict[str, Any]:
    return {
        "schema_version": "pheroos.capability_security_roadmap.v0.1",
        "current_enforcement_stage": "v0.1_local_trusted_capabilities",
        "stages": [
            {
                "stage": "v0.1_local_trusted_capabilities",
                "status": "active",
                "controls": [
                    {"id": "manifest_validation", "status": "enforced"},
                    {"id": "checksum_display", "status": "diagnostic"},
                    {"id": "network_allowlist_declaration", "status": "declared"},
                    {"id": "permission_confirmation", "status": "enforced"},
                    {"id": "quarantine_signal", "status": "diagnostic"},
                    {"id": "model_gateway_boundary", "status": "enforced"},
                    {"id": "tool_registry_boundary", "status": "enforced"},
                    {"id": "secret_handle_boundary", "status": "enforced"},
                ],
            },
            {
                "stage": "v0.2_signed_capabilities",
                "status": "planned",
                "controls": [
                    {"id": "capability_signing", "status": "planned"},
                    {"id": "public_key_trust_store", "status": "planned"},
                    {"id": "provenance_metadata", "status": "planned"},
                    {"id": "revocation_list", "status": "planned"},
                    {"id": "install_audit_log", "status": "planned"},
                ],
            },
            {
                "stage": "v0.3_sandboxed_execution",
                "status": "planned",
                "controls": [
                    {"id": "restricted_imports", "status": "planned"},
                    {"id": "subprocess_isolation", "status": "planned"},
                    {"id": "network_policy_enforcement", "status": "planned"},
                    {"id": "filesystem_mount_policy", "status": "planned"},
                    {"id": "resource_limits", "status": "planned"},
                    {"id": "deterministic_tool_boundary", "status": "planned"},
                ],
            },
        ],
    }


def verify_signature_status(
    *,
    signature: dict[str, Any],
    declared_checksum: str | None,
    computed_checksum: str | None,
) -> dict[str, Any]:
    if declared_checksum and computed_checksum:
        return {
            "status": "checksum_match" if declared_checksum == computed_checksum else "checksum_mismatch",
            "declared_checksum": declared_checksum,
            "computed_checksum": computed_checksum,
        }
    if declared_checksum and not computed_checksum:
        return {"status": "checksum_unverified", "declared_checksum": declared_checksum}
    signature_status = str(signature.get("status") or "").strip().lower()
    if signature_status in {"signed", "verified"}:
        return {"status": "signed_unverified", "signature": redact_signature(signature)}
    return {"status": "unsigned"}


def redact_signature(signature: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(signature)
    for key in ("value", "signature", "public_key", "certificate"):
        if key in redacted:
            redacted[key] = "[redacted]"
    return redacted


def compute_capability_checksum(capability_dir: Path | None) -> str | None:
    if capability_dir is None or not capability_dir.exists() or not capability_dir.is_dir():
        return None
    digest = hashlib.sha256()
    for path in sorted(item for item in capability_dir.rglob("*") if item.is_file()):
        if should_skip_checksum_file(path):
            continue
        relative = path.relative_to(capability_dir).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def should_skip_checksum_file(path: Path) -> bool:
    parts = set(path.parts)
    if "__pycache__" in parts:
        return True
    if path.name in {".DS_Store"}:
        return True
    return path.suffix in {".pyc", ".pyo"}


def finding(code: str, severity: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message}
