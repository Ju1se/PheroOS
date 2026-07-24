from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import fields, replace
from types import SimpleNamespace
from typing import Any, cast

import pytest

from pheroos.governance._distributed_v2 import (
    authority_context as authority_context_module,
)
from pheroos.governance._distributed_v2 import (
    certificate_contracts as certificate_contracts_module,
)
from pheroos.governance._distributed_v2 import (
    conflict_contracts as conflict_contracts_module,
)
from pheroos.governance._distributed_v2 import operations as operations_module
from pheroos.governance._distributed_v2 import (
    proposal_contracts as proposal_contracts_module,
)
from pheroos.governance._distributed_v2 import source_builders as source_builders_module
from pheroos.governance._distributed_v2 import source_support as source_support_module
from pheroos.governance._distributed_v2 import state_contracts as state_contracts_module
from pheroos.governance._distributed_v2 import state_handle as state_handle_module
from pheroos.governance._distributed_v2 import state_records as state_records_module
from pheroos.conformance.checks._distributed_v2_context_support import (
    capability_v2,
    root_v2,
)
from pheroos.conformance.checks._distributed_v2_vertical_support import (
    DistributedV2Vertical,
    build_verified_distributed_vertical_v2,
    external_witness_conflict_observation_v2,
    _signed_witness_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance._distributed_v2.authority_context import (
    _dependency,
    _distributed_authority_context_v2,
    _validate_membership_context,
    _validated_manifest,
)
from pheroos.governance._distributed_v2.certificate_contracts import (
    _canonical_witnesses,
)
from pheroos.governance._distributed_v2.common import (
    MAX_DISTRIBUTED_TEXT_BYTES_V2,
    _canonical_texts,
    _exact_array,
    _exact_mapping,
    _install_root,
    _require_canonical_wire,
    _require_count,
    _require_root,
    _require_text,
)
from pheroos.governance._distributed_v2.conflict_contracts import (
    _validate_conflicting_value_binding_v2,
)
from pheroos.governance._distributed_v2.dependency_contracts import (
    DistributedDependencyV2,
    canonical_distributed_dependencies_v2,
)
from pheroos.governance._distributed_v2.enums import (
    DistributedDependencyRoleV2,
    DistributedLaneStatusV2,
    DistributedLaneV2,
    DistributedMutationKindV2,
)
from pheroos.governance._distributed_v2.events import (
    _distributed_event_v2,
    _lane_state_material,
)
from pheroos.governance._distributed_v2.lane_states import (
    DistributedCertificateStateV2,
    DistributedEpochStateV2,
    DistributedEquivocationFindingV2,
    DistributedProposalStateV2,
    DistributedWitnessStateV2,
    _canonical_certificates,
    _canonical_findings,
    _canonical_proposals,
    _canonical_records,
    _validate_finding_observations,
)
from pheroos.governance._distributed_v2.operations import (
    _committed_view_matches,
    _finality_failure,
    _load_dependency_heads,
    _load_exact_head,
    _load_parent,
    _require_request,
    _validated_session,
    _validated_source_and_heads,
)
from pheroos.governance._distributed_v2.policy import (
    DistributedPolicyBindingV2,
    distributed_policy_binding_v2,
    validate_distributed_membership_v2,
)
from pheroos.governance._distributed_v2.proposal_contracts import (
    DistributedCommitValueV2,
)
from pheroos.governance._distributed_v2.reducer import (
    _certificate_records,
    _proposal_records,
    _require_parent_lane,
    _state_context,
    _state_epoch,
    _witness_records,
    reduce_certificate_v2,
    reduce_epoch_v2,
    reduce_proposal_v2,
    reduce_witness_v2,
    reduce_witness_conflict_observation_v2,
)
from pheroos.governance._distributed_v2.source import (
    VerifiedDistributedAdvanceSourceV2,
    _SOURCE_TOKEN_V2,
    _verified_source_material_v2,
    verify_distributed_source_v2,
)
from pheroos.governance._distributed_v2.source_evaluation import (
    _epoch_conflicts_v2,
    _member_v2,
    _validate_epoch_v2,
    _verified_witnesses_v2,
)
from pheroos.governance._distributed_v2.source_builders import _build_recipe_v2
from pheroos.governance._distributed_v2.source_recipes import (
    _CertificateRecipeV2,
    _EpochRecipeV2,
    _WitnessConflictObservationRecipeV2,
)
from pheroos.governance._distributed_v2.source_support import (
    _EpochAuthorityContextV2,
    _current_lane_dependency_v2,
    _epoch_authority_context_v2,
    _lane_dependency_from_reader_v2,
    _manifest_for_membership,
    _parent_snapshot_v2,
)
from pheroos.governance._distributed_v2.state_contracts import (
    DistributedLaneSnapshotV2,
    _lane_state_epoch,
    _lane_state_frozen,
    distributed_genesis_history_root_v2,
    distributed_genesis_snapshot_root_v2,
    distributed_lane_stream_ref_v2,
)
from pheroos.governance._distributed_v2.state_handle import (
    VerifiedDistributedCertificateStateV2,
    VerifiedDistributedEpochStateV2,
    VerifiedDistributedProposalStateV2,
    VerifiedDistributedStateV2,
    VerifiedDistributedWitnessStateV2,
    _finality_status,
    _load_verified_material,
    _current_lane,
    _lane_for_handle,
    _request_from_portable,
    _require_domain,
    _require_reader,
    _verified_distributed_state_material_v2,
    distributed_state_is_current_v2,
    rehydrate_distributed_state_v2,
    require_current_distributed_state_v2,
)
from pheroos.governance._distributed_v2.state_records import (
    _dependency_snapshot_root,
    _decode_state_records_v2,
    _verify_dependencies,
    _verify_parent,
    _head_from_view_v2 as _records_head_from_view_v2,
    _required_actions,
    _validate_read_set_v2,
    _validate_session_binding,
)
from pheroos.governance._distributed_v2.witness_contracts import (
    verify_distributed_witness_v2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
)
from pheroos.governance.distributed_commit_v2 import (
    advance_distributed_commit_v2,
    open_distributed_authority_session_v2,
    prepare_distributed_proposal_v2,
    prepare_distributed_witness_v2,
)
from pheroos.governance.commit_finality_v2 import CommitFinalityStatusV2
from pheroos.protocol.commit_models import CommitAssurance, DistributedCommitPolicy
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


@pytest.fixture(scope="module")
def vertical() -> DistributedV2Vertical:
    return build_verified_distributed_vertical_v2(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        "distributed-v2-totality",
    )


@pytest.fixture(scope="module")
def observation(vertical: DistributedV2Vertical) -> object:
    return external_witness_conflict_observation_v2(
        vertical,
        "distributed-v2-totality",
    )


def _forge(instance: Any, **changes: object) -> Any:
    forged = object.__new__(type(instance))
    for field in fields(instance):
        object.__setattr__(
            forged,
            field.name,
            changes.get(field.name, getattr(instance, field.name)),
        )
    return forged


def _root(label: str) -> str:
    return root_v2(f"distributed-v2-totality:{label}")


def _valid_policy() -> DistributedCommitPolicy:
    return DistributedCommitPolicy(
        fault_model="byzantine_static_v1",
        membership_mode="static_epoch_verified_clusters_v1",
        membership_size=4,
        max_byzantine_faults=1,
        witness_quorum=3,
        witness_ttl_steps=20,
        minimum_failure_domain_diversity=1,
        epoch_transition_rule="certified_increment_v1",
        conflict_rule="freeze_v1",
    )


def _valid_binding() -> DistributedPolicyBindingV2:
    return distributed_policy_binding_v2(_valid_policy(), policy_root=_root("policy"))


def _request(vertical: DistributedV2Vertical, lane: DistributedLaneV2) -> object:
    return {
        DistributedLaneV2.EPOCH: vertical.epoch_request,
        DistributedLaneV2.PROPOSAL: vertical.proposal_request,
        DistributedLaneV2.WITNESS: vertical.witness_request,
        DistributedLaneV2.CERTIFICATE: vertical.certificate_request,
    }[lane]


def _snapshot(vertical: DistributedV2Vertical, lane: DistributedLaneV2) -> object:
    return object.__getattribute__(_request(vertical, lane), "snapshot")


def _state(vertical: DistributedV2Vertical, lane: DistributedLaneV2) -> object:
    return object.__getattribute__(_snapshot(vertical, lane), "state")


def _replace_snapshot(snapshot: object, **changes: object) -> object:
    values = {
        "dependency_set_root": "",
        "snapshot_state_root": "",
        "history_root": "",
        "snapshot_root": "",
        **changes,
    }
    return replace(cast(Any, snapshot), **values)


def _finding(observation: object | None = None) -> DistributedEquivocationFindingV2:
    if observation is None:
        return DistributedEquivocationFindingV2(
            principal_ref="principal:finding",
            epoch=1,
            first_semantic_value_root=_root("finding-semantic-one"),
            second_semantic_value_root=_root("finding-semantic-two"),
            first_witness_root=_root("finding-witness-one"),
            second_witness_root=_root("finding-witness-two"),
        )
    observed = cast(Any, observation).witness
    return DistributedEquivocationFindingV2(
        principal_ref=observed.principal_ref,
        epoch=observed.epoch,
        first_semantic_value_root=observed.semantic_value_root,
        second_semantic_value_root=_root("finding-other-semantic"),
        first_witness_root=observed.witness_root,
        second_witness_root=_root("finding-other-witness"),
        conflict_observation=cast(Any, observation),
    )


@pytest.mark.parametrize(
    ("value", "error"),
    (
        (1, TypeError),
        ("", ValueError),
        ("has\x00null", ValueError),
        ("\ud800", ValueError),
        ("x" * (MAX_DISTRIBUTED_TEXT_BYTES_V2 + 1), ValueError),
    ),
)
def test_common_text_totality(value: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        _require_text(value, "value")


@pytest.mark.parametrize("value", ("sha256:ABC", "x", "sha256:" + ("g" * 64)))
def test_common_root_totality(value: str) -> None:
    with pytest.raises(ValueError, match="lowercase sha256"):
        _require_root(value, "root")


def test_common_empty_root_is_explicitly_opt_in() -> None:
    assert _require_root("", "root", allow_empty=True) == ""


@pytest.mark.parametrize("value", (True, -1, 4))
def test_common_count_totality(value: object) -> None:
    with pytest.raises(ValueError, match="integer bound"):
        _require_count(value, "count", maximum=3)


@pytest.mark.parametrize(
    ("payload", "error"),
    (
        ((), TypeError),
        ({1: "value"}, ValueError),
        ({"other": "value"}, ValueError),
    ),
)
def test_common_exact_mapping_totality(
    payload: object,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        _exact_mapping(payload, frozenset({"field"}), "mapping")


@pytest.mark.parametrize(
    ("payload", "allow_empty", "maximum", "error"),
    (
        ((), True, 1, TypeError),
        ([], False, 1, ValueError),
        ([1, 2], True, 1, ValueError),
    ),
)
def test_common_exact_array_totality(
    payload: object,
    allow_empty: bool,
    maximum: int,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        _exact_array(
            payload,
            "array",
            allow_empty=allow_empty,
            maximum=maximum,
        )


@pytest.mark.parametrize(
    ("values", "allow_empty", "maximum", "error"),
    (
        ({"a"}, True, 2, TypeError),
        ((), False, 2, ValueError),
        (("a", "b"), True, 1, ValueError),
        (("a", "a"), True, 2, ValueError),
    ),
)
def test_common_canonical_text_totality(
    values: object,
    allow_empty: bool,
    maximum: int,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        _canonical_texts(
            cast(Any, values),
            "texts",
            allow_empty=allow_empty,
            maximum=maximum,
        )


def test_common_root_install_and_wire_mismatch_totality() -> None:
    target = SimpleNamespace()
    with pytest.raises(ValueError, match="mismatched"):
        _install_root(target, "root", _root("wrong"), "test", {"value": 1})
    with pytest.raises(ValueError, match="canonical wire"):
        _require_canonical_wire({"a": 1}, {"a": 2}, "wire")


@pytest.mark.parametrize(
    "changes",
    (
        {"membership_size": 3},
        {"witness_quorum": 4},
        {"witness_quorum": 2},
        {"minimum_failure_domain_diversity": 4},
        {"binding_root": _root("wrong-binding")},
    ),
)
def test_policy_binding_rejects_each_fault_model_invariant(
    changes: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "policy_root": _root("policy-binding"),
        "membership_size": 4,
        "max_byzantine_faults": 1,
        "witness_quorum": 3,
        "witness_ttl_steps": 20,
        "minimum_failure_domain_diversity": 1,
        "epoch_transition_rule": "certified_increment_v1",
    }
    values.update(changes)
    with pytest.raises(ValueError):
        DistributedPolicyBindingV2(**cast(Any, values))


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("fault_model", "crash"),
        ("membership_mode", "dynamic"),
        ("conflict_rule", "ignore"),
    ),
)
def test_policy_binding_factory_rejects_unsupported_modes(
    field: str,
    value: str,
) -> None:
    policy = replace(_valid_policy(), **{field: value})
    with pytest.raises(ValueError, match="unsupported"):
        distributed_policy_binding_v2(policy, policy_root=_root("policy-mode"))


def test_policy_binding_factory_requires_exact_policy() -> None:
    with pytest.raises(TypeError, match="exact DistributedCommitPolicy"):
        distributed_policy_binding_v2(object(), policy_root=_root("policy-type"))  # type: ignore[arg-type]


def test_membership_validation_requires_exact_inputs(
    vertical: DistributedV2Vertical,
) -> None:
    membership = vertical.identity.membership.snapshot
    with pytest.raises(TypeError, match="exact MembershipSnapshotV2"):
        validate_distributed_membership_v2(
            object(),  # type: ignore[arg-type]
            _valid_binding(),
            current_step=10,
        )
    with pytest.raises(TypeError, match="exact policy binding"):
        validate_distributed_membership_v2(
            membership,
            object(),  # type: ignore[arg-type]
            current_step=10,
        )


def test_membership_validation_rejects_wrong_eligible_count(
    vertical: DistributedV2Vertical,
) -> None:
    membership = vertical.identity.membership.snapshot
    binding = _forge(
        cast(
            DistributedEpochStateV2,
            vertical.epoch.snapshot.state,
        ).transition_certificate.policy_binding,
        membership_size=sum(len(item.principals) for item in membership.clusters) + 1,
    )
    with pytest.raises(ValueError, match="exact eligible set"):
        validate_distributed_membership_v2(membership, binding, current_step=10)


def test_membership_validation_rejects_duplicate_identity(
    vertical: DistributedV2Vertical,
) -> None:
    membership = vertical.identity.membership.snapshot
    first_cluster = membership.clusters[0]
    duplicated = _forge(
        first_cluster,
        principals=(first_cluster.principals[0], first_cluster.principals[0]),
    )
    forged = _forge(membership, clusters=(duplicated,))
    binding = DistributedPolicyBindingV2(
        policy_root=_root("duplicate-policy"),
        membership_size=2,
        max_byzantine_faults=0,
        witness_quorum=2,
        witness_ttl_steps=20,
        minimum_failure_domain_diversity=1,
        epoch_transition_rule="certified_increment_v1",
    )
    with pytest.raises(ValueError, match="repeats a principal"):
        validate_distributed_membership_v2(forged, binding, current_step=10)


def test_membership_validation_rejects_empty_domain_and_cluster(
    vertical: DistributedV2Vertical,
) -> None:
    membership = vertical.identity.membership.snapshot
    principal = _forge(
        membership.clusters[0].principals[0],
        failure_domain_ref="",
    )
    cluster = _forge(membership.clusters[0], principals=(principal,))
    forged = _forge(membership, clusters=(cluster,))
    binding = DistributedPolicyBindingV2(
        policy_root=_root("domain-policy"),
        membership_size=1,
        max_byzantine_faults=0,
        witness_quorum=1,
        witness_ttl_steps=20,
        minimum_failure_domain_diversity=1,
        epoch_transition_rule="certified_increment_v1",
    )
    with pytest.raises(ValueError, match="failure domains"):
        validate_distributed_membership_v2(forged, binding, current_step=10)
    with pytest.raises(ValueError, match="declared clusters"):
        validate_distributed_membership_v2(
            _forge(membership, clusters=()),
            _forge(binding, membership_size=0),
            current_step=10,
        )


def test_membership_validation_rejects_diversity_and_time(
    vertical: DistributedV2Vertical,
) -> None:
    membership = vertical.identity.membership.snapshot
    principal_count = sum(len(item.principals) for item in membership.clusters)
    base_binding = cast(
        DistributedEpochStateV2,
        vertical.epoch.snapshot.state,
    ).transition_certificate.policy_binding
    binding = _forge(
        base_binding,
        membership_size=principal_count,
        minimum_failure_domain_diversity=2,
    )
    same_domain_clusters = tuple(
        _forge(
            cluster,
            principals=tuple(
                _forge(principal, failure_domain_ref="failure-domain:one")
                for principal in cluster.principals
            ),
        )
        for cluster in membership.clusters
    )
    with pytest.raises(ValueError, match="declared diversity"):
        validate_distributed_membership_v2(
            _forge(membership, clusters=same_domain_clusters),
            binding,
            current_step=10,
        )
    with pytest.raises(ValueError, match="not current"):
        validate_distributed_membership_v2(
            membership,
            base_binding,
            current_step=membership.expires_at_step,
        )


@pytest.mark.parametrize(
    ("changes", "error"),
    (
        ({"schema": "unsupported"}, ValueError),
        ({"role": object()}, TypeError),
        (
            {
                "revision": 0,
                "transition_id": "transition:present",
                "snapshot_root": "",
                "receipt_root": "",
                "inclusion_root": "",
            },
            ValueError,
        ),
        ({"revision": 1, "transition_id": ""}, ValueError),
    ),
)
def test_dependency_contract_totality(
    vertical: DistributedV2Vertical,
    changes: dict[str, object],
    error: type[Exception],
) -> None:
    dependency = vertical.proposal_request.snapshot.dependencies[0]
    with pytest.raises(error):
        replace(dependency, **changes, dependency_root="")


def test_dependency_wire_rejects_unknown_role(
    vertical: DistributedV2Vertical,
) -> None:
    payload = vertical.proposal_request.snapshot.dependencies[0].to_dict()
    payload["role"] = "unknown"
    with pytest.raises(ValueError, match="role is unsupported"):
        DistributedDependencyV2.from_dict(payload)


@pytest.mark.parametrize(
    ("dependencies", "error"),
    (
        ({}, TypeError),
        ((object(),), TypeError),
    ),
)
def test_dependency_sequence_requires_exact_records(
    dependencies: object,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        canonical_distributed_dependencies_v2(cast(Any, dependencies))


def test_dependency_sequence_rejects_closed_set_overflow_and_duplicates(
    vertical: DistributedV2Vertical,
) -> None:
    dependency = vertical.proposal_request.snapshot.dependencies[0]
    overflow = tuple(dependency for _ in range(len(DistributedDependencyRoleV2) + 1))
    with pytest.raises(ValueError, match="closed roles"):
        canonical_distributed_dependencies_v2(overflow)
    duplicate = _forge(
        dependency,
        dependency_root=_root("dependency-duplicate"),
    )
    with pytest.raises(ValueError, match="repeat role or stream"):
        canonical_distributed_dependencies_v2((dependency, duplicate))


@pytest.mark.parametrize(
    ("changes", "error"),
    (
        ({"schema": "unsupported"}, ValueError),
        ({"proposal": object()}, TypeError),
        ({"witness": object()}, TypeError),
        ({"observed_at_step": 9}, ValueError),
        ({"observed_at_step": 30}, ValueError),
    ),
)
def test_conflict_observation_contract_totality(
    observation: object,
    changes: dict[str, object],
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        replace(cast(Any, observation), **changes, observation_root="")


def test_conflict_observation_rejects_cross_bound_witness(
    observation: object,
) -> None:
    current = cast(Any, observation)
    witness = _forge(current.witness, proposal_digest=_root("other-proposal"))
    with pytest.raises(ValueError, match="proposal/witness is cross-bound"):
        replace(current, witness=witness, observation_root="")


def test_conflicting_value_binding_requires_distinct_exact_values(
    vertical: DistributedV2Vertical,
    observation: object,
) -> None:
    current = (
        cast(
            DistributedProposalStateV2,
            vertical.proposal.snapshot.state,
        )
        .proposals[0]
        .value
    )
    observed = cast(Any, observation).proposal.value
    with pytest.raises(TypeError, match="exact values"):
        _validate_conflicting_value_binding_v2(object(), current)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not semantically distinct"):
        _validate_conflicting_value_binding_v2(current, current)
    _validate_conflicting_value_binding_v2(observed, current)
    with pytest.raises(ValueError, match="changes sealed authority"):
        _validate_conflicting_value_binding_v2(
            _forge(observed, candidate_ref="candidate:substituted"),
            current,
        )


@pytest.mark.parametrize(
    ("changes", "error"),
    (
        ({"schema": "unsupported"}, ValueError),
        ({"value": object()}, TypeError),
        ({"witness_set_root": _root("wrong-witness-set")}, ValueError),
    ),
)
def test_certificate_contract_header_totality(
    vertical: DistributedV2Vertical,
    changes: dict[str, object],
    error: type[Exception],
) -> None:
    certificate = cast(
        DistributedCertificateStateV2,
        vertical.certificate.snapshot.state,
    ).certificates[0]
    with pytest.raises(error):
        replace(certificate, **changes, certificate_root="")


def test_certificate_contract_rejects_invalid_fault_model(
    vertical: DistributedV2Vertical,
) -> None:
    certificate = cast(
        DistributedCertificateStateV2,
        vertical.certificate.snapshot.state,
    ).certificates[0]
    with pytest.raises(ValueError, match="fault model"):
        replace(
            certificate,
            membership_size=3,
            max_byzantine_faults=1,
            witness_quorum=1,
            minimum_failure_domain_diversity=1,
            witness_set_root="",
            certificate_root="",
        )


def test_certificate_contract_rejects_duplicate_principal_quorum(
    vertical: DistributedV2Vertical,
) -> None:
    certificate = cast(
        DistributedCertificateStateV2,
        vertical.certificate.snapshot.state,
    ).certificates[0]
    witness = certificate.witnesses[0]
    witnesses = (
        witness,
        _forge(witness, witness_root=_root("witness-two")),
        _forge(witness, witness_root=_root("witness-three")),
    )
    with pytest.raises(ValueError, match="distinct-principal quorum"):
        replace(
            certificate,
            witnesses=witnesses,
            membership_size=4,
            max_byzantine_faults=1,
            witness_quorum=3,
            witness_set_root="",
            certificate_root="",
        )


def test_certificate_contract_rejects_insufficient_diversity(
    vertical: DistributedV2Vertical,
) -> None:
    certificate = cast(
        DistributedCertificateStateV2,
        vertical.certificate.snapshot.state,
    ).certificates[0]
    witness = certificate.witnesses[0]
    witnesses = (
        witness,
        _forge(
            witness,
            principal_ref="principal:two",
            witness_root=_root("diversity-witness-two"),
        ),
        _forge(
            witness,
            principal_ref="principal:three",
            witness_root=_root("diversity-witness-three"),
        ),
    )
    with pytest.raises(ValueError, match="failure-domain diversity"):
        replace(
            certificate,
            witnesses=witnesses,
            membership_size=4,
            max_byzantine_faults=1,
            witness_quorum=3,
            minimum_failure_domain_diversity=2,
            witness_set_root="",
            certificate_root="",
        )


def test_certificate_contract_rejects_cross_bound_witness(
    vertical: DistributedV2Vertical,
) -> None:
    certificate = cast(
        DistributedCertificateStateV2,
        vertical.certificate.snapshot.state,
    ).certificates[0]
    witness = _forge(
        certificate.witnesses[0],
        semantic_value_root=_root("other-semantic-value"),
        witness_root=_root("cross-bound-witness"),
    )
    with pytest.raises(ValueError, match="cross-bound witness"):
        replace(
            certificate,
            witnesses=(witness,),
            witness_set_root="",
            certificate_root="",
        )


@pytest.mark.parametrize(
    ("witnesses", "error"),
    (
        ({}, TypeError),
        ((), ValueError),
        ((object(),), TypeError),
    ),
)
def test_certificate_witness_sequence_totality(
    witnesses: object,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        _canonical_witnesses(cast(Any, witnesses))


def test_certificate_witness_sequence_rejects_duplicate_roots(
    vertical: DistributedV2Vertical,
) -> None:
    witness = (
        cast(
            DistributedCertificateStateV2,
            vertical.certificate.snapshot.state,
        )
        .certificates[0]
        .witnesses[0]
    )
    with pytest.raises(ValueError, match="repeats witness roots"):
        _canonical_witnesses((witness, witness))


@pytest.mark.parametrize(
    ("changes", "error"),
    (
        ({"schema": "unsupported"}, ValueError),
        ({"policy_binding": object()}, TypeError),
        ({"transition_rule": "other"}, ValueError),
        ({"prior_epoch_snapshot_root": _root("genesis-prior")}, ValueError),
    ),
)
def test_epoch_certificate_header_totality(
    vertical: DistributedV2Vertical,
    changes: dict[str, object],
    error: type[Exception],
) -> None:
    certificate = cast(
        DistributedEpochStateV2,
        vertical.epoch.snapshot.state,
    ).transition_certificate
    with pytest.raises(error):
        replace(certificate, **changes, certificate_root="")


@pytest.mark.parametrize(
    "changes",
    (
        {
            "from_epoch": (2**53 - 1),
            "to_epoch": (2**53 - 1),
            "prior_epoch_snapshot_root": _root("prior-max"),
        },
        {
            "from_epoch": 3,
            "to_epoch": 5,
            "prior_epoch_snapshot_root": _root("prior-gap"),
        },
        {
            "from_epoch": 3,
            "to_epoch": 4,
            "prior_epoch_snapshot_root": "",
        },
    ),
)
def test_epoch_certificate_transition_totality(
    vertical: DistributedV2Vertical,
    changes: dict[str, object],
) -> None:
    certificate = cast(
        DistributedEpochStateV2,
        vertical.epoch.snapshot.state,
    ).transition_certificate
    with pytest.raises(ValueError):
        replace(certificate, **changes, certificate_root="")


@pytest.mark.parametrize(
    "changes",
    (
        {"required_action_refs": ("recovery",)},
        {
            "required_action_refs": ("epoch_transition", "recovery"),
            "conflict_history_roots": (),
        },
    ),
)
def test_epoch_certificate_action_totality(
    vertical: DistributedV2Vertical,
    changes: dict[str, object],
) -> None:
    certificate = cast(
        DistributedEpochStateV2,
        vertical.epoch.snapshot.state,
    ).transition_certificate
    with pytest.raises(ValueError):
        replace(certificate, **changes, certificate_root="")


def test_epoch_certificate_wire_rejects_invalid_from_epoch(
    vertical: DistributedV2Vertical,
) -> None:
    payload = cast(
        DistributedEpochStateV2,
        vertical.epoch.snapshot.state,
    ).transition_certificate.to_dict()
    payload["from_epoch"] = "zero"
    with pytest.raises(TypeError, match="from_epoch is invalid"):
        type(
            cast(
                DistributedEpochStateV2,
                vertical.epoch.snapshot.state,
            ).transition_certificate
        ).from_dict(payload)


@pytest.mark.parametrize(
    ("changes", "error"),
    (
        ({"schema": "unsupported"}, ValueError),
        ({"expires_at_step": 10}, ValueError),
        ({"signing_root": _root("wrong-signing")}, ValueError),
    ),
)
def test_witness_contract_totality(
    vertical: DistributedV2Vertical,
    changes: dict[str, object],
    error: type[Exception],
) -> None:
    witness = cast(
        DistributedWitnessStateV2,
        vertical.witness.snapshot.state,
    ).witnesses[0]
    with pytest.raises(error):
        replace(witness, **changes, witness_root="")


@pytest.mark.parametrize(
    ("changes", "error"),
    (
        ({"schema": "unsupported"}, ValueError),
        ({"assurance": "distributed"}, TypeError),
        ({"assurance": CommitAssurance.CERTIFIED}, ValueError),
        ({"central_certificate_body": object()}, TypeError),
        ({"scope_ref": "scope:substituted"}, ValueError),
    ),
)
def test_semantic_value_contract_totality(
    vertical: DistributedV2Vertical,
    changes: dict[str, object],
    error: type[Exception],
) -> None:
    value = (
        cast(
            DistributedProposalStateV2,
            vertical.proposal.snapshot.state,
        )
        .proposals[0]
        .value
    )
    with pytest.raises(error):
        replace(value, **changes, semantic_value_root="")


def test_semantic_value_wire_rejects_unknown_assurance(
    vertical: DistributedV2Vertical,
) -> None:
    payload = (
        cast(
            DistributedProposalStateV2,
            vertical.proposal.snapshot.state,
        )
        .proposals[0]
        .value.to_dict()
    )
    payload["assurance"] = "unknown"
    with pytest.raises(ValueError, match="assurance is unsupported"):
        DistributedCommitValueV2.from_dict(payload)


@pytest.mark.parametrize(
    ("changes", "error"),
    (
        ({"schema": "unsupported"}, ValueError),
        ({"value": object()}, TypeError),
    ),
)
def test_proposal_contract_totality(
    vertical: DistributedV2Vertical,
    changes: dict[str, object],
    error: type[Exception],
) -> None:
    proposal = cast(
        DistributedProposalStateV2,
        vertical.proposal.snapshot.state,
    ).proposals[0]
    with pytest.raises(error):
        replace(proposal, **changes, proposal_digest="")


def test_equivocation_finding_requires_distinct_values() -> None:
    root = _root("same-semantic")
    with pytest.raises(ValueError, match="does not prove equivocation"):
        DistributedEquivocationFindingV2(
            principal_ref="principal:finding",
            epoch=1,
            first_semantic_value_root=root,
            second_semantic_value_root=root,
            first_witness_root=_root("first-witness"),
            second_witness_root=_root("second-witness"),
        )


def test_equivocation_finding_observation_totality(
    observation: object,
) -> None:
    finding = _finding()
    with pytest.raises(TypeError, match="wrong exact type"):
        replace(finding, conflict_observation=object(), finding_root="")
    observed = cast(Any, observation).witness
    with pytest.raises(ValueError, match="cross-bound"):
        DistributedEquivocationFindingV2(
            principal_ref="principal:other",
            epoch=observed.epoch,
            first_semantic_value_root=observed.semantic_value_root,
            second_semantic_value_root=_root("finding-cross-semantic"),
            first_witness_root=observed.witness_root,
            second_witness_root=_root("finding-cross-witness"),
            conflict_observation=cast(Any, observation),
        )
    assert _finding(observation).conflict_observation is observation


def test_epoch_state_requires_exact_certificate_and_history(
    vertical: DistributedV2Vertical,
) -> None:
    state = cast(DistributedEpochStateV2, vertical.epoch.snapshot.state)
    with pytest.raises(TypeError, match="exact certificate"):
        DistributedEpochStateV2(
            transition_certificate=object(),  # type: ignore[arg-type]
            conflict_history_roots=(),
        )
    with pytest.raises(ValueError, match="history is mismatched"):
        replace(
            state,
            conflict_history_roots=(_root("unexpected-history"),),
            state_root="",
        )


@pytest.mark.parametrize(
    "lane",
    (
        DistributedLaneV2.PROPOSAL,
        DistributedLaneV2.WITNESS,
        DistributedLaneV2.CERTIFICATE,
    ),
)
def test_lane_states_reject_cross_epoch_records(
    vertical: DistributedV2Vertical,
    lane: DistributedLaneV2,
) -> None:
    state = _state(vertical, lane)
    if lane is DistributedLaneV2.PROPOSAL:
        proposal = cast(DistributedProposalStateV2, state).proposals[0]
        forged = _forge(proposal, value=_forge(proposal.value, epoch=2))
        with pytest.raises(ValueError, match="cross-epoch"):
            DistributedProposalStateV2(epoch=1, proposals=(forged,))
    elif lane is DistributedLaneV2.WITNESS:
        witness = cast(DistributedWitnessStateV2, state).witnesses[0]
        with pytest.raises(ValueError, match="cross-epoch"):
            DistributedWitnessStateV2(
                epoch=witness.epoch + 1,
                witnesses=(witness,),
                equivocations=(),
            )
    else:
        certificate = cast(DistributedCertificateStateV2, state).certificates[0]
        with pytest.raises(ValueError, match="cross-epoch"):
            DistributedCertificateStateV2(
                epoch=certificate.value.epoch + 1,
                certificates=(certificate,),
                conflict_roots=(),
            )


def test_certificate_state_requires_conflict_evidence_bijection(
    vertical: DistributedV2Vertical,
) -> None:
    certificate = cast(
        DistributedCertificateStateV2,
        vertical.certificate.snapshot.state,
    ).certificates[0]
    distinct = _forge(
        certificate,
        value=_forge(
            certificate.value,
            semantic_value_root=_root("distinct-certificate-value"),
        ),
        certificate_root=_root("distinct-certificate"),
    )
    with pytest.raises(ValueError, match="conflict is not frozen"):
        DistributedCertificateStateV2(
            epoch=certificate.value.epoch,
            certificates=(certificate, distinct),
            conflict_roots=(),
        )
    with pytest.raises(ValueError, match="lacks distinct values"):
        DistributedCertificateStateV2(
            epoch=certificate.value.epoch,
            certificates=(certificate,),
            conflict_roots=(_root("unsupported-conflict"),),
        )


@pytest.mark.parametrize(
    ("function", "label"),
    (
        (_canonical_proposals, "proposals"),
        (_canonical_witnesses, "certificate witnesses"),
        (_canonical_certificates, "certificates"),
    ),
)
def test_lane_record_sequences_reject_wrong_container(
    function: Any,
    label: str,
) -> None:
    with pytest.raises(TypeError, match="exact sequence"):
        function({})
    assert label


def test_lane_record_sequences_reject_empty_noncanonical_and_duplicates(
    vertical: DistributedV2Vertical,
) -> None:
    proposal = cast(
        DistributedProposalStateV2,
        vertical.proposal.snapshot.state,
    ).proposals[0]
    with pytest.raises(ValueError, match="count or type"):
        _canonical_proposals(())
    with pytest.raises(ValueError, match="count or type"):
        _canonical_proposals((object(),))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="repeat roots"):
        _canonical_proposals((proposal, proposal))


def test_finding_sequence_and_durable_observation_totality(
    observation: object,
    vertical: DistributedV2Vertical,
) -> None:
    assert _canonical_findings(()) == ()
    with pytest.raises(TypeError, match="exact sequence"):
        _canonical_findings({})  # type: ignore[arg-type]
    finding = _finding(observation)
    witness = cast(
        DistributedWitnessStateV2,
        vertical.witness.snapshot.state,
    ).witnesses[0]
    with pytest.raises(ValueError, match="not durable"):
        _validate_finding_observations((witness,), (finding,))


def test_generic_canonical_record_totality() -> None:
    with pytest.raises(TypeError, match="exact sequence"):
        _canonical_records({}, str, 1, "value", "strings")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="count or type"):
        _canonical_records((), str, 1, "value", "strings")


@pytest.mark.parametrize(
    ("function", "value"),
    (
        (distributed_lane_stream_ref_v2, object()),
        (distributed_genesis_snapshot_root_v2, object()),
        (distributed_genesis_history_root_v2, object()),
    ),
)
def test_lane_identity_helpers_require_exact_lane(
    function: Any,
    value: object,
) -> None:
    with pytest.raises(TypeError, match="lane is invalid"):
        if function is distributed_lane_stream_ref_v2:
            function("scope", "protocol", "run", "target", value)
        else:
            function(value)


@pytest.mark.parametrize(
    ("changes", "error"),
    (
        ({"schema": "unsupported"}, ValueError),
        ({"lane": object()}, TypeError),
        ({"mutation_kind": object()}, TypeError),
        ({"status": object()}, TypeError),
        ({"stream_ref": "authority:wrong"}, ValueError),
        ({"transition_id": "transition:wrong"}, ValueError),
        ({"revision": 2, "parent_revision": 0}, ValueError),
        ({"history_count": 3}, ValueError),
        ({"parent_transition_id": "not-genesis"}, ValueError),
    ),
)
def test_snapshot_header_and_lineage_totality(
    vertical: DistributedV2Vertical,
    changes: dict[str, object],
    error: type[Exception],
) -> None:
    snapshot = vertical.proposal.snapshot
    with pytest.raises(error):
        _replace_snapshot(snapshot, **changes)


def test_snapshot_dependency_and_root_binding_totality(
    vertical: DistributedV2Vertical,
) -> None:
    snapshot = vertical.proposal.snapshot
    with pytest.raises(ValueError, match="dependency_set_root"):
        replace(
            snapshot,
            dependency_set_root=_root("wrong-dependency-set"),
            snapshot_state_root="",
            history_root="",
            snapshot_root="",
        )
    with pytest.raises(ValueError, match="history_root"):
        replace(
            snapshot,
            history_root=_root("wrong-history"),
            snapshot_state_root="",
            snapshot_root="",
        )


@pytest.mark.parametrize(
    "changes",
    (
        {"state": object()},
        {"dependencies": ()},
        {"mutation_kind": DistributedMutationKindV2.EPOCH_INITIALIZED},
        {"status": DistributedLaneStatusV2.VERIFIED},
    ),
)
def test_snapshot_state_binding_totality(
    vertical: DistributedV2Vertical,
    changes: dict[str, object],
) -> None:
    snapshot = vertical.proposal.snapshot
    expected = TypeError if "state" in changes else ValueError
    with pytest.raises(expected):
        _replace_snapshot(snapshot, **changes)


def test_snapshot_state_epoch_binding_totality(
    vertical: DistributedV2Vertical,
) -> None:
    snapshot = vertical.proposal.snapshot
    state = _forge(snapshot.state, epoch=snapshot.current_epoch + 1)
    with pytest.raises(ValueError, match="state epoch"):
        _replace_snapshot(snapshot, state=state)


def test_snapshot_wire_rejects_unknown_enum(
    vertical: DistributedV2Vertical,
) -> None:
    payload = vertical.proposal.snapshot.to_dict()
    payload["lane"] = "unknown"
    with pytest.raises(ValueError, match="enum is unsupported"):
        DistributedLaneSnapshotV2.from_dict(payload)


def test_lane_state_helpers_are_total(
    vertical: DistributedV2Vertical,
) -> None:
    for lane in DistributedLaneV2:
        state = cast(Any, _state(vertical, lane))
        assert _lane_state_epoch(state) == vertical.epoch.snapshot.current_epoch
        assert _lane_state_frozen(state) is False
    with pytest.raises(TypeError, match="unsupported"):
        _lane_state_epoch(object())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "error"),
    (
        ({"schema": "unsupported"}, ValueError),
        ({"snapshot": object()}, TypeError),
        ({"stream_ref": "authority:wrong"}, ValueError),
    ),
)
def test_advance_request_contract_totality(
    vertical: DistributedV2Vertical,
    changes: dict[str, object],
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        replace(
            vertical.proposal_request,
            **changes,
            request_root="",
        )


def test_advance_request_rejects_cross_bound_snapshot(
    vertical: DistributedV2Vertical,
) -> None:
    snapshot = _forge(
        vertical.proposal_request.snapshot,
        mutation_issuer_ref="issuer:substituted",
    )
    with pytest.raises(ValueError, match="snapshot is cross-bound"):
        replace(
            vertical.proposal_request,
            snapshot=snapshot,
            request_root="",
        )


@pytest.mark.parametrize(
    "handle_type",
    (
        VerifiedDistributedStateV2,
        VerifiedDistributedEpochStateV2,
        VerifiedDistributedProposalStateV2,
        VerifiedDistributedWitnessStateV2,
        VerifiedDistributedCertificateStateV2,
    ),
)
def test_verified_state_handles_are_nonconstructible(handle_type: type[object]) -> None:
    with pytest.raises(TypeError, match="cannot be constructed"):
        handle_type()


@pytest.mark.parametrize(
    "lane",
    tuple(DistributedLaneV2),
)
def test_verified_state_handle_protocol_surface(
    vertical: DistributedV2Vertical,
    lane: DistributedLaneV2,
) -> None:
    handle = {
        DistributedLaneV2.EPOCH: vertical.epoch,
        DistributedLaneV2.PROPOSAL: vertical.proposal,
        DistributedLaneV2.WITNESS: vertical.witness,
        DistributedLaneV2.CERTIFICATE: vertical.certificate,
    }[lane]
    assert copy(handle) is handle
    assert deepcopy(handle) is handle
    assert handle.stream_ref == cast(Any, _snapshot(vertical, lane)).stream_ref
    assert handle.transition_id == cast(Any, _snapshot(vertical, lane)).transition_id
    assert handle.receipt_root.startswith("sha256:")
    assert handle.position is GovernanceCommitPositionV2.CURRENT
    assert "redacted" in repr(handle)
    with pytest.raises(AttributeError, match="immutable"):
        handle.changed = True  # type: ignore[attr-defined]
    with pytest.raises(TypeError, match="not portable"):
        handle.__getstate__()


def test_verified_state_material_rejects_incomplete_and_wrong_lane(
    vertical: DistributedV2Vertical,
) -> None:
    incomplete = object.__new__(VerifiedDistributedEpochStateV2)
    with pytest.raises(Exception):
        _verified_distributed_state_material_v2(incomplete)
    wrong_lane = object.__new__(VerifiedDistributedProposalStateV2)
    for name in ("_reader", "_domain", "_request", "_receipt_root"):
        object.__setattr__(
            wrong_lane,
            name,
            object.__getattribute__(vertical.epoch, name),
        )
    with pytest.raises(Exception):
        _verified_distributed_state_material_v2(wrong_lane)


def test_verified_state_material_rejects_corrupt_request(
    vertical: DistributedV2Vertical,
) -> None:
    corrupt = object.__new__(VerifiedDistributedEpochStateV2)
    for name in ("_reader", "_domain", "_receipt_root"):
        object.__setattr__(
            corrupt,
            name,
            object.__getattribute__(vertical.epoch, name),
        )
    object.__setattr__(corrupt, "_request", object())
    with pytest.raises(Exception):
        _verified_distributed_state_material_v2(corrupt)


def test_state_rehydration_boundary_totality(
    vertical: DistributedV2Vertical,
) -> None:
    request = vertical.epoch_request
    with pytest.raises(TypeError, match="exact AuthorityDomainV2"):
        rehydrate_distributed_state_v2(
            request,
            domain=object(),  # type: ignore[arg-type]
            state_reader=vertical.context.store,
        )
    with pytest.raises(TypeError, match="StateReader v2"):
        rehydrate_distributed_state_v2(
            request,
            domain=vertical.context.domain,
            state_reader=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(Exception):
        rehydrate_distributed_state_v2(
            {},
            domain=vertical.context.domain,
            state_reader=vertical.context.store,
        )
    other_domain = _forge(
        vertical.context.domain,
        domain_root=_root("other-domain"),
    )
    with pytest.raises(Exception):
        rehydrate_distributed_state_v2(
            request,
            domain=other_domain,
            state_reader=vertical.context.store,
        )


def test_state_handle_total_helpers_reject_unverified_objects() -> None:
    assert not distributed_state_is_current_v2(object())
    with pytest.raises(Exception):
        _lane_for_handle(object())
    with pytest.raises(Exception):
        _request_from_portable({})
    with pytest.raises(TypeError, match="exact AuthorityDomainV2"):
        _require_domain(object())
    with pytest.raises(TypeError, match="StateReader v2"):
        _require_reader(object())


def test_current_lane_rejects_cross_lane_handle(
    vertical: DistributedV2Vertical,
) -> None:
    with pytest.raises(Exception):
        _current_lane(vertical.epoch, DistributedLaneV2.CERTIFICATE)


def test_finality_status_rejects_wrong_lane_state(
    vertical: DistributedV2Vertical,
) -> None:
    snapshot = SimpleNamespace(state=object())
    with pytest.raises(TypeError, match="lane state is invalid"):
        _finality_status(
            cast(Any, snapshot),
            vertical.proposal.snapshot,
            vertical.witness.snapshot,
            vertical.epoch.snapshot,
            semantic_value_root=_root("semantic"),
            current_step=10,
        )


def test_finality_status_distinguishes_conflict_unavailable_and_stale(
    vertical: DistributedV2Vertical,
) -> None:
    certificate = cast(
        DistributedCertificateStateV2,
        vertical.certificate.snapshot.state,
    )
    proposal = cast(DistributedProposalStateV2, vertical.proposal.snapshot.state)
    witness = cast(DistributedWitnessStateV2, vertical.witness.snapshot.state)
    epoch = cast(DistributedEpochStateV2, vertical.epoch.snapshot.state)
    semantic = certificate.certificates[0].value.semantic_value_root
    conflict_witness = _forge(witness, equivocations=(_finding(),))
    conflict = _finality_status(
        SimpleNamespace(state=certificate),
        SimpleNamespace(state=proposal),
        SimpleNamespace(state=conflict_witness),
        SimpleNamespace(state=epoch),
        semantic_value_root=semantic,
        current_step=10,
    )
    assert conflict[0] is CommitFinalityStatusV2.CONFLICT
    unavailable = _finality_status(
        SimpleNamespace(state=_forge(certificate, epoch=certificate.epoch + 1)),
        SimpleNamespace(state=proposal),
        SimpleNamespace(state=witness),
        SimpleNamespace(state=epoch),
        semantic_value_root=semantic,
        current_step=10,
    )
    assert unavailable[0] is CommitFinalityStatusV2.UNAVAILABLE
    stale_certificate = _forge(
        certificate.certificates[0],
        witnesses=tuple(
            _forge(item, expires_at_step=10)
            for item in certificate.certificates[0].witnesses
        ),
    )
    stale = _finality_status(
        SimpleNamespace(state=_forge(certificate, certificates=(stale_certificate,))),
        SimpleNamespace(state=proposal),
        SimpleNamespace(state=witness),
        SimpleNamespace(state=epoch),
        semantic_value_root=semantic,
        current_step=10,
    )
    assert stale == (
        CommitFinalityStatusV2.UNAVAILABLE,
        ("distributed_proof_stale",),
    )


def test_finality_status_verified_baseline(
    vertical: DistributedV2Vertical,
) -> None:
    certificate = cast(
        DistributedCertificateStateV2,
        vertical.certificate.snapshot.state,
    )
    result = _finality_status(
        vertical.certificate.snapshot,
        vertical.proposal.snapshot,
        vertical.witness.snapshot,
        vertical.epoch.snapshot,
        semantic_value_root=certificate.certificates[0].value.semantic_value_root,
        current_step=10,
    )
    assert result == (
        CommitFinalityStatusV2.VERIFIED,
        ("distributed_quorum_verified",),
    )


def _committed_view(
    vertical: DistributedV2Vertical,
    lane: DistributedLaneV2 = DistributedLaneV2.PROPOSAL,
) -> GovernanceCommitViewV2:
    request = cast(Any, _request(vertical, lane))
    return vertical.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
    )


def _state_records(
    vertical: DistributedV2Vertical,
    lane: DistributedLaneV2 = DistributedLaneV2.PROPOSAL,
) -> dict[str, object]:
    view = _committed_view(vertical, lane)
    assert view.committed_transition is not None
    transition = view.committed_transition.batch.transition
    assert transition is not None
    return dict(cast(dict[str, object], transition.state_records))


def test_committed_state_records_decode_valid_baseline(
    vertical: DistributedV2Vertical,
) -> None:
    request, snapshot, binding = _decode_state_records_v2(
        _state_records(vertical),
        vertical.context.domain,
    )
    assert request.request_root == vertical.proposal_request.request_root
    assert snapshot.snapshot_root == vertical.proposal.snapshot.snapshot_root
    assert binding["request_root"] == request.request_root


@pytest.mark.parametrize(
    "change",
    (
        {"schema": "unsupported"},
        {"domain_root": "sha256:" + ("0" * 64)},
        {"scope_ref": "scope:other"},
    ),
)
def test_committed_state_records_reject_domain_substitution(
    vertical: DistributedV2Vertical,
    change: dict[str, object],
) -> None:
    records = _state_records(vertical)
    records.update(change)
    with pytest.raises(ValueError, match="domain is mismatched"):
        _decode_state_records_v2(records, vertical.context.domain)


def test_committed_state_records_reject_shape_and_cross_binding(
    vertical: DistributedV2Vertical,
) -> None:
    with pytest.raises(ValueError, match="fields are invalid"):
        _decode_state_records_v2({}, vertical.context.domain)
    records = _state_records(vertical)
    records["request_root"] = _root("wrong-stored-request")
    with pytest.raises(ValueError, match="cross-bound"):
        _decode_state_records_v2(records, vertical.context.domain)


def test_stored_session_binding_rejects_shape_identity_and_grant(
    vertical: DistributedV2Vertical,
) -> None:
    request = vertical.proposal_request
    binding = cast(dict[str, object], _state_records(vertical)["session_binding"])
    with pytest.raises(ValueError, match="fields are invalid"):
        _validate_session_binding({}, request)
    wrong_identity = dict(binding)
    wrong_identity["request_root"] = _root("wrong-session-request")
    with pytest.raises(ValueError, match="session binding is mismatched"):
        _validate_session_binding(wrong_identity, request)
    wrong_grant = dict(binding)
    wrong_grant["grant_ref"] = ""
    with pytest.raises(ValueError, match="grant binding is invalid"):
        _validate_session_binding(wrong_grant, request)


def test_committed_read_set_rejects_duplicate_and_open_set(
    vertical: DistributedV2Vertical,
) -> None:
    view = _committed_view(vertical)
    assert view.committed_transition is not None
    snapshot = vertical.proposal.snapshot
    binding = _validate_session_binding(
        _state_records(vertical)["session_binding"],
        vertical.proposal_request,
    )
    _validate_read_set_v2(view, snapshot, binding)
    read_set = view.committed_transition.batch.read_set
    duplicate = _forge(read_set, entries=(read_set.entries[0], read_set.entries[0]))
    transition = _forge(
        view.committed_transition,
        batch=_forge(view.committed_transition.batch, read_set=duplicate),
    )
    with pytest.raises(ValueError, match="repeats a stream"):
        _validate_read_set_v2(
            _forge(view, committed_transition=transition), snapshot, binding
        )
    incomplete = _forge(read_set, entries=read_set.entries[:-1])
    transition = _forge(
        view.committed_transition,
        batch=_forge(view.committed_transition.batch, read_set=incomplete),
    )
    with pytest.raises(ValueError, match="not closed"):
        _validate_read_set_v2(
            _forge(view, committed_transition=transition), snapshot, binding
        )


def test_state_record_helpers_cover_action_and_head_totality(
    vertical: DistributedV2Vertical,
) -> None:
    assert _required_actions(vertical.proposal.snapshot) == ()
    assert _required_actions(vertical.epoch.snapshot) == ("epoch_transition",)
    invalid_epoch = _forge(vertical.epoch.snapshot, state=object())
    with pytest.raises(TypeError, match="action state is invalid"):
        _required_actions(invalid_epoch)
    missing = vertical.context.store.load_commit_view_v2(
        vertical.proposal_request.scope_ref,
        vertical.proposal_request.stream_ref,
        "transition:missing",
    )
    with pytest.raises(ValueError, match="head is unavailable"):
        _records_head_from_view_v2(missing, vertical.context.domain)


def test_trace_projection_rejects_non_mapping_binding(
    vertical: DistributedV2Vertical,
) -> None:
    with pytest.raises(TypeError, match="session binding is invalid"):
        _distributed_event_v2(
            vertical.proposal_request,
            cast(Any, ()),
            parent_head_root=_root("parent-head"),
            read_set_root=_root("read-set"),
        )
    with pytest.raises(TypeError, match="lane state is invalid"):
        _lane_state_material(object())


def _forged_source(
    request: object,
    *,
    token: object = _SOURCE_TOKEN_V2,
    recipe: object | None = None,
    anchor: str | None = None,
) -> VerifiedDistributedAdvanceSourceV2:
    source = object.__new__(VerifiedDistributedAdvanceSourceV2)
    object.__setattr__(source, "_request", request)
    object.__setattr__(
        source,
        "_recipe",
        object.__new__(_EpochRecipeV2) if recipe is None else recipe,
    )
    object.__setattr__(
        source,
        "_anchor_root",
        object.__getattribute__(request, "request_root") if anchor is None else anchor,
    )
    object.__setattr__(source, "_self_anchor", source)
    object.__setattr__(source, "_token", token)
    return source


def test_source_handle_protocol_totality(
    vertical: DistributedV2Vertical,
) -> None:
    with pytest.raises(TypeError, match="cannot be constructed"):
        VerifiedDistributedAdvanceSourceV2()
    with pytest.raises(TypeError, match="final"):

        class _ForbiddenSource(VerifiedDistributedAdvanceSourceV2):
            pass

    source = _forged_source(vertical.epoch_request)
    assert copy(source) is source
    assert deepcopy(source) is source
    assert "redacted" in repr(source)
    with pytest.raises(AttributeError, match="immutable"):
        source.changed = True  # type: ignore[attr-defined]
    with pytest.raises(TypeError, match="not portable"):
        source.__getstate__()


def test_source_material_rejects_shape_token_and_anchor(
    vertical: DistributedV2Vertical,
) -> None:
    with pytest.raises(TypeError, match="wrong exact type"):
        _verified_source_material_v2(object())
    incomplete = object.__new__(VerifiedDistributedAdvanceSourceV2)
    with pytest.raises(TypeError, match="incomplete"):
        _verified_source_material_v2(incomplete)
    with pytest.raises(TypeError, match="authority token"):
        _verified_source_material_v2(
            _forged_source(vertical.epoch_request, token=object())
        )
    with pytest.raises(ValueError, match="anchor is mismatched"):
        _verified_source_material_v2(
            _forged_source(vertical.epoch_request, anchor=_root("wrong-anchor"))
        )
    with pytest.raises(ValueError, match="anchor is mismatched"):
        _verified_source_material_v2(
            _forged_source(vertical.epoch_request, recipe=object())
        )


def test_source_request_binding_precedes_rebuild(
    vertical: DistributedV2Vertical,
) -> None:
    with pytest.raises(ValueError, match="source request is mismatched"):
        verify_distributed_source_v2(
            vertical.proposal_request,
            source=_forged_source(vertical.epoch_request),
            committed_parent_snapshot=None,
        )


def test_witness_verifier_totality(
    vertical: DistributedV2Vertical,
) -> None:
    proposal = cast(
        DistributedProposalStateV2,
        vertical.proposal.snapshot.state,
    ).proposals[0]
    witness = cast(
        DistributedWitnessStateV2,
        vertical.witness.snapshot.state,
    ).witnesses[0]
    cluster = vertical.identity.membership.snapshot.clusters[0]
    member = cluster.principals[0]
    assert not verify_distributed_witness_v2(
        object(),  # type: ignore[arg-type]
        proposal=proposal,
        member=member,
        cluster_ref=cluster.cluster_ref,
        current_step=10,
        witness_ttl_steps=20,
        trusted_verifier=vertical.verifier,
    )
    assert not verify_distributed_witness_v2(
        witness,
        proposal=proposal,
        member=member,
        cluster_ref=cluster.cluster_ref,
        current_step=10,
        witness_ttl_steps=20,
        trusted_verifier=object(),  # type: ignore[arg-type]
    )
    assert not verify_distributed_witness_v2(
        witness,
        proposal=proposal,
        member=member,
        cluster_ref=cluster.cluster_ref,
        current_step=True,  # type: ignore[arg-type]
        witness_ttl_steps=20,
        trusted_verifier=vertical.verifier,
    )


@pytest.mark.parametrize(
    "witness_changes",
    (
        {"witnessed_at_step": 11},
        {"witnessed_at_step": (2**53 - 1), "expires_at_step": (2**53 - 1)},
        {"expires_at_step": 29},
        {"cluster_ref": "cluster:other"},
    ),
)
def test_witness_verifier_rejects_time_and_binding_substitution(
    vertical: DistributedV2Vertical,
    witness_changes: dict[str, object],
) -> None:
    proposal = cast(
        DistributedProposalStateV2,
        vertical.proposal.snapshot.state,
    ).proposals[0]
    witness = cast(
        DistributedWitnessStateV2,
        vertical.witness.snapshot.state,
    ).witnesses[0]
    cluster = vertical.identity.membership.snapshot.clusters[0]
    member = cluster.principals[0]
    assert not verify_distributed_witness_v2(
        _forge(witness, **witness_changes),
        proposal=proposal,
        member=member,
        cluster_ref=cluster.cluster_ref,
        current_step=10,
        witness_ttl_steps=20,
        trusted_verifier=vertical.verifier,
    )


class _ExplodingVerifier:
    def verify_distributed_witness_v2(self, **_kwargs: object) -> bool:
        raise RuntimeError("unavailable")


class _AlwaysVerifier:
    def verify_distributed_witness_v2(self, **_kwargs: object) -> bool:
        return True


class _TruthyVerifier:
    def verify_distributed_witness_v2(self, **_kwargs: object) -> object:
        return 1


@pytest.mark.parametrize(
    "verifier",
    (_ExplodingVerifier(), _TruthyVerifier()),
)
def test_witness_verifier_requires_exact_true_and_contains_adapter_failure(
    vertical: DistributedV2Vertical,
    verifier: object,
) -> None:
    proposal = cast(
        DistributedProposalStateV2,
        vertical.proposal.snapshot.state,
    ).proposals[0]
    witness = cast(
        DistributedWitnessStateV2,
        vertical.witness.snapshot.state,
    ).witnesses[0]
    cluster = vertical.identity.membership.snapshot.clusters[0]
    assert not verify_distributed_witness_v2(
        witness,
        proposal=proposal,
        member=cluster.principals[0],
        cluster_ref=cluster.cluster_ref,
        current_step=10,
        witness_ttl_steps=20,
        trusted_verifier=cast(Any, verifier),
    )


def test_source_epoch_validation_and_conflict_collection_totality(
    vertical: DistributedV2Vertical,
) -> None:
    membership = vertical.identity.membership.snapshot
    with pytest.raises(TypeError, match="current epoch binding"):
        _validate_epoch_v2(vertical.epoch.snapshot, object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="authority is mismatched"):
        _validate_epoch_v2(
            vertical.epoch.snapshot,
            _forge(membership, membership_root=_root("wrong-membership")),
        )
    with pytest.raises(TypeError, match="parent state is invalid"):
        _epoch_conflicts_v2(
            SimpleNamespace(state=object()),  # type: ignore[arg-type]
            None,
            None,
        )
    finding = _finding()
    witness = _forge(
        vertical.witness.snapshot,
        state=_forge(
            vertical.witness.snapshot.state,
            equivocations=(finding,),
        ),
    )
    certificate = _forge(
        vertical.certificate.snapshot,
        state=_forge(
            vertical.certificate.snapshot.state,
            conflict_roots=(_root("certificate-conflict"),),
        ),
    )
    assert set(_epoch_conflicts_v2(vertical.epoch.snapshot, witness, certificate)) == {
        finding.finding_root,
        _root("certificate-conflict"),
    }


def test_source_member_lookup_totality(
    vertical: DistributedV2Vertical,
) -> None:
    clusters = vertical.identity.membership.snapshot.clusters
    with pytest.raises(TypeError, match="cluster is invalid"):
        _member_v2((object(),), "principal:alpha")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not eligible"):
        _member_v2(clusters, "principal:missing")
    cluster_ref, member = _member_v2(clusters, clusters[0].principals[0].principal_ref)
    assert cluster_ref == clusters[0].cluster_ref
    assert member is clusters[0].principals[0]


def test_verified_witness_selection_skips_unknown_and_untrusted(
    vertical: DistributedV2Vertical,
) -> None:
    proposal = cast(
        DistributedProposalStateV2,
        vertical.proposal.snapshot.state,
    ).proposals[0]
    witness_state = cast(
        DistributedWitnessStateV2,
        vertical.witness.snapshot.state,
    )
    context = SimpleNamespace(
        membership=vertical.identity.membership.snapshot,
        policy_binding=cast(
            DistributedEpochStateV2,
            vertical.epoch.snapshot.state,
        ).transition_certificate.policy_binding,
    )
    assert (
        _verified_witnesses_v2(
            context=cast(Any, context),
            proposals={},
            witness_state=witness_state,
            current_step=10,
            trusted_verifier=vertical.verifier,
        )
        == ()
    )
    assert (
        _verified_witnesses_v2(
            context=cast(Any, context),
            proposals={proposal.proposal_digest: proposal},
            witness_state=witness_state,
            current_step=10,
            trusted_verifier=cast(Any, _TruthyVerifier()),
        )
        == ()
    )


def test_verified_witness_selection_keeps_canonical_principal_record(
    vertical: DistributedV2Vertical,
) -> None:
    proposal = cast(
        DistributedProposalStateV2,
        vertical.proposal.snapshot.state,
    ).proposals[0]
    witness = cast(
        DistributedWitnessStateV2,
        vertical.witness.snapshot.state,
    ).witnesses[0]
    later = _forge(witness, witness_root="sha256:" + ("f" * 64))
    earlier = _forge(witness, witness_root="sha256:" + ("0" * 64))
    witness_state = _forge(
        vertical.witness.snapshot.state,
        witnesses=(later, earlier),
    )
    epoch = cast(DistributedEpochStateV2, vertical.epoch.snapshot.state)
    context = SimpleNamespace(
        membership=vertical.identity.membership.snapshot,
        policy_binding=epoch.transition_certificate.policy_binding,
    )
    selected = _verified_witnesses_v2(
        context=cast(Any, context),
        proposals={proposal.proposal_digest: proposal},
        witness_state=witness_state,
        current_step=10,
        trusted_verifier=cast(Any, _AlwaysVerifier()),
    )
    assert selected == (earlier,)


def test_source_support_manifest_and_parent_boundaries(
    vertical: DistributedV2Vertical,
) -> None:
    membership = vertical.identity.membership.snapshot
    with pytest.raises(TypeError, match="exact scoped manifest"):
        _manifest_for_membership(object(), membership)  # type: ignore[arg-type]
    detached, policy, binding = _manifest_for_membership(
        vertical.context.manifest,
        membership,
    )
    assert detached.manifest_root == vertical.context.manifest.manifest_root
    assert policy is not None
    assert binding.membership_size > 0
    assert _parent_snapshot_v2(None, DistributedLaneV2.EPOCH) is None
    with pytest.raises(ValueError, match="cross-bound"):
        _current_lane_dependency_v2(
            vertical.epoch,
            DistributedDependencyRoleV2.PROPOSAL,
            DistributedLaneV2.PROPOSAL,
        )


def test_lane_dependency_reader_validates_exact_head(
    vertical: DistributedV2Vertical,
) -> None:
    membership = vertical.identity.membership.snapshot
    epoch = cast(DistributedEpochStateV2, vertical.epoch.snapshot.state)
    context = _EpochAuthorityContextV2(
        manifest=vertical.context.manifest,
        policy=_valid_policy(),
        policy_binding=epoch.transition_certificate.policy_binding,
        membership=membership,
        membership_dependency=vertical.epoch.snapshot.dependencies[0],
        verification_dependency=vertical.epoch.snapshot.dependencies[1],
        reader=vertical.context.store,
        domain=vertical.context.domain,
    )
    snapshot, dependency = _lane_dependency_from_reader_v2(
        context,
        role=DistributedDependencyRoleV2.PROPOSAL,
        lane=DistributedLaneV2.PROPOSAL,
    )
    assert snapshot is not None
    assert dependency.revision == vertical.proposal.snapshot.revision
    broken = replace(context, reader=cast(Any, _WrongHeadReader()))
    with pytest.raises(TypeError, match="lane head is invalid"):
        _lane_dependency_from_reader_v2(
            broken,
            role=DistributedDependencyRoleV2.PROPOSAL,
            lane=DistributedLaneV2.PROPOSAL,
        )


class _WrongHeadReader:
    def load_head_v2(self, *_args: object, **_kwargs: object) -> object:
        return object()


def test_authority_context_requires_exact_verified_inputs(
    vertical: DistributedV2Vertical,
) -> None:
    values = {
        "decision_state": vertical.decision,
        "central_certificate_state": vertical.central,
        "membership_state": vertical.identity.membership,
        "manifest": vertical.context.manifest,
        "current_step": 10,
    }
    for field in (
        "decision_state",
        "central_certificate_state",
        "membership_state",
    ):
        invalid = dict(values)
        invalid[field] = object()
        with pytest.raises(TypeError, match="requires verified"):
            _distributed_authority_context_v2(**invalid)


def test_authority_manifest_and_membership_context_totality(
    vertical: DistributedV2Vertical,
) -> None:
    context = _distributed_authority_context_v2(
        decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=vertical.identity.membership,
        manifest=vertical.context.manifest,
        current_step=10,
    )
    with pytest.raises(TypeError, match="exact scoped manifest"):
        _validated_manifest(object(), context.decision)  # type: ignore[arg-type]
    detached, policy, binding = _validated_manifest(
        vertical.context.manifest,
        context.decision,
    )
    assert detached.manifest_root == context.manifest.manifest_root
    assert policy is not None
    with pytest.raises(ValueError, match="membership is cross-bound"):
        _validate_membership_context(
            _forge(context.membership, run_ref="run:substituted"),
            decision=context.decision,
            binding=binding,
            current_step=10,
        )
    stale = _forge(
        context.membership,
        verification_current_step=11,
        verification_expires_at_step=12,
    )
    with pytest.raises(ValueError, match="verification is stale"):
        _validate_membership_context(
            stale,
            decision=context.decision,
            binding=binding,
            current_step=10,
        )


def test_authority_dependency_requires_committed_transition(
    vertical: DistributedV2Vertical,
) -> None:
    missing = vertical.context.store.load_commit_view_v2(
        vertical.proposal_request.scope_ref,
        vertical.proposal_request.stream_ref,
        "transition:missing",
    )
    with pytest.raises(ValueError, match="no committed transition"):
        _dependency(
            DistributedDependencyRoleV2.PROPOSAL,
            missing,
            snapshot_root=_root("missing-snapshot"),
        )


def test_reducer_state_helpers_cover_all_lanes_and_unknown(
    vertical: DistributedV2Vertical,
) -> None:
    for lane in DistributedLaneV2:
        state = cast(Any, _state(vertical, lane))
        assert len(_state_context(state)) == 5
        assert _state_epoch(state) == vertical.epoch.snapshot.current_epoch
    with pytest.raises(TypeError, match="context is unsupported"):
        _state_context(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="epoch is unsupported"):
        _state_epoch(object())  # type: ignore[arg-type]


def test_reducer_parent_lane_and_record_totality(
    vertical: DistributedV2Vertical,
) -> None:
    with pytest.raises(TypeError, match="parent lane is invalid"):
        _require_parent_lane(object(), DistributedLaneV2.EPOCH)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="parent lane is invalid"):
        _require_parent_lane(
            vertical.proposal.snapshot,
            DistributedLaneV2.EPOCH,
        )
    assert _proposal_records(None, 1) == ()
    assert _witness_records(None, 1) == ((), ())
    assert _certificate_records(None, 1) == ((), ())
    assert (
        _proposal_records(
            vertical.proposal.snapshot,
            vertical.proposal.snapshot.current_epoch + 1,
        )
        == ()
    )
    assert _witness_records(
        vertical.witness.snapshot,
        vertical.witness.snapshot.current_epoch + 1,
    ) == ((), ())
    assert _certificate_records(
        vertical.certificate.snapshot,
        vertical.certificate.snapshot.current_epoch + 1,
    ) == ((), ())


def test_epoch_reducer_rejects_prior_genesis_and_wrong_parent_state(
    vertical: DistributedV2Vertical,
) -> None:
    certificate = cast(
        DistributedEpochStateV2,
        vertical.epoch.snapshot.state,
    ).transition_certificate
    dependencies = vertical.epoch.snapshot.dependencies
    with pytest.raises(ValueError, match="initialization has a prior"):
        reduce_epoch_v2(
            certificate=_forge(certificate, from_epoch=0),
            parent=None,
            dependencies=dependencies,
            mutation_ref="mutation:epoch:prior",
            mutation_issuer_ref=certificate.issuer_ref,
        )
    with pytest.raises(TypeError, match="parent state is invalid"):
        reduce_epoch_v2(
            certificate=certificate,
            parent=_forge(vertical.epoch.snapshot, state=object()),
            dependencies=dependencies,
            mutation_ref="mutation:epoch:wrong-state",
            mutation_issuer_ref=certificate.issuer_ref,
        )


def test_epoch_reducer_rejects_parent_mismatch_and_history_erasure(
    vertical: DistributedV2Vertical,
) -> None:
    parent = vertical.epoch.snapshot
    certificate = cast(
        DistributedEpochStateV2,
        parent.state,
    ).transition_certificate
    with pytest.raises(ValueError, match="parent is mismatched"):
        reduce_epoch_v2(
            certificate=certificate,
            parent=parent,
            dependencies=parent.dependencies,
            mutation_ref="mutation:epoch:mismatch",
            mutation_issuer_ref=certificate.issuer_ref,
        )
    history = (_root("committed-conflict"),)
    parent_state = _forge(parent.state, conflict_history_roots=history)
    parent_with_history = _forge(parent, state=parent_state)
    successor = _forge(
        certificate,
        from_epoch=certificate.to_epoch,
        to_epoch=certificate.to_epoch + 1,
        prior_epoch_snapshot_root=parent.snapshot_root,
        conflict_history_roots=(),
    )
    with pytest.raises(ValueError, match="erased conflict history"):
        reduce_epoch_v2(
            certificate=successor,
            parent=parent_with_history,
            dependencies=parent.dependencies,
            mutation_ref="mutation:epoch:erase-history",
            mutation_issuer_ref=certificate.issuer_ref,
        )


def test_conflict_reducer_requires_exact_observation(
    vertical: DistributedV2Vertical,
) -> None:
    with pytest.raises(TypeError, match="exact observation"):
        reduce_witness_conflict_observation_v2(
            observation=object(),  # type: ignore[arg-type]
            parent=vertical.witness.snapshot,
            dependencies=vertical.witness.snapshot.dependencies,
            mutation_ref="mutation:conflict:wrong-type",
            mutation_issuer_ref=vertical.context.grant.issuer_ref,
            current_step=10,
        )


def test_conflict_reducer_rejects_nonfreezing_observation(
    vertical: DistributedV2Vertical,
    observation: object,
) -> None:
    baseline_witness = cast(
        DistributedWitnessStateV2,
        vertical.witness.snapshot.state,
    ).witnesses[0]
    nonconflict = _forge(
        observation,
        witness=baseline_witness,
    )
    with pytest.raises(ValueError, match="only freeze witnesses"):
        reduce_witness_conflict_observation_v2(
            observation=nonconflict,
            parent=vertical.witness.snapshot,
            dependencies=vertical.witness.snapshot.dependencies,
            mutation_ref="mutation:conflict:nonfreezing",
            mutation_issuer_ref=vertical.context.grant.issuer_ref,
            current_step=10,
        )


class _ThrowingHeadStore:
    def load_head_v2(self, *_args: object, **_kwargs: object) -> object:
        raise RuntimeError("load failed")


class _StaticHeadStore:
    def __init__(self, head: object) -> None:
        self.head = head

    def load_head_v2(self, *_args: object, **_kwargs: object) -> object:
        return self.head


class _DelegatingHeadStore:
    def __init__(self, store: object, *, delta: int = 0) -> None:
        self.store = store
        self.delta = delta

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> object:
        head = self.store.load_head_v2(scope_ref, stream_ref)
        if self.delta:
            return _forge(head, revision=head.revision + self.delta)
        return head


def test_operation_request_and_session_validation_totality(
    vertical: DistributedV2Vertical,
) -> None:
    with pytest.raises(TypeError, match="exact request"):
        _require_request(object())
    session, failure = _validated_session(object(), vertical.proposal_request)
    assert session is None
    assert failure is not None


def test_operation_exact_head_load_failures(
    vertical: DistributedV2Vertical,
) -> None:
    request = vertical.proposal_request
    loaded = _load_exact_head(
        cast(Any, _ThrowingHeadStore()),
        vertical.context.domain,
        request,
        request.stream_ref,
    )
    assert isinstance(loaded, GovernanceCommitAttemptV2)
    loaded = _load_exact_head(
        cast(Any, _StaticHeadStore(object())),
        vertical.context.domain,
        request,
        request.stream_ref,
    )
    assert isinstance(loaded, GovernanceCommitAttemptV2)


def test_operation_genesis_parent_rejects_stale_and_bad_lineage(
    vertical: DistributedV2Vertical,
) -> None:
    request = vertical.proposal_request
    current_head = vertical.context.store.load_head_v2(
        request.scope_ref,
        request.stream_ref,
    )
    stale = _load_parent(
        cast(Any, _StaticHeadStore(current_head)),
        vertical.context.domain,
        request,
    )
    assert isinstance(stale, GovernanceCommitAttemptV2)
    genesis = _forge(
        current_head,
        revision=0,
        transition_id="genesis",
    )
    bad_request = _forge(request, parent_transition_id="not-genesis")
    invalid = _load_parent(
        cast(Any, _StaticHeadStore(genesis)),
        vertical.context.domain,
        bad_request,
    )
    assert isinstance(invalid, GovernanceCommitAttemptV2)


def test_operation_non_genesis_parent_loads_current_record(
    vertical: DistributedV2Vertical,
) -> None:
    request = vertical.proposal_request
    current = vertical.proposal.snapshot
    successor = _forge(
        request,
        parent_revision=current.revision,
        parent_transition_id=current.transition_id,
        parent_snapshot_root=current.snapshot_root,
    )
    loaded = _load_parent(
        vertical.context.store,
        vertical.context.domain,
        successor,
    )
    assert not isinstance(loaded, GovernanceCommitAttemptV2)


def test_operation_dependency_heads_reject_stale_and_duplicates(
    vertical: DistributedV2Vertical,
) -> None:
    request = vertical.proposal_request
    stale = _load_dependency_heads(
        cast(Any, _DelegatingHeadStore(vertical.context.store, delta=1)),
        vertical.context.domain,
        request,
    )
    assert isinstance(stale, GovernanceCommitAttemptV2)
    dependency = request.snapshot.dependencies[0]
    duplicate_snapshot = _forge(
        request.snapshot,
        dependencies=(dependency, dependency),
    )
    duplicate_request = _forge(request, snapshot=duplicate_snapshot)
    duplicated = _load_dependency_heads(
        vertical.context.store,
        vertical.context.domain,
        duplicate_request,
    )
    assert isinstance(duplicated, GovernanceCommitAttemptV2)


def test_operation_source_validation_rejects_non_source(
    vertical: DistributedV2Vertical,
) -> None:
    result = _validated_source_and_heads(
        vertical.context.store,
        vertical.context.domain,
        vertical.proposal_request,
        object(),
    )
    assert isinstance(result, GovernanceCommitAttemptV2)


def test_operation_committed_match_contains_invalid_view(
    vertical: DistributedV2Vertical,
) -> None:
    request = vertical.proposal_request
    session = open_distributed_authority_session_v2(
        capability_v2(vertical.context, request.observed_epoch),
        request,
    )
    state, failure = _validated_session(session, request)
    assert failure is None
    assert state is not None
    missing = vertical.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        "transition:missing",
    )
    assert not _committed_view_matches(missing, request, state)


def test_operation_finality_failure_preserves_or_synthesizes_diagnostic(
    vertical: DistributedV2Vertical,
) -> None:
    request = vertical.proposal_request
    missing = vertical.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        "transition:missing",
    )
    synthesized = _finality_failure(request, _forge(missing, failure=None))
    assert synthesized.failure is not None
    if missing.failure is not None:
        preserved = _finality_failure(request, missing)
        assert preserved.failure is not None
        assert preserved.failure.code is missing.failure.code


