from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pheroos.protocol.manifest import load_capability_protocol


CONFIG_FILENAME = "pheroos-minimal.json"
LOCAL_STATE_DIR = ".pheroos"
TRACE_FILENAME = "minimal-traces.jsonl"
REPO_ROOT = Path(__file__).resolve().parents[1]
MINIMAL_DISTRO_MANIFEST_PATH = REPO_ROOT / "distros" / "minimal" / "pheroos.distro.json"
TOY_REVIEW_CAPABILITY_PATH = REPO_ROOT / "capabilities" / "toy-review"


def init_minimal_project(path: str | Path = ".") -> dict[str, Any]:
    workspace = Path(path).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    state_dir = workspace / LOCAL_STATE_DIR
    state_dir.mkdir(exist_ok=True)

    config = minimal_config()
    config_path = workspace / CONFIG_FILENAME
    trace_path = state_dir / TRACE_FILENAME
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    trace_path.touch(exist_ok=True)

    return {
        "ok": True,
        "distro_id": "minimal",
        "workspace": str(workspace),
        "config_path": str(config_path),
        "trace_path": str(trace_path),
        "external_api_required": False,
        "enabled_capabilities": ["toy-review"],
    }


def minimal_config() -> dict[str, Any]:
    config = load_minimal_distro_manifest()
    return {
        **config,
        "forbidden_runtime_assumptions": [
            "external_api_key",
            "financial_data_provider",
            "provider_secret",
        ],
    }


def load_minimal_distro_manifest() -> dict[str, Any]:
    if MINIMAL_DISTRO_MANIFEST_PATH.exists():
        payload = json.loads(MINIMAL_DISTRO_MANIFEST_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    return embedded_minimal_distro_manifest()


def embedded_minimal_distro_manifest() -> dict[str, Any]:
    return {
        "schema_version": "pheroos.distro.v0.1",
        "distro_id": "minimal",
        "name": "PheroOS Minimal",
        "description": "No-key PheroOS reference distro using toy-review, mock model/tool drivers, and local JSONL trace storage.",
        "enabled_capabilities": ["toy-review"],
        "drivers": [
            {
                "driver_kind": "model",
                "driver_id": "mock-model",
                "external_api_required": False,
                "model_calls": "deterministic_mock",
            },
            {
                "driver_kind": "tool",
                "driver_id": "mock-lookup",
                "side_effect_class": "read_only",
                "external_api_required": False,
            },
            {
                "driver_kind": "storage",
                "driver_id": "local-jsonl-trace",
                "path": f"{LOCAL_STATE_DIR}/{TRACE_FILENAME}",
            },
        ],
        "network_access": "none",
        "secrets_required": [],
    }


def run_minimal_task(task: str, *, workspace: str | Path = ".") -> dict[str, Any]:
    workspace_path = Path(workspace).expanduser().resolve()
    if not (workspace_path / CONFIG_FILENAME).exists():
        init_minimal_project(workspace_path)
    config = load_workspace_config(workspace_path)
    validation_errors = validate_minimal_distro_config(config)
    if validation_errors:
        return {
            "ok": False,
            "distro_id": "minimal",
            "workspace": str(workspace_path),
            "errors": validation_errors,
        }

    trace_path = minimal_trace_path(workspace_path)
    trace_path.parent.mkdir(exist_ok=True)

    protocol = load_toy_review_protocol()
    candidate_set = protocol_candidate_set(protocol)
    fallback_candidate = protocol_fallback_candidate(protocol)
    output_policy = protocol_output_policy(protocol)
    final_judge_required_checks = list(output_policy.get("final_judge_required_checks") or [])
    required_caveats = list(output_policy.get("required_caveats") or [])
    allowed_output_modes = list(output_policy.get("allowed_output_modes") or [])

    evidence = mock_evidence_for_task(task)
    committed_candidate = protocol_commit_candidate(candidate_set, fallback_candidate, evidence_available=evidence["evidence_available"])
    run_id = f"minimal-{uuid4().hex[:12]}"
    trace = {
        "schema_version": "pheroos.trace.v0.1",
        "run_id": run_id,
        "timestamp": utc_now(),
        "distro_id": "minimal",
        "runtime": "pheroos.reference_runtime.mock",
        "task": task,
        "capabilities": [{"id": capability_id, "source": "reference_capability"} for capability_id in config["enabled_capabilities"]],
        "drivers": config["drivers"],
        "governance": {
            "protocol_is_authority": True,
            "agent_authority": "proposal_only",
            "writer_can_create_facts": output_policy.get("writer_can_create_facts") is True,
            "final_judge_required_checks": final_judge_required_checks,
            "protocol_source": "capabilities/toy-review/capability.json",
        },
        "evidence": evidence,
        "quorum": {
            "candidate_set": [candidate["candidate"] for candidate in candidate_set],
            "committed_candidate": committed_candidate,
            "fallback_candidate": fallback_candidate,
        },
        "output": {
            "mode": protocol_output_mode(
                allowed_output_modes,
                evidence_available=evidence["evidence_available"],
                committed_candidate=committed_candidate,
                fallback_candidate=fallback_candidate,
            ),
            "required_caveats": required_caveats,
            "publication_permission": evidence["evidence_available"],
        },
        "network_access": config["network_access"],
        "secrets_used": list(config["secrets_required"]),
    }
    with trace_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(trace, sort_keys=True) + "\n")

    return {"ok": True, "trace_path": str(trace_path), **trace}


