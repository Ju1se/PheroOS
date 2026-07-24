from __future__ import annotations

from dataclasses import fields, replace
from types import SimpleNamespace
from typing import Any

import pytest

import pheroos.governance as governance
from pheroos.governance._distributed._certificate_contract import (
    _validate_certificate_proposal_binding,
    _validate_certificate_state_binding,
    _validate_receipt_state_binding,
)
from pheroos.governance._distributed._epoch_contract import _require_action_gate
from pheroos.governance._distributed._finality_contract import (
    _validate_outcome_state_binding,
)
from pheroos.governance._distributed._membership_contract import (
    _portable_snapshot_payload_unchecked,
    _validate_membership_policy,
    _validate_portable_membership_snapshot,
)
from pheroos.governance._distributed._proposal_contract import (
    _validate_receipt_certificate_lineage,
    _validate_proposal_certificate_lineage,
    _validate_proposal_membership,
    distributed_commit_value_payload_from_mapping,
    validate_distributed_commit_value_payload,
    validate_distributed_commit_proposal,
)
from pheroos.governance._distributed._state_contract import (
    _validate_proposal_state_binding,
    _validate_verification_state_binding,
)
from pheroos.governance._distributed._witness_contract import (
    _attestation_matches,
    _validate_witness_proposal_binding,
    validate_quorum_witness,
)
from pheroos.governance._distributed.certificate import (
    _distributed_certificate_body_root,
    _validate_distributed_commit_certificate,
)
from pheroos.governance._distributed.invariants import (
    _canonical_fingerprints,
    _coerce_assurance,
    _coerce_authority,
    _public_dataclass_payload,
    _require_mapping,
    _require_sequence,
    _strict_dataclass_payload,
    _validate_distributed_policy,
)
from pheroos.governance._distributed.state import _current_distributed_state_head
from pheroos.governance._distributed.witness import _validate_witness_verification
from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.distributed_commit import (
    DISTRIBUTED_COMMIT_VALUE_VERSION,
    DISTRIBUTED_PROPOSAL_VERSION,
    QUORUM_WITNESS_VERSION,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    CERTIFIED_COMMIT_PROFILE_VERSION,
    DISTRIBUTED_COMMIT_PROFILE_VERSION,
    CommitAction,
    CommitAssurance,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from tests.governance.test_distributed_commit import (
    _fingerprint,
    _public_action_gate,
    _public_membership,
    _public_portable_scenario,
    _portable_semantic_conflict,
)


@pytest.fixture(scope="module")
def portable_bundle() -> Any:
    return _public_portable_scenario("legacy-totality")


def _view(value: object, **changes: object) -> SimpleNamespace:
    payload = {
        item.name: getattr(value, item.name)
        for item in fields(value)
        if not item.name.startswith("_")
    }
    payload.update(changes)
    return SimpleNamespace(**payload)


def _portable_certificate_clone(bundle: Any) -> Any:
    return governance.distributed_commit_certificate_from_payload(
        governance.distributed_commit_certificate_payload(bundle.certificate)
    )


def _verify_portable_certificate(certificate: object, bundle: Any) -> bool:
    return governance.verify_distributed_commit_certificate(
        certificate,  # type: ignore[arg-type]
        commit_policy=bundle.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
    )


def _register_portable_certificate(state: object, bundle: Any) -> Any:
    return governance.register_distributed_commit_certificate(
        state,  # type: ignore[arg-type]
        bundle.certificate,
        commit_policy=bundle.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        current_step=6,
    )


def _next_public_membership(bundle: Any, label: str) -> tuple[Any, Any]:
    _, snapshot, epoch_state = _public_membership(
        label=label,
        policy=bundle.policy,
        manifest_root=bundle.state.manifest_root,
        protocol_id=bundle.state.protocol_id,
        run_id=bundle.state.run_id,
        epoch=bundle.state.epoch + 1,
    )
    return snapshot, epoch_state


def _freeze_public_bundle(bundle: Any) -> Any:
    registered = _register_portable_certificate(bundle.state, bundle)
    facade = SimpleNamespace(
        portable_certificate=bundle.portable_certificate,
        scenario=SimpleNamespace(
            run_id=bundle.state.run_id,
            membership_snapshot=bundle.membership_snapshot,
            policy=bundle.policy,
        ),
        proposal=bundle.proposal,
        issuer_trust=bundle.issuer_trust,
        witness_trust=bundle.witness_trust,
        principals=bundle.principals,
    )
    (
        _,
        conflict_portable,
        conflict_issuer_trust,
        conflict_witness_trust,
        conflict_certificate,
    ) = _portable_semantic_conflict(
        facade,
        field_name="claim_fingerprint",
        field_value=_fingerprint(f"claim:conflict:{bundle.state.run_id}"),
        suffix="legacy-totality-conflict",
    )
    return governance.register_distributed_commit_certificate(
        registered,
        conflict_certificate,
        commit_policy=bundle.policy,
        portable_certificate=conflict_portable,
        trusted_issuer_attestations=conflict_issuer_trust,
        trusted_witness_attestations=conflict_witness_trust,
        current_step=6,
    )


def _transition_public_bundle(bundle: Any) -> Any:
    snapshot, epoch_state = _next_public_membership(
        bundle,
        "legacy-totality-transition:new",
    )
    decision_ref = governance.epoch_transition_decision_ref(
        bundle.state,
        snapshot,
        epoch_state,
        commit_policy=bundle.policy,
    )
    stop, permission = _public_action_gate(
        bundle,
        action=CommitAction.EPOCH_TRANSITION,
        decision_ref=decision_ref,
        suffix="totality-transition",
    )
    metadata = {
        "certificate_id": "epoch-transition:legacy-totality:transition",
        "issuer_id": "governance:legacy-totality",
        "authority": AuthorityLevel.GOVERNANCE,
        "issued_at_step": 8,
        "provenance": "urn:test:legacy-totality:transition",
        "trace_event_id": "trace:legacy-totality:transition",
    }
    body_root = governance.epoch_transition_certificate_body_root(
        bundle.state,
        snapshot,
        epoch_state,
        stop,
        permission,
        commit_policy=bundle.policy,
        **metadata,
    )
    attestation_ref = "attestation:legacy-totality:transition"
    certificate = governance.issue_epoch_transition_certificate(
        bundle.state,
        snapshot,
        epoch_state,
        stop,
        permission,
        commit_policy=bundle.policy,
        issuer_attestation_refs=(attestation_ref,),
        trusted_issuer_attestations={attestation_ref: body_root},
        **metadata,
    )
    transitioned, _ = governance.transition_distributed_commit_epoch(
        bundle.state,
        certificate,
        snapshot,
        epoch_state,
        commit_policy=bundle.policy,
        trusted_issuer_attestations={attestation_ref: body_root},
        issuer_id="governance:legacy-totality:new-state",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:legacy-totality:new-state",
        trace_event_id="trace:legacy-totality:new-state",
    )
    return transitioned


class _ExplodingLock:
    def __enter__(self) -> None:
        raise RuntimeError("corrupt distributed state lock")

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        return None


def test_contract_bindings_report_each_distinct_lineage_failure(
    portable_bundle: Any,
) -> None:
    proposal = portable_bundle.proposal
    state = portable_bundle.state
    certificate = portable_bundle.certificate

    with pytest.raises(GovernanceError, match="receipt state run_id mismatch"):
        _validate_receipt_state_binding(_view(proposal, run_id="run:other"), state)
    with pytest.raises(GovernanceError, match="membership snapshot mismatch"):
        _validate_receipt_state_binding(
            _view(
                proposal,
                membership_snapshot_root=_fingerprint("membership:other"),
            ),
            state,
        )
    with pytest.raises(GovernanceError, match="membership epoch mismatch"):
        _validate_receipt_state_binding(
            _view(
                proposal,
                membership_epoch_state_root=_fingerprint("membership-epoch:other"),
            ),
            state,
        )

    substituted_membership = _view(
        certificate.membership_snapshot,
        membership_root=_fingerprint("membership-root:other"),
    )
    with pytest.raises(GovernanceError, match="certificate membership root mismatch"):
        _validate_certificate_proposal_binding(
            _view(certificate, membership_snapshot=substituted_membership)
        )
    with pytest.raises(GovernanceError, match="certificate state run_id mismatch"):
        _validate_certificate_state_binding(
            _view(certificate, run_id="run:other"),
            state,
        )

    verification = portable_bundle.verifications[0]
    with pytest.raises(
        GovernanceError,
        match="witness verification state run_id mismatch",
    ):
        _validate_verification_state_binding(
            _view(
                verification,
                witness=_view(verification.witness, run_id="run:other"),
            ),
            state,
        )
    with pytest.raises(
        GovernanceError,
        match="witness verification state membership mismatch",
    ):
        _validate_verification_state_binding(
            _view(
                verification,
                witness=_view(
                    verification.witness,
                    membership_root=_fingerprint("membership-root:other"),
                ),
            ),
            state,
        )
    with pytest.raises(GovernanceError, match="proposal state run_id mismatch"):
        _validate_proposal_state_binding(_view(proposal, run_id="run:other"), state)
    with pytest.raises(GovernanceError, match="outcome state run_id mismatch"):
        _validate_outcome_state_binding(_view(state, run_id="run:other"), state)


def test_action_gate_distinguishes_stop_and_permission_denial(
    portable_bundle: Any,
) -> None:
    decision_ref = _fingerprint("decision:action-gate-totality")
    stop, permission = _public_action_gate(
        portable_bundle,
        action=CommitAction.EPOCH_TRANSITION,
        decision_ref=decision_ref,
    )
    with pytest.raises(GovernanceError, match="stop gate is not resolved"):
        _require_action_gate(
            stop=stop,
            permission=permission,
            state=portable_bundle.state,
            action=CommitAction.EPOCH_TRANSITION,
            decision_ref=decision_ref,
            current_step=stop.expires_at_step,
        )
    with pytest.raises(GovernanceError, match="permission gate is denied"):
        _require_action_gate(
            stop=stop,
            permission=None,  # type: ignore[arg-type]
            state=portable_bundle.state,
            action=CommitAction.EPOCH_TRANSITION,
            decision_ref=decision_ref,
            current_step=8,
        )


def test_portable_membership_totality_guards_are_semantically_distinct(
    portable_bundle: Any,
) -> None:
    membership = portable_bundle.portable_membership
    with pytest.raises(GovernanceError, match="assurance is not distributed"):
        _validate_portable_membership_snapshot(
            _view(membership, assurance=CommitAssurance.CERTIFIED)
        )
    with pytest.raises(GovernanceError, match="expiry must follow issuance"):
        _validate_portable_membership_snapshot(
            _view(membership, expires_at_step=membership.issued_at_step)
        )
    with pytest.raises(GovernanceError, match="issuer lacks authority"):
        _validate_portable_membership_snapshot(
            _view(membership, authority=AuthorityLevel.AGENT)
        )
    forged_membership = _view(
        membership,
        membership_root=_fingerprint("membership:forged"),
    )
    forged_membership.snapshot_fingerprint = commit_payload_fingerprint(
        _portable_snapshot_payload_unchecked(forged_membership),
        schema="pheroos-eligible-principal-snapshot-v1",
        profile=forged_membership.profile,
    )
    with pytest.raises(GovernanceError, match="membership root is invalid"):
        _validate_portable_membership_snapshot(forged_membership)

    policy = portable_bundle.policy.distributed
    assert policy is not None
    with pytest.raises(GovernanceError, match="membership size"):
        _validate_membership_policy(
            membership,
            replace(policy, membership_size=policy.membership_size + 1),
        )
    with pytest.raises(GovernanceError, match="failure-domain diversity"):
        _validate_membership_policy(
            membership,
            replace(
                policy,
                minimum_failure_domain_diversity=policy.membership_size + 1,
            ),
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("value_version", "value-v0", "value version is unsupported"),
        ("wire_version", "wire-v0", "wire version is unsupported"),
        ("canonicalization", "json-v0", "canonicalization is unsupported"),
        ("hash_algorithm", "sha512", "hash algorithm is unsupported"),
        ("profile", CERTIFIED_COMMIT_PROFILE_VERSION, "profile is invalid"),
        ("assurance", CommitAssurance.CERTIFIED, "assurance is invalid"),
        (
            "local_receipt_version",
            "receipt-v0",
            "local receipt version is unsupported",
        ),
        (
            "portable_certificate_version",
            "certificate-v0",
            "portable certificate version is unsupported",
        ),
    ),
)
def test_distributed_value_payload_rejects_each_version_and_profile_substitution(
    portable_bundle: Any,
    field: str,
    value: object,
    message: str,
) -> None:
    payload = governance.distributed_commit_value_payload(portable_bundle.proposal)
    payload[field] = value
    with pytest.raises(GovernanceError, match=message):
        validate_distributed_commit_value_payload(
            payload,
            value_version=DISTRIBUTED_COMMIT_VALUE_VERSION,
        )