def test_manifest_guards_distinguish_missing_policy_and_distributed_mode(
    vertical: DistributedV2Vertical,
) -> None:
    context = _distributed_authority_context_v2(
        decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=vertical.identity.membership,
        manifest=vertical.context.manifest,
        current_step=10,
    )
    manifest = vertical.context.manifest
    policy = manifest.collective_commit_policy
    assert policy is not None
    without_policy = replace(manifest, collective_commit_policy=None)
    with pytest.raises(ValueError, match="collective commit policy"):
        _validated_manifest(without_policy, context.decision)
    with pytest.raises(ValueError, match="lacks commit policy"):
        _manifest_for_membership(without_policy, context.membership)
    without_distributed = replace(
        manifest,
        collective_commit_policy=replace(policy, distributed=None),
    )
    with pytest.raises(ValueError, match="static epoch policy"):
        _validated_manifest(without_distributed, context.decision)
    with pytest.raises(ValueError, match="lacks distributed policy"):
        _manifest_for_membership(without_distributed, context.membership)


def test_manifest_guards_reject_cross_bound_policy(
    vertical: DistributedV2Vertical,
) -> None:
    context = _distributed_authority_context_v2(
        decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=vertical.identity.membership,
        manifest=vertical.context.manifest,
        current_step=10,
    )
    changed_decision = _forge(
        context.decision,
        snapshot=_forge(
            context.decision.snapshot,
            manifest_root=_root("substituted-manifest"),
        ),
    )
    with pytest.raises(ValueError, match="manifest is cross-bound"):
        _validated_manifest(vertical.context.manifest, changed_decision)
    with pytest.raises(ValueError, match="manifest is cross-bound"):
        _manifest_for_membership(
            vertical.context.manifest,
            _forge(context.membership, protocol_ref="protocol:substituted"),
        )


