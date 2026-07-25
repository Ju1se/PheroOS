from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import dataclass, fields, replace
from hashlib import sha256
from types import MappingProxyType, SimpleNamespace
from typing import Any, cast

import pytest

import pheroos.governance._commit_decision_v2.common as decision_common_module
import pheroos.governance._commit_decision_v2.evaluation as decision_evaluation_module
import pheroos.governance._commit_decision_v2.finality_inputs as decision_finality_inputs_module
import pheroos.governance._commit_decision_v2.genesis_inputs as decision_genesis_inputs_module
import pheroos.governance._commit_decision_v2.liveness_records as decision_liveness_module
import pheroos.governance._commit_decision_v2.operations as decision_operations_module
import pheroos.governance._commit_decision_v2.proposals as decision_proposals_module
import pheroos.governance._commit_decision_v2.reducer as decision_reducer_module
import pheroos.governance._commit_decision_v2.seal_context as decision_seal_context_module
import pheroos.governance._commit_decision_v2.snapshot as decision_snapshot_module
import pheroos.governance._commit_decision_v2.source as decision_source_module
import pheroos.governance._commit_decision_v2.source_inputs as decision_source_inputs_module
import pheroos.governance._commit_decision_v2.state_handle as decision_state_handle_module
import pheroos.governance._commit_decision_v2.state_records as decision_state_records_module

from tests.governance.test_commit_decision_v2_operations import (
    PROFILE,
    RUN_REF,
    TARGET,
    _commit_decision,
    _decision_context,
    _fresh_inputs,
    _capability,
)

from pheroos.governance._commit_decision_v2.assessment_records import (
    COMMIT_CANDIDATE_METRICS_SCHEMA_V2,
    CommitAssessmentV2,
    CommitCandidateMetricsV2,
)
from pheroos.governance._commit_decision_v2.common import (
    COMMIT_DECISION_ASSESSMENT_SCHEMA_V2,
    COMMIT_DECISION_CANDIDATE_PROPOSAL_SCHEMA_V2,
    COMMIT_DECISION_EVIDENCE_PROPOSAL_SCHEMA_V2,
    COMMIT_DECISION_OUTCOME_SCHEMA_V2,
    COMMIT_DECISION_OUTPUT_PROPOSAL_SCHEMA_V2,
    COMMIT_DECISION_PROGRESS_SCHEMA_V2,
    COMMIT_DECISION_REQUEST_SCHEMA_V2,
    COMMIT_DECISION_SEAL_SCHEMA_V2,
    COMMIT_DECISION_SNAPSHOT_SCHEMA_V2,
    COMMIT_DECISION_STATE_SCHEMA_V2,
    COMMIT_DECISION_WINDOW_SCHEMA_V2,
    MAX_COMMIT_DECISION_ITEMS_V2,
    MAX_COMMIT_DECISION_RESOURCE_NODES_V2,
    MAX_COMMIT_DECISION_RESOURCE_TEXT_BYTES_V2,
    MAX_COMMIT_DECISION_TEXT_BYTES_V2,
    _canonical_roots,
    _canonical_texts,
    _exact_array,
    _exact_mapping,
    _freeze_json,
    _install_root,
    _portable_json,
    _preflight_resource,
    _require_bool,
    _require_canonical_wire,
    _require_root,
    _require_text,
    _resource_node,
)
from pheroos.governance._commit_decision_v2.dependencies import (
    CommitDecisionDependencyV2,
    canonical_commit_decision_dependencies_v2,
    dependency_by_role_v2,
)
from pheroos.governance._commit_decision_v2.enums import (
    CommitDecisionCommandV2,
    CommitDecisionDependencyRoleV2,
    CommitDecisionMutationKindV2,
    CommitDecisionOutcomeKindV2,
    CommitDecisionPhaseV2,
)
from pheroos.governance._commit_decision_v2.evaluation import (
    _authoritative_claims_v2,
    _candidate_evidence_v2,
    _candidate_metrics,
    _closed_candidate_proposal_v2,
    _closed_candidate_proposals_v2,
    _evidence_by_candidate_v2,
    _global_reasons,
    derive_commit_assessment_v2,
)
from pheroos.governance._commit_decision_v2.events import (
    _base_lineage,
    _commit_decision_events_v2,
)
from pheroos.governance._commit_decision_v2.finality_inputs import (
    _committed_owner_observation_v2,
    _observed_finality_input_v2,
    _optional_verified_finality_input_v2,
    _restricted_owner_snapshot_root_v2,
)
from pheroos.governance._commit_decision_v2.genesis_inputs import (
    _canonical_genesis_inputs_v2,
    _current_request_payload_v2,
    _genesis_dependency_v2,
    _rehydrate_current_owner_v2,
    _validate_committed_context_v2,
)
from pheroos.governance._commit_decision_v2.gate_status import (
    COMMIT_DECISION_GATE_STATUS_SCHEMA_V2,
    CommitDecisionGateStatusV2,
)
from pheroos.governance._commit_decision_v2.liveness_records import (
    CommitDecisionOutcomeV2,
    CommitDecisionProgressV2,
    CommitDecisionWindowSealV2,
)
from pheroos.governance._commit_decision_v2.operations import (
    _committed_view_matches,
    _load_current_parent,
    _load_dependency_heads,
    _parent_view_failure,
    _require_request as _require_operation_request,
    _validated_session,
    advance_commit_decision_v2,
    open_commit_decision_authority_session_v2,
)
from pheroos.governance._commit_decision_v2.proposals import (
    CommitDecisionCandidateProposalV2,
    CommitDecisionEvidenceProposalV2,
    CommitDecisionOutputProposalV2,
    canonical_candidate_proposals_v2,
)
from pheroos.governance._commit_decision_v2.request import CommitDecisionRequestV2
from pheroos.governance._commit_decision_v2.reducer import (
    _evaluate,
    _explicit_unseal,
    _initialize,
    _missing_inputs_successor,
    _restart_epoch,
    reduce_commit_decision_v2,
)
from pheroos.governance._commit_decision_v2.reducer_support import (
    _deadline_outcome,
    _gate_status_outcome,
    _progress,
    _validate_finality_projection,
    _validate_parent_dependency,
    _validate_request_context,
    _validate_seal_inclusion,
)
from pheroos.governance._commit_decision_v2.seal_context import (
    _VerifiedCommitDecisionSealContextV2,
    _inclusion_v2,
    _verified_commit_decision_seal_context_material_v2,
    _verified_commit_decision_seal_context_v2,
)
from pheroos.governance._commit_decision_v2.seal_reducer import (
    _same_stable_leader,
    _seal_commit_decision_v2,
)
from pheroos.governance._commit_decision_v2.sealed_reducer import (
    _continuity_failure,
    _evaluate_sealed_v2,
    _evidence_bound_terminal,
    _external_finality_kind,
    _same_step_terminal_priority,
    _validate_verified_finality_inputs,
)
from pheroos.governance._commit_decision_v2.snapshot import (
    CommitDecisionSnapshotV2,
    commit_decision_history_advance_v2,
)
from pheroos.governance._commit_decision_v2.source import (
    prepare_commit_decision_initialize_v2,
    prepare_commit_decision_missing_inputs_v2,
    prepare_commit_decision_successor_v2,
)
from pheroos.governance._commit_decision_v2.source_inputs import (
    _collect_commit_decision_inputs_v2,
    _current_gate_v2,
    _current_parent_v2,
    _effective_candidate_proposals_v2,
    _evidence_evaluations_v2,
    _gate_status_v2,
    _require_same_precondition,
    _validate_gate_context,
)
from pheroos.governance._commit_evidence_projection_v2.evaluation import (
    CommitEvidenceEvaluationV2,
)
from pheroos.governance._commit_evidence_projection_v2.projection import (
    CommitEvidenceProjectionV2,
)
from pheroos.governance._commit_decision_v2.source_proof import (
    VerifiedCommitDecisionSourceV2,
    _source_context_root_v2,
    _validated_source_material_v2,
    _verified_source_material_v2,
    verify_commit_decision_request_source_v2,
)
from pheroos.governance._commit_decision_v2.state_handle import (
    VerifiedCommitDecisionStateV2,
    _verified_state_view_v2,
    commit_decision_state_is_current_v2,
    rehydrate_commit_decision_state_v2,
    require_current_commit_decision_state_v2,
)
from pheroos.governance._commit_decision_v2.state_records import (
    _decode_committed_decision_view_v2,
    _head_from_view_v2,
    _validate_history,
    _validate_read_set,
    _validate_session_binding,
    _validate_successor,
)
from pheroos.governance._commit_finality_v2 import (
    CommitFinalityOwnerV2,
    CommitFinalityProjectionV2,
    CommitFinalityStatusV2,
    _issue_verified_commit_finality_input_v2,
    commit_finality_owner_stream_ref_v2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    AuthorityDiagnosticCodeV2,
    GovernanceReadPreconditionV2,
)
from pheroos.protocol.commit_models import CommitAssurance, CollectiveCommitPolicy


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _finality_projection(
    parent: CommitDecisionSnapshotV2,
    *,
    owner: CommitFinalityOwnerV2 = CommitFinalityOwnerV2.CERTIFICATE,
    status: CommitFinalityStatusV2 = CommitFinalityStatusV2.VERIFIED,
    stream_ref: str = "",
    verified_at_step: int = 8,
) -> CommitFinalityProjectionV2:
    assert parent.seal is not None
    return CommitFinalityProjectionV2(
        owner=owner,
        status=status,
        stream_ref=stream_ref
        or commit_finality_owner_stream_ref_v2(
            owner,
            parent.scope_ref,
            parent.protocol_ref,
            parent.run_ref,
            parent.target_ref,
        ),
        revision=1,
        transition_id="transition:finality:totality",
        snapshot_root=_root("finality:totality:snapshot"),
        head_root=_root("finality:totality:head"),
        receipt_root=_root("finality:totality:receipt"),
        seal_transition_id=parent.transition_id,
        seal_root=parent.seal.seal_root,
        frozen_dependency_root=parent.seal.frozen_dependency_root,
        verified_at_step=verified_at_step,
        reason_codes=("finality:totality",),
    )


@dataclass(frozen=True, slots=True)
class _Fixture:
    context: Any
    request: CommitDecisionRequestV2
    source: VerifiedCommitDecisionSourceV2
    state: VerifiedCommitDecisionStateV2
    snapshot: CommitDecisionSnapshotV2


@dataclass(frozen=True, slots=True)
class _SealedFixture:
    context: Any
    inputs: tuple[object, ...]
    ready_state: VerifiedCommitDecisionStateV2
    sealed_state: VerifiedCommitDecisionStateV2
    proposal: CommitDecisionCandidateProposalV2
    output: CommitDecisionOutputProposalV2
    seal_request: CommitDecisionRequestV2
    seal_source: VerifiedCommitDecisionSourceV2


_SOURCE_MATERIAL_SLOTS = (
    "_request",
    "_manifest",
    "_profile",
    "_dependencies",
    "_parent",
    "_assessment",
    "_required_stability_steps",
    "_finality",
    "_finality_input_root",
    "_seal_inclusion",
    "_gate_status",
    "_source_context_root",
    "_snapshot",
)


@pytest.fixture(scope="module")
def decision_fixture() -> _Fixture:
    context = _decision_context("scope:commit-decision-v2:totality")
    request, source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref="mutation:commit-decision-v2:totality",
        current_step=4,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    state = _commit_decision(context, request, source)
    return _Fixture(context, request, source, state, state.snapshot)


@pytest.fixture(scope="module")
def sealed_fixture() -> _SealedFixture:
    context = _decision_context(
        "scope:commit-decision-v2:totality:sealed",
        stability_steps=1,
    )
    claim_root = _root("commit-decision-v2:totality:sealed:claim")
    inputs = _fresh_inputs(context, claim_root)
    initialize, initialize_source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref="mutation:commit-decision-v2:totality:sealed:initialize",
        current_step=6,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    state = _commit_decision(context, initialize, initialize_source)
    proposal = CommitDecisionCandidateProposalV2(
        candidate_ref="candidate:accept",
        claim_root=claim_root,
        evidence=(),
    )
    evaluate, evaluate_source = prepare_commit_decision_successor_v2(
        parent_state=state,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:commit-decision-v2:totality:sealed:evaluate",
        current_step=7,
        mutation_issuer_ref=context.grant.issuer_ref,
        command=CommitDecisionCommandV2.EVALUATE,
        candidate_proposals=(proposal,),
        commit_replay_state=inputs[0],
        risk_state=inputs[1],
        membership_state=inputs[2],
        support_state=inputs[3],
        evidence_state=inputs[4],
        stop_state=inputs[5],
        permission_state=inputs[6],
    )
    ready_state = _commit_decision(context, evaluate, evaluate_source)
    output = CommitDecisionOutputProposalV2(
        candidate_ref=proposal.candidate_ref,
        claim_root=proposal.claim_root,
        output_contract_root=_root(
            "commit-decision-v2:totality:sealed:output-contract"
        ),
        payload={"answer": "accepted"},
    )
    seal_request, seal_source = prepare_commit_decision_successor_v2(
        parent_state=ready_state,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:commit-decision-v2:totality:sealed:seal",
        current_step=7,
        mutation_issuer_ref=context.grant.issuer_ref,
        command=CommitDecisionCommandV2.SEAL,
        output_proposal=output,
        commit_replay_state=inputs[0],
        risk_state=inputs[1],
        membership_state=inputs[2],
        support_state=inputs[3],
        evidence_state=inputs[4],
        stop_state=inputs[5],
        permission_state=inputs[6],
    )
    sealed_state = _commit_decision(context, seal_request, seal_source)
    return _SealedFixture(
        context,
        cast(tuple[object, ...], inputs),
        ready_state,
        sealed_state,
        proposal,
        output,
        seal_request,
        seal_source,
    )


def _metric(
    candidate: str = "candidate:alpha",
    *,
    score: int = 2,
    reasons: tuple[str, ...] = (),
) -> CommitCandidateMetricsV2:
    return CommitCandidateMetricsV2(
        candidate_ref=candidate,
        claim_root=_root(f"claim:{candidate}"),
        positive_evidence_count=2,
        counterevidence_count=0,
        counterevidence_ratio_ppm=0,
        active_support_clusters=1,
        support_ratio_ppm=1_000_000,
        source_diversity=1,
        challenge_categories=("accuracy",),
        evidence_root=_root(f"evidence:{candidate}"),
        challenge_root=_root(f"challenge:{candidate}"),
        lease_root=_root(f"lease:{candidate}"),
        net_evidence=score,
        score=score,
        ready_for_stability=not reasons,
        reason_codes=reasons,
    )


def _assessment(
    metric: CommitCandidateMetricsV2 | None = None,
) -> CommitAssessmentV2:
    selected = _metric() if metric is None else metric
    return CommitAssessmentV2(
        current_step=4,
        candidate_metrics=(selected,),
        leader_candidate_ref=selected.candidate_ref,
        tied_candidate_refs=(selected.candidate_ref,),
        unique_leader=True,
        leader_margin=2,
        leader_ready_for_stability=selected.ready_for_stability,
        stop_clear=True,
        permission_allowed=True,
        blocker_refs=(),
        equivocation_refs=(),
        replay_conflict_refs=(),
        reason_codes=(),
        dependency_set_root=_root("dependency-set"),
        evaluation_context_root=_root("evaluation-context"),
        collective_evidence_root=_root("collective-evidence"),
        collective_challenge_root=_root("collective-challenge"),
        collective_claim_root=_root("collective-claim"),
        collective_lease_root=_root("collective-lease"),
    )


def _outcome(
    kind: CommitDecisionOutcomeKindV2 = CommitDecisionOutcomeKindV2.SAFE_FALLBACK,
) -> CommitDecisionOutcomeV2:
    commit = kind is CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT
    return CommitDecisionOutcomeV2(
        kind=kind,
        candidate_ref="candidate:alpha",
        claim_root=_root("outcome:claim") if commit else "",
        output_contract_root=_root("outcome:contract") if commit else "",
        output_payload_root=_root("outcome:payload") if commit else "",
        finality_root=_root("outcome:finality") if commit else "",
        epistemically_committed=commit,
        delivery_eligible=True,
        publication_eligible=False,
        execution_eligible=False,
        reason_codes=("terminal:totality",),
        current_step=8,
        evidence_deadline_step=8,
        finality_deadline_step=10,
        window_root=_root("outcome:window"),
        seal_root=_root("outcome:seal") if commit else "",
        frozen_dependency_root=_root("outcome:frozen"),
    )