def test_distributed_value_mapping_totality_rejects_shape_and_missing_fields(
    portable_bundle: Any,
) -> None:
    with pytest.raises(GovernanceError, match="must be a mapping"):
        validate_distributed_commit_value_payload(  # type: ignore[arg-type]
            (),
            value_version=DISTRIBUTED_COMMIT_VALUE_VERSION,
        )
    payload = governance.distributed_commit_value_payload(portable_bundle.proposal)
    payload.pop("candidate_id")
    with pytest.raises(GovernanceError, match="payload keys mismatch"):
        validate_distributed_commit_value_payload(
            payload,
            value_version=DISTRIBUTED_COMMIT_VALUE_VERSION,
        )
    with pytest.raises(GovernanceError, match="is missing wire_version"):
        distributed_commit_value_payload_from_mapping(
            {},
            value_version=DISTRIBUTED_COMMIT_VALUE_VERSION,
        )


def test_proposal_contracts_reject_assurance_and_external_lineage_substitution(
    portable_bundle: Any,
) -> None:
    proposal = portable_bundle.proposal
    with pytest.raises(GovernanceError, match="proposal assurance is invalid"):
        validate_distributed_commit_proposal(
            _view(proposal, assurance=CommitAssurance.CERTIFIED),
            proposal_version=DISTRIBUTED_PROPOSAL_VERSION,
            commit_value_version=DISTRIBUTED_COMMIT_VALUE_VERSION,
        )
    with pytest.raises(
        GovernanceError,
        match="proposal run_id does not match portable certificate",
    ):
        _validate_proposal_certificate_lineage(
            _view(proposal, run_id="run:other"),
            portable_bundle.portable_certificate,
        )
    with pytest.raises(
        GovernanceError,
        match="proposal portable certificate mismatch",
    ):
        _validate_proposal_certificate_lineage(
            _view(
                proposal,
                portable_certificate_ref=_fingerprint("certificate:other"),
            ),
            portable_bundle.portable_certificate,
        )
    with pytest.raises(GovernanceError, match="proposal membership run_id mismatch"):
        _validate_proposal_membership(
            _view(proposal, run_id="run:other"),
            portable_bundle.portable_membership,
        )
    with pytest.raises(GovernanceError, match="proposal membership root mismatch"):
        _validate_proposal_membership(
            _view(
                proposal,
                membership_snapshot_root=_fingerprint("membership:other"),
            ),
            portable_bundle.portable_membership,
        )