def test_epoch_authority_context_rejects_unverified_and_stale_membership(
    vertical: DistributedV2Vertical,
) -> None:
    with pytest.raises(TypeError, match="verified Membership"):
        _epoch_authority_context_v2(
            membership_state=object(),
            manifest=vertical.context.manifest,
            current_step=10,
        )
    membership = vertical.identity.membership.snapshot
    stale_step = membership.verification_expires_at_step
    if stale_step < membership.expires_at_step:
        with pytest.raises(ValueError, match="verification is stale"):
            _epoch_authority_context_v2(
                membership_state=vertical.identity.membership,
                manifest=vertical.context.manifest,
                current_step=stale_step,
            )


def test_source_verification_rebuild_parent_totality(
    vertical: DistributedV2Vertical,
) -> None:
    request, source = prepare_distributed_proposal_v2(
        decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=vertical.identity.membership,
        epoch_state=vertical.epoch,
        manifest=vertical.context.manifest,
        proposal_ref="proposal:distributed:totality:successor",
        proposer_ref="principal:alpha",
        proposal_nonce="nonce:distributed:totality:successor",
        provenance_ref="urn:test:distributed:totality:successor",
        source_trace_roots=(_root("successor-trace"),),
        mutation_ref="mutation:distributed:totality:successor",
        mutation_issuer_ref=vertical.context.grant.issuer_ref,
        current_step=10,
        parent_state=vertical.proposal,
    )
    with pytest.raises(ValueError, match="parent presence"):
        verify_distributed_source_v2(
            request,
            source=source,
            committed_parent_snapshot=None,
        )
    with pytest.raises(ValueError, match="source parent is mismatched"):
        verify_distributed_source_v2(
            request,
            source=source,
            committed_parent_snapshot=vertical.epoch.snapshot,
        )
    recipe = object.__getattribute__(source, "_recipe")
    changed = _forged_source(
        request,
        recipe=_forge(
            recipe,
            proposal_ref="proposal:distributed:totality:changed",
        ),
    )
    with pytest.raises(ValueError, match="replacement changed"):
        verify_distributed_source_v2(
            request,
            source=changed,
            committed_parent_snapshot=vertical.proposal.snapshot,
        )