def _status(
    *,
    reasons: tuple[str, ...] = (),
    stop_clear: bool = True,
    permission_allowed: bool = True,
    evidence_current: bool = True,
) -> CommitDecisionGateStatusV2:
    return CommitDecisionGateStatusV2(
        current_step=7,
        stop_clear=stop_clear,
        permission_allowed=permission_allowed,
        risk_current=True,
        membership_current=True,
        verification_current=True,
        evidence_current=evidence_current,
        support_current=True,
        blocker_roots=(),
        reason_codes=reasons,
    )


def _snapshot_replace(
    snapshot: CommitDecisionSnapshotV2,
    **changes: object,
) -> CommitDecisionSnapshotV2:
    return replace(
        snapshot,
        state_root="",
        history_root="",
        snapshot_root="",
        **changes,
    )


def _successor_request(
    base: CommitDecisionRequestV2,
    *,
    command: CommitDecisionCommandV2,
    step: int,
    suffix: str,
    restart_epoch: int | None = None,
    output: CommitDecisionOutputProposalV2 | None = None,
) -> CommitDecisionRequestV2:
    return replace(
        base,
        mutation_ref=f"mutation:commit-decision-v2:totality:{suffix}",
        command=command,
        current_step=step,
        candidate_proposals=(),
        output_proposal=output,
        finality_projection=None,
        restart_epoch=restart_epoch,
        stream_ref="",
        transition_id="",
        request_root="",
    )


def _clone_source(
    source: VerifiedCommitDecisionSourceV2,
) -> VerifiedCommitDecisionSourceV2:
    clone = object.__new__(VerifiedCommitDecisionSourceV2)
    for name in VerifiedCommitDecisionSourceV2.__slots__:
        object.__setattr__(clone, name, object.__getattribute__(source, name))
    return clone


def _clone_state(
    state: VerifiedCommitDecisionStateV2,
) -> VerifiedCommitDecisionStateV2:
    clone = object.__new__(VerifiedCommitDecisionStateV2)
    for name in VerifiedCommitDecisionStateV2.__slots__:
        object.__setattr__(clone, name, object.__getattribute__(state, name))
    return clone


class _ReaderStub:
    def __init__(
        self,
        *,
        head: object = None,
        view: object = None,
        state: object = None,
        fail_head: bool = False,
        fail_view: bool = False,
    ) -> None:
        self.head = head
        self.view = view
        self.state = {} if state is None else state
        self.fail_head = fail_head
        self.fail_view = fail_view

    def load_head_v2(self, _scope_ref: str, _stream_ref: str) -> Any:
        if self.fail_head:
            raise KeyError("head unavailable")
        return self.head

    def load_state_v2(self, _scope_ref: str, _stream_ref: str) -> Any:
        return self.state

    def load_commit_view_v2(
        self,
        _scope_ref: str,
        _stream_ref: str,
        _transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> Any:
        del expected_receipt_root
        if self.fail_view:
            raise KeyError("view unavailable")
        return self.view


class _InvalidUpstreamHeadReader:
    def __init__(self, reader: GovernanceStateReaderV2) -> None:
        self.reader = reader

    def load_head_v2(self, _scope_ref: str, _stream_ref: str) -> Any:
        return object()

    def load_state_v2(self, scope_ref: str, stream_ref: str) -> Any:
        return self.reader.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> Any:
        return self.reader.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )


@pytest.mark.parametrize("value", [None, 1, True, str])
def test_text_requires_an_exact_string(value: object) -> None:
    with pytest.raises(TypeError, match="exact string"):
        _require_text(value, "value")


@pytest.mark.parametrize(
    "value, message",
    [
        ("\ud800", "UTF-8"),
        ("x" * (MAX_COMMIT_DECISION_TEXT_BYTES_V2 + 1), "text bound"),
    ],
)
def test_text_resource_limits_are_explicit(value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _require_text(value, "value")


@pytest.mark.parametrize(
    "value",
    [
        "sha256:short",
        "sha256:" + "A" * 64,
        "sha257:" + "0" * 64,
    ],
)
def test_roots_require_exact_lowercase_sha256(value: str) -> None:
    with pytest.raises(ValueError, match="lowercase sha256"):
        _require_root(value, "root")


def test_common_exact_container_and_bool_guards() -> None:
    with pytest.raises(TypeError, match="exact bool"):
        _require_bool(1, "flag")
    with pytest.raises(TypeError, match="exact object"):
        _exact_mapping(MappingProxyType({"field": 1}), frozenset({"field"}), "wire")
    with pytest.raises(TypeError, match="exact array"):
        _exact_array((), "wire")
    with pytest.raises(ValueError, match="item bound"):
        _exact_array([None] * (MAX_COMMIT_DECISION_ITEMS_V2 + 1), "wire")


@pytest.mark.parametrize(
    "function, value, message",
    [
        (_canonical_texts, {"value"}, "exact array or tuple"),
        (
            _canonical_texts,
            ("value",) * (MAX_COMMIT_DECISION_ITEMS_V2 + 1),
            "item bound",
        ),
        (_canonical_texts, ("value", "value"), "unique values"),
        (_canonical_roots, {_root("one")}, "exact array or tuple"),
        (
            _canonical_roots,
            (_root("one"),) * (MAX_COMMIT_DECISION_ITEMS_V2 + 1),
            "item bound",
        ),
        (_canonical_roots, (_root("one"), _root("one")), "unique roots"),
    ],
)
def test_common_canonical_sequence_guards(
    function: Any,
    value: object,
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        function(value, "values")


def test_common_canonical_wire_and_installed_root_guards() -> None:
    metric = _metric()
    with pytest.raises(ValueError, match="mismatched"):
        _install_root(metric, "metrics_root", _root("wrong"), "candidate-metrics", {})
    with pytest.raises(ValueError, match="canonical wire"):
        _require_canonical_wire({"value": 1}, {"value": 2}, "wire")


def test_common_json_freeze_and_portable_projection_totality() -> None:
    frozen = _freeze_json({"nested": [1, {"value": "ok"}]})
    assert isinstance(frozen, MappingProxyType)
    assert _portable_json(frozen) == {"nested": [1, {"value": "ok"}]}
    assert _portable_json((1, 2)) == [1, 2]
    with pytest.raises(TypeError, match="non-string key"):
        _freeze_json({1: "value"})
    with pytest.raises(TypeError, match="non-portable value"):
        _freeze_json(object())


def test_common_resource_preflight_enforces_all_bounds() -> None:
    with pytest.raises(ValueError, match="node bound"):
        _preflight_resource([None] * MAX_COMMIT_DECISION_RESOURCE_NODES_V2)
    nested: object = None
    for _ in range(26):
        nested = [nested]
    with pytest.raises(ValueError, match="depth bound"):
        _preflight_resource(nested)
    text = "x" * MAX_COMMIT_DECISION_TEXT_BYTES_V2
    count = MAX_COMMIT_DECISION_RESOURCE_TEXT_BYTES_V2 // len(text) + 1
    with pytest.raises(ValueError, match="text-byte bound"):
        _preflight_resource([text] * count)
    with pytest.raises(TypeError, match="non-string key"):
        _resource_node({1: "value"}, 0)
    with pytest.raises(TypeError, match="non-portable value"):
        _resource_node(object(), 0)


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"schema": "unsupported"}, "schema"),
        ({"net_evidence": -1}, "net evidence"),
        ({"score": 1}, "net evidence"),
        ({"ready_for_stability": False}, "readiness"),
        ({"ready_for_stability": True, "reason_codes": ("blocked",)}, "readiness"),
    ],
)
def test_candidate_metrics_reject_inconsistent_authority_projections(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_metric(), metrics_root="", **changes)