def latest_minimal_trace(*, workspace: str | Path = ".") -> dict[str, Any]:
    trace_path = minimal_trace_path(Path(workspace).expanduser().resolve())
    if not trace_path.exists():
        return {"ok": False, "error": "no minimal trace store found", "trace_path": str(trace_path)}

    latest: dict[str, Any] | None = None
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            latest = json.loads(line)
    if latest is None:
        return {"ok": False, "error": "no minimal traces found", "trace_path": str(trace_path)}
    return {"ok": True, "trace_path": str(trace_path), "trace": latest}


def minimal_trace_path(workspace: str | Path) -> Path:
    return Path(workspace) / LOCAL_STATE_DIR / TRACE_FILENAME


def load_workspace_config(workspace: str | Path) -> dict[str, Any]:
    config_path = Path(workspace) / CONFIG_FILENAME
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return payload


def validate_minimal_distro_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if config.get("schema_version") != "pheroos.distro.v0.1":
        errors.append("schema_version must be pheroos.distro.v0.1")
    if config.get("distro_id") != "minimal":
        errors.append("distro_id must be minimal")
    if config.get("enabled_capabilities") != ["toy-review"]:
        errors.append("minimal distro must enable only toy-review")
    if config.get("network_access") != "none":
        errors.append("minimal distro must not request network access")
    if config.get("secrets_required") != []:
        errors.append("minimal distro must not require secrets")
    for driver in list(config.get("drivers") or []):
        if not isinstance(driver, dict):
            errors.append("drivers must be objects")
            continue
        if driver.get("external_api_required") is True:
            errors.append(f"driver {driver.get('driver_id') or '<unknown>'} must not require external APIs")
    return errors


def load_toy_review_protocol() -> dict[str, Any]:
    return load_capability_protocol(TOY_REVIEW_CAPABILITY_PATH).protocol


def protocol_candidate_set(protocol: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = protocol.get("candidates") if isinstance(protocol.get("candidates"), list) else []
    return [dict(candidate) for candidate in candidates if isinstance(candidate, dict) and candidate.get("candidate")]


def protocol_fallback_candidate(protocol: dict[str, Any]) -> str:
    quorum_policy = protocol.get("quorum_policy") if isinstance(protocol.get("quorum_policy"), dict) else {}
    return str(quorum_policy.get("candidate_fallback") or "")


def protocol_output_policy(protocol: dict[str, Any]) -> dict[str, Any]:
    output_policy = protocol.get("output_policy") if isinstance(protocol.get("output_policy"), dict) else {}
    return dict(output_policy)


def protocol_commit_candidate(
    candidates: list[dict[str, Any]],
    fallback_candidate: str,
    *,
    evidence_available: bool,
) -> str:
    if not evidence_available:
        return fallback_candidate
    for candidate in candidates:
        if candidate.get("safe_fallback") is True:
            continue
        return str(candidate["candidate"])
    return fallback_candidate


def protocol_output_mode(
    allowed_output_modes: list[str],
    *,
    evidence_available: bool,
    committed_candidate: str,
    fallback_candidate: str,
) -> str:
    if not evidence_available or committed_candidate == fallback_candidate:
        if "defect_memo" in allowed_output_modes:
            return "defect_memo"
    return allowed_output_modes[0] if allowed_output_modes else "minimal_trace"


def mock_evidence_for_task(task: str) -> dict[str, Any]:
    text = task.lower()
    evidence_available = "missing" not in text and "no evidence" not in text and "unsupported" not in text
    return {
        "source": "mock_tool:toy_lookup",
        "claim_type": "toy_claim",
        "evidence_available": evidence_available,
        "candidate_count": 1 if evidence_available else 0,
        "full_text_count": 1 if evidence_available else 0,
        "external_fetch": False,
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