def test_witness_contract_totality_distinguishes_shape_binding_and_trust(
    portable_bundle: Any,
) -> None:
    witness = portable_bundle.verifications[0].witness
    with pytest.raises(GovernanceError, match="witness assurance is invalid"):
        validate_quorum_witness(
            _view(witness, assurance=CommitAssurance.CERTIFIED),
            witness_version=QUORUM_WITNESS_VERSION,
        )
    with pytest.raises(GovernanceError, match="expiry must follow signing"):
        validate_quorum_witness(
            _view(witness, expires_at_step=witness.witnessed_at_step),
            witness_version=QUORUM_WITNESS_VERSION,
        )
    with pytest.raises(GovernanceError, match="witness run_id binding mismatch"):
        _validate_witness_proposal_binding(
            _view(witness, run_id="run:other"),
            portable_bundle.proposal,
        )
    assert not _attestation_matches(
        witness.attestation_ref,
        object(),  # type: ignore[arg-type]
        governance.quorum_witness_signing_root(witness),
    )


def test_invariant_totality_guards_reject_wrong_authority_shapes(
    portable_bundle: Any,
) -> None:
    policy = portable_bundle.policy
    proposal = portable_bundle.proposal
    common = {
        "profile": proposal.profile,
        "assurance": proposal.assurance,
        "target": proposal.target,
        "commit_policy_root": proposal.commit_policy_root,
    }
    with pytest.raises(GovernanceError, match="canonical commit policy"):
        _validate_distributed_policy(object(), **common)  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="profile is invalid"):
        _validate_distributed_policy(
            policy,
            **{**common, "profile": CERTIFIED_COMMIT_PROFILE_VERSION},
        )
    with pytest.raises(GovernanceError, match="assurance is invalid"):
        _validate_distributed_policy(
            policy,
            **{**common, "assurance": CommitAssurance.CERTIFIED},
        )
    with pytest.raises(GovernanceError, match="policy binding mismatch"):
        _validate_distributed_policy(
            policy,
            **{**common, "target": "decision:other"},
        )
    assert policy.distributed is not None
    invalid_policy = replace(
        policy,
        distributed=replace(policy.distributed, membership_size=3),
    )
    with pytest.raises(GovernanceError, match="static Byzantine model"):
        _validate_distributed_policy(
            invalid_policy,
            **{
                **common,
                "commit_policy_root": commit_policy_fingerprint(
                    invalid_policy,
                    profile=DISTRIBUTED_COMMIT_PROFILE_VERSION,
                ),
            },
        )

    with pytest.raises(GovernanceError, match="must not be empty"):
        _canonical_fingerprints((), "roots")
    root = _fingerprint("duplicate")
    with pytest.raises(GovernanceError, match="contains a duplicate"):
        _canonical_fingerprints((root, root), "roots")
    with pytest.raises(GovernanceError, match="dataclass instance"):
        _public_dataclass_payload(object())
    with pytest.raises(GovernanceError, match="target must be a dataclass type"):
        _strict_dataclass_payload({}, object, "payload")
    with pytest.raises(GovernanceError, match="must be a mapping"):
        _require_mapping((), "mapping")
    with pytest.raises(GovernanceError, match="keys must be strings"):
        _require_mapping({1: "value"}, "mapping")
    with pytest.raises(GovernanceError, match="must be a sequence"):
        _require_sequence("not-an-array", "sequence")
    with pytest.raises(GovernanceError, match="assurance is invalid"):
        _coerce_assurance("unknown")
    with pytest.raises(GovernanceError, match="authority is invalid"):
        _coerce_authority(True)
    with pytest.raises(GovernanceError, match="authority is invalid"):
        _coerce_authority("unknown")
    assert _coerce_authority(AuthorityLevel.GOVERNANCE.value) is (
        AuthorityLevel.GOVERNANCE
    )