@pytest.mark.parametrize(
    "changes, error, message",
    [
        ({"schema": "unsupported"}, ValueError, "schema"),
        ({"candidate_metrics": set()}, TypeError, "exact array or tuple"),
        ({"candidate_metrics": (object(),)}, TypeError, "noncanonical"),
        (
            {"candidate_metrics": (_metric(), _metric())},
            ValueError,
            "candidate set",
        ),
        (
            {"unique_leader": False},
            ValueError,
            "leader projection",
        ),
        (
            {"tied_candidate_refs": ("candidate:missing",)},
            ValueError,
            "tie set",
        ),
    ],
)
def test_assessment_rejects_noncanonical_candidate_sets(
    changes: dict[str, object],
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        replace(_assessment(), assessment_root="", **changes)


@pytest.mark.parametrize(
    "changes, error, message",
    [
        ({"schema": "unsupported"}, ValueError, "schema"),
        ({"role": object()}, TypeError, "role"),
        ({"observed_position": object()}, TypeError, "position"),
        ({"transition_id": "not-genesis"}, ValueError, "genesis"),
        (
            {
                "revision": 1,
                "transition_id": "transition:one",
                "observed_position": GovernanceCommitPositionV2.SUPERSEDED,
            },
            ValueError,
            "current dependencies",
        ),
    ],
)
def test_dependency_record_rejects_invalid_authority_coordinates(
    decision_fixture: _Fixture,
    changes: dict[str, object],
    error: type[Exception],
    message: str,
) -> None:
    dependency = decision_fixture.snapshot.dependencies[0]
    with pytest.raises(error, match=message):
        replace(dependency, dependency_root="", **changes)


def test_dependency_wire_and_collection_totality(
    decision_fixture: _Fixture,
) -> None:
    dependency = decision_fixture.snapshot.dependencies[0]
    wire = dependency.to_dict()
    wire["role"] = "unsupported"
    with pytest.raises(ValueError, match="enum"):
        CommitDecisionDependencyV2.from_dict(wire)
    assert dependency.root() == dependency.dependency_root
    with pytest.raises(TypeError, match="exact array or tuple"):
        canonical_commit_decision_dependencies_v2(set())
    with pytest.raises(TypeError, match="noncanonical"):
        canonical_commit_decision_dependencies_v2((object(),))
    with pytest.raises(ValueError, match="roles must be unique"):
        canonical_commit_decision_dependencies_v2((dependency, dependency))
    duplicate_stream = replace(
        dependency,
        role=CommitDecisionDependencyRoleV2.EVIDENCE,
        dependency_root="",
    )
    with pytest.raises(ValueError, match="streams must be unique"):
        canonical_commit_decision_dependencies_v2((dependency, duplicate_stream))
    with pytest.raises(ValueError, match="is absent"):
        dependency_by_role_v2(
            (dependency,),
            CommitDecisionDependencyRoleV2.EVIDENCE,
        )


def test_proposal_record_and_wire_guards() -> None:
    evidence = CommitDecisionEvidenceProposalV2(_root("qualified"))
    with pytest.raises(ValueError, match="schema"):
        replace(evidence, schema="unsupported", proposal_root="")
    assert CommitDecisionEvidenceProposalV2.from_dict(evidence.to_dict()) == evidence

    candidate = CommitDecisionCandidateProposalV2(
        candidate_ref="candidate:alpha",
        claim_root=_root("claim:alpha"),
        evidence=(evidence,),
    )
    with pytest.raises(ValueError, match="schema"):
        replace(candidate, schema="unsupported", proposal_root="")
    with pytest.raises(TypeError, match="exact array or tuple"):
        replace(candidate, evidence=set(), proposal_root="")
    with pytest.raises(TypeError, match="noncanonical"):
        replace(candidate, evidence=(object(),), proposal_root="")
    with pytest.raises(ValueError, match="repeats"):
        replace(candidate, evidence=(evidence, evidence), proposal_root="")
    with pytest.raises(TypeError, match="exact array or tuple"):
        canonical_candidate_proposals_v2(set())
    with pytest.raises(TypeError, match="noncanonical"):
        canonical_candidate_proposals_v2((object(),))
    with pytest.raises(ValueError, match="repeat"):
        canonical_candidate_proposals_v2((candidate, candidate))


def test_output_proposal_resource_and_wire_guards() -> None:
    output = CommitDecisionOutputProposalV2(
        candidate_ref="candidate:alpha",
        claim_root=_root("output:claim"),
        output_contract_root=_root("output:contract"),
        payload={"answer": ["yes"]},
    )
    assert output.canonical_bytes()
    with pytest.raises(ValueError, match="schema"):
        replace(output, schema="unsupported", proposal_root="")
    with pytest.raises(TypeError, match="object"):
        replace(output, payload=object(), proposal_root="")
    wire = output.to_dict()
    wire["payload"] = ()
    with pytest.raises(TypeError, match="exact object"):
        CommitDecisionOutputProposalV2.from_dict(wire)


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"schema": "unsupported"}, "schema"),
        ({"streak_started_at_step": 1}, "empty commit streak"),
        (
            {
                "streak_count": 1,
                "streak_started_at_step": None,
                "leader_candidate_ref": "",
                "last_ready": False,
            },
            "active commit streak",
        ),
    ],
)
def test_window_rejects_inconsistent_streak_state(
    decision_fixture: _Fixture,
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(decision_fixture.snapshot.window, window_root="", **changes)


def test_seal_progress_and_outcome_record_guards(
    decision_fixture: _Fixture,
) -> None:
    window = decision_fixture.snapshot.window
    seal = CommitDecisionWindowSealV2(
        parent_transition_id=decision_fixture.snapshot.transition_id,
        parent_snapshot_root=decision_fixture.snapshot.snapshot_root,
        window_root=window.window_root,
        frozen_dependency_root=_root("seal:frozen"),
        sealed_at_step=5,
        candidate_ref="candidate:alpha",
        claim_root=_root("seal:claim"),
        output_contract_root=_root("seal:contract"),
        output_payload_root=_root("seal:payload"),
        output_payload={"answer": "yes"},
    )
    with pytest.raises(ValueError, match="schema"):
        replace(seal, schema="unsupported", seal_root="")
    with pytest.raises(TypeError, match="object"):
        replace(seal, output_payload=object(), seal_root="")
    seal_wire = seal.to_dict()
    seal_wire["output_payload"] = ()
    with pytest.raises(TypeError, match="exact object"):
        CommitDecisionWindowSealV2.from_dict(seal_wire)

    progress = cast(CommitDecisionProgressV2, decision_fixture.snapshot.progress)
    with pytest.raises(ValueError, match="schema or phase"):
        replace(progress, schema="unsupported", progress_root="")
    with pytest.raises(ValueError, match="cannot be terminal"):
        replace(progress, terminal=True, progress_root="")
    progress_wire = progress.to_dict()
    progress_wire["phase"] = "unsupported"
    with pytest.raises(ValueError, match="phase is unsupported"):
        CommitDecisionProgressV2.from_dict(progress_wire)

    outcome = _outcome()
    with pytest.raises(ValueError, match="schema or kind"):
        replace(outcome, schema="unsupported", outcome_root="")
    with pytest.raises(ValueError, match="must be terminal"):
        replace(outcome, terminal=False, outcome_root="")
    with pytest.raises(ValueError, match="must be deliverable"):
        replace(outcome, delivery_eligible=False, outcome_root="")
    with pytest.raises(ValueError, match="cannot authorize"):
        replace(outcome, publication_eligible=True, outcome_root="")
    with pytest.raises(ValueError, match="non-commit"):
        replace(outcome, epistemically_committed=True, outcome_root="")
    commit = _outcome(CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT)
    with pytest.raises(ValueError, match="frozen output bindings"):
        replace(commit, claim_root="", outcome_root="")
    with pytest.raises(ValueError, match="epistemically committed"):
        replace(commit, epistemically_committed=False, outcome_root="")
    outcome_wire = outcome.to_dict()
    outcome_wire["kind"] = "unsupported"
    with pytest.raises(ValueError, match="kind is unsupported"):
        CommitDecisionOutcomeV2.from_dict(outcome_wire)


def test_gate_status_rejects_false_without_reason_and_clear_with_runtime_reason() -> (
    None
):
    clear = CommitDecisionGateStatusV2(
        current_step=4,
        stop_clear=True,
        permission_allowed=True,
        risk_current=True,
        membership_current=True,
        verification_current=True,
        evidence_current=True,
        support_current=True,
        blocker_roots=(),
        reason_codes=(),
    )
    with pytest.raises(ValueError, match="schema"):
        replace(clear, schema="unsupported", status_root="")
    with pytest.raises(ValueError, match="requires a reason"):
        replace(clear, stop_clear=False, status_root="")
    with pytest.raises(ValueError, match="meta reasons"):
        replace(clear, reason_codes=("input:missing",), status_root="")


@pytest.mark.parametrize(
    "changes, error, message",
    [
        ({"schema": "unsupported"}, ValueError, "version"),
        ({"command": object()}, TypeError, "command"),
        ({"output_proposal": object()}, TypeError, "output proposal"),
        ({"finality_projection": object()}, TypeError, "finality projection"),
        ({"stream_ref": "authority:wrong"}, ValueError, "identity"),
    ],
)
def test_request_rejects_noncanonical_version_types_and_identity(
    decision_fixture: _Fixture,
    changes: dict[str, object],
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        replace(decision_fixture.request, request_root="", **changes)


def test_request_wire_rejects_unknown_command(
    decision_fixture: _Fixture,
) -> None:
    wire = decision_fixture.request.to_dict()
    wire["command"] = "unsupported"
    with pytest.raises(ValueError, match="command is unsupported"):
        CommitDecisionRequestV2.from_dict(wire)
    assert decision_fixture.request.canonical_bytes()


def test_snapshot_history_and_context_guards(
    decision_fixture: _Fixture,
) -> None:
    snapshot = decision_fixture.snapshot
    with pytest.raises(TypeError, match="mutation kind"):
        commit_decision_history_advance_v2(
            snapshot.parent_history_root,
            snapshot.parent_history_count,
            snapshot.transition_id,
            cast(CommitDecisionMutationKindV2, object()),
            snapshot.state_root,
        )
    with pytest.raises(ValueError, match="dependency_set_root"):
        replace(snapshot, dependency_set_root=_root("wrong:dependencies"))
    with pytest.raises(ValueError, match="history_root"):
        replace(snapshot, history_root=_root("wrong:history"), state_root="")
    with pytest.raises(ValueError, match="schema"):
        replace(snapshot, schema="unsupported")
    with pytest.raises(ValueError, match="canonical version"):
        replace(snapshot, canonical_version="unsupported")
    with pytest.raises(ValueError, match="profile and assurance"):
        replace(snapshot, assurance=object())
    with pytest.raises(TypeError, match="mutation kind"):
        replace(snapshot, mutation_kind=object())


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"stream_ref": "authority:wrong"}, "stream identity"),
        ({"transition_id": "transition:wrong"}, "transition identity"),
        ({"revision": 2}, "revision is not contiguous"),
        ({"parent_transition_id": "wrong"}, "genesis lineage"),
        ({"history_count": 2}, "history count"),
        ({"current_step": 3}, "predates initialization"),
        ({"evidence_deadline_step": 4}, "deadlines"),
    ],
)
def test_snapshot_continuity_guards(
    decision_fixture: _Fixture,
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(decision_fixture.snapshot, **changes)


@pytest.mark.parametrize(
    "changes, error, message",
    [
        ({"window": object()}, TypeError, "exact window"),
        ({"assessment": object()}, TypeError, "assessment"),
        ({"seal": object()}, TypeError, "seal"),
        ({"progress": object()}, TypeError, "progress"),
        ({"outcome": object()}, TypeError, "outcome"),
        ({"progress": None}, ValueError, "exactly progress or outcome"),
        (
            {
                "progress": None,
                "outcome": _outcome(),
                "mutation_kind": CommitDecisionMutationKindV2.ASSESSED,
            },
            ValueError,
            "nonterminal mutation",
        ),
        (
            {
                "progress": replace(
                    CommitDecisionProgressV2(
                        phase=CommitDecisionPhaseV2.SEARCH,
                        current_step=4,
                        evidence_deadline_step=16,
                        finality_deadline_step=28,
                        assessment_root="",
                        window_root=_root("alternate:window"),
                        seal_root="",
                        dependency_set_root=_root("alternate:dependency"),
                        heartbeat_sequence=0,
                        previous_progress_root="",
                        remaining_reset_budget=1,
                        remaining_epoch_restart_budget=1,
                        leader_candidate_ref="",
                        streak_count=0,
                        next_required_inputs=(),
                        unmet_gates=(),
                    ),
                    current_step=5,
                    progress_root="",
                )
            },
            ValueError,
            "progress step",
        ),
    ],
)
def test_snapshot_nested_record_guards(
    decision_fixture: _Fixture,
    changes: dict[str, object],
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        replace(decision_fixture.snapshot, **changes)


def test_snapshot_wire_rejects_unknown_enums(
    decision_fixture: _Fixture,
) -> None:
    wire = decision_fixture.snapshot.to_dict()
    wire["mutation_kind"] = "unsupported"
    with pytest.raises(ValueError, match="enum is unsupported"):
        CommitDecisionSnapshotV2.from_dict(wire)


def test_verified_source_handle_is_opaque_immutable_and_nonportable(
    decision_fixture: _Fixture,
) -> None:
    source = decision_fixture.source
    assert repr(source) == "<VerifiedCommitDecisionSourceV2 redacted>"
    assert copy(source) is source
    assert deepcopy(source) is source
    with pytest.raises(TypeError, match="cannot be constructed"):
        VerifiedCommitDecisionSourceV2()
    with pytest.raises(TypeError, match="final"):
        type("DerivedCommitDecisionSource", (VerifiedCommitDecisionSourceV2,), {})
    with pytest.raises(AttributeError, match="immutable"):
        setattr(source, "_profile", "substituted")
    with pytest.raises(TypeError, match="not portable"):
        source.__reduce__()
    with pytest.raises(TypeError, match="not portable"):
        source.__reduce_ex__(4)
    with pytest.raises(TypeError, match="not portable"):
        source.__getstate__()


def test_verified_source_material_rejects_forged_slot_shapes(
    decision_fixture: _Fixture,
) -> None:
    with pytest.raises(TypeError, match="wrong exact type"):
        _verified_source_material_v2(object())
    missing = object.__new__(VerifiedCommitDecisionSourceV2)
    with pytest.raises(TypeError, match="incomplete"):
        _verified_source_material_v2(missing)
    bad_token = _clone_source(decision_fixture.source)
    object.__setattr__(bad_token, "_token", object())
    with pytest.raises(TypeError, match="token"):
        _verified_source_material_v2(bad_token)
    incomplete = _clone_source(decision_fixture.source)
    object.__delattr__(incomplete, "_snapshot")
    with pytest.raises(TypeError, match="incomplete"):
        _verified_source_material_v2(incomplete)


@pytest.mark.parametrize(
    "slot, replacement, message",
    [
        ("_request", object(), "context is invalid"),
        ("_manifest", object(), "context is invalid"),
        ("_profile", object(), "context is invalid"),
        ("_dependencies", (object(),), "noncanonical"),
        ("_parent", object(), "parent is invalid"),
        ("_assessment", object(), "assessment is invalid"),
        ("_required_stability_steps", 0, "threshold is invalid"),
        ("_finality", object(), "finality is invalid"),
        ("_seal_inclusion", object(), "seal inclusion is invalid"),
        ("_gate_status", object(), "gate status is invalid"),
        ("_snapshot", object(), "snapshot is invalid"),
    ],
)
def test_verified_source_material_revalidates_every_slot(
    decision_fixture: _Fixture,
    slot: str,
    replacement: object,
    message: str,
) -> None:
    values = [
        object.__getattribute__(decision_fixture.source, name)
        for name in _SOURCE_MATERIAL_SLOTS
    ]
    values[_SOURCE_MATERIAL_SLOTS.index(slot)] = replacement
    with pytest.raises((TypeError, ValueError), match=message):
        _validated_source_material_v2(tuple(values))


def test_verified_source_material_rejects_unpaired_finality_binding(
    decision_fixture: _Fixture,
) -> None:
    values = [
        object.__getattribute__(decision_fixture.source, name)
        for name in _SOURCE_MATERIAL_SLOTS
    ]
    values[_SOURCE_MATERIAL_SLOTS.index("_finality_input_root")] = _root(
        "unpaired-finality"
    )
    with pytest.raises(ValueError, match="binding is inconsistent"):
        _validated_source_material_v2(tuple(values))


def test_source_verifier_rejects_request_parent_context_and_replacement_substitution(
    decision_fixture: _Fixture,
) -> None:
    with pytest.raises(TypeError, match="exact request"):
        verify_commit_decision_request_source_v2(
            cast(CommitDecisionRequestV2, object()),
            source=decision_fixture.source,
            committed_parent_snapshot=None,
        )
    request_substitution = replace(
        decision_fixture.request,
        mutation_issuer_ref="issuer:substituted",
        request_root="",
    )
    with pytest.raises(ValueError, match="request is mismatched"):
        verify_commit_decision_request_source_v2(
            request_substitution,
            source=decision_fixture.source,
            committed_parent_snapshot=None,
        )
    with pytest.raises(ValueError, match="parent presence"):
        verify_commit_decision_request_source_v2(
            decision_fixture.request,
            source=decision_fixture.source,
            committed_parent_snapshot=decision_fixture.snapshot,
        )

    context_substitution = _clone_source(decision_fixture.source)
    object.__setattr__(
        context_substitution,
        "_source_context_root",
        _root("substituted-context"),
    )
    with pytest.raises(ValueError, match="context is mismatched"):
        verify_commit_decision_request_source_v2(
            decision_fixture.request,
            source=context_substitution,
            committed_parent_snapshot=None,
        )

    replacement_substitution = _clone_source(decision_fixture.source)
    other_request, other_source = prepare_commit_decision_initialize_v2(
        domain=decision_fixture.context.domain,
        manifest=decision_fixture.context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref="mutation:commit-decision-v2:other-replacement",
        current_step=4,
        mutation_issuer_ref=decision_fixture.context.grant.issuer_ref,
    )
    other_snapshot = object.__getattribute__(other_source, "_snapshot")
    object.__setattr__(replacement_substitution, "_snapshot", other_snapshot)
    material = _verified_source_material_v2(replacement_substitution)
    context_root = _source_context_root_v2(
        request=decision_fixture.request,
        manifest=material.manifest,
        dependencies=material.dependencies,
        parent=None,
        assessment=material.assessment,
        finality=material.finality,
        finality_input_root=material.finality_input_root,
        seal_inclusion=material.seal_inclusion,
        gate_status=material.gate_status,
    )
    object.__setattr__(replacement_substitution, "_source_context_root", context_root)
    assert other_request.transition_id == other_snapshot.transition_id
    with pytest.raises(ValueError, match="replacement is mismatched"):
        verify_commit_decision_request_source_v2(
            decision_fixture.request,
            source=replacement_substitution,
            committed_parent_snapshot=None,
        )


def test_verified_state_handle_accessors_and_nonportable_contract(
    decision_fixture: _Fixture,
) -> None:
    state = decision_fixture.state
    assert repr(state) == "<VerifiedCommitDecisionStateV2 redacted>"
    assert copy(state) is state
    assert deepcopy(state) is state
    assert state.request_root == decision_fixture.request.request_root
    assert state.stream_ref == decision_fixture.request.stream_ref
    assert state.transition_id == decision_fixture.request.transition_id
    assert state.receipt_root.startswith("sha256:")
    assert state.position is GovernanceCommitPositionV2.CURRENT
    assert commit_decision_state_is_current_v2(state)
    assert not commit_decision_state_is_current_v2(object())
    with pytest.raises(TypeError, match="cannot be constructed"):
        VerifiedCommitDecisionStateV2()
    with pytest.raises(TypeError, match="final"):
        type("DerivedCommitDecisionState", (VerifiedCommitDecisionStateV2,), {})
    with pytest.raises(AttributeError, match="immutable"):
        setattr(state, "_request", object())
    with pytest.raises(TypeError, match="not portable"):
        state.__reduce__()
    with pytest.raises(TypeError, match="not portable"):
        state.__reduce_ex__(4)
    with pytest.raises(TypeError, match="not portable"):
        state.__getstate__()


def test_evaluation_totality_closes_candidate_claim_and_wire_inputs(
    decision_fixture: _Fixture,
) -> None:
    manifest_without_policy = replace(
        decision_fixture.context.manifest,
        collective_commit_policy=None,
    )
    with pytest.raises(ValueError, match="no commit policy"):
        derive_commit_assessment_v2(
            manifest=manifest_without_policy,
            current_step=4,
            epoch=1,
            proposals=(),
            authoritative_subjects=(),
            evidence_evaluations=(),
            risk=cast(Any, object()),
            membership_state=object(),
            support_state=object(),
            stop=cast(Any, object()),
            permission=cast(Any, object()),
            stop_dependencies_current=False,
            permission_dependencies_current=False,
            dependency_set_root=_root("evaluation:dependency"),
            evaluation_context_root=_root("evaluation:context"),
        )
    with pytest.raises(TypeError, match="subjects must be exact"):
        _authoritative_claims_v2(set())
    with pytest.raises(TypeError, match="subject is malformed"):
        _authoritative_claims_v2((("candidate:accept",),))

    proposal = CommitDecisionCandidateProposalV2(
        candidate_ref="candidate:accept",
        claim_root=_root("evaluation:claim"),
        evidence=(),
    )
    missing, missing_reasons = _closed_candidate_proposal_v2(
        "candidate:accept",
        proposal=None,
        claims=(),
    )
    assert missing.candidate_ref == "candidate:accept"
    assert "invalid:missing_candidate_proposal" in missing_reasons
    _, multiple_reasons = _closed_candidate_proposal_v2(
        "candidate:accept",
        proposal=proposal,
        claims=(_root("evaluation:claim"), _root("evaluation:other-claim")),
    )
    assert "safety:multiple_active_claims" in multiple_reasons
    _, unavailable_reasons = _closed_candidate_proposal_v2(
        "candidate:accept",
        proposal=proposal,
        claims=(),
    )
    assert "input:authoritative_claim_unavailable" in unavailable_reasons
    _, substituted_reasons = _closed_candidate_proposal_v2(
        "candidate:accept",
        proposal=proposal,
        claims=(_root("evaluation:authoritative"),),
    )
    assert "invalid:claim_substitution" in substituted_reasons
    _, global_reasons = _closed_candidate_proposals_v2(
        manifest=decision_fixture.context.manifest,
        proposals=(proposal,),
        authoritative_subjects=(
            ("candidate:accept", _root("evaluation:claim")),
            ("candidate:accept", _root("evaluation:other-claim")),
        ),
    )
    assert "safety:subject_claim_conflict" in global_reasons


def test_evaluation_evidence_and_global_reason_totality() -> None:
    proposal = CommitDecisionCandidateProposalV2(
        candidate_ref="candidate:accept",
        claim_root=_root("evaluation:evidence:claim"),
        evidence=(),
    )
    assert _candidate_evidence_v2(
        proposal,
        evidence=None,
        current_step=4,
    ) == (None, None, "unavailable")
    projection = SimpleNamespace(records=(), projection_root=_root("projection"))
    evaluated = SimpleNamespace(
        projection_root=_root("other-projection"),
        candidate_ref=proposal.candidate_ref,
        claim_root=proposal.claim_root,
        replayed_record_roots=(),
    )
    assert _candidate_evidence_v2(
        proposal,
        evidence=cast(Any, (projection, evaluated)),
        current_step=4,
    ) == (None, None, "unbound")
    with pytest.raises(TypeError, match="evaluations must be exact"):
        _evidence_by_candidate_v2(set())
    with pytest.raises(TypeError, match="is malformed"):
        _evidence_by_candidate_v2((object(),))
    with pytest.raises(TypeError, match="is invalid"):
        _evidence_by_candidate_v2(((object(), object()),))

    missing = _global_reasons(
        has_proposals=False,
        has_eligible=False,
        unique=False,
        margin=0,
        minimum_margin=2,
        stop_clear=True,
        permission_allowed=True,
        stop=cast(Any, object()),
        permission=cast(Any, object()),
        stop_dependencies_current=True,
        permission_dependencies_current=True,
        current_step=4,
    )
    assert "input:candidates_missing" in missing
    margin = _global_reasons(
        has_proposals=True,
        has_eligible=True,
        unique=True,
        margin=1,
        minimum_margin=2,
        stop_clear=True,
        permission_allowed=True,
        stop=cast(Any, object()),
        permission=cast(Any, object()),
        stop_dependencies_current=True,
        permission_dependencies_current=True,
        current_step=4,
    )
    assert margin == ("leader:margin_insufficient",)


@pytest.mark.parametrize(
    "status, expected",
    [
        (_status(reasons=("invalid:binding",)), CommitDecisionOutcomeKindV2.INVALID),
        (
            _status(reasons=("safety:conflict",)),
            CommitDecisionOutcomeKindV2.SAFETY_VIOLATION,
        ),
        (
            _status(reasons=("stop:blocked",), stop_clear=False),
            CommitDecisionOutcomeKindV2.BLOCKED,
        ),
        (
            _status(reasons=("evidence:not_current",), evidence_current=False),
            CommitDecisionOutcomeKindV2.FINALITY_UNAVAILABLE,
        ),
    ],
)
def test_reducer_gate_status_priority_is_total(
    status: CommitDecisionGateStatusV2,
    expected: CommitDecisionOutcomeKindV2,
) -> None:
    assert _gate_status_outcome(status) is expected


@pytest.mark.parametrize(
    "assessment, sealed, expected",
    [
        (
            replace(
                _assessment(),
                reason_codes=("invalid:binding",),
                assessment_root="",
            ),
            False,
            CommitDecisionOutcomeKindV2.INVALID,
        ),
        (
            _assessment(_metric(score=0, reasons=("safety:equivocation",))),
            False,
            CommitDecisionOutcomeKindV2.SAFETY_VIOLATION,
        ),
        (
            replace(_assessment(), stop_clear=False, assessment_root=""),
            False,
            CommitDecisionOutcomeKindV2.BLOCKED,
        ),
        (
            _assessment(),
            True,
            CommitDecisionOutcomeKindV2.FINALITY_UNAVAILABLE,
        ),
        (
            _assessment(),
            False,
            CommitDecisionOutcomeKindV2.SAFE_FALLBACK,
        ),
    ],
)
def test_deadline_outcome_normalizes_every_terminal_priority(
    decision_fixture: _Fixture,
    assessment: CommitAssessmentV2,
    sealed: bool,
    expected: CommitDecisionOutcomeKindV2,
) -> None:
    policy = decision_fixture.context.manifest.collective_commit_policy
    assert policy is not None
    outcome = _deadline_outcome(
        decision_fixture.snapshot.evidence_deadline_step,
        policy=policy,
        parent=decision_fixture.snapshot,
        assessment=assessment,
        window=decision_fixture.snapshot.window,
        dependency_root=_root("deadline:dependency"),
        sealed=sealed,
    )
    assert outcome is not None
    assert outcome.kind is expected


def test_reducer_support_context_parent_and_projection_guards(
    decision_fixture: _Fixture,
) -> None:
    request = decision_fixture.request
    manifest = decision_fixture.context.manifest
    protocol_substitution = replace(
        request,
        protocol_ref="protocol:substituted",
        stream_ref="",
        transition_id="",
        request_root="",
    )
    with pytest.raises(ValueError, match="protocol identity"):
        _validate_request_context(
            protocol_substitution,
            manifest,
            PROFILE,
            None,
        )
    non_initialize = _successor_request(
        request,
        command=CommitDecisionCommandV2.EXPLICIT_UNSEAL,
        step=5,
        suffix="genesis-command",
    )
    with pytest.raises(ValueError, match="genesis command"):
        _validate_request_context(non_initialize, manifest, PROFILE, None)
    earlier = _successor_request(
        request,
        command=CommitDecisionCommandV2.EVALUATE,
        step=3,
        suffix="earlier-successor",
    )
    with pytest.raises(ValueError, match="successor context"):
        _validate_request_context(earlier, manifest, PROFILE, decision_fixture.snapshot)
    wrong_epoch = replace(
        non_initialize,
        observed_epoch=2,
        request_root="",
    )
    with pytest.raises(ValueError, match="epoch changed"):
        _validate_request_context(
            wrong_epoch,
            manifest,
            PROFILE,
            decision_fixture.snapshot,
        )

    dependency = decision_fixture.snapshot.dependencies[0]
    wrong_dependency = replace(
        dependency,
        snapshot_root=_root("wrong:parent:snapshot"),
        dependency_root="",
    )
    with pytest.raises(ValueError, match="parent dependency"):
        _validate_parent_dependency(
            decision_fixture.snapshot,
            (wrong_dependency,),
        )
    with pytest.raises(ValueError, match="finality projection"):
        _validate_finality_projection(
            cast(Any, object()),
            cast(Any, object()),
            assurance=CommitAssurance.EVIDENCE_BOUND,
            seal_transition_id="transition:seal",
            step=4,
        )
    with pytest.raises(ValueError, match="seal inclusion"):
        _validate_seal_inclusion(
            cast(Any, object()),
            decision_fixture.snapshot,
        )
    with pytest.raises(TypeError, match="progress phase"):
        _progress(
            parent=None,
            phase=cast(CommitDecisionPhaseV2, object()),
            current_step=4,
            evidence_deadline=5,
            finality_deadline=6,
            window=decision_fixture.snapshot.window,
            dependency_root=_root("progress:dependency"),
            next_inputs=(),
            unmet=(),
        )


def test_reducer_entry_and_evaluation_guards(
    decision_fixture: _Fixture,
) -> None:
    manifest = decision_fixture.context.manifest
    with pytest.raises(TypeError, match="exact request"):
        reduce_commit_decision_v2(
            cast(Any, object()),
            manifest=manifest,
            profile=PROFILE,
            dependencies=(),
            source_context_root=_root("reducer:source"),
            parent=None,
            assessment=None,
            required_stability_steps=1,
        )
    with pytest.raises(TypeError, match="exact manifest"):
        reduce_commit_decision_v2(
            decision_fixture.request,
            manifest=cast(Any, object()),
            profile=PROFILE,
            dependencies=(),
            source_context_root=_root("reducer:source"),
            parent=None,
            assessment=None,
            required_stability_steps=1,
        )
    with pytest.raises(ValueError, match="exact commit policy"):
        reduce_commit_decision_v2(
            decision_fixture.request,
            manifest=replace(manifest, collective_commit_policy=None),
            profile=PROFILE,
            dependencies=decision_fixture.snapshot.dependencies,
            source_context_root=_root("reducer:source"),
            parent=None,
            assessment=None,
            required_stability_steps=1,
        )
    with pytest.raises(ValueError, match="terminal state is sticky"):
        reduce_commit_decision_v2(
            decision_fixture.request,
            manifest=manifest,
            profile=PROFILE,
            dependencies=decision_fixture.snapshot.dependencies,
            source_context_root=_root("reducer:source"),
            parent=cast(Any, SimpleNamespace(outcome=object())),
            assessment=None,
            required_stability_steps=1,
        )
    policy = manifest.collective_commit_policy
    assert isinstance(policy, CollectiveCommitPolicy)
    with pytest.raises(ValueError, match="only its parent"):
        _initialize(
            decision_fixture.request,
            manifest=manifest,
            profile=PROFILE,
            dependencies=(
                decision_fixture.snapshot.dependencies[0],
                replace(
                    decision_fixture.snapshot.dependencies[0],
                    role=CommitDecisionDependencyRoleV2.EVIDENCE,
                    stream_ref="authority:evidence",
                    dependency_root="",
                ),
            ),
            dependency_root=_root("reducer:dependency"),
            source_context_root=_root("reducer:source"),
            required_stability_steps=1,
        )

    successor = _successor_request(
        decision_fixture.request,
        command=CommitDecisionCommandV2.EVALUATE,
        step=5,
        suffix="assessment-guards",
    )
    with pytest.raises(ValueError, match="same-step assessment"):
        _evaluate(
            successor,
            policy=policy,
            parent=decision_fixture.snapshot,
            dependencies=decision_fixture.snapshot.dependencies,
            dependency_root=_root("reducer:dependency"),
            source_context_root=_root("reducer:source"),
            assessment=_assessment(),
            required_stability_steps=1,
            verified_finality=None,
            verified_seal_inclusion=None,
            current_gate_status=None,
        )
    same_step = replace(_assessment(), current_step=5, assessment_root="")
    with pytest.raises(ValueError, match="assessment dependencies"):
        _evaluate(
            successor,
            policy=policy,
            parent=decision_fixture.snapshot,
            dependencies=decision_fixture.snapshot.dependencies,
            dependency_root=_root("reducer:dependency"),
            source_context_root=_root("reducer:source"),
            assessment=same_step,
            required_stability_steps=1,
            verified_finality=None,
            verified_seal_inclusion=None,
            current_gate_status=None,
        )
    with pytest.raises(ValueError, match="no missing dependency"):
        _missing_inputs_successor(
            successor,
            policy=policy,
            parent=decision_fixture.snapshot,
            dependencies=decision_fixture.snapshot.dependencies,
            dependency_root=_root("reducer:dependency"),
            source_context_root=_root("reducer:source"),
        )


def test_epoch_restart_exhaustion_before_and_at_deadline(
    decision_fixture: _Fixture,
) -> None:
    policy = decision_fixture.context.manifest.collective_commit_policy
    assert policy is not None
    parent_window = replace(
        decision_fixture.snapshot.window,
        remaining_epoch_restart_budget=0,
        window_root="",
    )
    parent = _snapshot_replace(decision_fixture.snapshot, window=parent_window)
    unavailable = _successor_request(
        decision_fixture.request,
        command=CommitDecisionCommandV2.EVALUATE,
        step=5,
        suffix="restart-unavailable",
    )
    with pytest.raises(ValueError, match="restart is not available"):
        _restart_epoch(
            unavailable,
            policy=policy,
            parent=parent,
            dependencies=parent.dependencies,
            dependency_root=parent.dependency_set_root,
            source_context_root=_root("restart:source"),
            required_stability_steps=1,
        )
    noncontiguous = _successor_request(
        decision_fixture.request,
        command=CommitDecisionCommandV2.EPOCH_RESTART,
        step=5,
        suffix="restart-noncontiguous",
        restart_epoch=2,
    )
    noncontiguous = replace(
        noncontiguous,
        observed_epoch=2,
        restart_epoch=3,
        request_root="",
    )
    with pytest.raises(ValueError, match="restart is not contiguous"):
        _restart_epoch(
            noncontiguous,
            policy=policy,
            parent=parent,
            dependencies=parent.dependencies,
            dependency_root=parent.dependency_set_root,
            source_context_root=_root("restart:source"),
            required_stability_steps=1,
        )
    before = _successor_request(
        decision_fixture.request,
        command=CommitDecisionCommandV2.EPOCH_RESTART,
        step=5,
        suffix="restart-exhausted-before",
        restart_epoch=2,
    )
    assert (
        _restart_epoch(
            before,
            policy=policy,
            parent=parent,
            dependencies=parent.dependencies,
            dependency_root=parent.dependency_set_root,
            source_context_root=_root("restart:source:before"),
            required_stability_steps=1,
        ).outcome
        is None
    )
    deadline = _successor_request(
        decision_fixture.request,
        command=CommitDecisionCommandV2.EPOCH_RESTART,
        step=parent.evidence_deadline_step,
        suffix="restart-exhausted-deadline",
        restart_epoch=2,
    )
    assert (
        _restart_epoch(
            deadline,
            policy=policy,
            parent=parent,
            dependencies=parent.dependencies,
            dependency_root=parent.dependency_set_root,
            source_context_root=_root("restart:source:deadline"),
            required_stability_steps=1,
        ).outcome
        is not None
    )


def test_explicit_unseal_before_and_at_deadline(
    sealed_fixture: _SealedFixture,
) -> None:
    parent = sealed_fixture.sealed_state.snapshot
    policy = sealed_fixture.context.manifest.collective_commit_policy
    assert policy is not None
    dependencies = cast(
        tuple[CommitDecisionDependencyV2, ...],
        object.__getattribute__(sealed_fixture.seal_source, "_dependencies"),
    )
    dependency_root = parent.dependency_set_root
    before = _successor_request(
        sealed_fixture.seal_request,
        command=CommitDecisionCommandV2.EXPLICIT_UNSEAL,
        step=parent.current_step + 1,
        suffix="unseal-before",
    )
    assert (
        _explicit_unseal(
            before,
            policy=policy,
            parent=parent,
            dependencies=dependencies,
            dependency_root=dependency_root,
            source_context_root=_root("unseal:before"),
        ).seal
        is None
    )
    deadline = _successor_request(
        sealed_fixture.seal_request,
        command=CommitDecisionCommandV2.EXPLICIT_UNSEAL,
        step=parent.finality_deadline_step,
        suffix="unseal-deadline",
    )
    assert (
        _explicit_unseal(
            deadline,
            policy=policy,
            parent=parent,
            dependencies=dependencies,
            dependency_root=dependency_root,
            source_context_root=_root("unseal:deadline"),
        ).outcome
        is not None
    )


def test_seal_reducer_same_step_dependency_deadline_and_output_guards(
    sealed_fixture: _SealedFixture,
) -> None:
    parent = sealed_fixture.ready_state.snapshot
    policy = sealed_fixture.context.manifest.collective_commit_policy
    assert policy is not None
    dependencies = cast(
        tuple[CommitDecisionDependencyV2, ...],
        object.__getattribute__(sealed_fixture.seal_source, "_dependencies"),
    )
    dependency_root = cast(
        CommitAssessmentV2,
        object.__getattribute__(sealed_fixture.seal_source, "_assessment"),
    ).dependency_set_root
    assessment = cast(
        CommitAssessmentV2,
        object.__getattribute__(sealed_fixture.seal_source, "_assessment"),
    )
    with pytest.raises(ValueError, match="same-step assessment"):
        _seal_commit_decision_v2(
            sealed_fixture.seal_request,
            policy=policy,
            parent=parent,
            dependencies=dependencies,
            dependency_root=dependency_root,
            source_context_root=_root("seal:source"),
            assessment=None,
        )
    with pytest.raises(ValueError, match="assessment dependencies"):
        _seal_commit_decision_v2(
            sealed_fixture.seal_request,
            policy=policy,
            parent=parent,
            dependencies=dependencies,
            dependency_root=_root("seal:wrong-dependency"),
            source_context_root=_root("seal:source"),
            assessment=assessment,
        )
    deadline_request = _successor_request(
        sealed_fixture.seal_request,
        command=CommitDecisionCommandV2.SEAL,
        step=parent.evidence_deadline_step,
        suffix="seal-deadline",
        output=sealed_fixture.output,
    )
    deadline_assessment = replace(
        assessment,
        current_step=parent.evidence_deadline_step,
        assessment_root="",
    )
    assert (
        _seal_commit_decision_v2(
            deadline_request,
            policy=policy,
            parent=parent,
            dependencies=dependencies,
            dependency_root=dependency_root,
            source_context_root=_root("seal:deadline"),
            assessment=deadline_assessment,
        ).outcome
        is not None
    )
    wrong_output = replace(
        sealed_fixture.output,
        candidate_ref="candidate:substituted",
        proposal_root="",
    )
    wrong_request = replace(
        sealed_fixture.seal_request,
        mutation_ref="mutation:commit-decision-v2:totality:wrong-output",
        output_proposal=wrong_output,
        transition_id="",
        request_root="",
    )
    with pytest.raises(ValueError, match="stable leader"):
        _seal_commit_decision_v2(
            wrong_request,
            policy=policy,
            parent=parent,
            dependencies=dependencies,
            dependency_root=dependency_root,
            source_context_root=_root("seal:wrong-output"),
            assessment=assessment,
        )
    changed_metric = replace(
        assessment.candidate_metrics[0],
        claim_root=_root("seal:changed-claim"),
        metrics_root="",
    )
    changed_assessment = replace(
        assessment,
        candidate_metrics=(changed_metric,),
        assessment_root="",
    )
    assert _same_stable_leader(parent, changed_assessment) is None


def test_sealed_reducer_priority_continuity_and_external_status_totality(
    sealed_fixture: _SealedFixture,
) -> None:
    parent = sealed_fixture.sealed_state.snapshot
    invalid = _same_step_terminal_priority(
        continuity_reason="invalid:frozen_dependency_changed",
        gate_status=_status(),
        finality=None,
    )
    assert invalid is not None and invalid[0] is CommitDecisionOutcomeKindV2.INVALID
    safety = _same_step_terminal_priority(
        continuity_reason="",
        gate_status=_status(),
        finality=cast(
            Any,
            SimpleNamespace(status=CommitFinalityStatusV2.CONFLICT),
        ),
    )
    assert safety is not None
    assert safety[0] is CommitDecisionOutcomeKindV2.SAFETY_VIOLATION
    blocked = _same_step_terminal_priority(
        continuity_reason="",
        gate_status=_status(reasons=("stop:blocked",), stop_clear=False),
        finality=None,
    )
    assert blocked is not None and blocked[0] is CommitDecisionOutcomeKindV2.BLOCKED
    assert (
        _continuity_failure(
            sealed_fixture.seal_request,
            parent,
            _root("sealed:wrong-frozen"),
        )
        == "invalid:frozen_dependency_changed"
    )
    certified_parent = SimpleNamespace(
        assurance=CommitAssurance.CERTIFIED,
        seal=parent.seal,
        current_step=parent.current_step,
    )
    gap_request = replace(
        sealed_fixture.seal_request,
        current_step=parent.current_step + 2,
        request_root="",
    )
    assert (
        _continuity_failure(
            gap_request,
            cast(Any, certified_parent),
            cast(CommitDecisionWindowSealV2, parent.seal).frozen_dependency_root,
        )
        == "invalid:heartbeat_step_gap"
    )
    assert (
        _external_finality_kind(
            cast(Any, SimpleNamespace(status=CommitFinalityStatusV2.VERIFIED))
        )
        is CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT
    )
    assert (
        _external_finality_kind(
            cast(Any, SimpleNamespace(status=CommitFinalityStatusV2.UNAVAILABLE))
        )
        is CommitDecisionOutcomeKindV2.FINALITY_UNAVAILABLE
    )


def test_sealed_reducer_rejects_missing_gate_and_evidence_inclusion(
    sealed_fixture: _SealedFixture,
) -> None:
    parent = sealed_fixture.sealed_state.snapshot
    dependencies = cast(
        tuple[CommitDecisionDependencyV2, ...],
        object.__getattribute__(sealed_fixture.seal_source, "_dependencies"),
    )
    with pytest.raises(ValueError, match="same-step current gates"):
        _evaluate_sealed_v2(
            sealed_fixture.seal_request,
            parent=parent,
            dependencies=dependencies,
            source_context_root=_root("sealed:source"),
            verified_finality=None,
            verified_seal_inclusion=None,
            current_gate_status=None,
        )
    with pytest.raises(ValueError, match="exact verified owner projection"):
        _validate_verified_finality_inputs(
            sealed_fixture.seal_request,
            parent=parent,
            verified_finality=cast(Any, object()),
            verified_seal_inclusion=None,
        )
    later = replace(
        sealed_fixture.seal_request,
        current_step=parent.current_step + 1,
        request_root="",
    )
    assert (
        _evidence_bound_terminal(
            later,
            parent=parent,
            dependencies=dependencies,
            frozen=cast(
                CommitDecisionWindowSealV2,
                parent.seal,
            ).frozen_dependency_root,
            source_context_root=_root("sealed:evidence:late"),
            inclusion=None,
        ).outcome
        is not None
    )
    with pytest.raises(ValueError, match="requires verified seal inclusion"):
        _evidence_bound_terminal(
            sealed_fixture.seal_request,
            parent=parent,
            dependencies=dependencies,
            frozen=cast(
                CommitDecisionWindowSealV2,
                parent.seal,
            ).frozen_dependency_root,
            source_context_root=_root("sealed:evidence:same-step"),
            inclusion=None,
        )


def test_seal_context_handle_and_inclusion_totality(
    decision_fixture: _Fixture,
    sealed_fixture: _SealedFixture,
) -> None:
    context = _verified_commit_decision_seal_context_v2(sealed_fixture.sealed_state)
    assert repr(context) == "<_VerifiedCommitDecisionSealContextV2 redacted>"
    assert copy(context) is context
    assert deepcopy(context) is context
    with pytest.raises(TypeError, match="cannot be constructed"):
        _VerifiedCommitDecisionSealContextV2()
    with pytest.raises(TypeError, match="final"):
        type("DerivedSealContext", (_VerifiedCommitDecisionSealContextV2,), {})
    with pytest.raises(AttributeError, match="immutable"):
        setattr(context, "_anchor_root", _root("seal:substituted"))
    with pytest.raises(TypeError, match="not portable"):
        context.__reduce__()
    with pytest.raises(TypeError, match="not portable"):
        context.__reduce_ex__(4)
    with pytest.raises(TypeError, match="not portable"):
        context.__getstate__()
    with pytest.raises(TypeError, match="wrong exact type"):
        _verified_commit_decision_seal_context_material_v2(object())
    incomplete = object.__new__(_VerifiedCommitDecisionSealContextV2)
    with pytest.raises(TypeError, match="incomplete"):
        _verified_commit_decision_seal_context_material_v2(incomplete)
    substituted = object.__new__(_VerifiedCommitDecisionSealContextV2)
    object.__setattr__(substituted, "_state", sealed_fixture.sealed_state)
    object.__setattr__(substituted, "_anchor_root", _root("seal:wrong-anchor"))
    with pytest.raises(ValueError, match="anchor is mismatched"):
        _verified_commit_decision_seal_context_material_v2(substituted)
    with pytest.raises(ValueError, match="current and non-terminal"):
        _verified_commit_decision_seal_context_v2(decision_fixture.state)
    with pytest.raises(TypeError, match="seal view is invalid"):
        _inclusion_v2(sealed_fixture.sealed_state.snapshot, object())
    view = decision_fixture.context.store.load_commit_view_v2(
        decision_fixture.request.scope_ref,
        decision_fixture.request.stream_ref,
        decision_fixture.request.transition_id,
    )
    with pytest.raises((TypeError, ValueError), match="view is invalid|unsealed"):
        _inclusion_v2(decision_fixture.snapshot, view)


def test_source_and_source_input_front_door_guards(
    decision_fixture: _Fixture,
    sealed_fixture: _SealedFixture,
) -> None:
    with pytest.raises(TypeError, match="exact authority domain"):
        prepare_commit_decision_initialize_v2(
            domain=cast(Any, object()),
            manifest=decision_fixture.context.manifest,
            profile=PROFILE,
            run_ref=RUN_REF,
            target_ref=TARGET,
            observed_epoch=1,
            mutation_ref="mutation:invalid-domain",
            current_step=1,
            mutation_issuer_ref="issuer",
        )
    with pytest.raises(TypeError, match="exact scoped manifest"):
        prepare_commit_decision_initialize_v2(
            domain=decision_fixture.context.domain,
            manifest=cast(Any, object()),
            profile=PROFILE,
            run_ref=RUN_REF,
            target_ref=TARGET,
            observed_epoch=1,
            mutation_ref="mutation:invalid-manifest",
            current_step=1,
            mutation_issuer_ref="issuer",
        )
    without_policy = replace(
        decision_fixture.context.manifest,
        collective_commit_policy=None,
    )
    with pytest.raises(ValueError, match="no commit policy"):
        prepare_commit_decision_initialize_v2(
            domain=decision_fixture.context.domain,
            manifest=without_policy,
            profile=PROFILE,
            run_ref=RUN_REF,
            target_ref=TARGET,
            observed_epoch=1,
            mutation_ref="mutation:no-policy",
            current_step=1,
            mutation_issuer_ref="issuer",
        )
    common = {
        "parent_state": decision_fixture.state,
        "profile": PROFILE,
        "mutation_ref": "mutation:invalid-successor",
        "current_step": 5,
        "mutation_issuer_ref": decision_fixture.context.grant.issuer_ref,
        "commit_replay_state": object(),
        "risk_state": object(),
        "membership_state": object(),
        "support_state": object(),
        "evidence_state": object(),
        "stop_state": object(),
        "permission_state": object(),
    }
    with pytest.raises(ValueError, match="cannot initialize"):
        prepare_commit_decision_successor_v2(
            manifest=decision_fixture.context.manifest,
            command=CommitDecisionCommandV2.INITIALIZE,
            **common,
        )
    with pytest.raises(TypeError, match="exact manifest"):
        prepare_commit_decision_successor_v2(
            manifest=cast(Any, object()),
            command=CommitDecisionCommandV2.EVALUATE,
            **common,
        )
    with pytest.raises(TypeError, match="exact manifest"):
        prepare_commit_decision_missing_inputs_v2(
            parent_state=decision_fixture.state,
            manifest=cast(Any, object()),
            profile=PROFILE,
            mutation_ref="mutation:missing:invalid-manifest",
            current_step=5,
            mutation_issuer_ref=decision_fixture.context.grant.issuer_ref,
        )
    with pytest.raises(ValueError, match="no missing dependency"):
        prepare_commit_decision_missing_inputs_v2(
            parent_state=sealed_fixture.sealed_state,
            manifest=sealed_fixture.context.manifest,
            profile=PROFILE,
            mutation_ref="mutation:missing:sealed",
            current_step=8,
            mutation_issuer_ref=sealed_fixture.context.grant.issuer_ref,
        )
    with pytest.raises(TypeError, match="verified parent state"):
        _current_parent_v2(object())
    assert _effective_candidate_proposals_v2(
        sealed_fixture.ready_state.snapshot,
        (),
    )
    with pytest.raises(ValueError, match="dependency head"):
        _require_same_precondition(
            cast(Any, SimpleNamespace(stream_ref="authority:missing")),
            {},
        )
    with pytest.raises(ValueError, match="gate context"):
        _validate_gate_context(
            SimpleNamespace(
                domain_root="wrong",
                scope_ref="wrong",
                manifest_root="wrong",
                commit_policy_root="wrong",
                profile="wrong",
                assurance=CommitAssurance.ADVISORY,
                protocol_ref="wrong",
                run_ref="wrong",
                target_ref="wrong",
            ),
            decision_fixture.snapshot,
            manifest=decision_fixture.context.manifest,
            profile=PROFILE,
        )


def test_source_input_evaluation_and_gate_status_totality(
    decision_fixture: _Fixture,
) -> None:
    false_material = SimpleNamespace(
        evidence_current=False,
        membership_current=True,
        verification_current=True,
    )
    assert (
        _evidence_evaluations_v2(
            cast(Any, object()),
            cast(Any, false_material),
        )
        == ()
    )
    conflict_material = SimpleNamespace(
        evidence_current=True,
        membership_current=True,
        verification_current=True,
        subject_conflicts=(SimpleNamespace(candidate_ref="candidate:accept"),),
        active_subjects=(("candidate:accept", _root("conflict:claim")),),
    )
    assert (
        _evidence_evaluations_v2(
            cast(Any, object()),
            cast(Any, conflict_material),
        )
        == ()
    )
    assessment = replace(
        _assessment(),
        replay_conflict_refs=(_root("replay:conflict"),),
        equivocation_refs=(_root("support:equivocation"),),
        assessment_root="",
    )
    risk = SimpleNamespace(
        assessment=SimpleNamespace(issued_at_step=1, expires_at_step=20)
    )
    membership = SimpleNamespace(issued_at_step=1, expires_at_step=20)
    evidence = SimpleNamespace(
        evidence_current=True,
        verification_current=True,
    )
    status = _gate_status_v2(
        decision_fixture.snapshot,
        assessment=assessment,
        risk=cast(Any, risk),
        membership=cast(Any, membership),
        evidence_material=cast(Any, evidence),
        current_step=4,
    )
    assert "invalid:replay_conflict" in status.reason_codes
    assert "safety:support_equivocation" in status.reason_codes
    sealed_parent = SimpleNamespace(
        seal=SimpleNamespace(
            candidate_ref="candidate:sealed",
            claim_root=_root("sealed:missing-metric"),
        )
    )
    missing = _gate_status_v2(
        cast(Any, sealed_parent),
        assessment=_assessment(),
        risk=cast(Any, risk),
        membership=cast(Any, membership),
        evidence_material=cast(Any, evidence),
        current_step=4,
    )
    assert "invalid:sealed_candidate_assessment_missing" in missing.reason_codes


def test_state_record_pure_successor_binding_and_head_guards(
    decision_fixture: _Fixture,
) -> None:
    request = decision_fixture.request
    view = decision_fixture.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    committed = view.committed_transition
    assert committed is not None
    transition = committed.batch.transition
    assert transition is not None
    state_records = cast(dict[str, object], transition.state_records)
    binding = cast(dict[str, object], state_records["session_binding"])
    wrong_binding = {**binding, "request_ref": "mutation:substituted"}
    with pytest.raises(ValueError, match="session binding"):
        _validate_session_binding(wrong_binding, request)
    invalid_grant = {**binding, "grant_ref": ""}
    with pytest.raises(ValueError, match="grant binding"):
        _validate_session_binding(invalid_grant, request)

    with pytest.raises(ValueError, match="successor parent lineage"):
        _validate_successor(
            cast(
                Any,
                SimpleNamespace(
                    parent_revision=99,
                    parent_transition_id="transition:wrong",
                    parent_snapshot_root=_root("wrong-parent"),
                    parent_history_root=_root("wrong-history"),
                    parent_history_count=99,
                    history_count=100,
                ),
            ),
            decision_fixture.snapshot,
        )
    parent = decision_fixture.snapshot
    fixed_child = SimpleNamespace(
        parent_revision=parent.revision,
        parent_transition_id=parent.transition_id,
        parent_snapshot_root=parent.snapshot_root,
        parent_history_root=parent.history_root,
        parent_history_count=parent.history_count,
        history_count=parent.history_count + 1,
        domain_root=parent.domain_root,
        scope_ref="scope:fixed-substitution",
        protocol_ref=parent.protocol_ref,
        run_ref=parent.run_ref,
        target_ref=parent.target_ref,
        profile=parent.profile,
        assurance=parent.assurance,
        manifest_root=parent.manifest_root,
        commit_policy_root=parent.commit_policy_root,
        stream_ref=parent.stream_ref,
        initialized_at_step=parent.initialized_at_step,
        evidence_deadline_step=parent.evidence_deadline_step,
        finality_deadline_step=parent.finality_deadline_step,
        current_step=parent.current_step,
    )
    with pytest.raises(ValueError, match="fixed context"):
        _validate_successor(cast(Any, fixed_child), parent)
    terminal_parent = SimpleNamespace(outcome=object())
    child = SimpleNamespace(
        parent_revision=1,
        parent_transition_id="transition:parent",
        parent_snapshot_root=_root("parent:snapshot"),
        parent_history_root=_root("parent:history"),
        parent_history_count=1,
        history_count=2,
        domain_root=_root("domain"),
        scope_ref="scope",
        protocol_ref="protocol",
        run_ref="run",
        target_ref="target",
        profile="profile",
        assurance=CommitAssurance.ADVISORY,
        manifest_root=_root("manifest"),
        commit_policy_root=_root("policy"),
        stream_ref="stream",
        initialized_at_step=1,
        evidence_deadline_step=5,
        finality_deadline_step=8,
        current_step=2,
    )
    for name, value in vars(child).items():
        setattr(terminal_parent, name, value)
    terminal_parent.revision = 1
    terminal_parent.transition_id = "transition:parent"
    terminal_parent.snapshot_root = _root("parent:snapshot")
    terminal_parent.history_root = _root("parent:history")
    terminal_parent.history_count = 1
    terminal_parent.current_step = 1
    with pytest.raises(ValueError, match="terminal state"):
        _validate_successor(cast(Any, child), cast(Any, terminal_parent))
    noncommitted = decision_fixture.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        "transition:commit-decision-v2:missing",
    )
    with pytest.raises(ValueError, match="no committed transition"):
        _head_from_view_v2(noncommitted, decision_fixture.context.domain)


def test_finality_input_unsealed_assurance_and_observation_reader_guards(
    decision_fixture: _Fixture,
    sealed_fixture: _SealedFixture,
) -> None:
    with pytest.raises(ValueError, match="requires a sealed decision"):
        _optional_verified_finality_input_v2(
            object(),
            parent_state=decision_fixture.state,
            parent=decision_fixture.snapshot,
            current_step=4,
        )
    with pytest.raises(ValueError, match="cannot satisfy this assurance"):
        _optional_verified_finality_input_v2(
            object(),
            parent_state=sealed_fixture.sealed_state,
            parent=sealed_fixture.sealed_state.snapshot,
            current_step=7,
        )
    parent = sealed_fixture.sealed_state.snapshot
    owner = CommitFinalityOwnerV2.CERTIFICATE
    role = CommitDecisionDependencyRoleV2.CERTIFICATE
    with pytest.raises(TypeError, match="parent StateReader"):
        _observed_finality_input_v2(
            SimpleNamespace(
                _reader=object(),
                _domain=sealed_fixture.context.domain,
            ),
            parent=parent,
            owner=owner,
            role=role,
        )
    with pytest.raises(TypeError, match="parent domain"):
        _observed_finality_input_v2(
            SimpleNamespace(
                _reader=_ReaderStub(),
                _domain=object(),
            ),
            parent=parent,
            owner=owner,
            role=role,
        )
    with pytest.raises(ValueError, match="head is unavailable"):
        _observed_finality_input_v2(
            SimpleNamespace(
                _reader=_ReaderStub(fail_head=True),
                _domain=sealed_fixture.context.domain,
            ),
            parent=parent,
            owner=owner,
            role=role,
        )
    with pytest.raises(TypeError, match="head is invalid"):
        _observed_finality_input_v2(
            SimpleNamespace(
                _reader=_ReaderStub(head=object()),
                _domain=sealed_fixture.context.domain,
            ),
            parent=parent,
            owner=owner,
            role=role,
        )
    cross_head = GovernanceHeadV2.genesis(
        sealed_fixture.context.domain,
        "authority:cross-bound-finality-owner",
    )
    with pytest.raises(ValueError, match="head is cross-bound"):
        _observed_finality_input_v2(
            SimpleNamespace(
                _reader=_ReaderStub(head=cross_head),
                _domain=sealed_fixture.context.domain,
            ),
            parent=parent,
            owner=owner,
            role=role,
        )


def test_finality_committed_owner_view_and_snapshot_restriction_guards(
    decision_fixture: _Fixture,
) -> None:
    domain = decision_fixture.context.domain
    request = decision_fixture.request
    valid_view = decision_fixture.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    valid_head = _head_from_view_v2(valid_view, domain)
    with pytest.raises(ValueError, match="view is unavailable"):
        _committed_owner_observation_v2(
            cast(Any, _ReaderStub(fail_view=True)),
            domain=domain,
            head=valid_head,
        )
    with pytest.raises(TypeError, match="view is invalid"):
        _committed_owner_observation_v2(
            cast(Any, _ReaderStub(view=object())),
            domain=domain,
            head=valid_head,
        )
    missing_view = decision_fixture.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        "transition:finality-owner:missing",
    )
    with pytest.raises(ValueError, match="view is not committed"):
        _committed_owner_observation_v2(
            cast(Any, _ReaderStub(view=missing_view)),
            domain=domain,
            head=valid_head,
        )
    genesis_head = GovernanceHeadV2.genesis(domain, request.stream_ref)
    with pytest.raises(ValueError, match="not the current head"):
        _committed_owner_observation_v2(
            cast(Any, _ReaderStub(view=valid_view)),
            domain=domain,
            head=genesis_head,
        )

    with pytest.raises(TypeError, match="state records are invalid"):
        _restricted_owner_snapshot_root_v2(
            object(),
            domain=domain,
            head=valid_head,
        )
    with pytest.raises(ValueError, match="state records are incomplete"):
        _restricted_owner_snapshot_root_v2(
            {},
            domain=domain,
            head=valid_head,
        )
    state = {
        "schema": "owner-state",
        "domain_root": domain.domain_root,
        "scope_ref": valid_head.scope_ref,
        "stream_ref": valid_head.stream_ref,
        "transition_id": valid_head.transition_id,
        "snapshot_root": _root("owner:snapshot"),
        "snapshot": object(),
    }
    with pytest.raises(TypeError, match="snapshot record is invalid"):
        _restricted_owner_snapshot_root_v2(
            state,
            domain=domain,
            head=valid_head,
        )
    with pytest.raises(ValueError, match="snapshot binding is incomplete"):
        _restricted_owner_snapshot_root_v2(
            {**state, "snapshot": {}},
            domain=domain,
            head=valid_head,
        )
    cross_snapshot = {
        "domain_root": _root("owner:cross-domain"),
        "scope_ref": valid_head.scope_ref,
        "stream_ref": valid_head.stream_ref,
        "transition_id": valid_head.transition_id,
        "revision": valid_head.revision,
        "snapshot_root": state["snapshot_root"],
    }
    with pytest.raises(ValueError, match="snapshot is cross-bound"):
        _restricted_owner_snapshot_root_v2(
            {**state, "snapshot": cross_snapshot},
            domain=domain,
            head=valid_head,
        )