def test_source_builder_rejects_unknown_recipe() -> None:
    with pytest.raises(TypeError, match="recipe is invalid"):
        _build_recipe_v2(object())  # type: ignore[arg-type]


def test_witness_source_builder_rejects_missing_proposal_and_untrusted_adapter(
    vertical: DistributedV2Vertical,
) -> None:
    proposal = cast(
        DistributedProposalStateV2,
        vertical.proposal.snapshot.state,
    ).proposals[0]
    witness, _ = _signed_witness_v2(
        proposal,
        vertical.identity,
        nonce="nonce:distributed:totality:witness-retry",
        current_step=10,
    )
    request, source = prepare_distributed_witness_v2(
        decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=vertical.identity.membership,
        epoch_state=vertical.epoch,
        proposal_state=vertical.proposal,
        manifest=vertical.context.manifest,
        witness=witness,
        trusted_verifier=vertical.verifier,
        mutation_ref="mutation:distributed:totality:witness-retry",
        mutation_issuer_ref=vertical.context.grant.issuer_ref,
        current_step=10,
        parent_state=vertical.witness,
    )
    recipe = object.__getattribute__(source, "_recipe")
    missing = _forge(
        recipe,
        witness=_forge(witness, proposal_digest=_root("missing-proposal")),
    )
    with pytest.raises(ValueError, match="not current and unique"):
        _build_recipe_v2(missing)
    untrusted = _forge(recipe, trusted_verifier=_TruthyVerifier())
    with pytest.raises(ValueError, match="attestation is not trusted"):
        _build_recipe_v2(untrusted)
    assert request.parent_revision == vertical.witness.snapshot.revision


