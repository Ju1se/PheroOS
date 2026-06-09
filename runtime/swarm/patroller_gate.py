from __future__ import annotations

from typing import Any

from runtime.swarm.legacy_tool_policy import legacy_wrds_source_readiness_detail
from runtime.swarm.tool_plan_policy import wrds_source_required_for_state
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState


def build_patroller_report(state: dict[str, Any]) -> dict[str, Any]:
    """Convert runtime readiness into a pre-execution patrol report.

    This is intentionally deterministic. It does not call tools or models; it
    only inspects OS plan, active capabilities, validation issues, and source
    policy already present in state metadata.
    """

    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    validation_issues = metadata.get("runtime_validation_issues") if isinstance(metadata.get("runtime_validation_issues"), list) else []
    enabled_capabilities = metadata.get("enabled_capabilities") if isinstance(metadata.get("enabled_capabilities"), list) else []
    capability_index = metadata.get("capability_index") if isinstance(metadata.get("capability_index"), dict) else {}
    tool_manifest = state.get("tool_manifest") if isinstance(state.get("tool_manifest"), list) else []
    source_mode = str(metadata.get("source_mode") or "").upper()

    checks = [
        {
            "name": "model_provider",
            "status": "ready" if capability_index.get("model_providers") else "degraded",
            "detail": "At least one model provider is active." if capability_index.get("model_providers") else "No active model provider found; runtime may use fallback/mock configuration.",
        },
        {
            "name": "enabled_capabilities",
            "status": "ready" if enabled_capabilities else "degraded",
            "detail": f"{len(enabled_capabilities)} capabilities enabled.",
        },
        {
            "name": "runtime_validation",
            "status": "ready" if not validation_issues else "blocked",
            "detail": "No validation issues." if not validation_issues else f"{len(validation_issues)} validation issues present.",
        },
    ]
    if wrds_source_required_for_state(state):
        has_wrds = bool(capability_index.get("financial_data_sources")) or any(
            isinstance(tool, dict) and str(tool.get("name") or "").startswith("wrds_")
            for tool in tool_manifest
        )
        checks.append(
            {
                "name": "wrds_source",
                "status": "ready" if has_wrds else "blocked",
                "detail": legacy_wrds_source_readiness_detail(ready=has_wrds),
            }
        )
    if os_plan.get("pending_permission_confirmations") or os_plan.get("needs_confirmation"):
        checks.append(
            {
                "name": "permission_confirmation",
                "status": "blocked",
                "detail": "One or more capability permissions require explicit confirmation.",
            }
        )

    statuses = {check["status"] for check in checks}
    status = "blocked" if "blocked" in statuses else ("degraded" if "degraded" in statuses else "ready")
    return {
        "status": status,
        "checks": checks,
        "source_mode": source_mode or "DEFAULT",
        "runtime_ready": bool(os_plan.get("runtime_ready", status != "blocked")),
    }


def patroller_signals(state: dict[str, Any], report: dict[str, Any]) -> list[PheromoneSignal]:
    run_id = str(state.get("run_id") or "unknown")
    tenant_id = str((state.get("metadata") or {}).get("tenant_id") or "default")
    signals: list[PheromoneSignal] = []
    for check in report.get("checks") or []:
        if not isinstance(check, dict):
            continue
        check_name = str(check.get("name") or "preflight")
        status = str(check.get("status") or "unknown")
        if status == "ready":
            signals.append(
                PheromoneSignal(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    type=SignalType.TOOL_HEALTH,
                    target=check_name,
                    content=str(check.get("detail") or f"{check_name} is ready."),
                    strength=0.75,
                    confidence=0.8,
                    source_module="patroller_gate",
                    verification_state=VerificationState.VERIFIED,
                )
            )
        elif status == "blocked":
            signals.append(
                PheromoneSignal(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    type=SignalType.STOP_SIGNAL,
                    target=f"patroller:{check_name}",
                    content=str(check.get("detail") or f"{check_name} blocked preflight."),
                    strength=1.0,
                    confidence=0.9,
                    decay_rate=0.0,
                    priority="hard",
                    verification_state=VerificationState.BLOCKING,
                    source_module="patroller_gate",
                    blocking=True,
                )
            )
        else:
            signals.append(
                PheromoneSignal(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    type=SignalType.RISK,
                    target=f"patroller:{check_name}",
                    content=str(check.get("detail") or f"{check_name} is degraded."),
                    strength=0.65,
                    confidence=0.75,
                    source_module="patroller_gate",
                )
            )
    return signals


def patroller_blocked(state: dict[str, Any]) -> bool:
    report = state.get("patroller_report") if isinstance(state.get("patroller_report"), dict) else {}
    if report.get("status") == "blocked":
        return True
    signals = state.get("stop_signals") if isinstance(state.get("stop_signals"), list) else []
    return any(
        isinstance(signal, dict)
        and signal.get("blocking")
        and str(signal.get("target") or "").startswith("patroller:")
        for signal in signals
    )


def render_patroller_defect_memo(state: dict[str, Any]) -> str:
    report = state.get("patroller_report") if isinstance(state.get("patroller_report"), dict) else {}
    checks = report.get("checks") if isinstance(report.get("checks"), list) else []
    lines = [
        "# Patroller Gate Report",
        "",
        "当前运行在进入工具执行或委员会讨论前被 PatrollerGate 阻止。系统没有继续执行外部数据抓取、受限结论或最终报告生成。",
        "",
        f"- Task: `{state.get('task')}`",
        f"- Source mode: `{report.get('source_mode', 'DEFAULT')}`",
        f"- Runtime ready: `{report.get('runtime_ready', False)}`",
        "",
        "## Preflight Checks",
    ]
    if checks:
        for check in checks:
            if not isinstance(check, dict):
                continue
            lines.append(
                f"- **{check.get('name', 'check')}**: `{check.get('status', 'unknown')}` — {check.get('detail', '')}"
            )
    else:
        lines.append("- No patroller checks were recorded.")
    lines.extend(
        [
            "",
            "## Required Action",
            "修复 blocked/degraded 的连接、权限或 capability 后重新运行。PatrollerGate 只读取现有 runtime 状态，不会直接调用模型、WRDS 或任意工具。",
        ]
    )
    return "\n".join(lines)