def test_genesis_input_policy_manifest_reader_and_owner_guards(
    decision_fixture: _Fixture,
) -> None:
    manifest = decision_fixture.context.manifest
    with pytest.raises(ValueError, match="no commit policy"):
        _canonical_genesis_inputs_v2(
            parent_state=decision_fixture.state,
            manifest=replace(manifest, collective_commit_policy=None),
            profile=PROFILE,
        )
    with pytest.raises(ValueError, match="manifest is mismatched"):
        _canonical_genesis_inputs_v2(
            parent_state=decision_fixture.state,
            manifest=manifest,
            profile="profile:substituted",
        )
    invalid_reader_state = _clone_state(decision_fixture.state)
    object.__setattr__(
        invalid_reader_state,
        "_reader",
        _InvalidUpstreamHeadReader(decision_fixture.context.store),
    )
    with pytest.raises(TypeError, match="dependency head is invalid"):
        _canonical_genesis_inputs_v2(
            parent_state=invalid_reader_state,
            manifest=manifest,
            profile=PROFILE,
        )
    dependency = decision_fixture.snapshot.dependencies[0]
    with pytest.raises(ValueError, match="no longer at genesis"):
        _genesis_dependency_v2(
            dependency.role,
            dependency.stream_ref,
            dependency.snapshot_root,
            domain=decision_fixture.context.domain,
            observed=cast(Any, object()),
        )
    with pytest.raises(ValueError, match="omits its request"):
        _current_request_payload_v2(
            cast(Any, _ReaderStub(state={})),
            decision_fixture.request.scope_ref,
            "authority:missing-request",
        )
    with pytest.raises(ValueError, match="role is unsupported"):
        _rehydrate_current_owner_v2(
            cast(CommitDecisionDependencyRoleV2, object()),
            {},
            domain=decision_fixture.context.domain,
            reader=decision_fixture.context.store,
        )
    with pytest.raises(ValueError, match="context is mismatched"):
        _validate_committed_context_v2(
            SimpleNamespace(
                domain_root="wrong",
                scope_ref="wrong",
                manifest_root="wrong",
                commit_policy_root="wrong",
                profile="wrong",
                assurance=CommitAssurance.ADVISORY,
                protocol_ref="wrong",
                run_ref="wrong",
                target_ref="wrong",
                stream_ref="wrong",
            ),
            stream_ref="authority:expected",
            parent=decision_fixture.snapshot,
            manifest=manifest,
            profile=PROFILE,
            assurance=decision_fixture.snapshot.assurance,
        )


