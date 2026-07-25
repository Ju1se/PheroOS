from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from pheroos.conformance.checks._commit_context import (
    ActiveCommitContext,
    active_commit_context,
)
from pheroos.conformance.report import CheckResult
from pheroos.protocol import CapabilityManifest
from pheroos.trace import (
    COMMIT_EVENT_TYPES,
    EVENT_LINEAGE_CONTRACTS,
    VALID_EVENT_TYPES,
    TraceEvent,
    make_commit_trace_event,
    replay_commit_trace,
)
from pheroos.trace.schema import trace_schema


_NORMATIVE_COMMIT_EVENTS = frozenset(
    {
        "principal_attested",
        "principal_verified",
        "risk_assessed",
        "membership_snapshot",
        "observation_recorded",
        "observation_verified",
        "counterevidence_disposed",
        "challenge_recorded",
        "evidence_bound",
        "support_lease_issued",
        "support_lease_revoked",
        "support_lease_expired",
        "support_equivocation",
        "commit_metrics",
        "commit_window_advanced",
        "commit_window_reset",
        "quorum_pending",
        "decision_outcome",
        "stop_resolution_verified",
        "action_permission_issued",
        "commit_certificate_issued",
        "quorum_witness",
        "epoch_certificate",
        "commit_provisional",
        "certificate_conflict",
        "output_decided",
    }
)


def check(manifest: CapabilityManifest) -> CheckResult:
    context = active_commit_context(manifest)
    if context is None:
        return CheckResult("commit_trace_contract", True)
    problems: list[str] = []
    _append_registry_problems(problems)
    _append_reference_replay_problems(context, problems)

    unique = sorted(set(problems))
    return CheckResult("commit_trace_contract", not unique, ", ".join(unique))


def _append_registry_problems(problems: list[str]) -> None:
    if COMMIT_EVENT_TYPES != _NORMATIVE_COMMIT_EVENTS:
        problems.append("event_allowlist_mismatch")
    if not COMMIT_EVENT_TYPES.issubset(VALID_EVENT_TYPES):
        problems.append("event_allowlist_unregistered")
    for event_type in sorted(COMMIT_EVENT_TYPES):
        if not EVENT_LINEAGE_CONTRACTS.get(event_type):
            problems.append(f"missing_lineage_contract:{event_type}")
    schema_conditions = {
        item["if"]["properties"]["event_type"]["const"]
        for item in trace_schema()["allOf"]
    }
    for event_type in sorted(COMMIT_EVENT_TYPES - schema_conditions):
        problems.append(f"missing_conditional_schema:{event_type}")


def _append_reference_replay_problems(
    context: ActiveCommitContext,
    problems: list[str],
) -> None:
    try:
        outcome = _terminal_invalid_event(context)
        output = _terminal_output_event(context, outcome)
        replay = replay_commit_trace((outcome, output))
        if not replay.complete or replay.outcome_kind != "invalid":
            problems.append("terminal_replay_mismatch")
        mutated = deepcopy(output.lineage)
        mutated["deliver"] = False
        try:
            TraceEvent(
                event_type=output.event_type,
                protocol_id=output.protocol_id,
                target=output.target,
                reason=output.reason,
                lineage=mutated,
            ).validate()
        except ValueError:
            pass
        else:
            problems.append("event_mutation_accepted")
        try:
            _terminal_invalid_event(
                context,
                extensions={"x-critical-unknown-authority": True},
            )
        except ValueError:
            pass
        else:
            problems.append("unknown_critical_extension_accepted")
    except Exception as exc:
        problems.append(f"reference_replay:{type(exc).__name__}:{exc}")


def _terminal_invalid_event(
    context: ActiveCommitContext,
    *,
    extensions: Mapping[str, Any] | None = None,
) -> TraceEvent:
    details = {
        "kind": "invalid",
        "authoritative_commit": False,
        "epistemically_committed": False,
        "candidate_id": "",
        "reason_codes": ["invalid_runtime_record"],
    }
    payload = {
        "assurance": context.assurance,
        "authoritative_commit": False,
        "candidate_id": "",
        "commit_policy_root": context.commit_policy_root,
        "epistemically_committed": False,
        "epoch": context.epoch,
        "kind": "invalid",
        "manifest_root": context.manifest_root,
        "profile": context.profile,
        "protocol_id": context.protocol_id,
        "reason_codes": ["invalid_runtime_record"],
        "run_id": context.run_id,
        "target": context.target,
    }
    return make_commit_trace_event(
        event_type="decision_outcome",
        protocol_id=context.protocol_id,
        target=context.target,
        reason="invalid runtime record failed closed",
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        run_id=context.run_id,
        epoch=context.epoch,
        step=0,
        record_schema="pheroos-conformance-invalid-outcome-v1",
        record_payload=payload,
        details=details,
        extensions=extensions,
    )


def _terminal_output_event(
    context: ActiveCommitContext,
    outcome: TraceEvent,
) -> TraceEvent:
    details = {
        "outcome_ref": outcome.lineage["outcome_ref"],
        "deliver": True,
        "publish": False,
        "execute": False,
        "reason_codes": ["terminal_outcome_delivered"],
    }
    payload = {
        "assurance": context.assurance,
        "commit_policy_root": context.commit_policy_root,
        "deliver": True,
        "epoch": context.epoch,
        "execute": False,
        "manifest_root": context.manifest_root,
        "outcome_ref": outcome.lineage["outcome_ref"],
        "profile": context.profile,
        "protocol_id": context.protocol_id,
        "publish": False,
        "reason_codes": ["terminal_outcome_delivered"],
        "run_id": context.run_id,
        "target": context.target,
    }
    return make_commit_trace_event(
        event_type="output_decided",
        protocol_id=context.protocol_id,
        target=context.target,
        reason="terminal outcome delivered",
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        run_id=context.run_id,
        epoch=context.epoch,
        step=0,
        record_schema="pheroos-conformance-output-authorization-v1",
        record_payload=payload,
        previous_event_ids=(outcome.lineage["event_id"],),
        details=details,
    )


__all__ = ["check"]