def test_public_membership_records_reject_duplicate_and_noncanonical_topology(
    portable_bundle: Any,
) -> None:
    membership = portable_bundle.portable_membership
    cluster = membership.eligible_clusters[0]
    principal = cluster.principals[0]

    with pytest.raises(GovernanceError, match="requires canonical principals"):
        governance.PortableEligibleCluster(
            cluster_id="cluster:empty",
            principals=(),
        )
    with pytest.raises(GovernanceError, match="repeats a principal"):
        governance.PortableEligibleCluster(
            cluster_id="cluster:duplicate-principal",
            principals=(principal, principal),
        )
    same_verification = replace(
        principal,
        principal_id="principal:other",
    )
    with pytest.raises(GovernanceError, match="repeats a verification"):
        governance.PortableEligibleCluster(
            cluster_id="cluster:duplicate-verification",
            principals=(principal, same_verification),
        )

    with pytest.raises(GovernanceError, match="canonical cluster records"):
        replace(membership, eligible_clusters=(object(),))  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="must not be empty"):
        replace(membership, eligible_clusters=())
    with pytest.raises(GovernanceError, match="repeats a cluster"):
        replace(membership, eligible_clusters=(cluster, cluster))
    second_cluster = governance.PortableEligibleCluster(
        cluster_id="cluster:other",
        principals=(principal,),
    )
    with pytest.raises(GovernanceError, match="multiple clusters"):
        replace(
            membership,
            eligible_clusters=(cluster, second_cluster),
        )

    with pytest.raises(GovernanceError, match="canonical distributed record"):
        governance.portable_membership_snapshot_payload(object())  # type: ignore[arg-type]
    payload_without_root = governance.portable_membership_snapshot_payload(
        membership,
        include_snapshot_fingerprint=False,
    )
    assert "snapshot_fingerprint" not in payload_without_root
    assert governance.portable_membership_snapshot_fingerprint(membership) == (
        membership.snapshot_fingerprint
    )
    assert governance.portable_membership_root(membership) == membership.membership_root