def test_trace_event_and_seal_inclusion_totality(
    decision_fixture: _Fixture,
    sealed_fixture: _SealedFixture,
) -> None:
    request = decision_fixture.request
    snapshot = decision_fixture.snapshot
    view = decision_fixture.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    committed = view.committed_transition
    assert committed is not None
    transition = committed.batch.transition
    assert transition is not None
    binding = cast(dict[str, object], transition.state_records["session_binding"])
    no_event = SimpleNamespace(
        **{item.name: getattr(snapshot, item.name) for item in fields(snapshot)}
    )
    no_event.mutation_kind = CommitDecisionMutationKindV2.HEARTBEAT
    no_event.assessment = None
    no_event.progress = None
    no_event.outcome = None
    with pytest.raises(ValueError, match="no applicable Trace event"):
        _commit_decision_events_v2(
            request,
            cast(Any, no_event),
            binding,
            parent_head_root=committed.receipt.parent_root,
            read_set_root=committed.batch.read_set.root(),
        )
    with pytest.raises(TypeError, match="session binding is invalid"):
        _base_lineage(
            request,
            snapshot,
            cast(Any, object()),
            parent_head_root=committed.receipt.parent_root,
            read_set_root=committed.batch.read_set.root(),
        )
    material = _verified_commit_decision_seal_context_material_v2(
        _verified_commit_decision_seal_context_v2(sealed_fixture.sealed_state)
    )
    with pytest.raises(ValueError, match="schema is unsupported"):
        replace(
            material.seal_inclusion,
            schema="unsupported",
            projection_root="",
        )


