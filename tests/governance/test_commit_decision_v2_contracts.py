from __future__ import annotations

import ast
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import pickle
from types import SimpleNamespace

import pytest

from pheroos.governance._commit_decision_v2.assessment_records import (
    CommitCandidateMetricsV2,
)
from pheroos.governance._commit_decision_v2.common import _saturating_future_step
from pheroos.governance._commit_decision_v2.dependencies import (
    CommitDecisionDependencyV2,
    commit_decision_frozen_dependency_root_v2,
)
from pheroos.governance._commit_decision_v2.enums import (
    CommitDecisionCommandV2,
    CommitDecisionDependencyRoleV2,
    CommitDecisionOutcomeKindV2,
)
from pheroos.governance._commit_decision_v2.evaluation import _select_leader_v2
from pheroos.governance._commit_decision_v2.gate_status import (
    CommitDecisionGateStatusV2,
)
from pheroos.governance._commit_decision_v2.liveness_records import (
    CommitDecisionOutcomeV2,
)
from pheroos.governance._commit_decision_v2.proposals import (
    CommitDecisionEvidenceProposalV2,
)
from pheroos.governance._commit_decision_v2.request import CommitDecisionRequestV2
from pheroos.governance._commit_decision_v2.reducer_support import (
    _gate_status_outcome,
)
from pheroos.governance._commit_decision_v2.snapshot import (
    commit_decision_stream_ref_v2,
    commit_decision_transition_id_v2,
)
from pheroos.governance._commit_certificate_v2.state_contracts import (
    COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2,
    commit_certificate_stream_ref_v2,
)
from pheroos.governance._distributed_v2.enums import DistributedLaneV2
from pheroos.governance._distributed_v2.state_contracts import (
    distributed_genesis_snapshot_root_v2,
    distributed_lane_stream_ref_v2,
)
from pheroos.governance._commit_finality_v2 import (
    CommitFinalityOwnerV2,
    CommitFinalityProjectionV2,
    CommitFinalityStatusV2,
    _issue_verified_commit_finality_input_v2,
    _verified_commit_finality_input_material_v2,
    commit_finality_owner_genesis_snapshot_root_v2,
    commit_finality_owner_stream_ref_v2,
)
from pheroos.governance.authority_store_v2 import GovernanceCommitPositionV2
from pheroos.protocol.authority_v2 import (
    MAX_AUTHORITY_REVISION_V2,
    GovernanceReadPreconditionV2,
)


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _metrics(
    candidate: str, *, score: int, reasons: tuple[str, ...]
) -> CommitCandidateMetricsV2:
    return CommitCandidateMetricsV2(
        candidate_ref=candidate,
        claim_root=_root(f"claim:{candidate}"),
        positive_evidence_count=1,
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


def test_fixed_selector_and_transition_exclude_mutable_authority_inputs() -> None:
    stream = commit_decision_stream_ref_v2(
        "scope:tenant", "protocol:optimal", "run:one", "target:answer"
    )
    assert stream == commit_decision_stream_ref_v2(
        "scope:tenant", "protocol:optimal", "run:one", "target:answer"
    )
    assert stream.startswith("authority:commit-decision-v2:")
    assert all(
        mutable not in stream
        for mutable in ("epoch", "issuer", "candidate", "manifest", "policy")
    )
    transition = commit_decision_transition_id_v2(stream, "mutation:one")
    assert transition.startswith("transition:commit-decision-v2:")
    assert transition != commit_decision_transition_id_v2(stream, "mutation:two")


def test_portable_proposal_can_only_select_a_qualified_record_root() -> None:
    proposal = CommitDecisionEvidenceProposalV2(
        qualified_record_root=_root("qualified:one")
    )
    assert set(proposal.to_dict()) == {
        "schema",
        "qualified_record_root",
        "proposal_root",
    }
    forged = proposal.to_dict()
    forged["positive_count"] = 100
    with pytest.raises(ValueError, match="fields"):
        CommitDecisionEvidenceProposalV2.from_dict(forged)


def test_bool_integer_and_nul_text_are_rejected_before_authority_io() -> None:
    with pytest.raises(ValueError, match="integer bound"):
        CommitDecisionDependencyV2(
            role=CommitDecisionDependencyRoleV2.EVIDENCE,
            stream_ref="authority:evidence",
            revision=True,  # type: ignore[arg-type]
            transition_id="transition:evidence",
            snapshot_root=_root("snapshot"),
            head_root=_root("head"),
            receipt_root=_root("receipt"),
            observed_position=GovernanceCommitPositionV2.CURRENT,
        )


def test_frozen_dependency_truth_includes_evidence_and_principal_verification() -> None:
    dependencies = tuple(
        CommitDecisionDependencyV2(
            role=role,
            stream_ref=f"authority:{role.value}",
            revision=1,
            transition_id=f"transition:{role.value}",
            snapshot_root=_root(f"snapshot:{role.value}"),
            head_root=_root(f"head:{role.value}"),
            receipt_root=_root(f"receipt:{role.value}"),
            observed_position=GovernanceCommitPositionV2.CURRENT,
        )
        for role in CommitDecisionDependencyRoleV2
    )
    baseline = commit_decision_frozen_dependency_root_v2(dependencies)
    excluded = {
        CommitDecisionDependencyRoleV2.PARENT,
        CommitDecisionDependencyRoleV2.CERTIFICATE,
        CommitDecisionDependencyRoleV2.DISTRIBUTED,
    }
    for role in CommitDecisionDependencyRoleV2:
        changed = tuple(
            replace(
                item,
                head_root=_root(f"changed:{role.value}"),
                dependency_root="",
            )
            if item.role is role
            else item
            for item in dependencies
        )
        observed = commit_decision_frozen_dependency_root_v2(changed)
        assert (observed == baseline) is (role in excluded)
    with pytest.raises(ValueError, match=r"U\+0000"):
        commit_decision_stream_ref_v2(
            "scope:bad\x00selector", "protocol", "run", "target"
        )


def test_command_request_has_no_derived_assessment_window_or_outcome_fields() -> None:
    request = CommitDecisionRequestV2(
        domain_root=_root("domain"),
        scope_ref="scope:one",
        protocol_ref="protocol:one",
        run_ref="run:one",
        target_ref="target:one",
        observed_epoch=1,
        mutation_ref="mutation:init",
        mutation_issuer_ref="issuer:one",
        command=CommitDecisionCommandV2.INITIALIZE,
        current_step=1,
        candidate_proposals=(),
        output_proposal=None,
        finality_projection=None,
        restart_epoch=None,
    )
    wire = request.to_dict()
    assert not {"assessment", "window", "progress", "outcome", "ready"}.intersection(
        wire
    )
    wire["outcome"] = "evidence_commit"
    with pytest.raises(ValueError, match="fields"):
        CommitDecisionRequestV2.from_dict(wire)


def test_epoch_restart_request_is_exactly_next_and_cannot_cross_max() -> None:
    base = dict(
        domain_root=_root("domain:restart"),
        scope_ref="scope:restart",
        protocol_ref="protocol:restart",
        run_ref="run:restart",
        target_ref="target:restart",
        observed_epoch=5,
        mutation_ref="mutation:restart",
        mutation_issuer_ref="issuer:restart",
        command=CommitDecisionCommandV2.EPOCH_RESTART,
        current_step=9,
        candidate_proposals=(),
        output_proposal=None,
        finality_projection=None,
        restart_epoch=6,
    )
    request = CommitDecisionRequestV2(**base)
    assert CommitDecisionRequestV2.from_dict(request.to_dict()).restart_epoch == 6
    for observed, restarted in (
        (5, 5),
        (5, 4),
        (5, 7),
        (MAX_AUTHORITY_REVISION_V2, MAX_AUTHORITY_REVISION_V2),
    ):
        with pytest.raises(ValueError, match="command fields"):
            CommitDecisionRequestV2(
                **{**base, "observed_epoch": observed, "restart_epoch": restarted}
            )
    with pytest.raises(ValueError, match="integer bound"):
        CommitDecisionRequestV2(**{**base, "restart_epoch": True})


def test_deadline_addition_saturates_and_rejects_nonrepresentable_or_bool_inputs() -> (
    None
):
    maximum = MAX_AUTHORITY_REVISION_V2
    assert _saturating_future_step(maximum - 2, maximum, "test deadline") == maximum
    assert _saturating_future_step(maximum - 1, maximum, "test deadline") == maximum
    with pytest.raises(ValueError, match="no representable future step"):
        _saturating_future_step(maximum, 1, "test deadline")
    for start, distance in ((True, 1), (1, True)):
        with pytest.raises(ValueError, match="integer bound"):
            _saturating_future_step(start, distance, "test deadline")


def test_finality_authority_is_exact_opaque_anchored_and_nonportable() -> None:
    head_root = _root("finality:head")
    receipt_root = _root("finality:receipt")
    projection = CommitFinalityProjectionV2(
        owner=CommitFinalityOwnerV2.CERTIFICATE,
        status=CommitFinalityStatusV2.VERIFIED,
        stream_ref="authority:certificate:scope:one",
        revision=2,
        transition_id="transition:certificate:two",
        snapshot_root=_root("finality:snapshot"),
        head_root=head_root,
        receipt_root=receipt_root,
        seal_transition_id="transition:commit-decision-v2:" + "1" * 64,
        seal_root=_root("finality:seal"),
        frozen_dependency_root=_root("finality:frozen"),
        verified_at_step=8,
        reason_codes=("certificate:verified",),
    )
    precondition = GovernanceReadPreconditionV2(
        stream_ref=projection.stream_ref,
        expected_revision=projection.revision,
        expected_root=head_root,
    )
    verified = _issue_verified_commit_finality_input_v2(
        projection=projection,
        owner_precondition=precondition,
        owner_receipt_root=receipt_root,
        owner_inclusion_root=_root("finality:inclusion"),
    )
    material = _verified_commit_finality_input_material_v2(verified)
    assert material.projection.to_dict() == projection.to_dict()
    assert material.owner_precondition.to_dict() == precondition.to_dict()
    assert material.input_root.startswith("sha256:")
    for forged in (
        projection,
        projection.to_dict(),
        SimpleNamespace(**projection.to_dict()),
    ):
        with pytest.raises(TypeError, match="wrong exact type"):
            _verified_commit_finality_input_material_v2(forged)
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(verified)
    with pytest.raises(ValueError, match="owner head"):
        _issue_verified_commit_finality_input_v2(
            projection=projection,
            owner_precondition=replace(
                precondition,
                expected_root=_root("finality:wrong-head"),
            ),
            owner_receipt_root=receipt_root,
            owner_inclusion_root=_root("finality:inclusion"),
        )


def test_neutral_finality_owner_identity_is_byte_equal_to_both_owners() -> None:
    selectors = ("scope:owner", "protocol:owner", "run:owner", "target:owner")
    assert commit_finality_owner_stream_ref_v2(
        CommitFinalityOwnerV2.CERTIFICATE, *selectors
    ) == commit_certificate_stream_ref_v2(*selectors)
    assert (
        commit_finality_owner_genesis_snapshot_root_v2(
            CommitFinalityOwnerV2.CERTIFICATE
        )
        == COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2
    )
    assert commit_finality_owner_stream_ref_v2(
        CommitFinalityOwnerV2.DISTRIBUTED, *selectors
    ) == distributed_lane_stream_ref_v2(*selectors, DistributedLaneV2.CERTIFICATE)
    assert commit_finality_owner_genesis_snapshot_root_v2(
        CommitFinalityOwnerV2.DISTRIBUTED
    ) == distributed_genesis_snapshot_root_v2(DistributedLaneV2.CERTIFICATE)


def test_authority_invalid_high_score_cannot_suppress_valid_leader() -> None:
    forged = _metrics(
        "candidate:forged",
        score=9_000_000,
        reasons=("invalid:evidence_projection_unbound",),
    )
    valid = _metrics("candidate:valid", score=10, reasons=())
    leader, ties, margin = _select_leader_v2((forged, valid))
    assert leader == "candidate:valid"
    assert ties == ("candidate:valid",)
    assert margin == 10


def test_committed_outcome_is_always_deliverable_and_commit_binds_finality() -> None:
    base = dict(
        kind=CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT,
        candidate_ref="candidate:answer",
        claim_root=_root("claim"),
        output_contract_root=_root("contract"),
        output_payload_root=_root("payload"),
        finality_root=_root("finality"),
        epistemically_committed=True,
        delivery_eligible=True,
        publication_eligible=False,
        execution_eligible=False,
        reason_codes=("evidence_finality_verified",),
        current_step=4,
        evidence_deadline_step=10,
        finality_deadline_step=20,
        window_root=_root("window"),
        seal_root=_root("seal"),
        frozen_dependency_root=_root("dependencies"),
    )
    outcome = CommitDecisionOutcomeV2(**base)
    assert outcome.delivery_eligible
    with pytest.raises(ValueError, match="deliverable"):
        CommitDecisionOutcomeV2(**{**base, "delivery_eligible": False})
    with pytest.raises(ValueError, match="frozen output bindings"):
        CommitDecisionOutcomeV2(**{**base, "finality_root": ""})


def test_all_fresh_gate_status_preserves_invalid_then_safety_priority() -> None:
    base = dict(
        current_step=8,
        stop_clear=True,
        permission_allowed=True,
        risk_current=True,
        membership_current=True,
        verification_current=True,
        evidence_current=True,
        support_current=True,
        blocker_roots=(),
    )
    invalid = CommitDecisionGateStatusV2(
        **base,
        reason_codes=("invalid:candidate_authority_binding",),
    )
    invalid = CommitDecisionGateStatusV2.from_dict(invalid.to_dict())
    assert not invalid.all_clear
    assert _gate_status_outcome(invalid) is CommitDecisionOutcomeKindV2.INVALID
    safety = CommitDecisionGateStatusV2(
        **base,
        reason_codes=("safety:support_equivocation",),
    )
    safety = CommitDecisionGateStatusV2.from_dict(safety.to_dict())
    assert not safety.all_clear
    assert _gate_status_outcome(safety) is (
        CommitDecisionOutcomeKindV2.SAFETY_VIOLATION
    )


def test_private_owner_has_no_legacy_authority_and_stays_locally_small() -> None:
    root = (
        Path(__file__).resolve().parents[2] / "pheroos/governance/_commit_decision_v2"
    )
    source = "\n".join(path.read_text() for path in root.glob("*.py"))
    for forbidden in (
        "_ISSUANCE",
        "authority_registry",
        "cursor",
        "pheroos.governance._commit.",
        "pheroos.governance._commit_state.",
        "pheroos.governance._certificate",
        "pheroos.governance._distributed",
    ):
        assert forbidden not in source
    assert max(len(path.read_text().splitlines()) for path in root.glob("*.py")) < 600


def test_private_owner_has_no_module_scope_mutable_dispatch_or_export_tables() -> None:
    root = (
        Path(__file__).resolve().parents[2] / "pheroos/governance/_commit_decision_v2"
    )
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for statement in tree.body:
            if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                continue
            value = statement.value
            assert not isinstance(value, (ast.Dict, ast.List, ast.Set)), (
                path.name,
                statement.lineno,
            )
            assert not (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id in {"dict", "list", "set"}
            ), (path.name, statement.lineno)