def test_public_proposal_totality_covers_payload_verification_and_authority(
    portable_bundle: Any,
) -> None:
    proposal = portable_bundle.proposal
    with pytest.raises(GovernanceError, match="canonical record"):
        governance.distributed_commit_proposal_payload(object())  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="requires canonical proposal"):
        governance.distributed_commit_value_payload(object())  # type: ignore[arg-type]

    proposal_payload = governance.distributed_commit_proposal_payload(proposal)
    assert governance.verify_distributed_commit_proposal(
        proposal_payload,
        commit_policy=portable_bundle.policy,
        portable_certificate=portable_bundle.portable_certificate,
        membership_snapshot=portable_bundle.portable_membership,
        trusted_issuer_attestations=portable_bundle.issuer_trust,
    )
    assert governance.verify_distributed_commit_proposal(
        proposal_payload,
        commit_policy=portable_bundle.policy,
        portable_certificate=portable_bundle.portable_certificate,
        membership_snapshot=portable_bundle.membership_snapshot,
        trusted_issuer_attestations=portable_bundle.issuer_trust,
    )
    assert not governance.verify_distributed_commit_proposal(
        proposal,
        commit_policy=portable_bundle.policy,
        portable_certificate=portable_bundle.portable_certificate,
        membership_snapshot=portable_bundle.portable_membership,
        trusted_issuer_attestations=portable_bundle.issuer_trust,
        expected_proposal_digest=_fingerprint("proposal:different"),
    )
    assert not governance.verify_distributed_commit_proposal(
        proposal,
        commit_policy=portable_bundle.policy,
        portable_certificate=portable_bundle.portable_certificate,
        membership_snapshot=portable_bundle.portable_membership,
        trusted_issuer_attestations=portable_bundle.issuer_trust,
        expected_commit_value_root=_fingerprint("value:different"),
    )
    assert not governance.verify_distributed_commit_proposal(
        object(),  # type: ignore[arg-type]
        commit_policy=portable_bundle.policy,
        portable_certificate=portable_bundle.portable_certificate,
        membership_snapshot=portable_bundle.portable_membership,
        trusted_issuer_attestations=portable_bundle.issuer_trust,
    )
    assert not governance.verify_distributed_commit_proposal(
        proposal,
        commit_policy=portable_bundle.policy,
        portable_certificate=portable_bundle.portable_certificate,
        membership_snapshot=object(),  # type: ignore[arg-type]
        trusted_issuer_attestations=portable_bundle.issuer_trust,
    )

    detached = governance.distributed_commit_proposal_from_payload(proposal_payload)
    object.__setattr__(detached, "assurance", CommitAssurance.CERTIFIED)
    assert not governance.distributed_commit_proposal_is_authoritative(detached)