def test_operation_session_parent_dependency_and_reconciliation_totality(
    decision_fixture: _Fixture,
) -> None:
    context = decision_fixture.context
    request = decision_fixture.request
    capability = _capability(context, request.observed_epoch)
    wrong_issuer = replace(
        request,
        mutation_issuer_ref="issuer:substituted",
        request_root="",
    )
    with pytest.raises(Exception, match="authority_binding_mismatch"):
        open_commit_decision_authority_session_v2(capability, wrong_issuer)
    session = open_commit_decision_authority_session_v2(capability, request)
    rejected_state, rejected = _validated_session(object(), request)
    assert rejected_state is None
    assert rejected is not None
    other_request = replace(
        request,
        mutation_ref="mutation:session-substitution",
        transition_id="",
        request_root="",
    )
    mismatched_state, mismatched = _validated_session(session, other_request)
    assert mismatched_state is None
    assert mismatched is not None
    session_state, session_failure = _validated_session(session, request)
    assert session_state is not None
    assert session_failure is None

    with pytest.raises(TypeError, match="exact request"):
        _require_operation_request(object())
    missing_parent = _load_current_parent(
        cast(Any, _ReaderStub(fail_head=True)),
        context.domain,
        request,
        source=decision_fixture.source,
    )
    assert not isinstance(missing_parent, tuple)
    invalid_parent = _load_current_parent(
        cast(Any, _ReaderStub(head=object())),
        context.domain,
        request,
        source=decision_fixture.source,
    )
    assert not isinstance(invalid_parent, tuple)

    missing_view = context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        "transition:operation:missing",
    )
    assert _parent_view_failure(request, missing_view) is not None
    assert not _committed_view_matches(
        missing_view,
        request,
        session_state,
    )

    parent_head = context.store.load_head_v2(request.scope_ref, request.stream_ref)
    dependency = decision_fixture.snapshot.dependencies[0]
    external = replace(
        dependency,
        role=CommitDecisionDependencyRoleV2.EVIDENCE,
        stream_ref="authority:operation:external",
        dependency_root="",
    )
    unavailable_dependencies = _load_dependency_heads(
        cast(Any, _ReaderStub(fail_head=True)),
        context.domain,
        request,
        (external,),
        parent_head=parent_head,
    )
    assert not isinstance(unavailable_dependencies, tuple)
    invalid_dependencies = _load_dependency_heads(
        cast(Any, _ReaderStub(head=object())),
        context.domain,
        request,
        (external,),
        parent_head=parent_head,
    )
    assert not isinstance(invalid_dependencies, tuple)


def test_candidate_metric_authority_binding_reasons_are_total(
    sealed_fixture: _SealedFixture,
) -> None:
    manifest = sealed_fixture.context.manifest
    policy = manifest.collective_commit_policy
    assert policy is not None
    declared = {
        item.id: item for item in manifest.candidates if item.target == policy.target
    }
    risk = cast(Any, sealed_fixture.inputs[1]).snapshot
    membership = sealed_fixture.inputs[2]
    support = sealed_fixture.inputs[3]
    stop = cast(Any, sealed_fixture.inputs[5]).snapshot
    permission = cast(Any, sealed_fixture.inputs[6]).snapshot
    common = {
        "preset_reasons": (),
        "manifest": manifest,
        "current_step": 7,
        "epoch": 1,
        "declared": declared,
        "risk": risk,
        "membership_state": membership,
        "support_state": support,
        "stop": stop,
        "permission": permission,
    }

    undeclared = CommitDecisionCandidateProposalV2(
        candidate_ref="candidate:undeclared",
        claim_root=_root("candidate:undeclared:claim"),
        evidence=(),
    )
    metric, _ = _candidate_metrics(
        undeclared,
        evidence=None,
        **common,
    )
    assert {
        "invalid:undeclared_candidate",
        "input:evidence_unavailable",
        "invalid:permission_claim_unbound",
        "invalid:permission_candidate_unbound",
    }.issubset(metric.reason_codes)

    fallback = CommitDecisionCandidateProposalV2(
        candidate_ref="candidate:safe_fallback",
        claim_root=sealed_fixture.proposal.claim_root,
        evidence=(),
    )
    fallback_metric, _ = _candidate_metrics(
        fallback,
        evidence=None,
        **common,
    )
    assert "invalid:safe_fallback_not_substantive" in fallback_metric.reason_codes

    projection = SimpleNamespace(records=(), projection_root=_root("projection"))
    evaluated = SimpleNamespace(
        projection_root=_root("other-projection"),
        candidate_ref=sealed_fixture.proposal.candidate_ref,
        claim_root=sealed_fixture.proposal.claim_root,
        replayed_record_roots=(),
    )
    unbound_metric, _ = _candidate_metrics(
        sealed_fixture.proposal,
        evidence=cast(Any, (projection, evaluated)),
        **common,
    )
    assert "invalid:evidence_projection_unbound" in unbound_metric.reason_codes


def test_verified_finality_owner_stream_step_and_assurance_guards(
    sealed_fixture: _SealedFixture,
) -> None:
    parent = sealed_fixture.sealed_state.snapshot
    certified_parent = SimpleNamespace(
        seal=parent.seal,
        assurance=CommitAssurance.CERTIFIED,
        scope_ref=parent.scope_ref,
        protocol_ref=parent.protocol_ref,
        run_ref=parent.run_ref,
        target_ref=parent.target_ref,
    )

    for projection, message in (
        (
            _finality_projection(
                parent,
                owner=CommitFinalityOwnerV2.DISTRIBUTED,
            ),
            "owner cannot satisfy",
        ),
        (
            _finality_projection(
                parent,
                stream_ref="authority:finality:noncanonical",
            ),
            "stream is not canonical",
        ),
        (
            _finality_projection(parent, verified_at_step=9),
            "not from the current step",
        ),
    ):
        verified = _issue_verified_commit_finality_input_v2(
            projection=projection,
            owner_precondition=GovernanceReadPreconditionV2(
                stream_ref=projection.stream_ref,
                expected_revision=projection.revision,
                expected_root=projection.head_root,
            ),
            owner_receipt_root=projection.receipt_root,
            owner_inclusion_root=_root("finality:totality:inclusion"),
        )
        with pytest.raises(ValueError, match=message):
            _optional_verified_finality_input_v2(
                verified,
                parent_state=sealed_fixture.sealed_state,
                parent=cast(Any, certified_parent),
                current_step=8,
            )

    projection = _finality_projection(parent)
    portable_request = SimpleNamespace(
        finality_projection=projection,
        current_step=projection.verified_at_step,
    )
    with pytest.raises(ValueError, match="assurance rejects external finality"):
        _validate_verified_finality_inputs(
            cast(Any, portable_request),
            parent=parent,
            verified_finality=projection,
            verified_seal_inclusion=None,
        )
    with pytest.raises(ValueError, match="requires verified seal inclusion"):
        _validate_verified_finality_inputs(
            cast(Any, portable_request),
            parent=cast(
                Any,
                SimpleNamespace(
                    assurance=CommitAssurance.CERTIFIED,
                    seal=parent.seal,
                ),
            ),
            verified_finality=projection,
            verified_seal_inclusion=None,
        )
    assert (
        _external_finality_kind(
            _finality_projection(
                parent,
                status=CommitFinalityStatusV2.CONFLICT,
            )
        )
        is None
    )


def test_operation_reducer_source_and_read_set_remaining_branches(
    decision_fixture: _Fixture,
    sealed_fixture: _SealedFixture,
) -> None:
    invalid_attempt = advance_commit_decision_v2(
        decision_fixture.request,
        source=decision_fixture.source,
        authority_session=object(),
    )
    assert invalid_attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED

    no_failure_view = SimpleNamespace(
        disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        failure=None,
    )
    assert (
        _parent_view_failure(
            decision_fixture.request,
            cast(Any, no_failure_view),
        )
        is not None
    )

    policy = decision_fixture.context.manifest.collective_commit_policy
    assert policy is not None
    with pytest.raises(ValueError, match="requires a seal"):
        _explicit_unseal(
            _successor_request(
                decision_fixture.request,
                command=CommitDecisionCommandV2.EXPLICIT_UNSEAL,
                step=5,
                suffix="unsealed-parent",
            ),
            policy=policy,
            parent=decision_fixture.snapshot,
            dependencies=decision_fixture.snapshot.dependencies,
            dependency_root=_root("explicit-unseal:dependency"),
            source_context_root=_root("explicit-unseal:context"),
        )

    with pytest.raises(ValueError, match="parent is not current"):
        _current_parent_v2(sealed_fixture.ready_state)
    with pytest.raises(ValueError, match="committed parent is mismatched"):
        verify_commit_decision_request_source_v2(
            sealed_fixture.seal_request,
            source=sealed_fixture.seal_source,
            committed_parent_snapshot=decision_fixture.snapshot,
        )

    precondition = GovernanceReadPreconditionV2(
        stream_ref="authority:duplicate-read",
        expected_revision=1,
        expected_root=_root("duplicate-read"),
    )
    duplicate_view = SimpleNamespace(
        committed_transition=SimpleNamespace(
            batch=SimpleNamespace(
                read_set=SimpleNamespace(entries=(precondition, precondition))
            )
        )
    )
    with pytest.raises(ValueError, match="duplicate streams"):
        _validate_read_set(
            cast(Any, duplicate_view),
            cast(Any, SimpleNamespace(dependencies=(), scope_ref="scope")),
            {},
        )


