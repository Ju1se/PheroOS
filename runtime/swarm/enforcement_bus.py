from __future__ import annotations

from typing import Any

from runtime.swarm.target_registry import canonical_target
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState


def apply_enforcement_bus(state: dict[str, Any], governance_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate governance actor contracts into one enforcement report.

    The bus does not replace the individual governance actors. It makes their
    runtime effect explicit and emits missing hard stop-signals for blocking
    results so publication/tool boundaries cannot depend on UI-only reports.
    """

    blocked_targets = sorted(
        {
            canonical_target(target)
            for result in governance_results
            if isinstance(result, dict)
            for target in result.get("blocked_targets") or []
            if str(target).strip()
        }
    )
    writer_constraints = unique_strings(
        [
            item
            for result in governance_results
            if isinstance(result, dict)
            for item in result.get("writer_constraints") or []
        ]
    )
    final_judge_checks = unique_strings(
        [
            item
            for result in governance_results
            if isinstance(result, dict)
            for item in result.get("final_judge_checks") or []
        ]
    )
    required_caveats = unique_strings(
        [
            item
            for result in governance_results
            if isinstance(result, dict)
            for item in result.get("required_caveats") or []
        ]
    )
    signals = enforcement_signals(state, governance_results, blocked_targets)
    return {
        "enforcement_bus_report": {
            "schema_version": "pheroos.enforcement_bus.v1",
            "status": "block" if blocked_targets else "warn" if writer_constraints or required_caveats else "pass",
            "blocked_targets": blocked_targets,
            "writer_constraints": writer_constraints,
            "final_judge_checks": final_judge_checks,
            "required_caveats": required_caveats,
            "signal_count": len(signals),
            "governance_result_count": len(governance_results),
        },
        "signals": signals,
    }


def enforcement_signals(
    state: dict[str, Any],
    governance_results: list[dict[str, Any]],
    blocked_targets: list[str],
) -> list[PheromoneSignal]:
    existing = {
        canonical_target(signal.get("target"))
        for signal in state.get("stop_signals") or []
        if isinstance(signal, dict) and signal.get("blocking")
    }
    run_id = str(state.get("run_id") or "unknown")
    tenant_id = str((state.get("metadata") or {}).get("tenant_id") or "default")
    by_target: dict[str, list[str]] = {target: [] for target in blocked_targets}
    for result in governance_results:
        if not isinstance(result, dict):
            continue
        actor = str(result.get("actor") or "governance_actor")
        for target in result.get("blocked_targets") or []:
            canonical = canonical_target(target)
            if canonical in by_target:
                by_target[canonical].append(actor)
    output: list[PheromoneSignal] = []
    for target in blocked_targets:
        if target in existing:
            continue
        actors = sorted(set(by_target.get(target) or []))
        output.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.STOP_SIGNAL,
                target=target,
                content=f"EnforcementBus blocked {target} from governance actor(s): {', '.join(actors) or 'unknown'}.",
                strength=1.0,
                confidence=0.9,
                decay_rate=0.0,
                priority="hard",
                verification_state=VerificationState.BLOCKING,
                source_module="enforcement_bus",
                evidence_ref="governance_results",
                blocking=True,
                metadata={"actors": actors},
            )
        )
    return output


def unique_strings(values: list[Any]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output