def test_public_witness_totality_covers_fingerprint_and_signing_root_failures(
    portable_bundle: Any,
) -> None:
    verification = portable_bundle.verifications[0]
    payload = governance.witness_verification_payload(verification)

    fingerprint_substitution = governance.witness_verification_from_payload(payload)
    object.__setattr__(
        fingerprint_substitution,
        "witness_fingerprint",
        _fingerprint("witness:fingerprint:other"),
    )
    assert not governance.verify_portable_witness_verification(
        fingerprint_substitution,
        membership_snapshot=portable_bundle.portable_membership,
        trusted_witness_attestations=portable_bundle.witness_trust,
        issued_at_step=6,
    )

    signing_substitution = governance.witness_verification_from_payload(payload)
    object.__setattr__(
        signing_substitution,
        "witness_signing_root",
        _fingerprint("witness:signing-root:other"),
    )
    assert not governance.verify_portable_witness_verification(
        signing_substitution,
        membership_snapshot=portable_bundle.portable_membership,
        trusted_witness_attestations=portable_bundle.witness_trust,
        issued_at_step=6,
    )

    malformed = governance.witness_verification_from_payload(payload)
    object.__setattr__(malformed, "verification_version", "verification-v0")
    assert not governance.witness_verification_is_authoritative(malformed)
    with pytest.raises(GovernanceError, match="lacks canonical witness"):
        _validate_witness_verification(_view(verification, witness=object()))


def test_state_authority_and_current_head_fail_closed_on_internal_corruption() -> None:
    malformed_bundle = _public_portable_scenario("legacy-totality-state-authority")
    malformed = malformed_bundle.state
    object.__setattr__(malformed, "assurance", CommitAssurance.CERTIFIED)
    assert not governance.distributed_commit_state_is_authoritative(malformed)

    portable = governance.distributed_commit_state_from_payload(
        governance.distributed_commit_state_payload(
            _public_portable_scenario("legacy-totality-portable-state").state
        )
    )
    with pytest.raises(GovernanceError, match="state is not authoritative"):
        _current_distributed_state_head(portable)

    unavailable_bundle = _public_portable_scenario(
        "legacy-totality-current-head-unavailable"
    )
    unavailable = unavailable_bundle.state
    cursor = object.__getattribute__(unavailable, "_cursor")
    object.__setattr__(cursor, "current_state", None)
    with pytest.raises(GovernanceError, match="current head is unavailable"):
        _current_distributed_state_head(unavailable)


def test_public_certificate_verifier_rejects_untrusted_proposal(
    portable_bundle: Any,
) -> None:
    certificate = _portable_certificate_clone(portable_bundle)
    assert not governance.verify_distributed_commit_certificate(
        certificate,
        commit_policy=portable_bundle.policy,
        portable_certificate=portable_bundle.portable_certificate,
        trusted_issuer_attestations={},
        trusted_witness_attestations=portable_bundle.witness_trust,
    )


@pytest.mark.parametrize(
    "field",
    (
        "membership_size",
        "max_byzantine_faults",
        "witness_quorum",
        "minimum_failure_domain_diversity",
    ),
)
def test_public_certificate_verifier_rejects_policy_scalar_substitution(
    portable_bundle: Any,
    field: str,
) -> None:
    certificate = _portable_certificate_clone(portable_bundle)
    object.__setattr__(certificate, field, getattr(certificate, field) + 1)
    assert not _verify_portable_certificate(certificate, portable_bundle)


def test_public_certificate_verifier_rejects_witness_binding_and_status_lies(
    portable_bundle: Any,
) -> None:
    witness_substitution = _portable_certificate_clone(portable_bundle)
    object.__setattr__(
        witness_substitution.witnesses[0].witness,
        "target",
        "decision:other",
    )
    assert not _verify_portable_certificate(witness_substitution, portable_bundle)

    false_final = _portable_certificate_clone(portable_bundle)
    object.__setattr__(false_final, "witnesses", false_final.witnesses[:1])
    assert not _verify_portable_certificate(false_final, portable_bundle)

    false_provisional = _portable_certificate_clone(portable_bundle)
    object.__setattr__(
        false_provisional,
        "status",
        governance.DistributedCertificateStatus.PROVISIONAL,
    )
    assert not _verify_portable_certificate(false_provisional, portable_bundle)


def test_certificate_canonical_validator_totality_guards_are_explicit(
    portable_bundle: Any,
) -> None:
    certificate = portable_bundle.certificate
    with pytest.raises(GovernanceError, match="status is invalid"):
        _validate_distributed_commit_certificate(_view(certificate, status="final"))
    with pytest.raises(GovernanceError, match="proposal is invalid"):
        _validate_distributed_commit_certificate(_view(certificate, proposal=object()))
    with pytest.raises(GovernanceError, match="membership is invalid"):
        _validate_distributed_commit_certificate(
            _view(certificate, membership_snapshot=object())
        )
    with pytest.raises(GovernanceError, match="quorum intersection is unsafe"):
        _validate_distributed_commit_certificate(
            _view(certificate, membership_size=certificate.membership_size - 1)
        )
    with pytest.raises(GovernanceError, match="membership size mismatch"):
        _validate_distributed_commit_certificate(
            _view(
                certificate,
                membership_size=certificate.membership_size + 1,
                witness_quorum=certificate.witness_quorum + 1,
            )
        )

    body_root = _distributed_certificate_body_root(
        {"marker": "certificate-without-witnesses"},
        profile=DISTRIBUTED_COMMIT_PROFILE_VERSION,
    )
    assert body_root.startswith("sha256:")