def test_state_handle_stale_forged_and_missing_view_paths(
    sealed_fixture: _SealedFixture,
) -> None:
    with pytest.raises(Exception, match="governance_read_set_stale"):
        require_current_commit_decision_state_v2(sealed_fixture.ready_state)
    assert (
        require_current_commit_decision_state_v2(
            sealed_fixture.sealed_state
        ).snapshot_root
        == sealed_fixture.sealed_state.snapshot.snapshot_root
    )
    incomplete = object.__new__(VerifiedCommitDecisionStateV2)
    with pytest.raises(Exception, match="authority_binding_mismatch"):
        _verified_state_view_v2(incomplete)
    invalid_request = _clone_state(sealed_fixture.sealed_state)
    object.__setattr__(invalid_request, "_request", object())
    with pytest.raises(Exception, match="authority_binding_mismatch"):
        _verified_state_view_v2(invalid_request)
    missing = _clone_state(sealed_fixture.sealed_state)
    request = object.__getattribute__(missing, "_request")
    missing_request = replace(
        request,
        mutation_ref="mutation:state-handle:missing",
        transition_id="",
        request_root="",
    )
    object.__setattr__(missing, "_request", missing_request)
    with pytest.raises(Exception, match="committed_transition_invalid"):
        _verified_state_view_v2(missing)


def test_state_record_decoder_read_set_and_history_guards(
    decision_fixture: _Fixture,
    sealed_fixture: _SealedFixture,
) -> None:
    request = decision_fixture.request
    missing_view = decision_fixture.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        "transition:state-record:missing",
    )
    with pytest.raises(ValueError, match="view is not committed"):
        _decode_committed_decision_view_v2(
            missing_view,
            decision_fixture.context.domain,
            reader=None,
        )
    valid_view = decision_fixture.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    with pytest.raises(ValueError, match="state domain is mismatched"):
        _decode_committed_decision_view_v2(
            valid_view,
            sealed_fixture.context.domain,
            reader=None,
        )
    committed = valid_view.committed_transition
    assert committed is not None
    transition = committed.batch.transition
    assert transition is not None
    binding = cast(dict[str, object], transition.state_records["session_binding"])
    mismatched_snapshot = SimpleNamespace(
        dependencies=(),
        scope_ref=decision_fixture.snapshot.scope_ref,
    )
    with pytest.raises(ValueError, match="read set is mismatched"):
        _validate_read_set(
            valid_view,
            cast(Any, mismatched_snapshot),
            binding,
        )
    with pytest.raises(ValueError, match="historical parent is unavailable"):
        _validate_history(
            cast(Any, _ReaderStub(fail_view=True)),
            sealed_fixture.context.domain,
            sealed_fixture.sealed_state.snapshot,
        )


def test_rehydrate_rejects_wrong_domain_reader_request_and_scope(
    decision_fixture: _Fixture,
) -> None:
    with pytest.raises(TypeError, match="exact authority domain"):
        rehydrate_commit_decision_state_v2(
            decision_fixture.request,
            domain=cast(Any, object()),
            state_reader=decision_fixture.context.store,
        )
    with pytest.raises(TypeError, match="StateReader"):
        rehydrate_commit_decision_state_v2(
            decision_fixture.request,
            domain=decision_fixture.context.domain,
            state_reader=cast(Any, object()),
        )
    with pytest.raises(TypeError, match="exact request"):
        rehydrate_commit_decision_state_v2(
            object(),
            domain=decision_fixture.context.domain,
            state_reader=decision_fixture.context.store,
        )
    cross_scope = replace(
        decision_fixture.request,
        domain_root=_root("cross-domain"),
        request_root="",
    )
    with pytest.raises(Exception, match="authority_scope_mismatch"):
        rehydrate_commit_decision_state_v2(
            cross_scope,
            domain=decision_fixture.context.domain,
            state_reader=decision_fixture.context.store,
        )


def test_snapshot_contract_constants_remain_bound_to_records() -> None:
    assert COMMIT_CANDIDATE_METRICS_SCHEMA_V2.startswith("pheroos-")
    assert COMMIT_DECISION_ASSESSMENT_SCHEMA_V2.startswith("pheroos-")
    assert COMMIT_DECISION_CANDIDATE_PROPOSAL_SCHEMA_V2.startswith("pheroos-")
    assert COMMIT_DECISION_EVIDENCE_PROPOSAL_SCHEMA_V2.startswith("pheroos-")
    assert COMMIT_DECISION_GATE_STATUS_SCHEMA_V2.startswith("pheroos-")
    assert COMMIT_DECISION_OUTCOME_SCHEMA_V2.startswith("pheroos-")
    assert COMMIT_DECISION_OUTPUT_PROPOSAL_SCHEMA_V2.startswith("pheroos-")
    assert COMMIT_DECISION_PROGRESS_SCHEMA_V2.startswith("pheroos-")
    assert COMMIT_DECISION_REQUEST_SCHEMA_V2.startswith("pheroos-")
    assert COMMIT_DECISION_SEAL_SCHEMA_V2.startswith("pheroos-")
    assert COMMIT_DECISION_SNAPSHOT_SCHEMA_V2.startswith("pheroos-")
    assert COMMIT_DECISION_STATE_SCHEMA_V2.startswith("pheroos-")