def test_reducer_parent_state_type_guards(
    vertical: DistributedV2Vertical,
) -> None:
    with pytest.raises(TypeError, match="proposal parent state"):
        _proposal_records(
            _forge(vertical.proposal.snapshot, state=object()),
            vertical.proposal.snapshot.current_epoch,
        )
    with pytest.raises(TypeError, match="witness parent state"):
        _witness_records(
            _forge(vertical.witness.snapshot, state=object()),
            vertical.witness.snapshot.current_epoch,
        )
    with pytest.raises(TypeError, match="certificate parent state"):
        _certificate_records(
            _forge(vertical.certificate.snapshot, state=object()),
            vertical.certificate.snapshot.current_epoch,
        )


def test_reducer_proposal_bound_is_fail_closed(
    vertical: DistributedV2Vertical,
) -> None:
    proposal = cast(
        DistributedProposalStateV2,
        vertical.proposal.snapshot.state,
    ).proposals[0]
    records = tuple(
        _forge(proposal, proposal_digest=f"sha256:{index:064x}") for index in range(256)
    )
    parent = _forge(
        vertical.proposal.snapshot,
        state=_forge(vertical.proposal.snapshot.state, proposals=records),
    )
    with pytest.raises(ValueError, match="proposal state exceeds"):
        reduce_proposal_v2(
            proposal=_forge(proposal, proposal_digest="sha256:" + ("f" * 64)),
            parent=parent,
            dependencies=vertical.proposal.snapshot.dependencies,
            mutation_ref="mutation:proposal:overflow",
            mutation_issuer_ref=vertical.context.grant.issuer_ref,
        )