def test_public_certificate_authority_and_finality_guards_fail_closed(
    portable_bundle: Any,
) -> None:
    malformed = _portable_certificate_clone(portable_bundle)
    object.__setattr__(malformed, "status", "final")
    assert not governance.distributed_commit_certificate_is_current_final(
        malformed,
        portable_bundle.state,
    )

    with pytest.raises(
        GovernanceError,
        match="requires current registered FINAL proof",
    ):
        governance.verify_distributed_commit_finality(
            portable_bundle.certificate,
            portable_bundle.state,
            object(),  # type: ignore[arg-type]
            current_step=6,
            verifier_id="governance:finality-totality",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:finality-totality",
            trace_event_id="trace:finality-totality",
        )


def test_public_certificate_issuance_rejects_untrusted_proposal(
    portable_bundle: Any,
) -> None:
    with pytest.raises(GovernanceError, match="proposal verification failed"):
        governance.issue_distributed_commit_certificate(
            portable_bundle.state,
            portable_bundle.proposal,
            verifications=portable_bundle.verifications,
            commit_policy=portable_bundle.policy,
            portable_certificate=portable_bundle.portable_certificate,
            trusted_issuer_attestations={},
            trusted_witness_attestations=portable_bundle.witness_trust,
            certificate_id="distributed:legacy-totality:untrusted",
            issuer_id="governance:legacy-totality",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=6,
            provenance="urn:test:legacy-totality:untrusted",
            trace_event_id="trace:legacy-totality:untrusted",
        )


def test_public_membership_and_proposal_type_guards(
    portable_bundle: Any,
) -> None:
    with pytest.raises(GovernanceError, match="authoritative snapshot"):
        governance.portable_membership_snapshot_from_eligible(
            object()  # type: ignore[arg-type]
        )
    assert governance.distributed_commit_value_root(portable_bundle.proposal) == (
        portable_bundle.proposal.commit_value_root
    )
    assert not governance.distributed_commit_proposal_is_authoritative(object())


def test_receipt_certificate_lineage_reports_central_leaf_substitution(
    portable_bundle: Any,
) -> None:
    certificate = portable_bundle.portable_certificate
    with pytest.raises(
        GovernanceError,
        match="manifest_root does not match receipt",
    ):
        _validate_receipt_certificate_lineage(
            _view(certificate, manifest_root=_fingerprint("manifest:other")),
            certificate,
        )

    receipt_values = {
        item.name: getattr(certificate, item.name)
        for item in fields(governance.LocalCommitReceipt)
        if not item.name.startswith("_") and hasattr(certificate, item.name)
    }
    receipt_values.update(
        schema_discriminator=governance.LOCAL_COMMIT_RECEIPT_DISCRIMINATOR,
        receipt_version=governance.LOCAL_COMMIT_RECEIPT_VERSION,
        receipt_id="receipt:legacy-totality:lineage",
        authority_scope=governance.AuthorityScope.GOVERNANCE_LOCAL,
    )
    receipt = governance.LocalCommitReceipt(**receipt_values)
    with pytest.raises(GovernanceError, match="local receipt ref mismatch"):
        _validate_receipt_certificate_lineage(receipt, certificate)


def test_public_proposal_issuance_rejects_non_authoritative_receipt(
    portable_bundle: Any,
) -> None:
    with pytest.raises(GovernanceError, match="authoritative local receipt"):
        governance.issue_distributed_commit_proposal(
            object(),  # type: ignore[arg-type]
            portable_bundle.portable_certificate,
            portable_bundle.membership_snapshot,
            portable_bundle.membership_state,
            commit_policy=portable_bundle.policy,
            trusted_issuer_attestations=portable_bundle.issuer_trust,
            proposal_id="proposal:legacy-totality:forged-receipt",
            proposed_at_step=6,
        )


def test_public_epoch_transition_rejects_portable_state(
    portable_bundle: Any,
) -> None:
    decision_ref = _fingerprint("decision:portable-epoch-transition")
    stop, permission = _public_action_gate(
        portable_bundle,
        action=CommitAction.EPOCH_TRANSITION,
        decision_ref=decision_ref,
        suffix="portable-state",
    )
    portable_state = governance.distributed_commit_state_from_payload(
        governance.distributed_commit_state_payload(portable_bundle.state)
    )
    with pytest.raises(GovernanceError, match="requires the current state"):
        governance.epoch_transition_certificate_body_root(
            portable_state,
            portable_bundle.membership_snapshot,
            portable_bundle.membership_state,
            stop,
            permission,
            commit_policy=portable_bundle.policy,
            certificate_id="epoch-transition:legacy-totality:portable-state",
            issuer_id="governance:legacy-totality",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=7,
            provenance="urn:test:legacy-totality:portable-state",
            trace_event_id="trace:legacy-totality:portable-state",
        )


