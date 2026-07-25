"""Private Commit TCK reference probes 27 30 handlers."""

from __future__ import annotations

from typing import Any

from pheroos.conformance._commit_reference import (
    build_reference_distributed_commit,
    build_reference_portable_commit,
    build_reference_stable_commit,
    issue_reference_distributed_certificate,
)
from pheroos.conformance._commit_reference_typing import collective_commit_policy

from pheroos.conformance._commit_tck.models import (
    result as _result,
)

from pheroos.conformance.commit_tck_v2_protocol import (
    CommitTckRequest as _CommitTckRequest,
)

from pheroos.governance.commit_state import (
    CommitFinalityStatus,
    DecisionOutcome,
    reduce_commit_liveness,
)

from pheroos.governance.distributed_commit import (
    distributed_commit_certificate_fingerprint,
    distributed_commit_certificate_is_current_final,
    distributed_commit_state_fingerprint,
    evaluate_distributed_finality,
    register_distributed_commit_certificate,
    verify_distributed_commit_certificate,
)

from pheroos.governance.output import (
    authorize_terminal_publication,
)

from pheroos.protocol.validation import validate_capability_manifest

from pheroos.conformance._commit_tck_reference.distributed import (
    _distributed_conflict,
    _output_gates,
)

from pheroos.conformance._commit_tck_reference.liveness import (
    _liveness_input,
)

from pheroos.conformance._commit_tck_reference.scenario import (
    _reference_scenario,
    _risk_trace_sequence,
)


def _probe_case_27(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    policy = collective_commit_policy(scenario.policy).distributed
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
            "n_equals_3f_plus_1": policy.membership_size
            == 3 * policy.max_byzantine_faults + 1,
            "q_equals_2f_plus_1": policy.witness_quorum
            == 2 * policy.max_byzantine_faults + 1,
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
    policy = collective_commit_policy(scenario.policy).distributed
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
        commit_policy=collective_commit_policy(scenario.policy),
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
    policy = collective_commit_policy(scenario.policy).distributed
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
        commit_policy=collective_commit_policy(scenario.policy),
        portable_certificate=portable.certificate,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        trusted_witness_attestations=bundle.trusted_witness_attestations,
        current_step=stable.window.last_evaluated_step,
    )
    minority_final = verify_distributed_commit_certificate(
        minority,
        commit_policy=collective_commit_policy(scenario.policy),
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
            "minority_certificate_ref": distributed_commit_certificate_fingerprint(
                minority
            ),
            "registered_state_ref": distributed_commit_state_fingerprint(registered),
        },
        outcome={
            "quorum_status": final.status.value,
            "quorum_current_final": distributed_commit_certificate_is_current_final(
                final, registered
            ),
            "minority_status": minority.status.value,
            "minority_final": minority_final,
        },
        trace_sequence=_risk_trace_sequence(scenario),
        certificate={"kind": "distributed_commit", "status": final.status.value},
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
        commit_policy=collective_commit_policy(scenario.policy),
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
        commit_policy=collective_commit_policy(scenario.policy),
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
        commit_policy=collective_commit_policy(scenario.policy),
        portable_certificate=conflict_portable,
        trusted_issuer_attestations=conflict_issuer_trust,
        trusted_witness_attestations=conflict_witness_trust,
        require_final=True,
    )
    semantic_conflict = bool(first.commit_value_root != conflict.commit_value_root)
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
                first.commit_value_root == same_value_retry.commit_value_root
            ),
        },
        failure_code=(
            "certificate_conflict"
            if frozen.frozen and semantic_conflict
            else "semantic_conflict_not_frozen"
        ),
    )