def test_reducer_witness_bound_is_fail_closed(
    vertical: DistributedV2Vertical,
) -> None:
    witness = cast(
        DistributedWitnessStateV2,
        vertical.witness.snapshot.state,
    ).witnesses[0]
    records = tuple(
        _forge(witness, witness_root=f"sha256:{index:064x}") for index in range(8192)
    )
    parent = _forge(
        vertical.witness.snapshot,
        state=_forge(vertical.witness.snapshot.state, witnesses=records),
    )
    with pytest.raises(ValueError, match="witness state exceeds"):
        reduce_witness_v2(
            witness=_forge(witness, witness_root="sha256:" + ("f" * 64)),
            parent=parent,
            dependencies=vertical.witness.snapshot.dependencies,
            mutation_ref="mutation:witness:overflow",
            mutation_issuer_ref=vertical.context.grant.issuer_ref,
            current_step=10,
        )


def test_reducer_certificate_bound_is_fail_closed(
    vertical: DistributedV2Vertical,
) -> None:
    certificate = cast(
        DistributedCertificateStateV2,
        vertical.certificate.snapshot.state,
    ).certificates[0]
    records = tuple(
        _forge(certificate, certificate_root=f"sha256:{index:064x}")
        for index in range(64)
    )
    parent = _forge(
        vertical.certificate.snapshot,
        state=_forge(vertical.certificate.snapshot.state, certificates=records),
    )
    with pytest.raises(ValueError, match="certificate state exceeds"):
        reduce_certificate_v2(
            certificate=_forge(
                certificate,
                certificate_root="sha256:" + ("f" * 64),
            ),
            parent=parent,
            dependencies=vertical.certificate.snapshot.dependencies,
            mutation_ref="mutation:certificate:overflow",
            mutation_issuer_ref=vertical.context.grant.issuer_ref,
        )


class _ThrowingViewStore:
    def load_commit_view_v2(self, *_args: object, **_kwargs: object) -> object:
        raise RuntimeError("view load failed")


class _StaticViewStore:
    def __init__(self, view: GovernanceCommitViewV2) -> None:
        self.view = view

    def load_commit_view_v2(self, *_args: object, **_kwargs: object) -> object:
        return self.view


def test_operation_open_and_advance_binding_failures(
    vertical: DistributedV2Vertical,
) -> None:
    request = vertical.proposal_request
    with pytest.raises(Exception):
        open_distributed_authority_session_v2(
            capability_v2(vertical.context, request.observed_epoch),
            _forge(request, mutation_issuer_ref="issuer:substituted"),
        )
    attempt = advance_distributed_commit_v2(
        request,
        source=object(),
        authority_session=object(),
    )
    assert attempt.failure is not None


def test_operation_parent_load_exception_and_invalid_view(
    vertical: DistributedV2Vertical,
) -> None:
    request = vertical.proposal_request
    assert isinstance(
        _load_parent(
            cast(Any, _ThrowingHeadStore()),
            vertical.context.domain,
            request,
        ),
        GovernanceCommitAttemptV2,
    )
    successor = _forge(
        request,
        parent_revision=1,
        parent_transition_id=request.transition_id,
        parent_snapshot_root=request.snapshot.snapshot_root,
    )
    assert isinstance(
        _load_parent(
            cast(Any, _ThrowingViewStore()),
            vertical.context.domain,
            successor,
        ),
        GovernanceCommitAttemptV2,
    )
    missing = vertical.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        "transition:missing",
    )
    assert isinstance(
        _load_parent(
            cast(Any, _StaticViewStore(missing)),
            vertical.context.domain,
            successor,
        ),
        GovernanceCommitAttemptV2,
    )