def test_public_state_current_guard_catches_lock_corruption() -> None:
    bundle = _public_portable_scenario("legacy-totality-corrupt-lock")
    cursor = object.__getattribute__(bundle.state, "_cursor")
    object.__setattr__(cursor, "lock", _ExplodingLock())
    assert not governance.distributed_commit_state_is_current(bundle.state)


def test_public_certificate_replay_rejects_missing_current_registration() -> None:
    bundle = _public_portable_scenario("legacy-totality-missing-registration")
    registered = _register_portable_certificate(bundle.state, bundle)
    cursor = object.__getattribute__(registered, "_cursor")
    object.__setattr__(cursor, "current_state", bundle.state)
    object.__setattr__(
        cursor,
        "current_state_fingerprint",
        governance.distributed_commit_state_fingerprint(bundle.state),
    )

    with pytest.raises(GovernanceError, match="absent from the current head"):
        _register_portable_certificate(registered, bundle)


def test_public_certificate_replay_rejects_corrupt_prior_state() -> None:
    bundle = _public_portable_scenario("legacy-totality-corrupt-replay")
    parent = bundle.state
    _register_portable_certificate(parent, bundle)
    cursor = object.__getattribute__(parent, "_cursor")
    parent_ref = governance.distributed_commit_state_fingerprint(parent)
    request_ref, _ = cursor.transitions[parent_ref]
    cursor.transitions[parent_ref] = (request_ref, object())

    with pytest.raises(GovernanceError, match="replay state is invalid"):
        _register_portable_certificate(parent, bundle)


def test_public_frozen_epoch_guards_block_state_certificate_and_recovery() -> None:
    bundle = _public_portable_scenario("legacy-totality-frozen-guards")
    frozen = _freeze_public_bundle(bundle)
    assert frozen.frozen

    with pytest.raises(GovernanceError, match="frozen distributed epoch"):
        governance.issue_distributed_commit_certificate(
            frozen,
            bundle.proposal,
            verifications=bundle.verifications,
            commit_policy=bundle.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            certificate_id="distributed:legacy-totality:frozen",
            issuer_id="governance:legacy-totality",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=6,
            provenance="urn:test:legacy-totality:frozen",
            trace_event_id="trace:legacy-totality:frozen",
        )
    with pytest.raises(GovernanceError, match="epoch is frozen"):
        governance.record_witness_verifications(
            frozen,
            (),
            current_step=6,
        )

    snapshot, epoch_state = _next_public_membership(
        bundle,
        "legacy-totality-frozen-guards:new",
    )
    recovery_ref = _fingerprint("recovery:legacy-totality:frozen")
    decision_ref = governance.epoch_transition_decision_ref(
        frozen,
        snapshot,
        epoch_state,
        commit_policy=bundle.policy,
        declared_recovery_ref=recovery_ref,
    )
    stop, permission = _public_action_gate(
        bundle,
        action=CommitAction.EPOCH_TRANSITION,
        decision_ref=decision_ref,
        suffix="frozen-recovery",
    )
    with pytest.raises(GovernanceError, match="explicit recovery stop and permission"):
        governance.epoch_transition_certificate_body_root(
            frozen,
            snapshot,
            epoch_state,
            stop,
            permission,
            commit_policy=bundle.policy,
            certificate_id="epoch-transition:legacy-totality:frozen",
            declared_recovery_ref=recovery_ref,
            issuer_id="governance:legacy-totality",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=8,
            provenance="urn:test:legacy-totality:frozen-transition",
            trace_event_id="trace:legacy-totality:frozen-transition",
        )


def test_public_transitioned_epoch_guards_block_state_and_certificates() -> None:
    bundle = _public_portable_scenario("legacy-totality-transitioned-guards")
    transitioned = _transition_public_bundle(bundle)
    assert transitioned.transitioned

    with pytest.raises(GovernanceError, match="transitioned distributed epoch"):
        governance.issue_distributed_commit_certificate(
            transitioned,
            bundle.proposal,
            verifications=bundle.verifications,
            commit_policy=bundle.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            certificate_id="distributed:legacy-totality:transitioned",
            issuer_id="governance:legacy-totality",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=8,
            provenance="urn:test:legacy-totality:transitioned",
            trace_event_id="trace:legacy-totality:transitioned",
        )
    with pytest.raises(GovernanceError, match="already transitioned"):
        governance.record_witness_verifications(
            transitioned,
            (),
            current_step=8,
        )
    with pytest.raises(GovernanceError, match="transitioned epoch"):
        governance.register_distributed_commit_certificate(
            transitioned,
            bundle.certificate,
            commit_policy=bundle.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            current_step=8,
        )
