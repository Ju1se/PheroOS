"""Reference adapter and ABI probes for the Commit Integrity TCK.

Vectors contain only JSON values.  The reference adapter delegates every
operation to a public Protocol, Governance, or Trace ABI function; it never
reimplements commit scoring, liveness, certificate, or finality algorithms.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import replace
import json
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import RLock
from typing import Any

from pheroos.conformance._commit_reference import (
    ReferenceDistributedCommit,
    ReferenceScenario,
    ReferenceStableCommit,
    assess_reference_scenario,
    build_reference_distributed_commit,
    build_reference_portable_commit,
    build_reference_scenario,
    build_reference_stable_commit,
    issue_reference_action_gates,
    issue_reference_binding,
    issue_reference_disposition,
    issue_reference_distributed_certificate,
    issue_reference_lease,
    issue_reference_observation,
    issue_reference_semantic_conflict_certificate,
    issue_reference_witness,
    initialize_reference_window,
    reference_fingerprint,
    rotate_reference_context,
)
from pheroos.conformance._commit_tck.artifacts import (
    COMMIT_TCK_ARTIFACT,
    COMMIT_TCK_SCHEMA_ID,
    commit_tck_artifact_root,
    commit_tck_schema,
    load_commit_tck_vectors,
)
from pheroos.conformance._commit_tck.models import (
    CommitTckVector,
    integer_value as _integer,
    json_result as _json_result,
    object_value as _object,
    request_from_vector as _request_from_vector,
    result as _result,
    text_value as _text,
    validate_expected_shape as _validate_expected_shape,
)
from pheroos.conformance.commit_tck_v2_protocol import (
    CommitTckRequest as _CommitTckRequest,
)
from pheroos.conformance.profile import profile_for_manifest
from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.attention import evaluate_hybrid_attention_step
from pheroos.governance.candidate import Candidate, CandidateSet
from pheroos.governance.certificate import (
    evidence_commit_certificate_fingerprint,
    evidence_commit_certificate_payload,
    local_commit_receipt_fingerprint,
    local_commit_receipt_is_authoritative,
    outcome_certificate_payload,
    issue_outcome_certificate,
    verify_evidence_commit_certificate,
    verify_local_commit_finality,
)
from pheroos.governance.collective import (
    ScoutReport,
)
from pheroos.governance.commit import (
    CandidateCommitInput,
    CommitAssessmentStatus,
    commit_assessment_fingerprint,
    candidate_commit_metrics_payload,
)
from pheroos.governance.commit_numeric import (
    multiply_scaled,
    scaled_ratio,
)
from pheroos.governance.commit_state import (
    CommitFinalityStatus,
    DecisionOutcome,
    DecisionOutcomeKind,
    DecisionProgress,
    ReplayNamespace,
    ReplayReceipt,
    advance_commit_window_state as _advance_commit_window_state,
    commit_finality_verification_fingerprint,
    commit_window_state_fingerprint,
    decision_outcome_fingerprint,
    decision_outcome_is_authoritative,
    decision_progress_fingerprint,
    issue_commit_liveness_input,
    record_commit_replay_receipts,
    reduce_commit_liveness,
    restart_commit_window_epoch,
    select_terminal_outcome_kind,
)
from pheroos.governance.distributed_commit import (
    assemble_portable_distributed_commit_certificate,
    distributed_commit_certificate_fingerprint,
    distributed_commit_certificate_is_current_final,
    distributed_commit_state_fingerprint,
    evaluate_distributed_finality,
    issue_distributed_commit_proposal,
    portable_membership_snapshot_from_eligible,
    register_distributed_commit_certificate,
    verify_distributed_commit_certificate,
)
from pheroos.governance.evidence_binding import (
    evidence_binding_fingerprint,
    evidence_binding_payload,
    evaluate_evidence_binding,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.hybrid_commit import (
    HYBRID_COMMIT_EVALUATION_REQUEST_VERSION,
    HybridCommitEvaluationRequest,
    bind_hybrid_commit_channels,
    evaluate_hybrid_commit_step,
    hybrid_attention_projection,
    hybrid_commit_truth_projection,
    hybrid_commit_evaluation_is_authoritative,
)
from pheroos.governance.observation import (
    CounterevidenceDispositionKind,
    ObservationPolarity,
    verified_observation_payload,
    verified_observation_fingerprint,
)
from pheroos.governance.output import (
    authorize_terminal_publication,
    commit_output_authorization_fingerprint,
    deliver_terminal_outcome,
)
from pheroos.governance.permission import (
    action_permission_payload,
    issue_action_permission,
)
from pheroos.governance.pheromone import (
    PheromoneNeighborhood,
    PheromoneSubject,
)
from pheroos.governance.principal import (
    principal_verification_payload,
)
from pheroos.governance.quorum import (
    QuorumSignal,
    evaluate_quorum_decision,
    quorum_decision_is_authoritative,
)
from pheroos.governance.risk import (
    RiskBand,
    commit_threshold_snapshot_fingerprint,
    initialize_risk_assessment_chain,
    issue_commit_threshold_snapshot,
    issue_risk_assessment,
    risk_assessment_payload,
)
from pheroos.governance.stop_signal import (
    StopResolution,
    stop_resolution_verification_fingerprint,
    stop_resolution_verification_payload,
    verify_stop_resolution,
)
from pheroos.governance.support_lease import (
    SupportLeaseProposal,
    evaluate_support_leases,
    initialize_support_lease_replay_state,
    issue_support_lease,
    revoke_support_lease,
    eligible_principal_snapshot_payload,
    support_lease_fingerprint,
    support_lease_payload,
)
from pheroos.governance.signal import verify_signal_input
from pheroos.protocol.commit_models import CommitAction
from pheroos.protocol.commit_wire import (
    canonical_commit_set,
    commit_manifest_fingerprint,
    commit_payload_fingerprint,
)
from pheroos.protocol.manifest import capability_manifest_from_dict
from pheroos.protocol.validation import validate_capability_manifest
from pheroos.trace import (
    TraceEvent,
    make_commit_trace_event,
    replay_commit_trace,
)


# Immutable authority substrates are expensive to issue and some public
# registries intentionally expose only their latest strong head.  Reuse the
# exact historical fixture for an identical full semantic specification while
# still re-running every probe, transition, verifier, and exact comparison.
# This is fixture memoization, never a TCK result cache.
_REFERENCE_FIXTURE_CACHE: dict[tuple[Any, ...], ReferenceScenario] = {}
_REFERENCE_FIXTURE_CACHE_LOCK = RLock()
_EPOCH_THRESHOLD_FIXTURE_CACHE: dict[tuple[Any, ...], Any] = {}
_EPOCH_THRESHOLD_FIXTURE_CACHE_LOCK = RLock()
_LIVENESS_INPUT_FIXTURE_CACHE: dict[tuple[Any, ...], Any] = {}
_LIVENESS_INPUT_FIXTURE_CACHE_LOCK = RLock()
_WINDOW_TRANSITION_FIXTURE_CACHE: dict[tuple[Any, ...], Any] = {}
_WINDOW_TRANSITION_FIXTURE_CACHE_LOCK = RLock()


def advance_commit_window_state(
    state: Any,
    *,
    assessment: Any,
    commit_policy: Any,
    threshold_snapshot: Any,
    current_step: int,
) -> Any:
    """Replay-safe access to an immutable historical window transition."""

    fixture_key = (
        commit_window_state_fingerprint(state),
        commit_assessment_fingerprint(assessment),
        commit_threshold_snapshot_fingerprint(threshold_snapshot),
        current_step,
    )
    with _WINDOW_TRANSITION_FIXTURE_CACHE_LOCK:
        cached = _WINDOW_TRANSITION_FIXTURE_CACHE.get(fixture_key)
        if cached is not None:
            return cached
    transitioned = _advance_commit_window_state(
        state,
        assessment=assessment,
        commit_policy=commit_policy,
        threshold_snapshot=threshold_snapshot,
        current_step=current_step,
    )
    with _WINDOW_TRANSITION_FIXTURE_CACHE_LOCK:
        _WINDOW_TRANSITION_FIXTURE_CACHE[fixture_key] = transitioned
    return transitioned


class ReferenceCommitTckAdapter:
    """Reference adapter composed exclusively from public PheroOS ABI calls."""

    def __init__(self) -> None:
        self._operations: dict[
            str, Callable[[_CommitTckRequest], dict[str, Any]]
        ] = {
            "canonical_fingerprint": self._canonical_fingerprint,
            "canonical_set_fingerprint": self._canonical_set_fingerprint,
            "fixed_point_multiply": self._fixed_point_multiply,
            "fixed_point_ratio": self._fixed_point_ratio,
            "manifest_validation": self._manifest_validation,
            "matrix_case": self._matrix_case,
            "terminal_priority": self._terminal_priority,
            "trace_replay": self._trace_replay,
        }

    def evaluate(
        self,
        request: _CommitTckRequest | CommitTckVector,
    ) -> Mapping[str, Any]:
        # Preserve direct v1 calls to the reference adapter without allowing
        # its implementation to consume harness-owned expected values.
        selected = (
            _request_from_vector(request)
            if isinstance(request, CommitTckVector)
            else request
        )
        operation = selected.inputs.get("operation")
        if not isinstance(operation, str) or operation not in self._operations:
            raise ValueError(
                f"TCK vector {selected.id} uses unsupported operation: {operation!r}"
            )
        actual = _json_result(self._operations[operation](selected))
        _validate_expected_shape(actual, label=f"actual result for {selected.id}")
        return actual

    def _canonical_fingerprint(self, vector: _CommitTckRequest) -> dict[str, Any]:
        payload = _object(vector.inputs.get("payload"), "canonical payload")
        schema = _text(vector.inputs.get("schema"), "canonical schema")
        root = commit_payload_fingerprint(
            payload,
            schema=schema,
            profile=vector.profile,
        )
        return _result(roots={"fingerprint": root})

    def _canonical_set_fingerprint(self, vector: _CommitTckRequest) -> dict[str, Any]:
        values = vector.inputs.get("values")
        if not isinstance(values, list):
            raise ValueError("canonical set values must be an array")
        normalized = canonical_commit_set(values)
        root = commit_payload_fingerprint(
            {"values": normalized},
            schema=_text(vector.inputs.get("schema"), "canonical set schema"),
            profile=vector.profile,
        )
        return _result(
            roots={"fingerprint": root},
            outcome={"canonical_values": list(normalized)},
        )

    def _fixed_point_multiply(self, vector: _CommitTckRequest) -> dict[str, Any]:
        left = _integer(vector.inputs.get("left"), "multiply left")
        right = _integer(vector.inputs.get("right"), "multiply right")
        scale = _integer(vector.inputs.get("scale"), "multiply scale")
        return _result(metrics={"value": multiply_scaled(left, right, scale=scale)})

    def _fixed_point_ratio(self, vector: _CommitTckRequest) -> dict[str, Any]:
        numerator = _integer(vector.inputs.get("numerator"), "ratio numerator")
        denominator = _integer(
            vector.inputs.get("denominator"), "ratio denominator"
        )
        scale = _integer(vector.inputs.get("scale"), "ratio scale")
        return _result(
            metrics={
                "value": scaled_ratio(
                    numerator,
                    denominator,
                    scale=scale,
                )
            }
        )

    def _manifest_validation(self, vector: _CommitTckRequest) -> dict[str, Any]:
        if vector.manifest is None:
            raise ValueError("manifest_validation vector requires manifest")
        try:
            manifest = capability_manifest_from_dict(vector.manifest)
        except Exception as exc:
            return _result(failure_code=f"load:{type(exc).__name__}")
        diagnostics = validate_capability_manifest(manifest)
        errors = sorted(
            item.code for item in diagnostics if item.level == "error"
        )
        return _result(
            outcome={"valid": not errors, "diagnostic_codes": errors},
            failure_code=(errors[0] if errors else None),
        )

    def _terminal_priority(self, vector: _CommitTckRequest) -> dict[str, Any]:
        inputs = vector.inputs
        kind = select_terminal_outcome_kind(
            invalid=bool(inputs.get("invalid", False)),
            safety_violation=bool(inputs.get("safety_violation", False)),
            blocked=bool(inputs.get("blocked", False)),
            evidence_commit_ready=bool(inputs.get("evidence_commit", False)),
            finality_unavailable=bool(inputs.get("finality_unavailable", False)),
            deadline_reached=bool(inputs.get("deadline_reached", False)),
            deadline_outcome=_text(
                inputs.get("deadline_outcome"), "deadline outcome"
            ),
        )
        return _result(outcome={"kind": kind.value if kind is not None else None})

    def _trace_replay(self, vector: _CommitTckRequest) -> dict[str, Any]:
        specs = vector.inputs.get("events")
        if not isinstance(specs, list):
            raise ValueError("trace_replay events must be an array")
        aliases: dict[str, Any] = {}
        events: list[Any] = []
        for index, raw in enumerate(specs):
            spec = _object(raw, f"trace event {index}")
            alias = _text(spec.get("alias"), f"trace event {index} alias")
            if alias in aliases:
                raise ValueError("trace replay contains a duplicate alias")
            predecessor_aliases = spec.get("previous", [])
            if not isinstance(predecessor_aliases, list):
                raise ValueError("trace event previous must be an array")
            try:
                previous_ids = [
                    aliases[name].lineage["event_id"]
                    for name in predecessor_aliases
                ]
            except KeyError as exc:
                raise ValueError(
                    f"trace event references an unseen alias: {exc.args[0]}"
                ) from exc
            event = make_commit_trace_event(
                event_type=_text(spec.get("event_type"), "trace event type"),
                protocol_id=_text(
                    spec.get("protocol_id"), "trace event protocol_id"
                ),
                target=_text(spec.get("target"), "trace event target"),
                reason=_text(spec.get("reason"), "trace event reason"),
                profile=vector.profile,
                assurance=_text(spec.get("assurance"), "trace event assurance"),
                manifest_root=_text(
                    spec.get("manifest_root"), "trace event manifest_root"
                ),
                commit_policy_root=_text(
                    spec.get("commit_policy_root"),
                    "trace event commit_policy_root",
                ),
                run_id=_text(spec.get("run_id"), "trace event run_id"),
                epoch=_integer(spec.get("epoch"), "trace event epoch"),
                step=_integer(spec.get("step"), "trace event step"),
                record_schema=_text(
                    spec.get("record_schema"), "trace event record_schema"
                ),
                record_payload=_object(
                    spec.get("record_payload"), "trace event record_payload"
                ),
                previous_event_ids=previous_ids,
                details=_object(spec.get("details"), "trace event details"),
                extensions=(
                    _object(spec["extensions"], "trace event extensions")
                    if "extensions" in spec
                    else None
                ),
            )
            aliases[alias] = event
            events.append(event)
        replay = replay_commit_trace(
            events,
            require_complete=bool(vector.inputs.get("require_complete", True)),
        )
        return _result(
            roots={
                "event_ids": list(replay.event_ids),
                "record_refs": list(replay.record_refs),
                "outcome_ref": replay.outcome_ref,
                "output_ref": replay.output_ref,
                "certificate_refs": list(replay.certificate_refs),
            },
            outcome={
                "kind": replay.outcome_kind,
                "complete": replay.complete,
            },
            trace_sequence=list(replay.event_types),
        )

    def _matrix_case(self, vector: _CommitTckRequest) -> dict[str, Any]:
        probe = _MATRIX_PROBES.get(vector.matrix_case)
        if probe is None:
            raise ValueError(
                f"TCK matrix case {vector.matrix_case} has no reference ABI probe"
            )
        return probe(vector)


def _require_vector_manifest(vector: _CommitTckRequest) -> dict[str, Any]:
    if vector.manifest is None:
        raise ValueError(f"TCK vector {vector.id} requires a manifest")
    return vector.manifest


def _reference_scenario(
    vector: _CommitTckRequest,
    *,
    variant: str = "base",
    tie: bool = False,
    blocked: bool = False,
    shared_cluster: bool = False,
    leader_observation_count: int = 2,
    other_observation_count: int | None = None,
    minimum_membership_size: int = 3,
) -> ReferenceScenario:
    manifest = _require_vector_manifest(vector)
    key = (
        vector.id,
        vector.profile,
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        variant,
        tie,
        blocked,
        shared_cluster,
        leader_observation_count,
        other_observation_count,
        minimum_membership_size,
    )
    with _REFERENCE_FIXTURE_CACHE_LOCK:
        cached = _REFERENCE_FIXTURE_CACHE.get(key)
        if cached is not None:
            return cached
        scenario = build_reference_scenario(
            vector.id,
            manifest,
            profile=vector.profile,
            variant=variant,
            tie=tie,
            blocked=blocked,
            shared_cluster=shared_cluster,
            leader_observation_count=leader_observation_count,
            other_observation_count=other_observation_count,
            minimum_membership_size=minimum_membership_size,
        )
        _REFERENCE_FIXTURE_CACHE[key] = scenario
        return scenario


def _observation(
    scenario: ReferenceScenario,
    *,
    index: int,
    principal_index: int = 0,
    candidate_id: str | None = None,
    polarity: ObservationPolarity = ObservationPolarity.SUPPORT,
    independence_group: str | None = None,
    source_domain: str | None = None,
    nonce: str | None = None,
    quality_ppm: int = 1_000_000,
    relevance_ppm: int = 1_000_000,
    materiality_ppm: int = 1_000_000,
    criticality_ppm: int = 0,
) -> Any:
    candidate = candidate_id or scenario.leader_id
    return issue_reference_observation(
        scenario.namespace,
        index=index,
        principal=scenario.principals[principal_index],
        candidate_id=candidate,
        claim_fingerprint=scenario.claims[candidate],
        profile=scenario.profile,
        assurance=scenario.assurance,
        manifest_root=scenario.manifest_root,
        commit_policy_root=scenario.commit_policy_root,
        protocol_id=scenario.protocol_id,
        run_id=scenario.run_id,
        target=scenario.target,
        epoch=scenario.epoch,
        evidence_policy=scenario.policy.evidence_qualification,
        polarity=polarity,
        independence_group=independence_group,
        source_domain=source_domain,
        nonce=nonce,
        quality_ppm=quality_ppm,
        relevance_ppm=relevance_ppm,
        materiality_ppm=materiality_ppm,
        criticality_ppm=criticality_ppm,
    )


def _binding(
    scenario: ReferenceScenario,
    *,
    candidate_id: str,
    positives: Sequence[Any],
    counters: Sequence[Any] = (),
    dispositions: Sequence[Any] = (),
    challenges: Sequence[Any] | None = None,
    variant: str,
) -> Any:
    return issue_reference_binding(
        scenario.namespace,
        candidate_id=candidate_id,
        claim_fingerprint=scenario.claims[candidate_id],
        observations=tuple(positives),
        counter_observations=tuple(counters),
        dispositions=tuple(dispositions),
        challenges=(
            (scenario.challenges[candidate_id],)
            if challenges is None
            else tuple(challenges)
        ),
        profile=scenario.profile,
        assurance=scenario.assurance,
        manifest_root=scenario.manifest_root,
        commit_policy_root=scenario.commit_policy_root,
        protocol_id=scenario.protocol_id,
        run_id=scenario.run_id,
        target=scenario.target,
        epoch=scenario.epoch,
        current_step=4,
        binding_variant=variant,
    )


def _evaluate_binding(
    scenario: ReferenceScenario,
    binding: Any,
    *,
    positives: Sequence[Any],
    counters: Sequence[Any] = (),
    dispositions: Sequence[Any] = (),
    challenges: Sequence[Any] | None = None,
    current_step: int = 5,
) -> Any:
    return evaluate_evidence_binding(
        binding,
        positive_observations=tuple(positives),
        counter_observations=tuple(counters),
        dispositions=tuple(dispositions),
        challenges=(
            (scenario.challenges[binding.candidate_id],)
            if challenges is None
            else tuple(challenges)
        ),
        evidence_policy=scenario.policy.evidence_qualification,
        current_step=current_step,
    )


def _risk_trace_event(scenario: ReferenceScenario) -> TraceEvent:
    threshold_ref = commit_threshold_snapshot_fingerprint(scenario.threshold)
    return make_commit_trace_event(
        event_type="risk_assessed",
        protocol_id=scenario.protocol_id,
        target=scenario.target,
        reason="tck_risk_assessed",
        profile=scenario.profile,
        assurance=scenario.assurance.value,
        manifest_root=scenario.manifest_root,
        commit_policy_root=scenario.commit_policy_root,
        run_id=scenario.run_id,
        epoch=scenario.epoch,
        step=scenario.risk_assessment.issued_at_step,
        record_schema="pheroos-tck-risk-observation-v1",
        record_payload={
            "risk_band": scenario.risk_assessment.risk_band.value,
            "threshold_ref": threshold_ref,
            "risk_chain_revision": scenario.risk_assessment.risk_chain_revision,
        },
        details={
            "risk_band": scenario.risk_assessment.risk_band.value,
            "risk_ref": "",
            "threshold_ref": threshold_ref,
            "risk_chain_revision": scenario.risk_assessment.risk_chain_revision,
        },
    )


def _risk_trace_sequence(scenario: ReferenceScenario) -> list[str]:
    event = _risk_trace_event(scenario)
    replay = replay_commit_trace((event,), require_complete=False)
    return list(replay.event_types)


def _probe_case_01(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    group = f"group:{scenario.namespace}:shared-positive"
    observations = tuple(
        _observation(
            scenario,
            index=100 + index,
            principal_index=(index - 1) % len(scenario.principals),
            independence_group=group,
            source_domain=f"domain:{scenario.namespace}:positive:{index}",
        )
        for index in range(1, 4)
    )
    binding = _binding(
        scenario,
        candidate_id=scenario.leader_id,
        positives=observations,
        variant="case-01",
    )
    summary = _evaluate_binding(
        scenario,
        binding,
        positives=observations,
    )
    contribution = summary.positive_groups[0]
    return _result(
        metrics={
            "raw_positive": contribution.raw_contribution,
            "counted_positive": contribution.counted_contribution,
            "positive_group_cap": scenario.policy.evidence_qualification.positive_group_cap,
            "observation_count": len(contribution.observation_fingerprints),
        },
        roots={"evidence_root": binding.evidence_root},
        outcome={"cap_enforced": contribution.counted_contribution <= scenario.policy.evidence_qualification.positive_group_cap},
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_02(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    group = f"group:{scenario.namespace}:shared-counter"
    counters = tuple(
        _observation(
            scenario,
            index=200 + index,
            polarity=ObservationPolarity.CONTRADICT,
            independence_group=group,
            source_domain=f"domain:{scenario.namespace}:counter:{index}",
        )
        for index in range(1, 4)
    )
    dispositions = tuple(
        issue_reference_disposition(
            scenario.namespace,
            item,
            index=200 + index,
            kind=CounterevidenceDispositionKind.ACCEPTED,
        )
        for index, item in enumerate(counters, start=1)
    )
    positives = scenario.observations[scenario.leader_id]
    binding = _binding(
        scenario,
        candidate_id=scenario.leader_id,
        positives=positives,
        counters=counters,
        dispositions=dispositions,
        variant="case-02",
    )
    summary = _evaluate_binding(
        scenario,
        binding,
        positives=positives,
        counters=counters,
        dispositions=dispositions,
    )
    contribution = summary.counter_groups[0]
    return _result(
        metrics={
            "raw_counter": contribution.raw_contribution,
            "counted_counter": contribution.counted_contribution,
            "counter_group_cap": scenario.policy.evidence_qualification.counter_group_cap,
            "active_counter_count": len(summary.active_counter_observation_fingerprints),
        },
        roots={"counter_root": binding.counter_root},
        outcome={"duplicate_amplification_blocked": contribution.counted_contribution <= scenario.policy.evidence_qualification.counter_group_cap},
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_03(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    counter = _observation(
        scenario,
        index=301,
        polarity=ObservationPolarity.CONTRADICT,
        materiality_ppm=1_000_000,
        criticality_ppm=1_000_000,
    )
    disposition = issue_reference_disposition(
        scenario.namespace,
        counter,
        index=301,
        kind=CounterevidenceDispositionKind.UNRESOLVED,
    )
    positives = scenario.observations[scenario.leader_id]
    binding = _binding(
        scenario,
        candidate_id=scenario.leader_id,
        positives=positives,
        counters=(counter,),
        dispositions=(disposition,),
        variant="case-03",
    )
    summary = _evaluate_binding(
        scenario,
        binding,
        positives=positives,
        counters=(counter,),
        dispositions=(disposition,),
    )
    return _result(
        metrics={
            "positive_evidence": summary.positive_evidence,
            "blocking_critical_count": len(summary.blocking_critical_counter_observation_fingerprints),
        },
        roots={
            "evidence_root": binding.evidence_root,
            "counter_root": binding.counter_root,
            "disposition_root": binding.disposition_root,
        },
        outcome={
            "critical_counterevidence_clear": summary.critical_counterevidence_clear,
            "commit_ready": summary.evidence_gates_satisfied,
        },
        trace_sequence=_risk_trace_sequence(scenario),
        failure_code="unresolved_critical_counterevidence",
    )


def _probe_case_04(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    counter = _observation(
        scenario,
        index=401,
        polarity=ObservationPolarity.CONTRADICT,
    )
    rejected = False
    error_type = ""
    try:
        issue_reference_disposition(
            scenario.namespace,
            counter,
            index=401,
            kind=CounterevidenceDispositionKind.REBUTTED,
            rebuttal_observations=(),
            resolution_ref="",
        )
    except (GovernanceError, ValueError) as exc:
        rejected = True
        error_type = type(exc).__name__
    return _result(
        metrics={"rebuttal_observation_count": 0},
        roots={"counter_observation_ref": verified_observation_fingerprint(counter)},
        outcome={"rejected": rejected, "error_type": error_type},
        trace_sequence=_risk_trace_sequence(scenario),
        failure_code="fake_rebuttal_rejected" if rejected else "fake_rebuttal_accepted",
    )


def _probe_case_05(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    observations = tuple(
        _observation(
            scenario,
            index=500 + index,
            source_domain=f"domain:{scenario.namespace}:low:{index}",
            quality_ppm=500_000,
            relevance_ppm=500_000,
        )
        for index in range(1, 9)
    )
    binding = _binding(
        scenario,
        candidate_id=scenario.leader_id,
        positives=observations,
        variant="case-05",
    )
    summary = _evaluate_binding(
        scenario,
        binding,
        positives=observations,
    )
    qualifying = sum(1 for item in summary.source_domains if item.qualifies)
    return _result(
        metrics={
            "domain_count": len(summary.source_domains),
            "qualifying_domain_count": qualifying,
            "source_diversity": summary.source_diversity,
            "domain_floor": scenario.policy.evidence_qualification.domain_contribution_floor,
        },
        roots={"positive_root": binding.positive_root},
        outcome={"low_weight_domains_raise_diversity": summary.source_diversity > 0},
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_06(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector, shared_cluster=True)
    replay = initialize_support_lease_replay_state(
        profile=scenario.profile,
        protocol_id=scenario.protocol_id,
        issuer_id=f"governance:tck:support-dedup:{scenario.namespace}",
        authority=AuthorityLevel.GOVERNANCE,
        initialized_at_step=0,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:support-dedup",
        trace_event_id=f"trace:{scenario.namespace}:support-dedup",
    )
    observations = tuple(
        _observation(
            scenario,
            index=600 + index,
            principal_index=index - 1,
            candidate_id=scenario.leader_id,
        )
        for index in range(1, 3)
    )
    leases = []
    for index, (principal, observation) in enumerate(
        zip(scenario.principals[:2], observations, strict=True), start=1
    ):
        lease, replay = issue_reference_lease(
            scenario.namespace,
            index=600 + index,
            principal=principal,
            observation=observation,
            candidate_id=scenario.leader_id,
            claim_fingerprint=scenario.claims[scenario.leader_id],
            profile=scenario.profile,
            assurance=scenario.assurance,
            manifest_root=scenario.manifest_root,
            commit_policy_root=scenario.commit_policy_root,
            protocol_id=scenario.protocol_id,
            run_id=scenario.run_id,
            target=scenario.target,
            epoch=scenario.epoch,
            policy=scenario.policy,
            membership_snapshot=scenario.membership_snapshot,
            membership_state=scenario.membership_state,
            replay_state=replay,
            prior_leases=tuple(leases),
            issuer_id=f"governance:tck:support-dedup:{scenario.namespace}",
        )
        leases.append(lease)
    evaluation = evaluate_support_leases(
        tuple(leases),
        revocations=(),
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=replay,
        commit_policy=scenario.policy,
        candidate_id=scenario.leader_id,
        claim_fingerprint=scenario.claims[scenario.leader_id],
        current_step=5,
    )
    return _result(
        metrics={
            "principal_count": 2,
            "eligible_cluster_count": evaluation.eligible_cluster_count,
            "active_support_cluster_count": evaluation.active_support_cluster_count,
        },
        roots={"lease_root": evaluation.lease_root},
        outcome={"cluster_deduplicated": evaluation.active_support_cluster_count == 1},
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_07(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    leader_leases = tuple(
        item for item in scenario.leases if item.candidate_id == scenario.leader_id
    )
    no_evidence_rejected = False
    try:
        empty_proposal = SupportLeaseProposal(
            proposal_id=f"support-proposal:{scenario.namespace}:empty",
            profile=scenario.profile,
            assurance=scenario.assurance,
            manifest_root=scenario.manifest_root,
            commit_policy_root=scenario.commit_policy_root,
            protocol_id=scenario.protocol_id,
            run_id=scenario.run_id,
            target=scenario.target,
            candidate_id=scenario.leader_id,
            claim_fingerprint=scenario.claims[scenario.leader_id],
            epoch=scenario.epoch,
            principal_id=scenario.principals[0].principal_id,
            positive_observation_fingerprints=(),
            nonce=f"nonce:lease:{scenario.namespace}:empty",
            proposed_at_step=3,
            provenance=f"urn:pheroos:tck:{scenario.namespace}:empty-lease",
            trace_event_id=f"trace:{scenario.namespace}:empty-lease",
        )
        issue_support_lease(
            empty_proposal,
            principal_verification=scenario.principals[0],
            membership_snapshot=scenario.membership_snapshot,
            membership_epoch_state=scenario.membership_state,
            replay_state=scenario.support_replay_state,
            positive_observations=(),
            commit_policy=scenario.policy,
            lease_id=f"lease:{scenario.namespace}:empty",
            issuer_id=f"governance:tck:support:{scenario.namespace}",
            authority=AuthorityLevel.GOVERNANCE,
            current_step=4,
            issuance_provenance=f"urn:pheroos:tck:{scenario.namespace}:empty-lease",
            issuance_trace_event_id=f"trace:{scenario.namespace}:empty-lease",
            prior_leases=scenario.leases,
        )
    except (GovernanceError, ValueError):
        no_evidence_rejected = True
    revocations = tuple(
        revoke_support_lease(
            lease,
            revocation_id=f"revocation:{scenario.namespace}:leader:{index}",
            reason_codes=("tck_revoked",),
            issuer_id=lease.issuer_id,
            authority=AuthorityLevel.GOVERNANCE,
            current_step=5,
            provenance=(
                f"urn:pheroos:tck:{scenario.namespace}:revocation:{index}"
            ),
            trace_event_id=(
                f"trace:{scenario.namespace}:revocation:{index}"
            ),
        )
        for index, lease in enumerate(leader_leases, start=1)
    )
    revoked = evaluate_support_leases(
        scenario.leases,
        revocations=revocations,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.support_replay_state,
        commit_policy=scenario.policy,
        candidate_id=scenario.leader_id,
        claim_fingerprint=scenario.claims[scenario.leader_id],
        current_step=5,
    )
    expired_step = max(item.expires_at_step for item in scenario.leases)
    expired = evaluate_support_leases(
        scenario.leases,
        revocations=(),
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.support_replay_state,
        commit_policy=scenario.policy,
        candidate_id=scenario.leader_id,
        claim_fingerprint=scenario.claims[scenario.leader_id],
        current_step=expired_step,
    )
    cross_replay = initialize_support_lease_replay_state(
        profile=scenario.profile,
        protocol_id=scenario.protocol_id,
        issuer_id=f"governance:tck:support-cross:{scenario.namespace}",
        authority=AuthorityLevel.GOVERNANCE,
        initialized_at_step=0,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:support-cross",
        trace_event_id=f"trace:{scenario.namespace}:support-cross",
    )
    cross_lease, cross_replay = issue_reference_lease(
        scenario.namespace,
        index=704,
        principal=scenario.principals[1],
        observation=scenario.observations[scenario.other_id][0],
        candidate_id=scenario.other_id,
        claim_fingerprint=scenario.claims[scenario.other_id],
        profile=scenario.profile,
        assurance=scenario.assurance,
        manifest_root=scenario.manifest_root,
        commit_policy_root=scenario.commit_policy_root,
        protocol_id=scenario.protocol_id,
        run_id=scenario.run_id,
        target=scenario.target,
        epoch=scenario.epoch,
        policy=scenario.policy,
        membership_snapshot=scenario.membership_snapshot,
        membership_state=scenario.membership_state,
        replay_state=cross_replay,
        prior_leases=(),
        issuer_id=f"governance:tck:support-cross:{scenario.namespace}",
    )
    cross_candidate = evaluate_support_leases(
        (cross_lease,),
        revocations=(),
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=cross_replay,
        commit_policy=scenario.policy,
        candidate_id=scenario.leader_id,
        claim_fingerprint=scenario.claims[scenario.leader_id],
        current_step=5,
    )
    return _result(
        metrics={
            "revoked_active": revoked.active_support_cluster_count,
            "expired_active": expired.active_support_cluster_count,
            "cross_candidate_active": cross_candidate.active_support_cluster_count,
        },
        roots={
            "revoked_lease_root": revoked.lease_root,
            "expired_lease_root": expired.lease_root,
            "cross_candidate_lease_root": cross_candidate.lease_root,
        },
        outcome={
            "no_evidence_rejected": no_evidence_rejected,
            "all_invalid_excluded": all(
                item == 0
                for item in (
                    revoked.active_support_cluster_count,
                    expired.active_support_cluster_count,
                    cross_candidate.active_support_cluster_count,
                )
            ),
        },
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_08(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector, shared_cluster=True)
    evaluation = evaluate_support_leases(
        scenario.leases,
        revocations=(),
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.support_replay_state,
        commit_policy=scenario.policy,
        candidate_id=scenario.leader_id,
        claim_fingerprint=scenario.claims[scenario.leader_id],
        current_step=5,
    )
    return _result(
        metrics={
            "equivocation_finding_count": len(evaluation.equivocation_findings),
            "active_support_cluster_count": evaluation.active_support_cluster_count,
            "excluded_lease_count": len(evaluation.excluded_lease_fingerprints),
        },
        roots={"lease_root": evaluation.lease_root},
        outcome={"equivocation_detected": bool(evaluation.equivocation_findings)},
        trace_sequence=_risk_trace_sequence(scenario),
        failure_code="support_equivocation",
    )


def _initialize_window(scenario: ReferenceScenario) -> Any:
    return initialize_reference_window(scenario)


def _liveness_input(
    scenario: ReferenceScenario,
    window: Any,
    *,
    assessment: Any | None,
    step: int,
    suffix: str,
    finality_status: CommitFinalityStatus,
    finality_verification: Any | None = None,
    previous_progress: DecisionProgress | None = None,
    invalid_reason_codes: Sequence[str] = (),
    safety_violation_reason_codes: Sequence[str] = (),
    blocked_reason_codes: Sequence[str] = (),
    finality_reason_codes: Sequence[str] = (),
    next_required_inputs: Sequence[str] = (),
) -> Any:
    fixture_key = (
        scenario.namespace,
        commit_window_state_fingerprint(window),
        (
            commit_assessment_fingerprint(assessment)
            if assessment is not None
            else ""
        ),
        step,
        suffix,
        finality_status.value,
        (
            commit_finality_verification_fingerprint(finality_verification)
            if finality_verification is not None
            else ""
        ),
        (
            decision_progress_fingerprint(previous_progress)
            if previous_progress is not None
            else ""
        ),
        tuple(invalid_reason_codes),
        tuple(safety_violation_reason_codes),
        tuple(blocked_reason_codes),
        tuple(finality_reason_codes),
        tuple(next_required_inputs),
    )
    with _LIVENESS_INPUT_FIXTURE_CACHE_LOCK:
        cached = _LIVENESS_INPUT_FIXTURE_CACHE.get(fixture_key)
        if cached is not None:
            return cached
    issued = issue_commit_liveness_input(
        window,
        assessment=assessment,
        replay_state=scenario.replay_state,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        support_replay_state=scenario.support_replay_state,
        commit_policy=scenario.policy,
        previous_progress=previous_progress,
        current_step=step,
        finality_status=finality_status,
        finality_verification=finality_verification,
        invalid_reason_codes=tuple(invalid_reason_codes),
        safety_violation_reason_codes=tuple(safety_violation_reason_codes),
        blocked_reason_codes=tuple(blocked_reason_codes),
        finality_reason_codes=tuple(finality_reason_codes),
        next_required_inputs=tuple(next_required_inputs),
        input_id=f"liveness:{scenario.namespace}:{suffix}:{step}",
        issuer_id="governance:tck:liveness",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:liveness:{suffix}:{step}",
        trace_event_id=f"trace:{scenario.namespace}:liveness:{suffix}:{step}",
    )
    with _LIVENESS_INPUT_FIXTURE_CACHE_LOCK:
        _LIVENESS_INPUT_FIXTURE_CACHE[fixture_key] = issued
    return issued


def _local_commit_outcome(stable: ReferenceStableCommit, *, suffix: str) -> DecisionOutcome:
    scenario = stable.scenario
    assessment = stable.assessments[-1]
    step = stable.window.last_evaluated_step
    finality = verify_local_commit_finality(
        stable.receipt,
        scenario.context,
        assessment,
        stable.window,
        commit_policy=scenario.policy,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.replay_state,
        support_replay_state=scenario.support_replay_state,
        current_step=step,
        verifier_id="governance:tck:local-finality",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:local-finality:{suffix}",
        trace_event_id=f"trace:{scenario.namespace}:local-finality:{suffix}",
    )
    result = reduce_commit_liveness(
        stable.window,
        commit_policy=scenario.policy,
        liveness_input=_liveness_input(
            scenario,
            stable.window,
            assessment=assessment,
            step=step,
            suffix=suffix,
            finality_status=CommitFinalityStatus.VERIFIED,
            finality_verification=finality,
        ),
    )
    if type(result) is not DecisionOutcome:
        raise ValueError("local finality did not produce a terminal outcome")
    return result


def _probe_case_09(vector: _CommitTckRequest) -> dict[str, Any]:
    manifest = capability_manifest_from_dict(_require_vector_manifest(vector))
    diagnostics = validate_capability_manifest(manifest)
    codes = sorted(item.code for item in diagnostics if item.level == "error")
    policy = manifest.protocol.collective_commit_policy
    assert policy is not None
    low = policy.risk_bands["LOW"]
    high = policy.risk_bands["HIGH"]
    monotonic = "commit_risk_monotonicity_invalid" not in codes
    return _result(
        metrics={
            "low_minimum_positive": low.minimum_positive_evidence,
            "high_minimum_positive": high.minimum_positive_evidence,
        },
        roots={
            "manifest_root": commit_manifest_fingerprint(
                manifest,
                profile=vector.profile,
            ),
        },
        outcome={
            "valid": not codes,
            "risk_transition_monotonic": monotonic,
            "diagnostic_codes": codes,
        },
        failure_code=(codes[0] if codes else None),
    )


def _probe_case_10(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector, variant="original-heads")
    window = _initialize_window(scenario)
    assessment = assess_reference_scenario(
        scenario,
        step=5,
        suffix="original-heads",
    )
    window = advance_commit_window_state(
        window,
        assessment=assessment,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        current_step=5,
    )
    changed = _reference_scenario(vector, variant="changed-heads")
    changed_assessment = assess_reference_scenario(
        changed,
        step=5,
        suffix="changed-heads",
    )
    rejected = False
    try:
        advance_commit_window_state(
            window,
            assessment=changed_assessment,
            commit_policy=scenario.policy,
            threshold_snapshot=changed.threshold,
            current_step=6,
        )
    except (GovernanceError, ValueError):
        rejected = True
    return _result(
        metrics={
            "original_window_count": window.window_count,
            "changed_risk_root": int(
                scenario.context.risk_assessment_fingerprint
                != changed.context.risk_assessment_fingerprint
            ),
            "changed_membership_root": int(
                scenario.context.membership_root != changed.context.membership_root
            ),
        },
        roots={
            "window_state_ref": commit_window_state_fingerprint(window),
            "original_risk_root": scenario.context.risk_assessment_fingerprint,
            "changed_risk_root": changed.context.risk_assessment_fingerprint,
            "original_membership_root": scenario.context.membership_root,
            "changed_membership_root": changed.context.membership_root,
        },
        outcome={"stale_window_reuse_rejected": rejected},
        trace_sequence=_risk_trace_sequence(scenario),
        failure_code="authority_head_changed" if rejected else None,
    )


def _verified_scout(
    scenario: ReferenceScenario,
    *,
    source_id: str,
    candidate_id: str,
) -> ScoutReport:
    trace_id = f"trace:{scenario.namespace}:{source_id}"
    return ScoutReport(
        source_id,
        candidate_id,
        f"evidence:{scenario.namespace}:{source_id}",
        f"runtime:tck:{source_id}",
        target=scenario.target,
        trace_event_id=trace_id,
        verification=verify_signal_input(
            target=scenario.target,
            source_id=source_id,
            subject_id=candidate_id,
            verifier_id="governance:tck:hybrid-attention",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="governance:tck:hybrid-attention",
            trace_event_id=f"{trace_id}:verified",
        ),
    )


def _probe_case_11(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    policy = scenario.manifest.protocol.collective_decision_policy
    if policy is None:
        raise ValueError("case 11 requires a declared Hybrid attention policy")
    assessment = assess_reference_scenario(scenario, step=5, suffix="hybrid-truth")
    attention_candidate = _text(
        vector.inputs.get("attention_candidate"),
        "case 11 attention_candidate",
    )
    candidates = CandidateSet(tuple(
        Candidate(item.id, item.target, item.safe_fallback)
        for item in scenario.manifest.protocol.candidates
    ))
    scouts = [
        _verified_scout(
            scenario,
            source_id=f"scout:{attention_candidate}:{index}",
            candidate_id=attention_candidate,
        )
        for index in range(1, 3)
    ]
    attention, directive = evaluate_hybrid_attention_step(
        protocol_id=scenario.protocol_id,
        candidate_set=candidates,
        policy=policy,
        target=scenario.target,
        current_step=5,
        scout_reports=scouts,
        topology=_candidate_topology(scenario),
        fallback_candidate_id=scenario.fallback_id,
    )
    bound = bind_hybrid_commit_channels(
        attention=attention,
        exploration_directive=directive,
        commit_assessment=assessment,
    )
    truth = hybrid_commit_truth_projection(bound)
    attention_projection = hybrid_attention_projection(bound)
    return _result(
        metrics={
            "leader_margin": bound.leader_margin,
            "attention_top_candidate": directive.candidate_order[0],
        },
        roots={
            "commit_truth_root": bound.commit_truth_root,
            "commit_evidence_root": bound.commit_evidence_root,
            "commit_challenge_root": bound.commit_challenge_root,
            "commit_lease_root": bound.commit_lease_root,
            "attention_root": bound.attention_fingerprint,
        },
        outcome={
            "commit_leader": bound.leader_candidate_id,
            "attention_commit_authority": bound.attention_commit_authority,
            "truth_projection": truth,
            "attention_projection": attention_projection,
        },
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_12(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    window = _initialize_window(scenario)
    assessment = assess_reference_scenario(scenario, step=5, suffix="single-step")
    window = advance_commit_window_state(
        window,
        assessment=assessment,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        current_step=5,
    )
    decision = reduce_commit_liveness(
        window,
        commit_policy=scenario.policy,
        liveness_input=_liveness_input(
            scenario,
            window,
            assessment=assessment,
            step=5,
            suffix="single-step",
            finality_status=CommitFinalityStatus.PENDING,
            next_required_inputs=("stability_window",),
        ),
    )
    if type(decision) is not DecisionProgress:
        raise ValueError("single-step readiness unexpectedly became terminal")
    return _result(
        metrics={
            "window_count": window.window_count,
            "required_stability_steps": window.minimum_stability_steps,
        },
        roots={
            "window_root": window.window_root,
            "progress_window_ref": decision.window_state_ref,
        },
        progress={
            "phase": decision.phase.value,
            "terminal": decision.terminal,
            "window_count": decision.window_count,
            "leader_candidate_id": decision.leader_candidate_id,
        },
        outcome=None,
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_13(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    stable = build_reference_stable_commit(scenario, variant="case-13")
    outcome = _local_commit_outcome(stable, suffix="case-13")
    return _result(
        metrics={
            "window_count": stable.window.window_count,
            "required_stability_steps": stable.window.minimum_stability_steps,
        },
        roots={
            "window_root": stable.window.window_root,
            "receipt_ref": local_commit_receipt_fingerprint(stable.receipt),
            "outcome_ref": decision_outcome_fingerprint(outcome),
        },
        progress=None,
        outcome={
            "kind": outcome.kind.value,
            "candidate_id": outcome.candidate_id,
            "authoritative_commit": outcome.authoritative_commit,
            "epistemically_committed": outcome.epistemically_committed,
        },
        trace_sequence=_risk_trace_sequence(scenario),
        certificate={
            "kind": "local_receipt",
            "ref": local_commit_receipt_fingerprint(stable.receipt),
        },
    )


def _epoch_threshold(scenario: ReferenceScenario, *, epoch: int, step: int) -> Any:
    fixture_key = (
        scenario.namespace,
        scenario.profile,
        scenario.manifest_root,
        scenario.commit_policy_root,
        epoch,
        step,
    )
    with _EPOCH_THRESHOLD_FIXTURE_CACHE_LOCK:
        cached = _EPOCH_THRESHOLD_FIXTURE_CACHE.get(fixture_key)
        if cached is not None:
            return cached
    chain = initialize_risk_assessment_chain(
        commit_policy=scenario.policy,
        profile=scenario.profile,
        assurance=scenario.assurance,
        manifest_root=scenario.manifest_root,
        commit_policy_root=scenario.commit_policy_root,
        protocol_id=scenario.protocol_id,
        run_id=scenario.run_id,
        target=scenario.target,
        epoch=epoch,
        issuer_id="governance:tck:risk-chain",
        authority=AuthorityLevel.GOVERNANCE,
        initialized_at_step=step,
        expires_at_step=30,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:risk-chain:{epoch}",
        trace_event_id=f"trace:{scenario.namespace}:risk-chain:{epoch}",
    )
    risk, chain = issue_risk_assessment(
        chain,
        assessment_id=f"risk:{scenario.namespace}:{epoch}",
        risk_band=RiskBand.LOW,
        risk_input_fingerprints=(reference_fingerprint(f"risk:{scenario.namespace}:{epoch}"),),
        rationale_codes=("epoch_restart",),
        assessment_method="declared-risk-matrix-v1",
        commit_policy=scenario.policy,
        profile=scenario.profile,
        assurance=scenario.assurance,
        manifest_root=scenario.manifest_root,
        commit_policy_root=scenario.commit_policy_root,
        protocol_id=scenario.protocol_id,
        run_id=scenario.run_id,
        target=scenario.target,
        epoch=epoch,
        issuer_id="governance:tck:risk",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=step,
        expires_at_step=30,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:risk:{epoch}",
        trace_event_id=f"trace:{scenario.namespace}:risk:{epoch}",
    )
    threshold = issue_commit_threshold_snapshot(
        risk,
        chain_state=chain,
        threshold_id=f"threshold:{scenario.namespace}:{epoch}",
        commit_policy=scenario.policy,
        issuer_id="governance:tck:threshold",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=step,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:threshold:{epoch}",
        trace_event_id=f"trace:{scenario.namespace}:threshold:{epoch}",
    )
    with _EPOCH_THRESHOLD_FIXTURE_CACHE_LOCK:
        _EPOCH_THRESHOLD_FIXTURE_CACHE[fixture_key] = threshold
    return threshold


def _probe_case_14(vector: _CommitTckRequest) -> dict[str, Any]:
    # Gate failure.
    gate = _reference_scenario(vector, variant="gate-reset")
    gate_window = _initialize_window(gate)
    ready = assess_reference_scenario(gate, step=5, suffix="gate-ready")
    gate_window = advance_commit_window_state(
        gate_window,
        assessment=ready,
        commit_policy=gate.policy,
        threshold_snapshot=gate.threshold,
        current_step=5,
    )
    stop, permission = issue_reference_action_gates(
        gate.namespace,
        context=gate.context,
        action=CommitAction.COMMIT,
        blocked=True,
        current_step=6,
        expires_at_step=20,
        suffix="gate-blocked",
    )
    blocked = assess_reference_scenario(
        gate,
        step=6,
        suffix="gate-blocked",
        stop_resolution=stop,
        permission=permission,
    )
    gate_reset = advance_commit_window_state(
        gate_window,
        assessment=blocked,
        commit_policy=gate.policy,
        threshold_snapshot=gate.threshold,
        current_step=6,
    )

    # Leader change after an append-only evidence/support head rotation.
    leader = _reference_scenario(
        vector,
        variant="leader-reset",
        minimum_membership_size=4,
    )
    leader_window = _initialize_window(leader)
    alpha_leads = assess_reference_scenario(
        leader,
        step=5,
        suffix="alpha-leads",
    )
    leader_window = advance_commit_window_state(
        leader_window,
        assessment=alpha_leads,
        commit_policy=leader.policy,
        threshold_snapshot=leader.threshold,
        current_step=5,
    )
    beta_extra = tuple(
        _observation(
            leader,
            index=1_400 + index,
            principal_index=3,
            candidate_id=leader.other_id,
        )
        for index in range(1, 3)
    )
    beta_original = next(
        item
        for item in leader.candidate_inputs
        if item.candidate_id == leader.other_id
    )
    beta_positives = (*beta_original.positive_observations, *beta_extra)
    beta_binding = _binding(
        leader,
        candidate_id=leader.other_id,
        positives=beta_positives,
        variant="beta-expanded",
    )
    beta_expanded = CandidateCommitInput(
        candidate_id=leader.other_id,
        claim_fingerprint=leader.claims[leader.other_id],
        evidence_binding=beta_binding,
        positive_observations=beta_positives,
        counter_observations=(),
        dispositions=(),
        challenges=(leader.challenges[leader.other_id],),
    )
    leader_inputs = tuple(
        beta_expanded if item.candidate_id == leader.other_id else item
        for item in leader.candidate_inputs
    )
    beta_lease, beta_support_replay = issue_reference_lease(
        leader.namespace,
        index=1_403,
        principal=leader.principals[3],
        observation=beta_extra[0],
        candidate_id=leader.other_id,
        claim_fingerprint=leader.claims[leader.other_id],
        profile=leader.profile,
        assurance=leader.assurance,
        manifest_root=leader.manifest_root,
        commit_policy_root=leader.commit_policy_root,
        protocol_id=leader.protocol_id,
        run_id=leader.run_id,
        target=leader.target,
        epoch=leader.epoch,
        policy=leader.policy,
        membership_snapshot=leader.membership_snapshot,
        membership_state=leader.membership_state,
        replay_state=leader.support_replay_state,
        prior_leases=leader.leases,
        current_step=6,
    )
    leader_leases = (*leader.leases, beta_lease)
    (
        leader_context,
        leader_replay,
        beta_support_replay,
        leader_stop,
        leader_permission,
    ) = rotate_reference_context(
        leader,
        candidate_inputs=leader_inputs,
        leases=leader_leases,
        current_step=6,
        suffix="beta-leads",
        support_replay_state=beta_support_replay,
    )
    beta_leads = assess_reference_scenario(
        leader,
        step=6,
        suffix="beta-leads",
        candidate_inputs=leader_inputs,
        leases=leader_leases,
        context=leader_context,
        replay_state=leader_replay,
        support_replay_state=beta_support_replay,
        stop_resolution=leader_stop,
        permission=leader_permission,
    )
    leader_reset = advance_commit_window_state(
        leader_window,
        assessment=beta_leads,
        commit_policy=leader.policy,
        threshold_snapshot=leader.threshold,
        current_step=6,
    )

    # Step gap.
    gap = _reference_scenario(vector, variant="gap-reset")
    gap_window = _initialize_window(gap)
    gap_first = assess_reference_scenario(gap, step=5, suffix="gap-first")
    gap_window = advance_commit_window_state(
        gap_window,
        assessment=gap_first,
        commit_policy=gap.policy,
        threshold_snapshot=gap.threshold,
        current_step=5,
    )
    gap_next = assess_reference_scenario(gap, step=7, suffix="gap-next")
    gap_reset = advance_commit_window_state(
        gap_window,
        assessment=gap_next,
        commit_policy=gap.policy,
        threshold_snapshot=gap.threshold,
        current_step=7,
    )

    # Epoch transition.
    epoch = _reference_scenario(vector, variant="epoch-reset")
    epoch_window = _initialize_window(epoch)
    epoch_first = assess_reference_scenario(epoch, step=5, suffix="epoch-first")
    epoch_window = advance_commit_window_state(
        epoch_window,
        assessment=epoch_first,
        commit_policy=epoch.policy,
        threshold_snapshot=epoch.threshold,
        current_step=5,
    )
    new_threshold = _epoch_threshold(epoch, epoch=epoch.epoch + 1, step=6)
    epoch_reset = restart_commit_window_epoch(
        epoch_window,
        new_epoch=epoch.epoch + 1,
        current_step=6,
        commit_policy=epoch.policy,
        threshold_snapshot=new_threshold,
        membership_root=reference_fingerprint(
            f"membership:{epoch.namespace}:{epoch.epoch + 1}"
        ),
    )
    reasons = {
        "gate_failure": gate_reset.reset_reason,
        "leader_change": leader_reset.reset_reason,
        "step_gap": gap_reset.reset_reason,
        "epoch_change": epoch_reset.reset_reason,
    }
    reset_counts = {
        "gate_failure": gate_reset.window_count,
        "leader_change": leader_reset.window_count,
        "step_gap": gap_reset.window_count,
        "epoch_change": epoch_reset.window_count,
    }
    prior_assessments_not_retained = bool(
        gate_reset.ordered_assessment_refs == ()
        and leader_reset.ordered_assessment_refs
        == (commit_assessment_fingerprint(beta_leads),)
        and gap_reset.ordered_assessment_refs
        == (commit_assessment_fingerprint(gap_next),)
        and epoch_reset.ordered_assessment_refs == ()
    )
    return _result(
        metrics={
            "gate_window_count": gate_reset.window_count,
            "leader_window_count": leader_reset.window_count,
            "gap_window_count": gap_reset.window_count,
            "epoch_window_count": epoch_reset.window_count,
        },
        roots={
            "gate_window_ref": commit_window_state_fingerprint(gate_reset),
            "leader_window_ref": commit_window_state_fingerprint(leader_reset),
            "gap_window_ref": commit_window_state_fingerprint(gap_reset),
            "epoch_window_ref": commit_window_state_fingerprint(epoch_reset),
        },
        outcome={
            "reset_reasons": reasons,
            "all_reset": bool(
                reasons
                == {
                    "gate_failure": "gate_failure",
                    "leader_change": "leader_change",
                    "step_gap": "step_gap",
                    "epoch_change": "epoch_change",
                }
                and reset_counts
                == {
                    "gate_failure": 0,
                    "leader_change": 1,
                    "step_gap": 1,
                    "epoch_change": 0,
                }
                and prior_assessments_not_retained
            ),
            "prior_assessments_not_retained": (
                prior_assessments_not_retained
            ),
            "deadlines_not_extended": epoch_reset.absolute_deadline_step == epoch_window.absolute_deadline_step,
        },
        trace_sequence=_risk_trace_sequence(gate),
    )


def _probe_case_15(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector, variant="evidence-continuity")
    leader = next(
        item
        for item in scenario.candidate_inputs
        if item.candidate_id == scenario.leader_id
    )
    extra = _observation(
        scenario,
        index=1_501,
        principal_index=0,
        candidate_id=scenario.leader_id,
    )
    expanded_positives = (*leader.positive_observations, extra)
    expanded_binding = _binding(
        scenario,
        candidate_id=scenario.leader_id,
        positives=expanded_positives,
        variant="expanded-positive",
    )
    expanded_leader = CandidateCommitInput(
        candidate_id=scenario.leader_id,
        claim_fingerprint=scenario.claims[scenario.leader_id],
        evidence_binding=expanded_binding,
        positive_observations=expanded_positives,
        counter_observations=(),
        dispositions=(),
        challenges=(scenario.challenges[scenario.leader_id],),
    )
    expanded_inputs = tuple(
        expanded_leader if item.candidate_id == scenario.leader_id else item
        for item in scenario.candidate_inputs
    )
    window = _initialize_window(scenario)
    first = assess_reference_scenario(
        scenario,
        step=5,
        suffix="two-positive",
    )
    window = advance_commit_window_state(
        window,
        assessment=first,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        current_step=5,
    )
    context, replay, support_replay, stop, permission = rotate_reference_context(
        scenario,
        candidate_inputs=expanded_inputs,
        leases=scenario.leases,
        current_step=6,
        suffix="expanded-positive",
    )
    second = assess_reference_scenario(
        scenario,
        step=6,
        suffix="three-positive",
        candidate_inputs=expanded_inputs,
        context=context,
        replay_state=replay,
        support_replay_state=support_replay,
        stop_resolution=stop,
        permission=permission,
    )
    continued = advance_commit_window_state(
        window,
        assessment=second,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        current_step=6,
    )
    return _result(
        metrics={
            "first_window_count": window.window_count,
            "second_window_count": continued.window_count,
        },
        roots={
            "first_evidence_root": first.collective_evidence_root,
            "second_evidence_root": second.collective_evidence_root,
            "window_root": continued.window_root,
        },
        outcome={
            "evidence_root_changed": first.collective_evidence_root != second.collective_evidence_root,
            "leader_continuous": first.leader_candidate_id == second.leader_candidate_id,
            "window_continued": continued.window_count == window.window_count + 1,
        },
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_16(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector, tie=True)
    assessment = assess_reference_scenario(scenario, step=5, suffix="tie")
    leaders = [
        item.candidate_id
        for item in assessment.candidate_metrics
        if item.net_evidence == max(
            metric.net_evidence for metric in assessment.candidate_metrics
        )
    ]
    return _result(
        metrics={
            "leader_margin": assessment.leader_margin,
            "top_candidate_count": len(leaders),
        },
        roots={"assessment_ref": commit_assessment_fingerprint(assessment)},
        outcome={
            "status": assessment.status.value,
            "unique_leader": assessment.unique_leader,
            "leader_candidate_id": assessment.leader_candidate_id,
            "lexical_tie_break_used": bool(assessment.leader_candidate_id),
        },
        trace_sequence=_risk_trace_sequence(scenario),
        failure_code="non_unique_argmax",
    )


def _probe_case_17(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    order = vector.inputs.get("candidate_order")
    if not isinstance(order, list) or sorted(order) != [0, 1]:
        raise ValueError("case 17 candidate_order must be a two-item permutation")
    candidates = tuple(scenario.candidate_inputs[index] for index in order)
    leases = (
        scenario.leases
        if order == [0, 1]
        else tuple(reversed(scenario.leases))
    )
    normalized_candidates = tuple(
        replace(
            item,
            positive_observations=tuple(reversed(item.positive_observations)),
            challenges=tuple(reversed(item.challenges)),
        )
        for item in candidates
    )
    assessment = assess_reference_scenario(
        scenario,
        step=5,
        suffix="permutation",
        candidate_inputs=normalized_candidates,
        leases=leases,
    )
    metrics = [
        candidate_commit_metrics_payload(item)
        for item in assessment.candidate_metrics
    ]
    return _result(
        metrics={
            "candidate_metrics": metrics,
            "leader_margin": assessment.leader_margin,
        },
        roots={
            "assessment_ref": commit_assessment_fingerprint(assessment),
            "evidence_root": assessment.collective_evidence_root,
            "challenge_root": assessment.collective_challenge_root,
            "lease_root": assessment.collective_lease_root,
        },
        outcome={
            "status": assessment.status.value,
            "leader_candidate_id": assessment.leader_candidate_id,
            "unique_leader": assessment.unique_leader,
        },
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _deadline_outcome(
    scenario: ReferenceScenario,
    *,
    suffix: str,
    finality_status: CommitFinalityStatus = CommitFinalityStatus.PENDING,
    finality_reason_codes: Sequence[str] = (),
) -> tuple[Any, DecisionOutcome]:
    window = _initialize_window(scenario)
    assessment = assess_reference_scenario(
        scenario,
        step=5,
        suffix=f"{suffix}:assessment",
    )
    window = advance_commit_window_state(
        window,
        assessment=assessment,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        current_step=5,
    )
    deadline = min(window.absolute_deadline_step, window.absolute_run_deadline_step)
    decision = reduce_commit_liveness(
        window,
        commit_policy=scenario.policy,
        liveness_input=_liveness_input(
            scenario,
            window,
            assessment=assessment,
            step=deadline,
            suffix=f"{suffix}:deadline",
            finality_status=finality_status,
            finality_reason_codes=finality_reason_codes,
        ),
    )
    if type(decision) is not DecisionOutcome:
        raise ValueError("deadline did not produce a terminal outcome")
    return window, decision


def _heartbeat_to_deadline(
    stable: ReferenceStableCommit,
    *,
    suffix: str,
    final_status: CommitFinalityStatus,
    final_reason_codes: Sequence[str] = (),
) -> tuple[DecisionProgress, DecisionOutcome]:
    scenario = stable.scenario
    assessment = stable.assessments[-1]
    sealed_step = stable.window.last_evaluated_step
    deadline = min(
        stable.window.absolute_deadline_step,
        stable.window.absolute_run_deadline_step,
    )
    first = reduce_commit_liveness(
        stable.window,
        commit_policy=scenario.policy,
        liveness_input=_liveness_input(
            scenario,
            stable.window,
            assessment=assessment,
            step=sealed_step,
            suffix=f"{suffix}:pending",
            finality_status=CommitFinalityStatus.PENDING,
            next_required_inputs=("finality_certificate",),
        ),
    )
    if type(first) is not DecisionProgress:
        raise ValueError("sealed pre-deadline state did not remain pending")
    progress = first
    for step in range(sealed_step + 1, deadline):
        next_value = reduce_commit_liveness(
            stable.window,
            commit_policy=scenario.policy,
            liveness_input=_liveness_input(
                scenario,
                stable.window,
                assessment=assessment,
                step=step,
                suffix=f"{suffix}:heartbeat",
                finality_status=CommitFinalityStatus.PENDING,
                previous_progress=progress,
                next_required_inputs=("finality_certificate",),
            ),
        )
        if type(next_value) is not DecisionProgress:
            raise ValueError("pre-deadline heartbeat became terminal")
        progress = next_value
    terminal = reduce_commit_liveness(
        stable.window,
        commit_policy=scenario.policy,
        liveness_input=_liveness_input(
            scenario,
            stable.window,
            assessment=assessment,
            step=deadline,
            suffix=f"{suffix}:deadline",
            finality_status=final_status,
            previous_progress=progress,
            finality_reason_codes=tuple(final_reason_codes),
        ),
    )
    if type(terminal) is not DecisionOutcome:
        raise ValueError("deadline heartbeat did not become terminal")
    return first, terminal


def _probe_case_18(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    stable = build_reference_stable_commit(scenario, variant="case-18")
    progress, terminal = _heartbeat_to_deadline(
        stable,
        suffix="case-18",
        final_status=CommitFinalityStatus.PENDING,
    )
    return _result(
        metrics={
            "pending_step": progress.current_step,
            "deadline_step": terminal.current_step,
        },
        roots={
            "window_root": stable.window.window_root,
            "terminal_outcome_ref": decision_outcome_fingerprint(terminal),
        },
        progress={
            "phase": progress.phase.value,
            "terminal": progress.terminal,
            "sealed_window": progress.sealed_window,
        },
        outcome={
            "kind": terminal.kind.value,
            "terminal": terminal.terminal,
            "deadline_reached": terminal.current_step
            >= min(
                terminal.absolute_deadline_step,
                terminal.absolute_run_deadline_step,
            ),
            "authoritative_commit": terminal.authoritative_commit,
        },
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_19(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    window, terminal = _deadline_outcome(scenario, suffix="case-19")
    assessment = assess_reference_scenario(
        scenario,
        step=5,
        suffix="case-19:assessment",
    )
    leader = next(
        item
        for item in assessment.candidate_metrics
        if item.candidate_id == assessment.leader_candidate_id
    )
    return _result(
        metrics={
            "positive_evidence": leader.positive_evidence,
            "minimum_positive_evidence": scenario.threshold.minimum_positive_evidence,
            "window_count": window.window_count,
        },
        roots={
            "threshold_root": commit_threshold_snapshot_fingerprint(scenario.threshold),
            "outcome_threshold_root": terminal.threshold_root,
        },
        outcome={
            "kind": terminal.kind.value,
            "authoritative_commit": terminal.authoritative_commit,
            "threshold_lowered": terminal.threshold_root != commit_threshold_snapshot_fingerprint(scenario.threshold),
            "failed_gate_became_commit": terminal.kind is DecisionOutcomeKind.EVIDENCE_COMMIT,
        },
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_20(vector: _CommitTckRequest) -> dict[str, Any]:
    manifest = _require_vector_manifest(vector)
    deadline_kind = _text(
        manifest["protocol"]["collective_commit_policy"]["terminal_outcome"]["deadline_outcome"],
        "case 20 deadline outcome",
    )
    scenario = _reference_scenario(
        vector,
        variant=f"deadline-{deadline_kind}",
    )
    _, terminal = _deadline_outcome(scenario, suffix=f"case-20:{deadline_kind}")
    return _result(
        metrics={"deadline_step": terminal.current_step},
        roots={"outcome_ref": decision_outcome_fingerprint(terminal)},
        outcome={
            "declared_deadline_outcome": deadline_kind,
            "kind": terminal.kind.value,
            "candidate_id": terminal.candidate_id,
            "authoritative_commit": terminal.authoritative_commit,
            "epistemically_committed": terminal.epistemically_committed,
        },
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_21(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector, blocked=True)
    window = _initialize_window(scenario)
    assessment = assess_reference_scenario(scenario, step=5, suffix="hard-stop")
    window = advance_commit_window_state(
        window,
        assessment=assessment,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        current_step=5,
    )
    terminal = reduce_commit_liveness(
        window,
        commit_policy=scenario.policy,
        liveness_input=_liveness_input(
            scenario,
            window,
            assessment=assessment,
            step=5,
            suffix="hard-stop",
            finality_status=CommitFinalityStatus.PENDING,
        ),
    )
    if type(terminal) is not DecisionOutcome:
        raise ValueError("hard commit stop did not become terminal")
    return _result(
        metrics={"window_count": window.window_count},
        roots={
            "stop_resolution_root": assessment.stop_resolution_fingerprint,
            "outcome_ref": decision_outcome_fingerprint(terminal),
        },
        outcome={
            "kind": terminal.kind.value,
            "candidate_id": terminal.candidate_id,
            "fallback_bypassed_stop": terminal.kind is DecisionOutcomeKind.SAFE_FALLBACK,
            "authoritative_commit": terminal.authoritative_commit,
        },
        trace_sequence=_risk_trace_sequence(scenario),
        failure_code="commit_hard_stop",
    )


def _probe_case_22(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    publish_stop, publish_permission = issue_reference_action_gates(
        scenario.namespace,
        context=scenario.context,
        action=CommitAction.PUBLISH,
        blocked=False,
        current_step=5,
        expires_at_step=20,
        suffix="publish-only",
    )
    commit_rejected_publish_stop = False
    try:
        mismatched = assess_reference_scenario(
            scenario,
            step=5,
            suffix="publish-stop-as-commit",
            stop_resolution=publish_stop,
            permission=publish_permission,
        )
        commit_rejected_publish_stop = (
            mismatched.status is not CommitAssessmentStatus.READY
        )
    except (GovernanceError, ValueError):
        commit_rejected_publish_stop = True
    execute_stop, _ = issue_reference_action_gates(
        scenario.namespace,
        context=scenario.context,
        action=CommitAction.EXECUTE,
        blocked=False,
        current_step=5,
        expires_at_step=20,
        suffix="execute-only",
    )
    return _result(
        metrics={"distinct_action_count": len({scenario.stop_resolution.action.value, publish_stop.action.value, execute_stop.action.value})},
        roots={
            "commit_stop_ref": stop_resolution_verification_fingerprint(scenario.stop_resolution),
            "publish_stop_ref": stop_resolution_verification_fingerprint(publish_stop),
            "execute_stop_ref": stop_resolution_verification_fingerprint(execute_stop),
        },
        outcome={
            "commit_rejected_publish_gate": commit_rejected_publish_stop,
            "actions": [scenario.stop_resolution.action.value, publish_stop.action.value, execute_stop.action.value],
        },
        trace_sequence=_risk_trace_sequence(scenario),
        failure_code="action_scope_mismatch" if commit_rejected_publish_stop else None,
    )


def _probe_case_23(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    other_stop, other_permission = issue_reference_action_gates(
        scenario.namespace,
        context=scenario.context,
        action=CommitAction.COMMIT,
        blocked=True,
        current_step=5,
        expires_at_step=20,
        suffix="other-target",
        target="decision:other",
    )
    rejected_other_target = False
    try:
        mismatched = assess_reference_scenario(
            scenario,
            step=5,
            suffix="other-target",
            stop_resolution=other_stop,
            permission=other_permission,
        )
        rejected_other_target = (
            mismatched.status is not CommitAssessmentStatus.READY
        )
    except (GovernanceError, ValueError):
        rejected_other_target = True
    unaffected = assess_reference_scenario(
        scenario,
        step=5,
        suffix="target-a",
    )
    return _result(
        metrics={"target_count": 2},
        roots={"target_a_assessment_ref": commit_assessment_fingerprint(unaffected)},
        outcome={
            "target_a": scenario.target,
            "target_b": other_stop.target,
            "target_b_stop_rejected_for_a": rejected_other_target,
            "target_a_ready": unaffected.status is CommitAssessmentStatus.READY,
        },
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_24(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    window, outcome = _deadline_outcome(scenario, suffix="case-24")
    assessment = assess_reference_scenario(
        scenario,
        step=5,
        suffix="case-24:assessment",
    )
    output_ref = commit_payload_fingerprint(
        {"terminal": outcome.kind.value, "candidate_id": outcome.candidate_id},
        schema="pheroos-tck-terminal-output-v1",
        profile=scenario.profile,
    )
    certificate = issue_outcome_certificate(
        outcome,
        window,
        commit_policy=scenario.policy,
        output_payload_fingerprint=output_ref,
        certificate_id=f"outcome-certificate:{scenario.namespace}:fallback",
        context=scenario.context,
        assessment=assessment,
        issuer_id="governance:tck:outcome-certificate",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=outcome.current_step,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:outcome-certificate",
        trace_event_id=f"trace:{scenario.namespace}:outcome-certificate",
    )
    payload = outcome_certificate_payload(certificate)
    accepted_as_commit = verify_evidence_commit_certificate(
        payload,
        trusted_issuer_attestations={},
    )
    return _result(
        metrics={"outcome_certificate_leaf_count": len(tuple(_scalar_leaf_paths(payload)))},
        roots={
            "outcome_certificate_root": certificate.certificate_root,
            "output_payload_fingerprint": output_ref,
        },
        outcome={
            "terminal_kind": outcome.kind.value,
            "accepted_as_commit_certificate": accepted_as_commit,
        },
        trace_sequence=_risk_trace_sequence(scenario),
        certificate={"kind": "outcome", "schema_discriminator": certificate.schema_discriminator},
        failure_code="certificate_kind_mismatch",
    )


def _scalar_leaf_paths(value: object, prefix: tuple[object, ...] = ()) -> Any:
    if isinstance(value, dict):
        for key in sorted(value):
            yield from _scalar_leaf_paths(value[key], (*prefix, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _scalar_leaf_paths(item, (*prefix, index))
    elif value is None or type(value) in {bool, int, str}:
        yield prefix


def _mutate_scalar(value: Any) -> Any:
    if value is None:
        return "tck-mutated"
    if type(value) is bool:
        return not value
    if type(value) is int:
        return value + 1
    if isinstance(value, str):
        if value.startswith("sha256:") and len(value) == 71:
            replacement = "0" if value[-1] != "0" else "1"
            return value[:-1] + replacement
        return value + ":tck-mutated"
    raise ValueError("TCK mutation selected a non-scalar leaf")


def _mutate_path(payload: dict[str, Any], path: Sequence[object]) -> None:
    parent: Any = payload
    for component in path[:-1]:
        parent = parent[component]
    key = path[-1]
    parent[key] = _mutate_scalar(parent[key])


def _probe_case_25(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    stable = build_reference_stable_commit(scenario, variant="case-25")
    portable = build_reference_portable_commit(stable, variant="case-25")
    payload = deepcopy(evidence_commit_certificate_payload(portable.certificate))
    certificate_mutation = vector.inputs.get("certificate_mutation_path")
    if not isinstance(certificate_mutation, list):
        raise ValueError("case 25 certificate_mutation_path must be an array")
    if certificate_mutation:
        _mutate_path(payload, certificate_mutation)
    certificate_valid = verify_evidence_commit_certificate(
        payload,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
    )

    event = _risk_trace_event(scenario)
    trace_mutation = vector.inputs.get("trace_mutation_path")
    if not isinstance(trace_mutation, list):
        raise ValueError("case 25 trace_mutation_path must be an array")
    trace_valid = True
    if trace_mutation:
        lineage = deepcopy(event.lineage)
        _mutate_path(lineage, trace_mutation)
        forged = replace(event, lineage=lineage)
        try:
            forged.validate()
        except (ValueError, TypeError):
            trace_valid = False
    else:
        event.validate()
    certificate_ref = evidence_commit_certificate_fingerprint(portable.certificate)
    return _result(
        metrics={
            "certificate_scalar_leaf_count": len(tuple(_scalar_leaf_paths(evidence_commit_certificate_payload(portable.certificate)))),
            "trace_scalar_leaf_count": len(tuple(_scalar_leaf_paths(event.lineage))),
        },
        roots={
            "certificate_ref": certificate_ref,
            "certificate_body_root": portable.certificate.certificate_body_root,
            "certificate_root": portable.certificate.certificate_root,
            "trace_event_id": event.lineage["event_id"],
        },
        outcome={
            "certificate_valid": certificate_valid,
            "trace_valid": trace_valid,
            "certificate_mutated": bool(certificate_mutation),
            "trace_mutated": bool(trace_mutation),
        },
        trace_sequence=([event.event_type] if trace_valid else []),
        certificate={
            "kind": "evidence_commit",
            "verified": certificate_valid,
            "ref": certificate_ref,
        },
        failure_code=(
            "certificate_leaf_mutation"
            if certificate_mutation and not certificate_valid
            else "trace_leaf_mutation"
            if trace_mutation and not trace_valid
            else None
        ),
    )


def _probe_case_26(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    stable = build_reference_stable_commit(scenario, variant="case-26")
    portable = build_reference_portable_commit(stable, variant="case-26")
    nonce = f"nonce:cross-scope:{scenario.namespace}"
    first = ReplayReceipt(
        namespace=ReplayNamespace.OBSERVATION,
        record_id=f"observation:{scenario.namespace}:scope-a",
        nonce=nonce,
        payload_fingerprint=reference_fingerprint(f"scope-a:{scenario.namespace}"),
        target=scenario.target,
        candidate_id=scenario.leader_id,
        epoch=scenario.epoch,
        principal_id=scenario.principals[0].principal_id,
    )
    second = ReplayReceipt(
        namespace=ReplayNamespace.OBSERVATION,
        record_id=f"observation:{scenario.namespace}:scope-b",
        nonce=nonce,
        payload_fingerprint=reference_fingerprint(f"scope-b:{scenario.namespace}"),
        target="decision:other",
        candidate_id=scenario.other_id,
        epoch=scenario.epoch + 1,
        principal_id=scenario.principals[0].principal_id,
    )
    replay = record_commit_replay_receipts(
        scenario.replay_state,
        current_step=6,
        receipts=(first,),
    )
    replay_rejected = False
    try:
        record_commit_replay_receipts(replay, current_step=7, receipts=(second,))
    except (GovernanceError, ValueError):
        replay_rejected = True
    certificate_claim_rejected = not verify_evidence_commit_certificate(
        portable.certificate,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        expected_claim_fingerprint=reference_fingerprint("wrong-claim"),
    )
    certificate_output_rejected = not verify_evidence_commit_certificate(
        portable.certificate,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        expected_output_payload_fingerprint=reference_fingerprint("wrong-output"),
    )
    return _result(
        metrics={"replay_scope_count": 3},
        roots={
            "receipt_ref": local_commit_receipt_fingerprint(stable.receipt),
            "certificate_ref": evidence_commit_certificate_fingerprint(portable.certificate),
        },
        outcome={
            "nonce_cross_scope_rejected": replay_rejected,
            "certificate_cross_candidate_rejected": certificate_claim_rejected,
            "certificate_cross_output_rejected": certificate_output_rejected,
        },
        trace_sequence=_risk_trace_sequence(scenario),
        certificate={"kind": "evidence_commit", "verified": True},
        failure_code="cross_scope_replay_rejected",
    )


def _output_gates(
    scenario: ReferenceScenario,
    outcome: DecisionOutcome,
    *,
    certificate_ref: str,
    suffix: str,
    issued_at_step: int,
    stop_expires_at_step: int,
    permission_expires_at_step: int,
    permission_allowed: bool = True,
) -> tuple[Any, Any]:
    outcome_ref = decision_outcome_fingerprint(outcome)
    stop = verify_stop_resolution(
        StopResolution(
            target=scenario.target,
            action=CommitAction.PUBLISH,
            blocked=False,
            reason="all_hard_stops_resolved",
        ),
        resolution_id=f"stop:{scenario.namespace}:output:{suffix}",
        profile=scenario.profile,
        assurance=scenario.assurance,
        manifest_root=scenario.manifest_root,
        commit_policy_root=scenario.commit_policy_root,
        protocol_id=scenario.protocol_id,
        run_id=scenario.run_id,
        epoch=scenario.epoch,
        decision_ref=outcome_ref,
        certificate_ref=certificate_ref,
        resolved_stop_root=reference_fingerprint(
            f"stop:{scenario.namespace}:output:{suffix}"
        ),
        verifier_id="governance:tck:output-stop",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=issued_at_step,
        expires_at_step=stop_expires_at_step,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:output-stop:{suffix}",
        trace_event_id=f"trace:{scenario.namespace}:output-stop:{suffix}",
    )
    permission = issue_action_permission(
        permission_id=f"permission:{scenario.namespace}:output:{suffix}",
        profile=scenario.profile,
        assurance=scenario.assurance,
        manifest_root=scenario.manifest_root,
        commit_policy_root=scenario.commit_policy_root,
        protocol_id=scenario.protocol_id,
        run_id=scenario.run_id,
        target=scenario.target,
        action=CommitAction.PUBLISH,
        epoch=scenario.epoch,
        decision_ref=outcome_ref,
        certificate_ref=certificate_ref,
        allowed=permission_allowed,
        reason_codes=("policy_authorized",) if permission_allowed else ("denied",),
        issuer_id="governance:tck:output-permission",
        policy_ref="policy:tck:output-v1",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=issued_at_step,
        expires_at_step=permission_expires_at_step,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:output-permission:{suffix}",
        trace_event_id=f"trace:{scenario.namespace}:output-permission:{suffix}",
    )
    return stop, permission


def _probe_case_27(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    policy = scenario.policy.distributed
    if policy is None:
        raise ValueError("case 27 requires distributed policy")
    diagnostics = validate_capability_manifest(scenario.manifest)
    codes = sorted(item.code for item in diagnostics if item.level == "error")
    state = build_reference_distributed_commit(
        build_reference_portable_commit(
            build_reference_stable_commit(scenario, variant="case-27"),
            variant="case-27",
        ),
        witness_count=0,
        variant="case-27",
    ).state
    intersection_excess = 2 * policy.witness_quorum - policy.membership_size
    return _result(
        metrics={
            "membership_size": policy.membership_size,
            "max_byzantine_faults": policy.max_byzantine_faults,
            "witness_quorum": policy.witness_quorum,
            "intersection_excess": intersection_excess,
        },
        roots={
            "membership_root": state.membership_root,
            "distributed_state_ref": distributed_commit_state_fingerprint(state),
        },
        outcome={
            "n_equals_3f_plus_1": policy.membership_size == 3 * policy.max_byzantine_faults + 1,
            "q_equals_2f_plus_1": policy.witness_quorum == 2 * policy.max_byzantine_faults + 1,
            "safe_intersection": intersection_excess > policy.max_byzantine_faults,
            "diagnostic_codes": codes,
        },
        trace_sequence=_risk_trace_sequence(scenario),
        failure_code=(codes[0] if codes else None),
    )


def _probe_case_28(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    stable = build_reference_stable_commit(scenario, variant="case-28")
    portable = build_reference_portable_commit(stable, variant="case-28")
    policy = scenario.policy.distributed
    assert policy is not None
    insufficient = policy.witness_quorum - 1
    bundle = build_reference_distributed_commit(
        portable,
        witness_count=insufficient,
        variant="case-28",
    )
    certificate = issue_reference_distributed_certificate(
        bundle,
        witness_count=insufficient,
        variant="case-28:partition-a",
    )
    decision = evaluate_distributed_finality(
        bundle.state,
        stable.receipt,
        certificate=certificate,
        current_step=stable.window.last_evaluated_step,
    )
    verifies_final = verify_distributed_commit_certificate(
        certificate,
        commit_policy=scenario.policy,
        portable_certificate=portable.certificate,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        trusted_witness_attestations=bundle.trusted_witness_attestations,
        require_final=True,
    )
    return _result(
        metrics={
            "partition_a_witnesses": insufficient,
            "partition_b_witnesses": insufficient,
            "required_quorum": policy.witness_quorum,
        },
        roots={
            "proposal_digest": bundle.proposal.proposal_digest,
            "certificate_ref": distributed_commit_certificate_fingerprint(certificate),
        },
        outcome={
            "certificate_status": certificate.status.value,
            "finality_kind": decision.kind.value,
            "partition_a_final": verifies_final,
            "partition_b_final": False,
            "authoritative_commit": decision.authoritative_commit,
        },
        trace_sequence=_risk_trace_sequence(scenario),
        certificate={"kind": "distributed_commit", "status": certificate.status.value},
        failure_code="insufficient_witness_quorum",
    )


def _probe_case_29(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    stable = build_reference_stable_commit(scenario, variant="case-29")
    portable = build_reference_portable_commit(stable, variant="case-29")
    policy = scenario.policy.distributed
    assert policy is not None
    bundle = build_reference_distributed_commit(
        portable,
        witness_count=policy.witness_quorum,
        variant="case-29",
    )
    final = issue_reference_distributed_certificate(
        bundle,
        witness_count=policy.witness_quorum,
        variant="case-29:quorum",
    )
    minority = issue_reference_distributed_certificate(
        bundle,
        witness_count=1,
        variant="case-29:minority",
    )
    registered = register_distributed_commit_certificate(
        bundle.state,
        final,
        commit_policy=scenario.policy,
        portable_certificate=portable.certificate,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        trusted_witness_attestations=bundle.trusted_witness_attestations,
        current_step=stable.window.last_evaluated_step,
    )
    minority_final = verify_distributed_commit_certificate(
        minority,
        commit_policy=scenario.policy,
        portable_certificate=portable.certificate,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        trusted_witness_attestations=bundle.trusted_witness_attestations,
        require_final=True,
    )
    return _result(
        metrics={
            "quorum_partition_witnesses": policy.witness_quorum,
            "minority_partition_witnesses": 1,
        },
        roots={
            "final_certificate_ref": distributed_commit_certificate_fingerprint(final),
            "minority_certificate_ref": distributed_commit_certificate_fingerprint(minority),
            "registered_state_ref": distributed_commit_state_fingerprint(registered),
        },
        outcome={
            "quorum_status": final.status.value,
            "quorum_current_final": distributed_commit_certificate_is_current_final(final, registered),
            "minority_status": minority.status.value,
            "minority_final": minority_final,
        },
        trace_sequence=_risk_trace_sequence(scenario),
        certificate={"kind": "distributed_commit", "status": final.status.value},
    )


def _distributed_conflict(
    vector: _CommitTckRequest,
) -> tuple[
    ReferenceDistributedCommit,
    Any,
    Any,
    Any,
    Any,
    Any,
    Mapping[str, str],
    Mapping[str, str],
    bool,
]:
    scenario = _reference_scenario(vector)
    stable = build_reference_stable_commit(scenario, variant="case-30")
    portable = build_reference_portable_commit(stable, variant="case-30")
    policy = scenario.policy.distributed
    assert policy is not None
    bundle = build_reference_distributed_commit(
        portable,
        witness_count=policy.witness_quorum,
        variant="case-30:first",
    )
    first = issue_reference_distributed_certificate(
        bundle,
        witness_count=policy.witness_quorum,
        variant="case-30:first",
    )
    first_state = register_distributed_commit_certificate(
        bundle.state,
        first,
        commit_policy=scenario.policy,
        portable_certificate=portable.certificate,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        trusted_witness_attestations=bundle.trusted_witness_attestations,
        current_step=stable.window.last_evaluated_step,
    )
    second_proposal = issue_distributed_commit_proposal(
        stable.receipt,
        portable.certificate,
        scenario.membership_snapshot,
        scenario.membership_state,
        commit_policy=scenario.policy,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        proposal_id=f"proposal:{scenario.namespace}:case-30:second",
        proposed_at_step=stable.window.last_evaluated_step,
    )
    second_trust = dict(bundle.trusted_witness_attestations)
    second_verifications = tuple(
        issue_reference_witness(
            scenario,
            second_proposal,
            principal,
            index=100 + index,
            variant="case-30:second",
            trusted_witness_attestations=second_trust,
        )
        for index, principal in enumerate(
            scenario.principals[: policy.witness_quorum], start=1
        )
    )
    second = assemble_portable_distributed_commit_certificate(
        second_proposal,
        portable_membership_snapshot_from_eligible(scenario.membership_snapshot),
        tuple(reversed(second_verifications)),
        commit_policy=scenario.policy,
        portable_certificate=portable.certificate,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        trusted_witness_attestations=second_trust,
        certificate_id=f"distributed-certificate:{scenario.namespace}:case-30:second",
        issuer_id="governance:tck:peer-certificate",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=stable.window.last_evaluated_step,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:peer-certificate",
        trace_event_id=f"trace:{scenario.namespace}:peer-certificate",
    )
    same_value_state = register_distributed_commit_certificate(
        first_state,
        second,
        commit_policy=scenario.policy,
        portable_certificate=portable.certificate,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        trusted_witness_attestations=second_trust,
        current_step=stable.window.last_evaluated_step,
    )
    second_ref = distributed_commit_certificate_fingerprint(second)
    same_value_accepted = bool(
        not same_value_state.frozen
        and first.commit_value_root == second.commit_value_root
        and verify_distributed_commit_certificate(
            second,
            commit_policy=scenario.policy,
            portable_certificate=portable.certificate,
            trusted_issuer_attestations=portable.trusted_issuer_attestations,
            trusted_witness_attestations=second_trust,
            require_final=True,
        )
        and any(
            item.certificate_ref == second_ref
            and item.commit_value_root == second.commit_value_root
            and item.proposal_digest == second.proposal_digest
            for item in same_value_state.final_registrations
        )
    )
    (
        conflict_proposal,
        conflict_portable,
        conflict_issuer_trust,
        conflict_witness_trust,
        conflict_certificate,
    ) = issue_reference_semantic_conflict_certificate(
        bundle,
        field_name="output_payload_fingerprint",
        field_value=reference_fingerprint(
            f"conflicting-output:{scenario.namespace}:case-30"
        ),
        variant="case-30:semantic-conflict",
    )
    if conflict_proposal.commit_value_root == first.commit_value_root:
        raise ValueError("case 30 semantic conflict did not change the value root")
    frozen = register_distributed_commit_certificate(
        same_value_state,
        conflict_certificate,
        commit_policy=scenario.policy,
        portable_certificate=conflict_portable,
        trusted_issuer_attestations=conflict_issuer_trust,
        trusted_witness_attestations=conflict_witness_trust,
        current_step=stable.window.last_evaluated_step,
    )
    return (
        bundle,
        first,
        second,
        conflict_certificate,
        frozen,
        conflict_portable,
        conflict_issuer_trust,
        conflict_witness_trust,
        same_value_accepted,
    )


def _probe_case_30(vector: _CommitTckRequest) -> dict[str, Any]:
    (
        bundle,
        first,
        same_value_retry,
        conflict,
        frozen,
        conflict_portable,
        conflict_issuer_trust,
        conflict_witness_trust,
        same_value_accepted,
    ) = _distributed_conflict(vector)
    portable = bundle.portable
    stable = portable.stable
    scenario = stable.scenario
    safety = evaluate_distributed_finality(
        frozen,
        stable.receipt,
        certificate=None,
        current_step=stable.window.last_evaluated_step,
    )
    terminal = reduce_commit_liveness(
        stable.window,
        commit_policy=scenario.policy,
        liveness_input=_liveness_input(
            scenario,
            stable.window,
            assessment=stable.assessments[-1],
            step=stable.window.last_evaluated_step,
            suffix="case-30:conflict",
            finality_status=CommitFinalityStatus.CONFLICT,
            safety_violation_reason_codes=("certificate_conflict",),
        ),
    )
    if type(terminal) is not DecisionOutcome:
        raise ValueError("distributed conflict did not produce safety outcome")
    first_ref = distributed_commit_certificate_fingerprint(first)
    stop, permission = _output_gates(
        scenario,
        terminal,
        certificate_ref=first_ref,
        suffix="case-30",
        issued_at_step=terminal.current_step,
        stop_expires_at_step=terminal.current_step + 2,
        permission_expires_at_step=terminal.current_step + 2,
    )
    publication = authorize_terminal_publication(
        terminal,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        certificate=first,
        output_payload_fingerprint=stable.output_fingerprint,
        stop_resolution=stop,
        permission=permission,
        current_step=terminal.current_step,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        distributed_state=frozen,
        portable_certificate=portable.certificate,
        trusted_witness_attestations=bundle.trusted_witness_attestations,
    )
    conflict_verified = verify_distributed_commit_certificate(
        conflict,
        commit_policy=scenario.policy,
        portable_certificate=conflict_portable,
        trusted_issuer_attestations=conflict_issuer_trust,
        trusted_witness_attestations=conflict_witness_trust,
        require_final=True,
    )
    semantic_conflict = bool(
        first.commit_value_root != conflict.commit_value_root
    )
    return _result(
        metrics={
            "conflict_finding_count": len(frozen.conflict_findings),
            "final_certificate_count": 3,
            "semantic_value_count": len(
                {
                    first.commit_value_root,
                    same_value_retry.commit_value_root,
                    conflict.commit_value_root,
                }
            ),
        },
        roots={
            "left_certificate_ref": first_ref,
            "same_value_retry_ref": distributed_commit_certificate_fingerprint(
                same_value_retry
            ),
            "right_certificate_ref": distributed_commit_certificate_fingerprint(
                conflict
            ),
            "left_commit_value_root": first.commit_value_root,
            "right_commit_value_root": conflict.commit_value_root,
            "frozen_state_ref": distributed_commit_state_fingerprint(frozen),
        },
        outcome={
            "same_value_retry_accepted": same_value_accepted,
            "semantic_conflict": semantic_conflict,
            "conflicting_certificate_verified": conflict_verified,
            "frozen": frozen.frozen,
            "finality_kind": safety.kind.value,
            "authoritative_commit": safety.authoritative_commit,
            "publication_authorized": publication.authorized,
            "publication_reason_codes": list(publication.reason_codes),
        },
        trace_sequence=_risk_trace_sequence(scenario),
        certificate={
            "kind": "distributed_conflict",
            "left_current": distributed_commit_certificate_is_current_final(
                first,
                frozen,
            ),
            "same_value_root_preserved": (
                first.commit_value_root
                == same_value_retry.commit_value_root
            ),
        },
        failure_code=(
            "certificate_conflict"
            if frozen.frozen and semantic_conflict
            else "semantic_conflict_not_frozen"
        ),
    )


def _probe_case_31(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    stable = build_reference_stable_commit(scenario, variant="case-31")
    portable = build_reference_portable_commit(stable, variant="case-31")
    bundle = build_reference_distributed_commit(
        portable,
        witness_count=0,
        variant="case-31",
    )
    progress, outcome = _heartbeat_to_deadline(
        stable,
        suffix="case-31",
        final_status=CommitFinalityStatus.UNAVAILABLE,
        final_reason_codes=("witness_quorum_unavailable",),
    )
    decision = evaluate_distributed_finality(
        bundle.state,
        stable.receipt,
        certificate=None,
        current_step=outcome.current_step,
        outcome=outcome,
    )
    return _result(
        metrics={
            "pending_step": progress.current_step,
            "deadline_step": outcome.current_step,
            "witness_count": len(bundle.state.witness_verifications),
        },
        roots={
            "outcome_ref": decision_outcome_fingerprint(outcome),
            "distributed_state_ref": distributed_commit_state_fingerprint(bundle.state),
        },
        progress={"phase": progress.phase.value, "terminal": progress.terminal},
        outcome={
            "kind": outcome.kind.value,
            "distributed_finality_kind": decision.kind.value,
            "terminal": decision.terminal,
            "authoritative_commit": decision.authoritative_commit,
            "epistemically_committed": outcome.epistemically_committed,
        },
        trace_sequence=_risk_trace_sequence(scenario),
        failure_code="finality_unavailable",
    )


def _probe_case_32(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    stable = build_reference_stable_commit(scenario, variant="case-32")
    outcome = _local_commit_outcome(stable, suffix="case-32")
    receipt_ref = local_commit_receipt_fingerprint(stable.receipt)
    stop, permission = _output_gates(
        scenario,
        outcome,
        certificate_ref=receipt_ref,
        suffix="case-32",
        issued_at_step=outcome.current_step,
        stop_expires_at_step=outcome.current_step + 3,
        permission_expires_at_step=outcome.current_step + 1,
    )
    current_step = outcome.current_step + 1
    publication = authorize_terminal_publication(
        outcome,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        certificate=stable.receipt,
        output_payload_fingerprint=stable.output_fingerprint,
        stop_resolution=stop,
        permission=permission,
        current_step=current_step,
    )
    return _result(
        metrics={
            "commit_step": outcome.current_step,
            "publication_step": current_step,
            "permission_expires_at_step": permission.expires_at_step,
        },
        roots={
            "outcome_ref": decision_outcome_fingerprint(outcome),
            "receipt_ref": receipt_ref,
        },
        outcome={
            "historical_outcome_authoritative": decision_outcome_is_authoritative(outcome),
            "historical_receipt_authoritative": local_commit_receipt_is_authoritative(stable.receipt),
            "publication_authorized": publication.authorized,
            "publication_reason_codes": list(publication.reason_codes),
        },
        trace_sequence=_risk_trace_sequence(scenario),
        certificate={"kind": "local_receipt", "historically_valid": True},
        failure_code="publication_permission_expired",
    )


def _terminal_variant_vector(
    vector: _CommitTckRequest,
    key: str,
) -> _CommitTckRequest:
    variants = _object(
        vector.inputs.get("terminal_variants"),
        "case 33 terminal_variants",
    )
    spec = _object(variants.get(key), f"case 33 terminal variant {key}")
    manifest = _object(spec.get("manifest"), f"case 33 {key} manifest")
    profile = _text(spec.get("profile"), f"case 33 {key} profile")
    return replace(
        vector,
        id=f"{vector.id}:{key}",
        manifest=deepcopy(manifest),
        profile=profile,
    )


def _coded_terminal_outcome(
    scenario: ReferenceScenario,
    *,
    suffix: str,
    invalid: Sequence[str] = (),
    safety: Sequence[str] = (),
    blocked: Sequence[str] = (),
) -> DecisionOutcome:
    window = _initialize_window(scenario)
    assessment = assess_reference_scenario(
        scenario,
        step=5,
        suffix=f"{suffix}:assessment",
    )
    window = advance_commit_window_state(
        window,
        assessment=assessment,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        current_step=5,
    )
    decision = reduce_commit_liveness(
        window,
        commit_policy=scenario.policy,
        liveness_input=_liveness_input(
            scenario,
            window,
            assessment=assessment,
            step=5,
            suffix=suffix,
            finality_status=CommitFinalityStatus.PENDING,
            invalid_reason_codes=invalid,
            safety_violation_reason_codes=safety,
            blocked_reason_codes=blocked,
        ),
    )
    if type(decision) is not DecisionOutcome:
        raise ValueError(f"{suffix} did not reduce to a terminal outcome")
    return decision


def _probe_case_33(vector: _CommitTckRequest) -> dict[str, Any]:
    outcomes: dict[str, DecisionOutcome] = {}

    evidence_vector = _terminal_variant_vector(vector, "evidence_commit")
    evidence = _reference_scenario(evidence_vector)
    evidence_stable = build_reference_stable_commit(
        evidence,
        variant="case-33:evidence",
    )
    outcomes["evidence_commit"] = _local_commit_outcome(
        evidence_stable,
        suffix="case-33:evidence",
    )

    for kind in ("safe_fallback", "advisory"):
        selected = _terminal_variant_vector(vector, kind)
        scenario = _reference_scenario(selected)
        _, outcomes[kind] = _deadline_outcome(
            scenario,
            suffix=f"case-33:{kind}",
        )

    for kind, codes in (
        ("blocked", {"blocked": ("hard_commit_stop",)}),
        ("invalid", {"invalid": ("invalid_protocol_instance",)}),
        ("safety_violation", {"safety": ("authority_conflict",)}),
    ):
        selected = _terminal_variant_vector(vector, kind)
        scenario = _reference_scenario(selected)
        outcomes[kind] = _coded_terminal_outcome(
            scenario,
            suffix=f"case-33:{kind}",
            **codes,
        )

    unavailable_vector = _terminal_variant_vector(
        vector,
        "finality_unavailable",
    )
    unavailable = _reference_scenario(unavailable_vector)
    unavailable_stable = build_reference_stable_commit(
        unavailable,
        variant="case-33:finality-unavailable",
    )
    _, outcomes["finality_unavailable"] = _heartbeat_to_deadline(
        unavailable_stable,
        suffix="case-33:finality-unavailable",
        final_status=CommitFinalityStatus.UNAVAILABLE,
        final_reason_codes=("portable_certificate_unavailable",),
    )

    expected_kinds = tuple(item.value for item in DecisionOutcomeKind)
    if set(outcomes) != set(expected_kinds):
        raise ValueError("case 33 did not construct every terminal outcome kind")
    deliveries = {
        kind: deliver_terminal_outcome(
            outcome,
            output_payload_fingerprint=reference_fingerprint(
                f"delivery:{vector.id}:{kind}"
            ),
        )
        for kind, outcome in outcomes.items()
    }
    denied = tuple(
        sorted(kind for kind, result in deliveries.items() if not result.authorized)
    )
    return _result(
        metrics={
            "terminal_outcome_count": len(outcomes),
            "authorized_delivery_count": sum(
                int(item.authorized) for item in deliveries.values()
            ),
        },
        roots={
            "outcome_refs": {
                kind: decision_outcome_fingerprint(outcome)
                for kind, outcome in sorted(outcomes.items())
            },
            "delivery_roots": {
                kind: commit_output_authorization_fingerprint(delivery)
                for kind, delivery in sorted(deliveries.items())
            },
        },
        outcome={
            "all_terminal": all(item.terminal for item in outcomes.values()),
            "all_authoritative": all(
                decision_outcome_is_authoritative(item)
                for item in outcomes.values()
            ),
            "all_delivered": not denied,
            "denied_kinds": list(denied),
            "kinds": list(sorted(outcomes)),
        },
        trace_sequence=["decision_outcome", "output_decided"],
        failure_code=("terminal_delivery_denied" if denied else None),
    )


def _authority_trace_events(
    scenario: ReferenceScenario,
) -> tuple[TraceEvent, ...]:
    """Materialize complete pre-decision authority lineage through Trace ABI."""

    events: list[TraceEvent] = []

    def append(
        event_type: str,
        *,
        step: int,
        schema: str,
        payload: Mapping[str, Any],
        details: Mapping[str, Any],
    ) -> TraceEvent:
        event = make_commit_trace_event(
            event_type=event_type,
            protocol_id=scenario.protocol_id,
            target=scenario.target,
            reason=f"tck_{event_type}",
            profile=scenario.profile,
            assurance=scenario.assurance.value,
            manifest_root=scenario.manifest_root,
            commit_policy_root=scenario.commit_policy_root,
            run_id=scenario.run_id,
            epoch=scenario.epoch,
            step=step,
            record_schema=schema,
            record_payload=payload,
            previous_event_ids=tuple(
                event.lineage["event_id"] for event in events
            ),
            details=details,
        )
        events.append(event)
        return event

    for principal in scenario.principals:
        append(
            "principal_attested",
            step=0,
            schema="pheroos-tck-principal-attestation-trace-v1",
            payload={
                "principal_id": principal.principal_id,
                "nonce": f"nonce:trace:{principal.principal_id}",
            },
            details={
                "principal_id": principal.principal_id,
                "attestation_fingerprint": "",
                "nonce": f"nonce:trace:{principal.principal_id}",
            },
        )
    for principal in scenario.principals:
        append(
            "principal_verified",
            step=0,
            schema="pheroos-principal-verification-v1",
            payload=principal_verification_payload(principal),
            details={
                "principal_id": principal.principal_id,
                "cluster_id": principal.cluster_id,
                "attestation_ref": principal.attestation_fingerprint,
                "verification_ref": "",
            },
        )
    append(
        "risk_assessed",
        step=1,
        schema="pheroos-risk-assessment-v1",
        payload=risk_assessment_payload(scenario.risk_assessment),
        details={
            "risk_band": scenario.risk_assessment.risk_band.value,
            "risk_ref": "",
            "threshold_ref": commit_threshold_snapshot_fingerprint(
                scenario.threshold
            ),
            "risk_chain_revision": (
                scenario.risk_assessment.risk_chain_revision
            ),
        },
    )
    append(
        "membership_snapshot",
        step=1,
        schema="pheroos-eligible-principal-snapshot-v1",
        payload=eligible_principal_snapshot_payload(
            scenario.membership_snapshot
        ),
        details={
            "snapshot_id": scenario.membership_snapshot.snapshot_id,
            "membership_root": scenario.membership_snapshot.membership_root,
            "snapshot_ref": "",
            "cluster_count": len(
                scenario.membership_snapshot.eligible_clusters
            ),
            "expires_at_step": scenario.membership_snapshot.expires_at_step,
        },
    )
    observations = {
        verified_observation_fingerprint(item): item
        for records in scenario.observations.values()
        for item in records
    }
    for observation_ref, observation in sorted(observations.items()):
        append(
            "observation_recorded",
            step=2,
            schema="pheroos-tck-observation-attestation-trace-v1",
            payload={
                "candidate_id": observation.candidate_id,
                "observation_id": observation.observation_id,
                "polarity": observation.polarity.value,
                "principal_id": observation.principal_id,
                "nonce": observation.nonce,
            },
            details={
                "observation_id": observation.observation_id,
                "candidate_id": observation.candidate_id,
                "polarity": observation.polarity.value,
                "principal_id": observation.principal_id,
                "nonce": observation.nonce,
                "attestation_fingerprint": "",
            },
        )
        append(
            "observation_verified",
            step=2,
            schema="pheroos-verified-observation-v1",
            payload=verified_observation_payload(observation),
            details={
                "observation_id": observation.observation_id,
                "candidate_id": observation.candidate_id,
                "polarity": observation.polarity.value,
                "principal_cluster_id": observation.principal_cluster_id,
                "observation_ref": "",
                "principal_verification_ref": (
                    observation.principal_verification_fingerprint
                ),
            },
        )
        if observation_ref != events[-1].lineage["record_ref"]:
            raise ValueError("verified observation trace root drift")
    for candidate_id, binding in sorted(scenario.bindings.items()):
        append(
            "evidence_bound",
            step=3,
            schema="pheroos-evidence-binding-authority-v1",
            payload=evidence_binding_payload(binding),
            details={
                "candidate_id": candidate_id,
                "claim_fingerprint": binding.claim_fingerprint,
                "binding_ref": "",
                "positive_root": binding.positive_root,
                "counter_root": binding.counter_root,
                "disposition_root": binding.disposition_root,
                "challenge_root": binding.challenge_root,
                "evidence_root": binding.evidence_root,
            },
        )
        if evidence_binding_fingerprint(binding) != events[-1].lineage["record_ref"]:
            raise ValueError("evidence binding trace root drift")
    for lease in scenario.leases:
        append(
            "support_lease_issued",
            step=4,
            schema="pheroos-support-lease-v1",
            payload=support_lease_payload(lease),
            details={
                "lease_id": lease.lease_id,
                "candidate_id": lease.candidate_id,
                "principal_cluster_id": lease.principal_cluster_id,
                "lease_ref": "",
                "evidence_refs": list(
                    lease.positive_observation_fingerprints
                ),
                "expires_at_step": lease.expires_at_step,
            },
        )
        if support_lease_fingerprint(lease) != events[-1].lineage["record_ref"]:
            raise ValueError("support lease trace root drift")
    append(
        "stop_resolution_verified",
        step=4,
        schema="pheroos-stop-resolution-verification-v1",
        payload=stop_resolution_verification_payload(
            scenario.stop_resolution
        ),
        details={
            "action": scenario.stop_resolution.action.value,
            "resolution_ref": "",
            "blocked": scenario.stop_resolution.blocked,
            "expires_at_step": scenario.stop_resolution.expires_at_step,
        },
    )
    append(
        "action_permission_issued",
        step=4,
        schema="pheroos-action-permission-v1",
        payload=action_permission_payload(scenario.permission),
        details={
            "action": scenario.permission.action.value,
            "permission_ref": "",
            "allowed": scenario.permission.allowed,
            "expires_at_step": scenario.permission.expires_at_step,
        },
    )
    replay_commit_trace(events, require_complete=False)
    return tuple(events)


def _hybrid_attention_for_scenario(
    scenario: ReferenceScenario,
    *,
    current_step: int,
    candidate_id: str,
) -> tuple[Any, Any]:
    policy = scenario.manifest.protocol.collective_decision_policy
    if policy is None:
        raise ValueError("Hybrid Commit TCK requires an attention policy")
    candidates = CandidateSet(tuple(
        Candidate(item.id, item.target, item.safe_fallback)
        for item in scenario.manifest.protocol.candidates
    ))
    scouts = [
        _verified_scout(
            scenario,
            source_id=f"scout:total:{candidate_id}:{index}",
            candidate_id=candidate_id,
        )
        for index in range(1, 3)
    ]
    return evaluate_hybrid_attention_step(
        protocol_id=scenario.protocol_id,
        candidate_set=candidates,
        policy=policy,
        target=scenario.target,
        current_step=current_step,
        scout_reports=scouts,
        topology=_candidate_topology(scenario),
        fallback_candidate_id=scenario.fallback_id,
    )


def _candidate_topology(
    scenario: ReferenceScenario,
) -> PheromoneNeighborhood:
    return PheromoneNeighborhood(
        subjects=[
            PheromoneSubject(
                "candidate",
                item.id,
                item.id,
                scenario.target,
            )
            for item in scenario.manifest.protocol.candidates
            if item.target == scenario.target
        ],
        edges=[],
    )


def _probe_case_34(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    stable = build_reference_stable_commit(scenario, variant="case-34")
    step = stable.window.last_evaluated_step
    attention, directive = _hybrid_attention_for_scenario(
        scenario,
        current_step=step,
        candidate_id=scenario.other_id,
    )
    request = HybridCommitEvaluationRequest(
        request_version=HYBRID_COMMIT_EVALUATION_REQUEST_VERSION,
        request_id=f"hybrid-evaluation:{scenario.namespace}:case-34",
        attention=attention,
        exploration_directive=directive,
        commit_assessment=stable.assessments[-1],
        context=scenario.context,
        window_state=stable.window,
        replay_state=scenario.replay_state,
        commit_policy=scenario.policy,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        support_replay_state=scenario.support_replay_state,
        current_step=step,
        output_payload_fingerprint=stable.output_fingerprint,
        issuer_id="governance:tck:hybrid-total",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:hybrid-total",
        trace_event_id=f"trace:{scenario.namespace}:hybrid-total",
        local_receipt=stable.receipt,
        prior_trace_events=_authority_trace_events(scenario),
    )
    evaluation = evaluate_hybrid_commit_step(request=request)
    mutation_field = vector.inputs.get("evaluation_mutation_field", "")
    if not isinstance(mutation_field, str):
        raise ValueError("case 34 evaluation_mutation_field must be a string")
    checked_evaluation = evaluation
    if mutation_field:
        if mutation_field != "evaluation_root":
            raise ValueError("case 34 evaluation mutation field is unsupported")
        checked_evaluation = replace(
            evaluation,
            evaluation_root=reference_fingerprint(
                f"tampered:{scenario.namespace}:evaluation-root"
            ),
        )
    verified_authoritative = hybrid_commit_evaluation_is_authoritative(
        checked_evaluation
    )
    progress = evaluation.decision_progress
    outcome = evaluation.decision_outcome
    return _result(
        metrics={
            "diagnostic_count": len(evaluation.diagnostics),
            "trace_event_count": len(evaluation.trace_events),
        },
        roots={
            "evaluation_root": evaluation.evaluation_root,
            "progress_ref": evaluation.progress_ref,
            "outcome_ref": evaluation.outcome_ref,
            "local_receipt_ref": evaluation.local_receipt_ref,
            "evidence_certificate_ref": evaluation.evidence_certificate_ref,
            "distributed_certificate_ref": evaluation.distributed_certificate_ref,
            "trace_root": evaluation.trace_root,
        },
        progress=(
            {
                "phase": progress.phase.value,
                "next_required_inputs": list(progress.next_required_inputs),
                "terminal": progress.terminal,
            }
            if progress is not None
            else None
        ),
        outcome=(
            {
                "kind": outcome.kind.value,
                "authoritative_commit": outcome.authoritative_commit,
                "epistemically_committed": outcome.epistemically_committed,
            }
            if outcome is not None
            else None
        ),
        trace_sequence=[item.event_type for item in evaluation.trace_events],
        certificate={
            "declared_assurance": evaluation.assurance.value,
            "assurance_downgraded": evaluation.assurance_downgraded,
            "local_receipt_present": bool(evaluation.local_receipt_ref),
            "required_certificate_present": bool(
                evaluation.evidence_certificate_ref
                or evaluation.distributed_certificate_ref
            ),
            "self_reported_authoritative": checked_evaluation.authoritative,
            "verified_authoritative": verified_authoritative,
            "embedded_mutation_field": mutation_field,
            "terminal": evaluation.terminal,
        },
        failure_code=(
            "embedded_authority_mutation"
            if mutation_field and not verified_authoritative
            else "assurance_input_missing"
            if progress is not None
            and not evaluation.evidence_certificate_ref
            and not evaluation.assurance_downgraded
            else None
        ),
    )


def _probe_case_35(vector: _CommitTckRequest) -> dict[str, Any]:
    from pheroos.conformance._manifest_check_registry import (
        project_active_manifest_checks,
    )

    manifest = capability_manifest_from_dict(_require_vector_manifest(vector))
    profile = profile_for_manifest(manifest)
    projection = project_active_manifest_checks(profile.required_checks)
    required = projection.required
    registered = projection.registered
    missing = projection.missing
    skipped = projection.skipped_or_na
    return _result(
        metrics={
            "required_check_count": len(required),
            "registered_check_count": len(registered),
            "missing_check_count": len(missing),
            "skipped_check_count": len(skipped),
        },
        roots={
            "active_check_set_root": commit_payload_fingerprint(
                {"required_checks": required},
                schema="pheroos-active-conformance-check-set-v1",
                profile=vector.profile,
            )
        },
        outcome={
            "profile": profile.version,
            "active": True,
            "all_registered": not missing,
            "no_skip_or_na": not skipped,
            "missing": list(missing),
            "skipped_or_na": list(skipped),
        },
        failure_code=(
            "active_conformance_check_missing"
            if missing
            else "active_conformance_check_skipped"
            if skipped
            else None
        ),
    )


def _probe_case_36(vector: _CommitTckRequest) -> dict[str, Any]:
    manifest_payload = _require_vector_manifest(vector)
    try:
        manifest = capability_manifest_from_dict(manifest_payload)
    except Exception as exc:
        return _result(
            outcome={
                "loaded": False,
                "valid": False,
                "profile_selected": False,
                "diagnostic_codes": [],
                "load_error": type(exc).__name__,
            },
            failure_code=f"fail_closed:{type(exc).__name__}",
        )
    diagnostics = validate_capability_manifest(manifest)
    codes = tuple(
        sorted(item.code for item in diagnostics if item.level == "error")
    )
    profile_selected = True
    profile_error = ""
    try:
        profile_for_manifest(manifest)
    except Exception as exc:
        profile_selected = False
        profile_error = type(exc).__name__
    valid = not codes and profile_selected
    return _result(
        roots={
            "declared_manifest_root": commit_manifest_fingerprint(
                manifest,
                profile=vector.profile,
            ),
        },
        outcome={
            "loaded": True,
            "valid": valid,
            "profile_selected": profile_selected,
            "diagnostic_codes": list(codes),
            "profile_error": profile_error,
        },
        failure_code=(
            None
            if valid
            else codes[0]
            if codes
            else f"fail_closed:{profile_error}"
        ),
    )


def _probe_case_37(vector: _CommitTckRequest) -> dict[str, Any]:
    manifest = capability_manifest_from_dict(_require_vector_manifest(vector))
    profile = profile_for_manifest(manifest)
    target = manifest.protocol.quorum_policy.target
    candidate_id = _text(
        vector.inputs.get("candidate_id"),
        "case 37 candidate_id",
    )
    source_id = _text(vector.inputs.get("source_id"), "case 37 source_id")
    candidates = CandidateSet(tuple(
        Candidate(item.id, item.target, item.safe_fallback)
        for item in manifest.protocol.candidates
    ))
    signal = QuorumSignal(
        source_id=source_id,
        candidate_id=candidate_id,
        target=target,
        verification=verify_signal_input(
            target=target,
            source_id=source_id,
            subject_id=candidate_id,
            verifier_id="governance:tck:legacy",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:pheroos:tck:legacy-quorum",
            trace_event_id=f"trace:{vector.id}:legacy-quorum",
        ),
    )
    decision = evaluate_quorum_decision(
        candidate_set=candidates,
        policy=manifest.protocol.quorum_policy,
        signals=[signal],
        fallback_candidate_id=manifest.protocol.quorum_policy.fallback_candidate,
    )
    event = TraceEvent(
        event_type="commit",
        protocol_id=manifest.protocol.id,
        target=target,
        reason=decision.reason,
        lineage={
            "target": target,
            "candidate_id": decision.candidate_id,
            "decision_reason": decision.reason,
            "upstream_score_lineage": [signal.verification.trace_event_id],
        },
    )
    event.validate()
    return _result(
        metrics={
            "signal_count": 1,
            "commit_threshold": manifest.protocol.quorum_policy.commit_threshold,
        },
        roots={
            "legacy_result_root": commit_payload_fingerprint(
                {
                    "candidate_id": decision.candidate_id,
                    "committed": decision.committed,
                    "reason": decision.reason,
                    "target": decision.target,
                },
                schema="pheroos-legacy-quorum-result-v1",
                profile=profile.version,
            ),
            "legacy_trace_root": commit_payload_fingerprint(
                {
                    "event_type": event.event_type,
                    "lineage": event.lineage,
                    "protocol_id": event.protocol_id,
                    "reason": event.reason,
                    "target": event.target,
                },
                schema="pheroos-legacy-quorum-trace-v1",
                profile=profile.version,
            ),
        },
        outcome={
            "profile": profile.version,
            "candidate_id": decision.candidate_id,
            "committed": decision.committed,
            "reason": decision.reason,
            "authoritative": quorum_decision_is_authoritative(decision),
        },
        trace_sequence=[event.event_type],
    )


def _probe_case_38(vector: _CommitTckRequest) -> dict[str, Any]:
    del vector
    vectors = load_commit_tck_vectors()
    cases = tuple(item.matrix_case for item in vectors)
    ids = tuple(item.id for item in vectors)
    schema = commit_tck_schema()
    matrix_root = commit_payload_fingerprint(
        {"matrix_cases": cases, "vector_ids": ids},
        schema="pheroos-commit-tck-matrix-index-v1",
        profile="pheroos-commit-integrity-v1",
    )
    schema_root = commit_payload_fingerprint(
        schema,
        schema="pheroos-commit-tck-schema-export-v1",
        profile="pheroos-commit-integrity-v1",
    )
    artifact_root = commit_tck_artifact_root()
    external_projection: dict[str, Any] = {}
    external_error = ""
    script = """