def test_changed_json_and_payload_shape_guards_are_fault_injection_safe(
    sealed_fixture: _SealedFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seal = sealed_fixture.sealed_state.snapshot.seal
    assert seal is not None
    with monkeypatch.context() as patcher:
        patcher.setattr(
            decision_common_module, "_preflight_resource", lambda _value: None
        )
        with pytest.raises(TypeError, match="non-string key"):
            decision_common_module._freeze_json({1: "value"})
        with pytest.raises(TypeError, match="non-portable value"):
            decision_common_module._freeze_json(object())

    with monkeypatch.context() as patcher:
        patcher.setattr(decision_liveness_module, "_freeze_json", lambda _value: None)
        with pytest.raises(TypeError, match="output payload must be an object"):
            replace(seal, output_payload={}, seal_root="")

    with monkeypatch.context() as patcher:
        patcher.setattr(decision_proposals_module, "_freeze_json", lambda _value: None)
        with pytest.raises(TypeError, match="output payload must be an object"):
            replace(
                sealed_fixture.output,
                payload={},
                payload_root="",
                proposal_root="",
            )


def test_changed_evaluation_guards_reject_policy_and_duplicate_claim_faults(
    sealed_fixture: _SealedFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = replace(
        sealed_fixture.context.manifest,
        collective_commit_policy=None,
    )
    risk = cast(Any, sealed_fixture.inputs[1]).snapshot
    membership = sealed_fixture.inputs[2]
    support = sealed_fixture.inputs[3]
    stop = cast(Any, sealed_fixture.inputs[5]).snapshot
    permission = cast(Any, sealed_fixture.inputs[6]).snapshot
    monkeypatch.setattr(
        decision_evaluation_module,
        "evaluate_support_v2",
        lambda **_kwargs: SimpleNamespace(
            active_support_cluster_count=0,
            support_ratio_ppm=0,
        ),
    )
    with pytest.raises(ValueError, match="manifest has no commit policy"):
        _candidate_metrics(
            sealed_fixture.proposal,
            evidence=None,
            preset_reasons=(),
            manifest=manifest,
            current_step=7,
            epoch=1,
            declared={},
            risk=risk,
            membership_state=membership,
            support_state=support,
            stop=stop,
            permission=permission,
        )

    projection = object.__new__(CommitEvidenceProjectionV2)
    object.__setattr__(projection, "projection_root", _root("duplicate:projection"))
    evaluated = object.__new__(CommitEvidenceEvaluationV2)
    object.__setattr__(evaluated, "projection_root", projection.projection_root)
    object.__setattr__(evaluated, "candidate_ref", "candidate:duplicate")
    object.__setattr__(evaluated, "claim_root", _root("duplicate:claim"))
    with pytest.raises(ValueError, match="repeats a candidate claim"):
        _evidence_by_candidate_v2(((projection, evaluated), (projection, evaluated)))


def test_changed_reducer_dispatch_and_deadline_guards(
    decision_fixture: _Fixture,
    sealed_fixture: _SealedFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = decision_fixture.context.manifest.collective_commit_policy
    assert policy is not None
    successor = _successor_request(
        decision_fixture.request,
        command=CommitDecisionCommandV2.EVALUATE,
        step=5,
        suffix="missing-parent-closure",
    )
    with monkeypatch.context() as patcher:
        patcher.setattr(
            decision_reducer_module,
            "_validate_request_context",
            lambda *_args, **_kwargs: None,
        )
        with pytest.raises(ValueError, match="requires a committed parent"):
            reduce_commit_decision_v2(
                successor,
                manifest=decision_fixture.context.manifest,
                profile=PROFILE,
                dependencies=decision_fixture.snapshot.dependencies,
                source_context_root=_root("missing-parent:context"),
                parent=None,
                assessment=None,
                required_stability_steps=1,
            )

    sealed_parent = sealed_fixture.sealed_state.snapshot
    explicit = _successor_request(
        sealed_fixture.seal_request,
        command=CommitDecisionCommandV2.EXPLICIT_UNSEAL,
        step=8,
        suffix="explicit-unseal-closure",
    )
    explicit_dependencies = tuple(
        replace(
            dependency,
            revision=sealed_parent.revision,
            transition_id=sealed_parent.transition_id,
            snapshot_root=sealed_parent.snapshot_root,
            dependency_root="",
        )
        if dependency.role is CommitDecisionDependencyRoleV2.PARENT
        else dependency
        for dependency in cast(
            tuple[CommitDecisionDependencyV2, ...],
            object.__getattribute__(sealed_fixture.seal_source, "_dependencies"),
        )
    )
    explicit_snapshot = reduce_commit_decision_v2(
        explicit,
        manifest=sealed_fixture.context.manifest,
        profile=PROFILE,
        dependencies=explicit_dependencies,
        source_context_root=_root("explicit-unseal:closure"),
        parent=sealed_parent,
        assessment=None,
        required_stability_steps=1,
    )
    assert explicit_snapshot.mutation_kind is CommitDecisionMutationKindV2.WINDOW_RESET
    assert explicit_snapshot.seal is None

    reversed_window = replace(
        policy.commit_window,
        deliberation_deadline_steps=10,
        run_deadline_steps=1,
    )
    reversed_policy = replace(policy, commit_window=reversed_window)
    reversed_manifest = replace(
        decision_fixture.context.manifest,
        collective_commit_policy=reversed_policy,
    )
    with pytest.raises(ValueError, match="deadlines are not ordered"):
        _initialize(
            decision_fixture.request,
            manifest=reversed_manifest,
            profile=PROFILE,
            dependencies=decision_fixture.snapshot.dependencies,
            dependency_root=decision_fixture.snapshot.dependency_set_root,
            source_context_root=_root("reversed-deadline:context"),
            required_stability_steps=1,
        )


def test_changed_snapshot_and_missing_input_size_guards(
    sealed_fixture: _SealedFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sealed_snapshot = sealed_fixture.sealed_state.snapshot
    monkeypatch.setattr(
        decision_snapshot_module,
        "MAX_COMMIT_DECISION_SNAPSHOT_BYTES_V2",
        1,
    )
    with pytest.raises(ValueError, match="snapshot exceeds its byte bound"):
        _snapshot_replace(sealed_snapshot)

    monkeypatch.setattr(
        decision_source_module,
        "_canonical_genesis_inputs_v2",
        lambda **_kwargs: (
            sealed_fixture.context.domain,
            sealed_snapshot,
            sealed_snapshot.dependencies,
        ),
    )
    with pytest.raises(ValueError, match="sealed decision"):
        prepare_commit_decision_missing_inputs_v2(
            parent_state=sealed_fixture.sealed_state,
            manifest=sealed_fixture.context.manifest,
            profile=PROFILE,
            mutation_ref="mutation:sealed-missing-input:closure",
            current_step=8,
            mutation_issuer_ref=sealed_fixture.context.grant.issuer_ref,
        )


def test_changed_source_input_policy_domain_gate_and_context_guards(
    decision_fixture: _Fixture,
    sealed_fixture: _SealedFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_without_policy = replace(
        decision_fixture.context.manifest,
        collective_commit_policy=None,
    )
    with pytest.raises(ValueError, match="manifest has no commit policy"):
        _collect_commit_decision_inputs_v2(
            parent_state=decision_fixture.state,
            manifest=manifest_without_policy,
            profile=PROFILE,
            current_step=5,
            proposals=(),
            commit_replay_state=object(),
            risk_state=object(),
            membership_state=object(),
            support_state=object(),
            evidence_state=object(),
            stop_state=object(),
            permission_state=object(),
        )

    request = decision_fixture.request
    view = decision_fixture.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    invalid_domain_state = _clone_state(decision_fixture.state)
    object.__setattr__(invalid_domain_state, "_domain", object())
    monkeypatch.setattr(
        decision_source_inputs_module,
        "_verified_decision_view_v2",
        lambda _state: (request, decision_fixture.snapshot, view),
    )
    with pytest.raises(TypeError, match="parent domain is invalid"):
        _current_parent_v2(invalid_domain_state)

    monkeypatch.setattr(
        decision_source_inputs_module,
        "require_current_commit_stop_state_v2",
        lambda _state: object(),
    )
    with pytest.raises(TypeError, match="wrong exact type"):
        _current_gate_v2(
            object(),
            role=CommitDecisionDependencyRoleV2.STOP,
            expected_type=type(cast(Any, sealed_fixture.inputs[5]).snapshot),
        )

    stop_snapshot = cast(Any, sealed_fixture.inputs[5]).snapshot
    monkeypatch.setattr(
        decision_source_inputs_module,
        "require_current_commit_stop_state_v2",
        lambda _state: stop_snapshot,
    )
    monkeypatch.setattr(
        decision_source_inputs_module,
        "_verified_gate_view_v2",
        lambda _state: (object(), SimpleNamespace(committed_transition=None)),
    )
    with pytest.raises(ValueError, match="has no committed receipt"):
        _current_gate_v2(
            object(),
            role=CommitDecisionDependencyRoleV2.STOP,
            expected_type=type(stop_snapshot),
        )

    material = SimpleNamespace(
        evidence_current=True,
        membership_current=True,
        verification_current=True,
        subject_conflicts=(),
        active_subjects=(("candidate:accept", _root("context-drift:claim")),),
        context_root=_root("context-drift:expected"),
    )
    monkeypatch.setattr(
        decision_source_inputs_module,
        "_verified_commit_evidence_assessment_v2",
        lambda *_args, **_kwargs: (
            SimpleNamespace(
                context_root=_root("context-drift:observed"),
                projection=object(),
            ),
            object(),
        ),
    )
    with pytest.raises(ValueError, match="context changed during assessment"):
        _evidence_evaluations_v2(object(), cast(Any, material))


def test_changed_finality_owner_genesis_and_transition_guards(
    decision_fixture: _Fixture,
    sealed_fixture: _SealedFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = sealed_fixture.sealed_state.snapshot
    domain = sealed_fixture.context.domain
    owner = CommitFinalityOwnerV2.CERTIFICATE
    role = CommitDecisionDependencyRoleV2.CERTIFICATE
    stream_ref = commit_finality_owner_stream_ref_v2(
        owner,
        parent.scope_ref,
        parent.protocol_ref,
        parent.run_ref,
        parent.target_ref,
    )
    genesis = GovernanceHeadV2.genesis(domain, stream_ref)
    malformed_genesis = copy(genesis)
    object.__setattr__(
        malformed_genesis,
        "state_root",
        _root("malformed-finality-genesis"),
    )
    with monkeypatch.context() as patcher:
        patcher.setattr(
            decision_finality_inputs_module.GovernanceHeadV2,
            "from_dict",
            classmethod(lambda _cls, _payload: malformed_genesis),
        )
        with pytest.raises(ValueError, match="genesis head is invalid"):
            _observed_finality_input_v2(
                SimpleNamespace(
                    _reader=_ReaderStub(head=genesis),
                    _domain=domain,
                ),
                parent=parent,
                owner=owner,
                role=role,
            )

    request = decision_fixture.request
    view = decision_fixture.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    head = _head_from_view_v2(view, decision_fixture.context.domain)
    committed = copy(view.committed_transition)
    assert committed is not None
    batch = copy(committed.batch)
    object.__setattr__(batch, "transition", None)
    object.__setattr__(committed, "batch", batch)
    canonical = SimpleNamespace(
        disposition=view.disposition,
        committed_transition=committed,
        position_observation=view.position_observation,
        domain_root=view.domain_root,
        scope_ref=view.scope_ref,
        stream_ref=view.stream_ref,
        transition_id=view.transition_id,
        observed_revision=view.observed_revision,
        observed_head_root=view.observed_head_root,
    )
    monkeypatch.setattr(
        decision_finality_inputs_module.GovernanceCommitViewV2,
        "from_dict",
        classmethod(lambda _cls, _payload: canonical),
    )
    with pytest.raises(ValueError, match="has no state transition"):
        _committed_owner_observation_v2(
            cast(Any, _ReaderStub(view=view)),
            domain=decision_fixture.context.domain,
            head=head,
        )


def test_changed_genesis_reader_and_committed_dependency_guards(
    decision_fixture: _Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain = decision_fixture.context.domain
    parent = decision_fixture.snapshot
    parent_dependency = parent.dependencies[0]
    monkeypatch.setattr(
        decision_genesis_inputs_module,
        "_current_parent_v2",
        lambda _state: (domain, parent, parent_dependency),
    )
    with pytest.raises(TypeError, match="parent StateReader is invalid"):
        _canonical_genesis_inputs_v2(
            parent_state=SimpleNamespace(_reader=object()),
            manifest=decision_fixture.context.manifest,
            profile=PROFILE,
        )

    stream_ref = "authority:changed-committed-dependency"
    state = SimpleNamespace(
        receipt_root=_root("changed-dependency:receipt"),
        stream_ref=stream_ref,
    )
    snapshot = SimpleNamespace(
        revision=1,
        transition_id="transition:changed-dependency",
        snapshot_root=_root("changed-dependency:snapshot"),
    )
    monkeypatch.setattr(
        decision_genesis_inputs_module,
        "_current_request_payload_v2",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        decision_genesis_inputs_module,
        "_rehydrate_current_owner_v2",
        lambda *_args, **_kwargs: (state, snapshot),
    )
    monkeypatch.setattr(
        decision_genesis_inputs_module,
        "_validate_committed_context_v2",
        lambda *_args, **_kwargs: None,
    )
    policy = decision_fixture.context.manifest.collective_commit_policy
    assert policy is not None
    kwargs = {
        "domain": domain,
        "parent": parent,
        "manifest": decision_fixture.context.manifest,
        "profile": PROFILE,
        "assurance": CommitAssurance(policy.assurance),
    }
    with pytest.raises(TypeError, match="dependency head is invalid"):
        decision_genesis_inputs_module._committed_dependency_v2(
            CommitDecisionDependencyRoleV2.EVIDENCE,
            stream_ref,
            reader=cast(Any, _ReaderStub(head=object())),
            **kwargs,
        )

    stale_head = GovernanceHeadV2.genesis(domain, stream_ref)
    with pytest.raises(ValueError, match="dependency is not current"):
        decision_genesis_inputs_module._committed_dependency_v2(
            CommitDecisionDependencyRoleV2.EVIDENCE,
            stream_ref,
            reader=cast(Any, _ReaderStub(head=stale_head)),
            **kwargs,
        )


def test_changed_seal_context_domain_reader_and_lineage_guards(
    sealed_fixture: _SealedFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = sealed_fixture.sealed_state
    snapshot = state.snapshot
    request = object.__getattribute__(state, "_request")
    view = sealed_fixture.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    monkeypatch.setattr(
        decision_seal_context_module,
        "_verified_state_view_v2",
        lambda _state: (request, snapshot, view),
    )

    invalid_domain = _clone_state(state)
    object.__setattr__(invalid_domain, "_domain", object())
    with pytest.raises(TypeError, match="seal domain is invalid"):
        decision_seal_context_module._seal_material_v2(invalid_domain)

    invalid_reader = _clone_state(state)
    object.__setattr__(invalid_reader, "_reader", object())
    with pytest.raises(TypeError, match="seal reader is invalid"):
        decision_seal_context_module._seal_material_v2(invalid_reader)

    current = SimpleNamespace(seal_root=_root("seal:current"))
    historical = SimpleNamespace(seal_root=_root("seal:historical"))
    inclusions = iter((current, historical))
    with monkeypatch.context() as patcher:
        patcher.setattr(
            decision_seal_context_module,
            "_inclusion_v2",
            lambda *_args, **_kwargs: next(inclusions),
        )
        patcher.setattr(
            decision_seal_context_module,
            "_sealed_transition_v2",
            lambda *_args, **_kwargs: (snapshot, view),
        )
        with pytest.raises(ValueError, match="current seal lineage is mismatched"):
            decision_seal_context_module._seal_material_v2(state)

    unavailable = SimpleNamespace(
        mutation_kind=CommitDecisionMutationKindV2.HEARTBEAT,
        parent_revision=0,
    )
    with pytest.raises(ValueError, match="seal transition is unavailable"):
        decision_seal_context_module._sealed_transition_v2(
            unavailable,
            object(),
            domain=sealed_fixture.context.domain,
            reader=cast(Any, _ReaderStub()),
        )

    changed = SimpleNamespace(
        mutation_kind=CommitDecisionMutationKindV2.HEARTBEAT,
        parent_revision=1,
        parent_transition_id="transition:parent",
        scope_ref=snapshot.scope_ref,
        stream_ref=snapshot.stream_ref,
        seal=snapshot.seal,
    )
    parent = SimpleNamespace(
        mutation_kind=CommitDecisionMutationKindV2.SEALED,
        seal=None,
    )
    monkeypatch.setattr(
        decision_seal_context_module,
        "_canonical_commit_view_v2",
        lambda value: value,
    )
    monkeypatch.setattr(
        decision_seal_context_module,
        "_decode_committed_decision_view_v2",
        lambda *_args, **_kwargs: (object(), parent, object()),
    )
    monkeypatch.setattr(
        decision_seal_context_module,
        "_validate_successor",
        lambda *_args, **_kwargs: None,
    )
    with pytest.raises(ValueError, match="seal lineage changed"):
        decision_seal_context_module._sealed_transition_v2(
            changed,
            object(),
            domain=sealed_fixture.context.domain,
            reader=cast(Any, _ReaderStub(view=object())),
        )


def test_changed_operation_session_and_source_failure_paths(
    decision_fixture: _Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = decision_fixture.request
    session = open_commit_decision_authority_session_v2(
        _capability(decision_fixture.context, request.observed_epoch),
        request,
    )
    injected = (
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        "/injected-precondition",
    )

    for failed_helper in (
        "_current_session_grant_failure",
        "_current_session_lifecycle_failure",
    ):
        with monkeypatch.context() as patcher:
            patcher.setattr(
                decision_operations_module,
                "_reconcile",
                lambda *_args, **_kwargs: None,
            )
            patcher.setattr(
                decision_operations_module,
                failed_helper,
                lambda _session: injected,
            )
            attempt = advance_commit_decision_v2(
                request,
                source=decision_fixture.source,
                authority_session=session,
            )
            assert attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED
            assert attempt.failure is not None
            assert attempt.failure.code is injected[0]

    with monkeypatch.context() as patcher:
        patcher.setattr(
            decision_operations_module,
            "_require_store",
            lambda _store: (_ for _ in ()).throw(TypeError("injected store failure")),
        )
        validated, failure = _validated_session(session, request)
        assert validated is None
        assert failure is not None
        assert failure.failure is not None
        assert (
            failure.failure.code
            is AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH
        )

    with monkeypatch.context() as patcher:
        patcher.setattr(
            decision_operations_module,
            "_reconcile",
            lambda *_args, **_kwargs: None,
        )
        patcher.setattr(
            decision_operations_module,
            "_current_session_grant_failure",
            lambda _session: None,
        )
        patcher.setattr(
            decision_operations_module,
            "_current_session_lifecycle_failure",
            lambda _session: None,
        )
        patcher.setattr(
            decision_operations_module,
            "_load_current_parent",
            lambda *_args, **_kwargs: (None, object()),
        )
        patcher.setattr(
            decision_operations_module,
            "verify_commit_decision_request_source_v2",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("injected source verifier failure")
            ),
        )
        attempt = advance_commit_decision_v2(
            request,
            source=decision_fixture.source,
            authority_session=session,
        )
        assert attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED
        assert attempt.failure is not None
        assert attempt.failure.path == "/source"


def test_changed_operation_parent_reconciliation_paths(
    sealed_fixture: _SealedFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = sealed_fixture.seal_request
    source = sealed_fixture.seal_source
    domain = sealed_fixture.context.domain
    parent_dependency = next(
        dependency
        for dependency in cast(
            tuple[CommitDecisionDependencyV2, ...],
            object.__getattribute__(source, "_dependencies"),
        )
        if dependency.role is CommitDecisionDependencyRoleV2.PARENT
    )
    view = sealed_fixture.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        parent_dependency.transition_id,
        expected_receipt_root=parent_dependency.receipt_root,
    )
    historical_head = _head_from_view_v2(view, domain)

    missing = _load_current_parent(
        cast(Any, _ReaderStub(head=historical_head, fail_view=True)),
        domain,
        request,
        source=source,
    )
    assert not isinstance(missing, tuple)
    assert missing.failure is not None
    assert missing.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE

    noncommitted = sealed_fixture.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        "transition:changed-parent:missing",
    )
    rejected = _load_current_parent(
        cast(Any, _ReaderStub(head=historical_head, view=noncommitted)),
        domain,
        request,
        source=source,
    )
    assert not isinstance(rejected, tuple)

    with monkeypatch.context() as patcher:
        current_view = copy(view)
        current_position = copy(view.position_observation)
        assert current_position is not None
        object.__setattr__(
            current_position,
            "position",
            GovernanceCommitPositionV2.CURRENT,
        )
        object.__setattr__(current_view, "position_observation", current_position)
        patcher.setattr(
            decision_operations_module,
            "_canonical_commit_view_v2",
            lambda _view: current_view,
        )
        patcher.setattr(
            decision_operations_module,
            "_decode_committed_decision_view_v2",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                ValueError("injected committed view failure")
            ),
        )
        malformed = _load_current_parent(
            cast(Any, _ReaderStub(head=historical_head, view=view)),
            domain,
            request,
            source=source,
        )
        assert not isinstance(malformed, tuple)
        assert malformed.failure is not None
        assert (
            malformed.failure.code
            is AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
        )

    ready_snapshot = sealed_fixture.ready_state.snapshot
    with monkeypatch.context() as patcher:
        patcher.setattr(
            decision_operations_module,
            "_decode_committed_decision_view_v2",
            lambda *_args, **_kwargs: (
                request,
                SimpleNamespace(
                    revision=ready_snapshot.revision + 1,
                    transition_id=ready_snapshot.transition_id,
                    snapshot_root=ready_snapshot.snapshot_root,
                ),
                {},
            ),
        )
        stale = _load_current_parent(
            cast(Any, _ReaderStub(head=historical_head, view=view)),
            domain,
            request,
            source=source,
        )
        assert not isinstance(stale, tuple)
        assert stale.failure is not None
        assert stale.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE

    with monkeypatch.context() as patcher:
        patcher.setattr(
            decision_operations_module,
            "_canonical_commit_view_v2",
            lambda _view: current_view,
        )
        patcher.setattr(
            decision_operations_module,
            "_decode_committed_decision_view_v2",
            lambda *_args, **_kwargs: (request, ready_snapshot, {}),
        )
        patcher.setattr(
            decision_operations_module,
            "_head_from_view_v2",
            lambda *_args, **_kwargs: GovernanceHeadV2.genesis(
                domain,
                "authority:changed-parent:detached",
            ),
        )
        stale = _load_current_parent(
            cast(Any, _ReaderStub(head=historical_head, view=view)),
            domain,
            request,
            source=source,
        )
        assert not isinstance(stale, tuple)
        assert stale.failure is not None
        assert stale.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE


def test_changed_state_handle_load_and_protocol_exception_paths(
    decision_fixture: _Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = decision_fixture.request
    domain = decision_fixture.context.domain
    with pytest.raises(Exception, match="governance_committed_transition_invalid"):
        decision_state_handle_module._load_verified_view_v2(
            cast(Any, _ReaderStub(fail_view=True)),
            domain,
            request,
            expected_receipt_root=None,
        )

    view = decision_fixture.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    other_request = replace(
        request,
        mutation_ref="mutation:changed-state-handle:mismatch",
        transition_id="",
        request_root="",
    )
    monkeypatch.setattr(
        decision_state_handle_module,
        "_decode_committed_decision_view_v2",
        lambda *_args, **_kwargs: (other_request, decision_fixture.snapshot, {}),
    )
    with pytest.raises(Exception, match="authority_binding_mismatch"):
        decision_state_handle_module._load_verified_view_v2(
            cast(Any, _ReaderStub(view=view)),
            domain,
            request,
            expected_receipt_root=None,
        )

    class _RaisingInstanceCheck(type):
        def __instancecheck__(cls, instance: object) -> bool:
            del cls, instance
            raise RuntimeError("injected protocol instance check failure")

    class _RaisingProtocol(metaclass=_RaisingInstanceCheck):
        pass

    monkeypatch.setattr(
        decision_state_handle_module,
        "GovernanceStateReaderV2",
        _RaisingProtocol,
    )
    with pytest.raises(TypeError, match="requires StateReader v2"):
        decision_state_handle_module._require_reader(object())


def test_changed_state_record_payload_receipt_trace_and_history_guards(
    decision_fixture: _Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = decision_fixture.request
    domain = decision_fixture.context.domain
    view = decision_fixture.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    committed = view.committed_transition
    assert committed is not None
    transition = committed.batch.transition
    assert transition is not None

    records = dict(transition.state_records)
    mismatched_records = {**records, "stream_ref": "authority:changed:mismatch"}
    payload_view = SimpleNamespace(
        disposition=view.disposition,
        committed_transition=SimpleNamespace(
            batch=SimpleNamespace(
                transition=SimpleNamespace(state_records=mismatched_records)
            )
        ),
        position_observation=view.position_observation,
    )
    with monkeypatch.context() as patcher:
        patcher.setattr(
            decision_state_records_module,
            "_canonical_commit_view_v2",
            lambda _view: payload_view,
        )
        with pytest.raises(ValueError, match="state payload is mismatched"):
            _decode_committed_decision_view_v2(payload_view, domain, reader=None)

    receipt = copy(committed.receipt)
    object.__setattr__(receipt, "stream_ref", "authority:changed:receipt")
    receipt_view = SimpleNamespace(
        disposition=view.disposition,
        committed_transition=SimpleNamespace(
            batch=SimpleNamespace(transition=SimpleNamespace(state_records=records)),
            receipt=receipt,
        ),
        position_observation=view.position_observation,
    )
    with monkeypatch.context() as patcher:
        patcher.setattr(
            decision_state_records_module,
            "_canonical_commit_view_v2",
            lambda _view: receipt_view,
        )
        with pytest.raises(ValueError, match="committed receipt is mismatched"):
            _decode_committed_decision_view_v2(receipt_view, domain, reader=None)

    with monkeypatch.context() as patcher:
        patcher.setattr(
            decision_state_records_module,
            "_commit_decision_events_v2",
            lambda *_args, **_kwargs: (),
        )
        with pytest.raises(ValueError, match="Trace lineage is mismatched"):
            _decode_committed_decision_view_v2(view, domain, reader=None)

    child = SimpleNamespace(
        transition_id="transition:changed-history:cycle",
        parent_revision=1,
        parent_transition_id="transition:changed-history:parent",
        scope_ref=request.scope_ref,
        stream_ref=request.stream_ref,
    )
    parent = SimpleNamespace(
        transition_id=child.transition_id,
        revision=1,
    )
    with monkeypatch.context() as patcher:
        patcher.setattr(
            decision_state_records_module,
            "_decode_committed_decision_view_v2",
            lambda *_args, **_kwargs: (object(), parent, {}),
        )
        patcher.setattr(
            decision_state_records_module,
            "_validate_successor",
            lambda *_args, **_kwargs: None,
        )
        with pytest.raises(ValueError, match="historical lineage is cyclic or gapped"):
            _validate_history(
                cast(Any, _ReaderStub(view=object())),
                domain,
                cast(Any, child),
            )
    assert COMMIT_DECISION_WINDOW_SCHEMA_V2.startswith("pheroos-")
    assert AUTHORITY_CANONICAL_VERSION_V2.startswith("pheroos-")