def test_operation_parent_binding_and_dependency_load_failures(
    vertical: DistributedV2Vertical,
) -> None:
    request = vertical.proposal_request
    successor = _forge(
        request,
        parent_revision=vertical.proposal.snapshot.revision,
        parent_transition_id=vertical.proposal.snapshot.transition_id,
        parent_snapshot_root=_root("wrong-parent-snapshot"),
    )
    assert isinstance(
        _load_parent(
            vertical.context.store,
            vertical.context.domain,
            successor,
        ),
        GovernanceCommitAttemptV2,
    )
    assert isinstance(
        _load_dependency_heads(
            cast(Any, _ThrowingHeadStore()),
            vertical.context.domain,
            request,
        ),
        GovernanceCommitAttemptV2,
    )


def test_state_handle_request_mismatch_and_manifest_guard(
    vertical: DistributedV2Vertical,
) -> None:
    with pytest.raises(Exception):
        _load_verified_material(
            vertical.context.store,
            vertical.context.domain,
            _forge(vertical.proposal_request, current_step=11),
            expected_receipt_root=None,
        )
    with pytest.raises(TypeError, match="exact scoped manifest"):
        from pheroos.governance.distributed_commit_v2 import (
            verified_distributed_commit_finality_input_v2,
        )

        verified_distributed_commit_finality_input_v2(
            vertical.certificate,
            proposal_state=vertical.proposal,
            witness_state=vertical.witness,
            epoch_state=vertical.epoch,
            sealed_decision_state=vertical.decision,
            central_certificate_state=vertical.central,
            membership_state=vertical.identity.membership,
            manifest=object(),
            current_step=10,
        )


class _MissingDependencyReader:
    def __init__(self, view: GovernanceCommitViewV2) -> None:
        self.view = view

    def load_commit_view_v2(self, *_args: object, **_kwargs: object) -> object:
        return self.view


def test_state_record_dependency_and_parent_verification_totality(
    vertical: DistributedV2Vertical,
) -> None:
    snapshot = vertical.proposal.snapshot
    missing = vertical.context.store.load_commit_view_v2(
        snapshot.scope_ref,
        snapshot.stream_ref,
        "transition:missing",
    )
    with pytest.raises(ValueError, match="dependency is unavailable"):
        _verify_dependencies(
            _forge(snapshot, dependencies=(snapshot.dependencies[0],)),
            vertical.context.domain,
            cast(Any, _MissingDependencyReader(missing)),
        )
    dependency = snapshot.dependencies[0]
    with pytest.raises(ValueError, match="dependency is mismatched"):
        _verify_dependencies(
            _forge(
                snapshot,
                dependencies=(
                    _forge(dependency, head_root=_root("wrong-dependency-head")),
                ),
            ),
            vertical.context.domain,
            vertical.context.store,
        )
    epoch_dependency = next(
        item
        for item in snapshot.dependencies
        if item.role is DistributedDependencyRoleV2.EPOCH
    )
    proposal_view = _committed_view(vertical, DistributedLaneV2.PROPOSAL)
    with pytest.raises(ValueError, match="dependency lane is mismatched"):
        _dependency_snapshot_root(
            epoch_dependency,
            proposal_view,
            vertical.context.domain,
            vertical.context.store,
        )
    child = _forge(
        snapshot,
        parent_revision=snapshot.revision,
        parent_transition_id=snapshot.transition_id,
        parent_snapshot_root=snapshot.snapshot_root,
        parent_history_root=_root("wrong-parent-history"),
        parent_history_count=snapshot.history_count,
    )
    with pytest.raises(ValueError, match="parent history is mismatched"):
        _verify_parent(child, vertical.context.domain, vertical.context.store)


def test_witness_verifier_overflow_guard(
    vertical: DistributedV2Vertical,
) -> None:
    proposal = cast(
        DistributedProposalStateV2,
        vertical.proposal.snapshot.state,
    ).proposals[0]
    witness = cast(
        DistributedWitnessStateV2,
        vertical.witness.snapshot.state,
    ).witnesses[0]
    cluster = vertical.identity.membership.snapshot.clusters[0]
    assert not verify_distributed_witness_v2(
        _forge(
            witness,
            witnessed_at_step=(2**53 - 1),
            expires_at_step=2**53,
        ),
        proposal=proposal,
        member=cluster.principals[0],
        cluster_ref=cluster.cluster_ref,
        current_step=(2**53 - 1),
        witness_ttl_steps=20,
        trusted_verifier=vertical.verifier,
    )