import json
from pheroos.conformance.commit_tck import commit_tck_artifact_root, commit_tck_schema, load_commit_tck_vectors
from pheroos.protocol.commit_wire import commit_payload_fingerprint
vectors = load_commit_tck_vectors()
cases = tuple(item.matrix_case for item in vectors)
ids = tuple(item.id for item in vectors)
print(json.dumps({
    "matrix_root": commit_payload_fingerprint(
        {"matrix_cases": cases, "vector_ids": ids},
        schema="pheroos-commit-tck-matrix-index-v1",
        profile="pheroos-commit-integrity-v1",
    ),
    "schema_root": commit_payload_fingerprint(
        commit_tck_schema(),
        schema="pheroos-commit-tck-schema-export-v1",
        profile="pheroos-commit-integrity-v1",
    ),
    "artifact_root": commit_tck_artifact_root(),
    "vector_count": len(vectors),
}, sort_keys=True))
"""
    try:
        with TemporaryDirectory(prefix="pheroos-tck-cwd-") as directory:
            completed = subprocess.run(
                [sys.executable, "-I", "-c", script],
                cwd=directory,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        if completed.returncode != 0:
            external_error = f"subprocess_exit_{completed.returncode}"
        else:
            loaded = json.loads(completed.stdout)
            if isinstance(loaded, dict):
                external_projection = loaded
            else:
                external_error = "subprocess_projection_invalid"
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        external_error = type(exc).__name__
    external_matches = external_projection == {
        "matrix_root": matrix_root,
        "schema_root": schema_root,
        "artifact_root": artifact_root,
        "vector_count": len(vectors),
    }
    complete = cases == tuple(range(1, 39))
    resource_present = bool(COMMIT_TCK_ARTIFACT.is_file())
    return _result(
        metrics={
            "vector_count": len(vectors),
            "matrix_case_count": len(set(cases)),
            "minimum_case": min(cases),
            "maximum_case": max(cases),
        },
        roots={
            "matrix_root": matrix_root,
            "schema_root": schema_root,
            "artifact_root": artifact_root,
        },
        outcome={
            "resource_present": resource_present,
            "complete_matrix": complete,
            "external_cwd_independent": external_matches,
            "duplicate_ids": len(ids) != len(set(ids)),
            "external_error": external_error,
        },
        certificate={
            "artifact_package": "pheroos.conformance",
            "artifact_name": "tck/commit-integrity-v1.json",
            "schema_id": COMMIT_TCK_SCHEMA_ID,
        },
        failure_code=(
            "tck_resource_missing"
            if not resource_present
            else "tck_matrix_incomplete"
            if not complete
            else "tck_external_cwd_failure"
            if not external_matches
            else None
        ),
    )


_MATRIX_PROBES: dict[int, Callable[[_CommitTckRequest], dict[str, Any]]] = {
    1: _probe_case_01,
    2: _probe_case_02,
    3: _probe_case_03,
    4: _probe_case_04,
    5: _probe_case_05,
    6: _probe_case_06,
    7: _probe_case_07,
    8: _probe_case_08,
    9: _probe_case_09,
    10: _probe_case_10,
    11: _probe_case_11,
    12: _probe_case_12,
    13: _probe_case_13,
    14: _probe_case_14,
    15: _probe_case_15,
    16: _probe_case_16,
    17: _probe_case_17,
    18: _probe_case_18,
    19: _probe_case_19,
    20: _probe_case_20,
    21: _probe_case_21,
    22: _probe_case_22,
    23: _probe_case_23,
    24: _probe_case_24,
    25: _probe_case_25,
    26: _probe_case_26,
    27: _probe_case_27,
    28: _probe_case_28,
    29: _probe_case_29,
    30: _probe_case_30,
    31: _probe_case_31,
    32: _probe_case_32,
    33: _probe_case_33,
    34: _probe_case_34,
    35: _probe_case_35,
    36: _probe_case_36,
    37: _probe_case_37,
    38: _probe_case_38,
}


__all__ = ["ReferenceCommitTckAdapter"]