def test_changed_contract_byte_bounds_remain_fail_closed(
    vertical: DistributedV2Vertical,
    observation: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    oversized = b"x" * (32 * 1024 * 1024 + 1)
    certificate = cast(
        DistributedCertificateStateV2,
        vertical.certificate.snapshot.state,
    ).certificates[0]
    proposal = cast(
        DistributedProposalStateV2,
        vertical.proposal.snapshot.state,
    ).proposals[0]
    proposal_snapshot = vertical.proposal.snapshot

    monkeypatch.setattr(
        certificate_contracts_module, "_canonical_bytes", lambda _: oversized
    )
    with pytest.raises(ValueError, match="certificate exceeds its byte bound"):
        replace(certificate, certificate_root="")

    monkeypatch.setattr(
        conflict_contracts_module, "_canonical_bytes", lambda _: oversized
    )
    with pytest.raises(ValueError, match="observation exceeds its byte bound"):
        replace(cast(Any, observation), observation_root="")

    monkeypatch.setattr(
        proposal_contracts_module, "_canonical_bytes", lambda _: oversized
    )
    with pytest.raises(ValueError, match="semantic value exceeds its byte bound"):
        replace(proposal.value, semantic_value_root="")

    monkeypatch.setattr(state_contracts_module, "_canonical_bytes", lambda _: oversized)
    with pytest.raises(ValueError, match="snapshot exceeds its byte bound"):
        _replace_snapshot(proposal_snapshot)


def test_changed_opaque_protocol_methods_are_explicitly_nonportable(
    vertical: DistributedV2Vertical,
) -> None:
    _, source = prepare_distributed_proposal_v2(
        decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=vertical.identity.membership,
        epoch_state=vertical.epoch,
        manifest=vertical.context.manifest,
        proposal_ref="proposal:distributed:totality:reduce",
        proposer_ref="principal:alpha",
        proposal_nonce="nonce:distributed:totality:reduce",
        provenance_ref="urn:test:distributed:totality:reduce",
        source_trace_roots=(_root("reduce-trace"),),
        mutation_ref="mutation:distributed:totality:reduce",
        mutation_issuer_ref=vertical.context.grant.issuer_ref,
        current_step=10,
        parent_state=vertical.proposal,
    )
    with pytest.raises(TypeError, match="not portable"):
        source.__reduce__()
    with pytest.raises(TypeError, match="not portable"):
        vertical.proposal.__reduce__()


def test_changed_state_handle_load_failures_are_fail_closed(
    vertical: DistributedV2Vertical,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = vertical.proposal_request
    with pytest.raises(Exception, match="governance_committed_transition_invalid"):
        _load_verified_material(
            cast(Any, _ThrowingViewStore()),
            vertical.context.domain,
            request,
            expected_receipt_root=None,
        )

    current = _committed_view(vertical)
    finality_unavailable = _forge(
        current,
        disposition=state_handle_module.GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
    )
    monkeypatch.setattr(
        state_handle_module, "_canonical_commit_view_v2", lambda view: view
    )
    with pytest.raises(Exception, match="governance_finality_unavailable"):
        _load_verified_material(
            cast(Any, _StaticViewStore(finality_unavailable)),
            vertical.context.domain,
            request,
            expected_receipt_root=None,
        )

    def reject_decode(*_args: object, **_kwargs: object) -> object:
        raise ValueError("invalid committed transition")

    monkeypatch.setattr(
        state_handle_module,
        "_decode_committed_distributed_view_v2",
        reject_decode,
    )
    with pytest.raises(Exception, match="governance_committed_transition_invalid"):
        _load_verified_material(
            cast(Any, _StaticViewStore(current)),
            vertical.context.domain,
            request,
            expected_receipt_root=None,
        )


def test_changed_current_state_and_reader_protocol_guards(
    vertical: DistributedV2Vertical,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = vertical.proposal.snapshot
    current = _committed_view(vertical)
    assert current.position_observation is not None
    stale_view = _forge(
        current,
        position_observation=_forge(
            current.position_observation,
            position=GovernanceCommitPositionV2.SUPERSEDED,
        ),
    )
    monkeypatch.setattr(
        state_handle_module,
        "_verified_distributed_state_material_v2",
        lambda _state: SimpleNamespace(
            snapshot=snapshot,
            view=stale_view,
        ),
    )
    with pytest.raises(Exception, match="governance_read_set_stale"):
        require_current_distributed_state_v2(vertical.proposal)

    class _ExplodingReaderMeta(type):
        def __instancecheck__(cls, _instance: object) -> bool:
            raise RuntimeError("reader protocol exploded")

    class _ExplodingReaderProtocol(metaclass=_ExplodingReaderMeta):
        pass

    monkeypatch.setattr(
        state_handle_module,
        "GovernanceStateReaderV2",
        _ExplodingReaderProtocol,
    )
    with pytest.raises(TypeError, match="StateReader v2"):
        state_handle_module._require_reader(object())


def test_changed_committed_record_guards_reject_partial_material(
    vertical: DistributedV2Vertical,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    view = _committed_view(vertical)
    assert view.committed_transition is not None
    committed = view.committed_transition
    monkeypatch.setattr(
        state_records_module, "_canonical_commit_view_v2", lambda item: item
    )

    without_transition = _forge(
        view,
        committed_transition=_forge(
            committed,
            batch=_forge(committed.batch, transition=None),
        ),
    )
    with pytest.raises(ValueError, match="state transition is unavailable"):
        state_records_module._decode_committed_distributed_view_v2(
            without_transition,
            vertical.context.domain,
            reader=None,
        )

    wrong_receipt = _forge(
        view,
        committed_transition=_forge(
            committed,
            receipt=_forge(committed.receipt, stream_ref="stream:substituted"),
        ),
    )
    with pytest.raises(ValueError, match="receipt is cross-bound"):
        state_records_module._decode_committed_distributed_view_v2(
            wrong_receipt,
            vertical.context.domain,
            reader=None,
        )

    wrong_trace = _forge(
        view,
        committed_transition=_forge(
            committed,
            batch=_forge(
                committed.batch,
                trace_batch=_forge(
                    committed.batch.trace_batch,
                    _event_snapshots=(),
                ),
            ),
        ),
    )
    with pytest.raises(ValueError, match="Trace lineage is mismatched"):
        state_records_module._decode_committed_distributed_view_v2(
            wrong_trace,
            vertical.context.domain,
            reader=None,
        )


def _proposal_successor(
    vertical: DistributedV2Vertical,
    label: str,
) -> tuple[object, VerifiedDistributedAdvanceSourceV2]:
    return prepare_distributed_proposal_v2(
        decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=vertical.identity.membership,
        epoch_state=vertical.epoch,
        manifest=vertical.context.manifest,
        proposal_ref=f"proposal:distributed:totality:{label}",
        proposer_ref="principal:alpha",
        proposal_nonce=f"nonce:distributed:totality:{label}",
        provenance_ref=f"urn:test:distributed:totality:{label}",
        source_trace_roots=(_root(f"{label}-trace"),),
        mutation_ref=f"mutation:distributed:totality:{label}",
        mutation_issuer_ref=vertical.context.grant.issuer_ref,
        current_step=10,
        parent_state=vertical.proposal,
    )


def test_changed_distributed_authority_rechecks_finality_and_heads(
    vertical: DistributedV2Vertical,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        authority_context_module,
        "_verified_commit_certificate_finality_context_material_v2",
        lambda _context: SimpleNamespace(
            projection=SimpleNamespace(status=SimpleNamespace(value="unavailable"))
        ),
    )
    with pytest.raises(ValueError, match="verified central certificate"):
        _distributed_authority_context_v2(
            decision_state=vertical.decision,
            central_certificate_state=vertical.central,
            membership_state=vertical.identity.membership,
            manifest=vertical.context.manifest,
            current_step=10,
        )

    monkeypatch.undo()
    original_dependency = authority_context_module._dependency

    def changed_dependency(
        role: DistributedDependencyRoleV2,
        view: object,
        *,
        snapshot_root: str,
    ) -> DistributedDependencyV2:
        dependency = original_dependency(role, view, snapshot_root=snapshot_root)
        if role is DistributedDependencyRoleV2.MEMBERSHIP:
            return _forge(dependency, revision=dependency.revision + 1)
        return dependency

    monkeypatch.setattr(authority_context_module, "_dependency", changed_dependency)
    with pytest.raises(ValueError, match="heads changed during preparation"):
        _distributed_authority_context_v2(
            decision_state=vertical.decision,
            central_certificate_state=vertical.central,
            membership_state=vertical.identity.membership,
            manifest=vertical.context.manifest,
            current_step=10,
        )


def test_changed_epoch_context_rechecks_verification_window_and_heads(
    vertical: DistributedV2Vertical,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_material = source_support_module._membership_parent_authority_material_v2
    membership, membership_precondition, verification_precondition = original_material(
        vertical.identity.membership
    )
    stale_membership = _forge(
        membership,
        verification_current_step=0,
        verification_expires_at_step=10,
    )
    monkeypatch.setattr(
        source_support_module,
        "_membership_parent_authority_material_v2",
        lambda _state: (
            stale_membership,
            membership_precondition,
            verification_precondition,
        ),
    )
    monkeypatch.setattr(
        source_support_module,
        "validate_distributed_membership_v2",
        lambda *_args, **_kwargs: None,
    )
    with pytest.raises(ValueError, match="verification is stale"):
        _epoch_authority_context_v2(
            membership_state=vertical.identity.membership,
            manifest=vertical.context.manifest,
            current_step=10,
        )

    monkeypatch.undo()
    original_dependency = source_support_module._dependency

    def changed_dependency(
        role: DistributedDependencyRoleV2,
        view: object,
        *,
        snapshot_root: str,
    ) -> DistributedDependencyV2:
        dependency = original_dependency(role, view, snapshot_root=snapshot_root)
        if role is DistributedDependencyRoleV2.MEMBERSHIP:
            return _forge(dependency, revision=dependency.revision + 1)
        return dependency

    monkeypatch.setattr(source_support_module, "_dependency", changed_dependency)
    with pytest.raises(ValueError, match="changed during preparation"):
        _epoch_authority_context_v2(
            membership_state=vertical.identity.membership,
            manifest=vertical.context.manifest,
            current_step=10,
        )


def test_changed_lane_dependency_rejects_stale_mismatched_and_raced_views(
    vertical: DistributedV2Vertical,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    material = state_handle_module._verified_distributed_state_material_v2(
        vertical.proposal
    )
    assert material.view.position_observation is not None
    stale_material = _forge(
        material,
        view=_forge(
            material.view,
            position_observation=_forge(
                material.view.position_observation,
                position=GovernanceCommitPositionV2.SUPERSEDED,
            ),
        ),
    )
    monkeypatch.setattr(
        source_support_module,
        "_verified_distributed_state_material_v2",
        lambda _state: stale_material,
    )
    with pytest.raises(ValueError, match="lane dependency is stale"):
        _current_lane_dependency_v2(
            vertical.proposal,
            DistributedDependencyRoleV2.PROPOSAL,
            DistributedLaneV2.PROPOSAL,
        )

    monkeypatch.undo()
    context = _epoch_authority_context_v2(
        membership_state=vertical.identity.membership,
        manifest=vertical.context.manifest,
        current_step=10,
    )
    proposal_snapshot = vertical.proposal.snapshot
    monkeypatch.setattr(
        source_support_module,
        "_decode_committed_distributed_view_v2",
        lambda *_args, **_kwargs: (
            vertical.proposal_request,
            _forge(proposal_snapshot, lane=DistributedLaneV2.WITNESS),
            {},
        ),
    )
    with pytest.raises(ValueError, match="current lane dependency is mismatched"):
        _lane_dependency_from_reader_v2(
            context,
            role=DistributedDependencyRoleV2.PROPOSAL,
            lane=DistributedLaneV2.PROPOSAL,
        )

    monkeypatch.undo()
    context = _epoch_authority_context_v2(
        membership_state=vertical.identity.membership,
        manifest=vertical.context.manifest,
        current_step=10,
    )

    class _RacedReader:
        def load_head_v2(self, scope_ref: str, stream_ref: str) -> object:
            return _forge(
                context.reader.load_head_v2(scope_ref, stream_ref),
                head_root=_root("raced-lane-head"),
            )

        def load_commit_view_v2(self, *args: object, **kwargs: object) -> object:
            return context.reader.load_commit_view_v2(*args, **kwargs)

    raced_context = replace(context, reader=cast(Any, _RacedReader()))
    monkeypatch.setattr(
        source_support_module,
        "_decode_committed_distributed_view_v2",
        lambda *_args, **_kwargs: (
            vertical.proposal_request,
            proposal_snapshot,
            {},
        ),
    )
    with pytest.raises(ValueError, match="lane head changed during preparation"):
        _lane_dependency_from_reader_v2(
            raced_context,
            role=DistributedDependencyRoleV2.PROPOSAL,
            lane=DistributedLaneV2.PROPOSAL,
        )


def test_changed_operation_session_and_precondition_failures(
    vertical: DistributedV2Vertical,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, source = _proposal_successor(vertical, "operation-guards")
    request = cast(Any, request)
    session = open_distributed_authority_session_v2(
        capability_v2(vertical.context, request.observed_epoch),
        request,
    )

    monkeypatch.setattr(
        operations_module,
        "_current_session_grant_failure",
        lambda _session: (
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED,
            "/authority_session/grant",
        ),
    )
    attempt = advance_distributed_commit_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert attempt.failure is not None
    assert attempt.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED

    monkeypatch.undo()
    monkeypatch.setattr(
        operations_module,
        "_current_session_lifecycle_failure",
        lambda _session: (
            AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED,
            "/authority_session/lifecycle",
        ),
    )
    attempt = advance_distributed_commit_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert attempt.failure is not None
    assert attempt.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED

    monkeypatch.undo()
    state, failure = _validated_session(session, request)
    assert state is not None and failure is None
    mismatched_state, mismatched = _validated_session(
        session,
        _forge(request, request_root=_root("mismatched-session-request")),
    )
    assert mismatched_state is None
    assert mismatched is not None

    def type_error(_candidate: object) -> object:
        raise TypeError("invalid session implementation")

    monkeypatch.setattr(
        operations_module,
        "_governance_authority_session_state_v2",
        type_error,
    )
    invalid_state, invalid = _validated_session(session, request)
    assert invalid_state is None
    assert invalid is not None


def test_changed_operation_source_and_parent_failures(
    vertical: DistributedV2Vertical,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, source = _proposal_successor(vertical, "source-guards")
    request = cast(Any, request)
    missing = vertical.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        "transition:missing",
    )
    dependency_failure = _finality_failure(request, missing)
    monkeypatch.setattr(
        operations_module,
        "_load_dependency_heads",
        lambda *_args: dependency_failure,
    )
    assert (
        _validated_source_and_heads(
            vertical.context.store,
            vertical.context.domain,
            request,
            source,
        )
        is dependency_failure
    )

    monkeypatch.undo()
    monkeypatch.setattr(
        operations_module,
        "verify_distributed_source_v2",
        lambda *_args, **_kwargs: _forge(
            request.snapshot,
            current_step=request.snapshot.current_step + 1,
        ),
    )
    mismatched = _validated_source_and_heads(
        vertical.context.store,
        vertical.context.domain,
        request,
        source,
    )
    assert isinstance(mismatched, GovernanceCommitAttemptV2)

    monkeypatch.undo()
    current = _committed_view(vertical)
    finality = _forge(
        current,
        disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
    )
    monkeypatch.setattr(
        operations_module, "_canonical_commit_view_v2", lambda view: view
    )
    successor = _forge(
        request,
        parent_revision=vertical.proposal.snapshot.revision,
        parent_transition_id=vertical.proposal.snapshot.transition_id,
        parent_snapshot_root=vertical.proposal.snapshot.snapshot_root,
    )
    parent_failure = _load_parent(
        cast(Any, _StaticViewStore(finality)),
        vertical.context.domain,
        successor,
    )
    assert isinstance(parent_failure, GovernanceCommitAttemptV2)


def _witness_recipe(
    vertical: DistributedV2Vertical,
    label: str,
) -> object:
    proposal = cast(
        DistributedProposalStateV2,
        vertical.proposal.snapshot.state,
    ).proposals[0]
    witness, _ = _signed_witness_v2(
        proposal,
        vertical.identity,
        nonce=f"nonce:distributed:totality:{label}",
        current_step=10,
    )
    _, source = prepare_distributed_witness_v2(
        decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=vertical.identity.membership,
        epoch_state=vertical.epoch,
        proposal_state=vertical.proposal,
        manifest=vertical.context.manifest,
        witness=witness,
        trusted_verifier=vertical.verifier,
        mutation_ref=f"mutation:distributed:totality:{label}",
        mutation_issuer_ref=vertical.context.grant.issuer_ref,
        current_step=10,
        parent_state=vertical.witness,
    )
    return object.__getattribute__(source, "_recipe")


def _conflict_recipe(
    vertical: DistributedV2Vertical,
    observation: object,
) -> _WitnessConflictObservationRecipeV2:
    return _WitnessConflictObservationRecipeV2(
        decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=vertical.identity.membership,
        epoch_state=vertical.epoch,
        proposal_state=vertical.proposal,
        parent_state=vertical.witness,
        manifest=vertical.context.manifest,
        observation=cast(Any, observation),
        trusted_verifier=vertical.verifier,
        mutation_ref="mutation:distributed:totality:conflict-guards",
        mutation_issuer_ref=vertical.context.grant.issuer_ref,
        current_step=10,
    )


def _certificate_recipe(vertical: DistributedV2Vertical) -> _CertificateRecipeV2:
    return _CertificateRecipeV2(
        decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=vertical.identity.membership,
        epoch_state=vertical.epoch,
        proposal_state=vertical.proposal,
        witness_state=vertical.witness,
        parent_state=vertical.certificate,
        manifest=vertical.context.manifest,
        trusted_verifier=vertical.verifier,
        certificate_ref="certificate:distributed:totality:input-guards",
        provenance_ref="urn:test:distributed:totality:input-guards",
        mutation_ref="mutation:distributed:totality:input-guards",
        mutation_issuer_ref=vertical.context.grant.issuer_ref,
        current_step=10,
    )


def _replace_lane_state(
    original: object,
    target: DistributedLaneV2,
    replacement: object,
) -> object:
    snapshot, dependency = cast(Any, original)
    if snapshot.lane is target:
        snapshot = _forge(snapshot, state=replacement)
    return snapshot, dependency


def test_changed_epoch_builder_rejects_a_raced_parent(
    vertical: DistributedV2Vertical,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipe = _EpochRecipeV2(
        membership_state=vertical.identity.membership,
        manifest=vertical.context.manifest,
        parent_state=vertical.epoch,
        transition_certificate_ref="certificate:distributed:epoch:raced-parent",
        mutation_ref="mutation:distributed:epoch:raced-parent",
        mutation_issuer_ref=vertical.context.grant.issuer_ref,
        current_step=10,
        provenance_ref="urn:test:distributed:epoch:raced-parent",
        source_trace_roots=(_root("epoch-raced-parent-trace"),),
    )
    monkeypatch.setattr(
        source_builders_module,
        "_parent_snapshot_v2",
        lambda *_args: _forge(
            vertical.epoch.snapshot,
            revision=vertical.epoch.snapshot.revision + 1,
        ),
    )
    with pytest.raises(ValueError, match="epoch parent is stale"):
        _build_recipe_v2(recipe)


def test_changed_witness_builder_rejects_a_nonproposal_lane_state(
    vertical: DistributedV2Vertical,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipe = _witness_recipe(vertical, "invalid-proposal-state")
    original = source_builders_module._current_lane_dependency_v2

    def invalid_proposal(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)
        lane = cast(DistributedLaneV2, args[2])
        return (
            _replace_lane_state(result, lane, object())
            if lane is DistributedLaneV2.PROPOSAL
            else result
        )

    monkeypatch.setattr(
        source_builders_module,
        "_current_lane_dependency_v2",
        invalid_proposal,
    )
    with pytest.raises(TypeError, match="proposal state is invalid"):
        _build_recipe_v2(cast(Any, recipe))


def test_changed_conflict_builder_guards_are_fail_closed(
    vertical: DistributedV2Vertical,
    observation: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipe = _conflict_recipe(vertical, observation)
    with pytest.raises(ValueError, match="observation step is mismatched"):
        _build_recipe_v2(replace(recipe, current_step=11))

    original = source_builders_module._current_lane_dependency_v2

    def invalid_proposal(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)
        lane = cast(DistributedLaneV2, args[2])
        return (
            _replace_lane_state(result, lane, object())
            if lane is DistributedLaneV2.PROPOSAL
            else result
        )

    monkeypatch.setattr(
        source_builders_module,
        "_current_lane_dependency_v2",
        invalid_proposal,
    )
    with pytest.raises(TypeError, match="conflict proposal state is invalid"):
        _build_recipe_v2(recipe)

    monkeypatch.undo()
    original = source_builders_module._current_lane_dependency_v2

    def empty_proposals(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)
        snapshot, _ = cast(Any, result)
        if snapshot.lane is DistributedLaneV2.PROPOSAL:
            return _replace_lane_state(
                result,
                DistributedLaneV2.PROPOSAL,
                _forge(snapshot.state, proposals=()),
            )
        return result

    monkeypatch.setattr(
        source_builders_module,
        "_current_lane_dependency_v2",
        empty_proposals,
    )
    with pytest.raises(ValueError, match="lacks the current local proposal"):
        _build_recipe_v2(recipe)

    monkeypatch.undo()
    monkeypatch.setattr(
        source_builders_module,
        "_parent_snapshot_v2",
        lambda *_args: None,
    )
    with pytest.raises(ValueError, match="durable witness parent"):
        _build_recipe_v2(recipe)

    monkeypatch.undo()
    monkeypatch.setattr(
        source_builders_module,
        "_parent_snapshot_v2",
        lambda *_args: _forge(
            vertical.witness.snapshot,
            state=_forge(vertical.witness.snapshot.state, witnesses=()),
        ),
    )
    with pytest.raises(ValueError, match="lacks prior current-value witness"):
        _build_recipe_v2(recipe)


def test_changed_certificate_builder_rejects_invalid_or_frozen_inputs(
    vertical: DistributedV2Vertical,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipe = _certificate_recipe(vertical)
    original = source_builders_module._current_lane_dependency_v2

    def invalid_proposal(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)
        snapshot, _ = cast(Any, result)
        if snapshot.lane is DistributedLaneV2.PROPOSAL:
            return _replace_lane_state(result, DistributedLaneV2.PROPOSAL, object())
        return result

    monkeypatch.setattr(
        source_builders_module,
        "_current_lane_dependency_v2",
        invalid_proposal,
    )
    with pytest.raises(TypeError, match="certificate input state is invalid"):
        _build_recipe_v2(recipe)

    monkeypatch.undo()
    original = source_builders_module._current_lane_dependency_v2

    def invalid_witness(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)
        snapshot, _ = cast(Any, result)
        if snapshot.lane is DistributedLaneV2.WITNESS:
            return _replace_lane_state(result, DistributedLaneV2.WITNESS, object())
        return result

    monkeypatch.setattr(
        source_builders_module,
        "_current_lane_dependency_v2",
        invalid_witness,
    )
    with pytest.raises(TypeError, match="certificate input state is invalid"):
        _build_recipe_v2(recipe)

    monkeypatch.undo()
    original = source_builders_module._current_lane_dependency_v2

    def frozen_witness(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)
        snapshot, _ = cast(Any, result)
        if snapshot.lane is DistributedLaneV2.WITNESS:
            return _replace_lane_state(
                result,
                DistributedLaneV2.WITNESS,
                _forge(snapshot.state, equivocations=(_finding(),)),
            )
        return result

    monkeypatch.setattr(
        source_builders_module,
        "_current_lane_dependency_v2",
        frozen_witness,
    )
    with pytest.raises(ValueError, match="frozen witnesses"):
        _build_recipe_v2(recipe)
