from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import pickle

import pytest

from pheroos.governance._support_v2.durable_context import (
    durable_support_context_v2,
)
from pheroos.governance._support_v2.membership_contracts import (
    MAX_MEMBERSHIP_CLUSTERS_V2,
    MEMBERSHIP_GENESIS_SNAPSHOT_ROOT_V2,
    MEMBERSHIP_GENESIS_TRANSITION_ID_V2,
    MembershipCommitRequestV2,
    MembershipSnapshotV2,
    membership_stream_ref_v2,
    membership_transition_id_v2,
)
from pheroos.governance._support_v2.membership_source import (
    _project_verifications,
)
from pheroos.governance._support_v2.principal_verification_contracts import (
    MAX_PRINCIPAL_VERIFICATION_SET_BYTES_V2,
    PRINCIPAL_VERIFICATION_GENESIS_SNAPSHOT_ROOT_V2,
    PRINCIPAL_VERIFICATION_GENESIS_TRANSITION_ID_V2,
    PrincipalVerificationSetAdvanceRequestV2,
    PrincipalVerificationSetSnapshotV2,
    principal_verification_stream_ref_v2,
    principal_verification_transition_id_v2,
)
from pheroos.governance._support_v2.principal_verification_operations import (
    VerifiedPrincipalVerificationSetStateV2,
    advance_principal_verification_set_v2,
)
from pheroos.governance._support_v2.principal_verification_records import (
    MAX_PRINCIPAL_VERIFICATIONS_V2,
    MAX_VERIFICATION_EVIDENCE_ROOTS_V2,
    MAX_VERIFICATION_SOURCE_TRACE_ROOTS_V2,
    PrincipalVerificationRecordV2,
)
from pheroos.governance._support_v2.principal_verification_source import (
    VerifiedPrincipalVerificationSourceV2,
    prepare_principal_verification_set_v2,
    verify_principal_verification_source_v2,
)
from pheroos.governance.authority_store_v2 import GovernanceCommitDispositionV2
from pheroos.protocol import COMMIT_INTEGRITY_PROFILE_VERSION
from pheroos.protocol.authority_manifest_v2 import (
    ScopedProtocolManifestV2,
    scoped_capability_manifest_v2_from_dict,
)
from pheroos.protocol.commit_models import CollectiveCommitPolicy, CommitAssurance
from pheroos.protocol.loader import load_capability_manifest


ROOT = Path(__file__).resolve().parents[2]
PROFILE = COMMIT_INTEGRITY_PROFILE_VERSION
TARGET = "decision:review"
RUN_REF = "run:membership-v2"
DOMAIN_ROOT = "sha256:" + sha256(b"membership-domain").hexdigest()
SCOPE_REF = "scope:membership-v2"


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode()).hexdigest()


def _manifest() -> ScopedProtocolManifestV2:
    payload = json.loads(
        (ROOT / "examples/scoped-output-protocol/capability.json").read_text()
    )
    scoped = scoped_capability_manifest_v2_from_dict(payload).protocol
    legacy = load_capability_manifest(
        ROOT / "examples/hybrid-commit-protocol/capability.json"
    )
    policy = legacy.protocol.collective_commit_policy
    assert type(policy) is CollectiveCommitPolicy
    return replace(scoped, collective_commit_policy=replace(policy, target=TARGET))


def _record(
    index: int, *, cluster: str = "cluster:shared"
) -> PrincipalVerificationRecordV2:
    return PrincipalVerificationRecordV2(
        principal_ref=f"principal:{index}",
        cluster_ref=cluster,
        failure_domain_ref=f"failure-domain:{index % 2}",
        verification_method="external-verifier-v2",
        verification_issuer_ref="identity:verifier",
        attestation_root=_root(f"attestation:{index}"),
        evidence_roots=(_root(f"evidence:{index}"),),
        issued_at_step=1,
        expires_at_step=10_000,
        provenance_ref=f"urn:test:principal:{index}",
        source_trace_roots=(_root(f"trace:{index}"),),
    )


def _prepare_verification(
    *,
    epoch: int = 1,
    advance_ref: str | None = None,
    records: tuple[PrincipalVerificationRecordV2, ...] = (),
    parent: PrincipalVerificationSetSnapshotV2 | None = None,
    mutation_issuer_ref: str = "issuer:verification:a",
):
    return prepare_principal_verification_set_v2(
        domain_root=DOMAIN_ROOT,
        scope_ref=SCOPE_REF,
        manifest=_manifest(),
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        run_ref=RUN_REF,
        target_ref=TARGET,
        epoch=epoch,
        observed_epoch=epoch + 10,
        advance_ref=advance_ref or f"advance:verification:{epoch}",
        snapshot_ref=f"snapshot:verification:{epoch}",
        current_step=epoch + 1,
        expires_at_step=9_000,
        mutation_issuer_ref=mutation_issuer_ref,
        records=records,
        parent_snapshot=parent,
    )


def test_portable_records_are_data_and_canonical_not_process_authority() -> None:
    alpha = _record(1)
    detached = PrincipalVerificationRecordV2.from_dict(alpha.to_dict())
    assert detached == alpha
    assert pickle.loads(pickle.dumps(alpha)) == alpha
    forged = dict(alpha.to_dict())
    forged["principal_ref"] = "principal:forged"
    with pytest.raises(ValueError, match="verification_root"):
        PrincipalVerificationRecordV2.from_dict(forged)
    unknown = dict(alpha.to_dict())
    unknown["unknown"] = True
    with pytest.raises(ValueError, match="fields"):
        PrincipalVerificationRecordV2.from_dict(unknown)
    missing_root = alpha.to_dict()
    missing_root["verification_root"] = ""
    with pytest.raises(ValueError, match="not canonical wire"):
        PrincipalVerificationRecordV2.from_dict(missing_root)
    ordered = replace(
        alpha,
        evidence_roots=(
            _root("evidence:wire:alpha"),
            _root("evidence:wire:omega"),
        ),
        verification_root="",
    )
    reordered = ordered.to_dict()
    evidence_roots = reordered["evidence_roots"]
    assert type(evidence_roots) is list
    reordered["evidence_roots"] = list(reversed(evidence_roots))
    with pytest.raises(ValueError, match="not canonical wire"):
        PrincipalVerificationRecordV2.from_dict(reordered)


def test_verification_set_is_complete_canonical_and_allows_explicit_empty() -> None:
    alpha = _record(1, cluster="cluster:shared")
    alias = _record(2, cluster="cluster:shared")
    first, first_source = _prepare_verification(records=(alpha, alias))
    second, second_source = _prepare_verification(records=(alias, alpha))
    empty, empty_source = _prepare_verification(
        epoch=2,
        parent=first.snapshot,
        mutation_issuer_ref="issuer:verification:b",
    )
    assert first == second
    assert first.request_root == second.request_root
    assert first_source.context_root == second_source.context_root
    assert empty.snapshot.records == ()
    assert empty.snapshot.record_count == 0
    assert empty.snapshot.parent_epoch == 1
    assert empty.snapshot.mutation_issuer_ref == "issuer:verification:b"
    assert empty_source.context_root
    assert PrincipalVerificationSetAdvanceRequestV2.from_dict(first.to_dict()) == first
    reused = replace(
        _record(3),
        attestation_root=alpha.attestation_root,
        verification_root="",
    )
    with pytest.raises(ValueError, match="reuses an attestation"):
        _prepare_verification(records=(alpha, reused))


def test_verification_source_is_nonportable_and_cross_request_proof_fails() -> None:
    first, source = _prepare_verification(records=(_record(1),))
    retry, _ = _prepare_verification(records=(_record(1),))
    conflict, conflict_source = _prepare_verification(records=(_record(2),))
    assert first == retry
    verify_principal_verification_source_v2(first, source=source)
    with pytest.raises(ValueError, match="another request"):
        verify_principal_verification_source_v2(first, source=conflict_source)
    assert first.stream_ref == conflict.stream_ref
    assert first.transition_id == conflict.transition_id
    assert first.request_root != conflict.request_root
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(source)
    with pytest.raises(TypeError, match="cannot be constructed"):
        VerifiedPrincipalVerificationSourceV2()


def test_fixed_verification_stream_survives_more_than_store_stream_limit() -> None:
    parent = None
    streams: set[str] = set()
    transitions: set[str] = set()
    for epoch in range(1, 131):
        request, _ = _prepare_verification(epoch=epoch, parent=parent)
        streams.add(request.stream_ref)
        transitions.add(request.transition_id)
        assert request.snapshot.revision == epoch
        parent = request.snapshot
    assert len(streams) == 1
    assert len(transitions) == 130


def test_fixed_stream_binds_every_exact_context_axis_but_not_epoch() -> None:
    manifest = _manifest()
    context = durable_support_context_v2(
        manifest,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        target_ref=TARGET,
    )
    baseline = principal_verification_stream_ref_v2(
        SCOPE_REF,
        PROFILE,
        CommitAssurance.EVIDENCE_BOUND,
        context.manifest_root,
        context.commit_policy_root,
        context.principal_verification_policy_root,
        context.protocol_ref,
        RUN_REF,
        TARGET,
    )
    variants = {
        principal_verification_stream_ref_v2(
            "scope:other",
            PROFILE,
            CommitAssurance.EVIDENCE_BOUND,
            context.manifest_root,
            context.commit_policy_root,
            context.principal_verification_policy_root,
            context.protocol_ref,
            RUN_REF,
            TARGET,
        ),
        principal_verification_stream_ref_v2(
            SCOPE_REF,
            PROFILE,
            CommitAssurance.EVIDENCE_BOUND,
            context.manifest_root,
            context.commit_policy_root,
            _root("verification-policy:other"),
            context.protocol_ref,
            RUN_REF,
            TARGET,
        ),
        principal_verification_stream_ref_v2(
            SCOPE_REF,
            PROFILE,
            CommitAssurance.EVIDENCE_BOUND,
            context.manifest_root,
            context.commit_policy_root,
            context.principal_verification_policy_root,
            context.protocol_ref,
            "run:other",
            TARGET,
        ),
    }
    assert baseline not in variants
    assert len(variants) == 3


def test_verification_and_membership_reject_semantically_invalid_support_policy() -> (
    None
):
    manifest = _manifest()
    policy = manifest.collective_commit_policy
    assert type(policy) is CollectiveCommitPolicy
    invalid = replace(
        manifest,
        collective_commit_policy=replace(
            policy,
            support_lease=replace(
                policy.support_lease,
                membership_mode="caller_asserted_membership",
            ),
        ),
    )

    with pytest.raises(ValueError, match="commit_support_semantics_invalid"):
        prepare_principal_verification_set_v2(
            domain_root=DOMAIN_ROOT,
            scope_ref=SCOPE_REF,
            manifest=invalid,
            profile=PROFILE,
            assurance=CommitAssurance.EVIDENCE_BOUND,
            run_ref=RUN_REF,
            target_ref=TARGET,
            epoch=1,
            observed_epoch=11,
            advance_ref="advance:invalid-support-policy",
            snapshot_ref="snapshot:invalid-support-policy",
            current_step=2,
            expires_at_step=9_000,
            mutation_issuer_ref="issuer:verification:a",
            records=(),
        )


def test_sybil_projection_counts_clusters_not_aliases_and_empty_is_explicit() -> None:
    request, _ = _prepare_verification(
        records=(
            _record(1, cluster="cluster:shared"),
            _record(2, cluster="cluster:shared"),
            _record(3, cluster="cluster:independent"),
        )
    )
    clusters = _project_verifications(request.snapshot)
    by_cluster = {item.cluster_ref: item for item in clusters}
    assert len(clusters) == 2
    assert len(by_cluster["cluster:shared"].principals) == 2
    assert _project_verifications(_prepare_verification()[0].snapshot) == ()


def _membership_snapshot(
    verification: PrincipalVerificationSetSnapshotV2,
    *,
    verification_head_root: str,
    epoch: int,
    revision: int,
    parent: MembershipSnapshotV2 | None,
) -> MembershipSnapshotV2:
    context = durable_support_context_v2(
        _manifest(),
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        target_ref=TARGET,
    )
    stream = membership_stream_ref_v2(
        SCOPE_REF,
        PROFILE,
        CommitAssurance.EVIDENCE_BOUND,
        context.manifest_root,
        context.commit_policy_root,
        context.membership_policy_root,
        context.protocol_ref,
        RUN_REF,
        TARGET,
    )
    request_ref = f"request:membership:{epoch}"
    clusters = _project_verifications(verification)
    return MembershipSnapshotV2(
        domain_root=DOMAIN_ROOT,
        scope_ref=SCOPE_REF,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        authority_policy_root=context.authority_policy_root,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        membership_policy_root=context.membership_policy_root,
        protocol_ref=context.protocol_ref,
        run_ref=RUN_REF,
        target_ref=TARGET,
        epoch=epoch,
        observed_epoch=epoch + 10,
        request_ref=request_ref,
        stream_ref=stream,
        transition_id=membership_transition_id_v2(stream, request_ref),
        snapshot_ref=f"snapshot:membership:{epoch}",
        revision=revision,
        parent_revision=0 if parent is None else parent.revision,
        parent_epoch=None if parent is None else parent.epoch,
        parent_transition_id=(
            MEMBERSHIP_GENESIS_TRANSITION_ID_V2
            if parent is None
            else parent.transition_id
        ),
        parent_snapshot_root=(
            MEMBERSHIP_GENESIS_SNAPSHOT_ROOT_V2
            if parent is None
            else parent.snapshot_root
        ),
        issued_at_step=epoch + 1,
        expires_at_step=8_000,
        mutation_issuer_ref=f"issuer:membership:{epoch % 2}",
        membership_method="store-current-verification-set-v2",
        provenance_ref="urn:test:membership",
        source_trace_roots=(_root(f"trace:membership:{epoch}"),),
        verification_stream_ref=verification.stream_ref,
        verification_transition_id=verification.transition_id,
        verification_policy_root=verification.verification_policy_root,
        verification_request_ref=verification.advance_ref,
        verification_revision=verification.revision,
        verification_head_root=verification_head_root,
        verification_snapshot_root=verification.snapshot_root,
        verification_set_root=verification.verification_set_root,
        verification_current_step=verification.current_step,
        verification_expires_at_step=verification.expires_at_step,
        verification_record_count=verification.record_count,
        clusters=clusters,
        cluster_count=len(clusters),
        principal_count=verification.record_count,
    )


def test_membership_fixed_lineage_and_verification_inclusion_are_portable() -> None:
    verification, _ = _prepare_verification(records=(_record(1),))
    first = _membership_snapshot(
        verification.snapshot,
        verification_head_root=_root("verification-head:1"),
        epoch=1,
        revision=1,
        parent=None,
    )
    second = _membership_snapshot(
        verification.snapshot,
        verification_head_root=_root("verification-head:1"),
        epoch=2,
        revision=2,
        parent=first,
    )
    assert first.stream_ref == second.stream_ref
    assert first.transition_id != second.transition_id
    assert second.parent_epoch == 1
    assert second.verification_set_root == verification.snapshot.verification_set_root
    request = MembershipCommitRequestV2(
        domain_root=DOMAIN_ROOT,
        scope_ref=SCOPE_REF,
        run_ref=RUN_REF,
        target_ref=TARGET,
        epoch=2,
        observed_epoch=12,
        request_ref=second.request_ref,
        stream_ref=second.stream_ref,
        transition_id=second.transition_id,
        snapshot=second,
    )
    assert MembershipCommitRequestV2.from_dict(request.to_dict()) == request
    unknown = request.to_dict()
    unknown["unknown"] = True
    with pytest.raises(ValueError, match="fields"):
        MembershipCommitRequestV2.from_dict(unknown)
    missing_root = request.to_dict()
    missing_root["request_root"] = ""
    with pytest.raises(ValueError, match="not canonical wire"):
        MembershipCommitRequestV2.from_dict(missing_root)
    missing_nested_root = request.to_dict()
    nested_snapshot = missing_nested_root["snapshot"]
    assert type(nested_snapshot) is dict
    nested_snapshot["membership_root"] = ""
    with pytest.raises(ValueError, match="not canonical wire"):
        MembershipCommitRequestV2.from_dict(missing_nested_root)


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"verification_policy_root": _root("other-policy")}, "lineage identity"),
        ({"verification_request_ref": "request:other"}, "lineage identity"),
        ({"verification_current_step": 3}, "timeline or count"),
        ({"verification_expires_at_step": 2}, "timeline or count"),
        ({"verification_record_count": 2}, "timeline or count"),
    ),
)
def test_membership_verification_projection_is_self_verifying(
    changes: dict[str, object],
    message: str,
) -> None:
    verification, _ = _prepare_verification(records=(_record(1),))
    snapshot = _membership_snapshot(
        verification.snapshot,
        verification_head_root=_root("verification-head:projection"),
        epoch=1,
        revision=1,
        parent=None,
    )

    with pytest.raises(ValueError, match=message):
        replace(snapshot, **changes, snapshot_root="")


def test_record_count_bound_and_record_freshness_are_exact() -> None:
    records = tuple(_record(index) for index in range(MAX_PRINCIPAL_VERIFICATIONS_V2))
    exact, _ = _prepare_verification(records=records)
    assert exact.snapshot.record_count == MAX_PRINCIPAL_VERIFICATIONS_V2
    with pytest.raises(ValueError, match="count exceeds"):
        _prepare_verification(
            records=(*records, _record(MAX_PRINCIPAL_VERIFICATIONS_V2))
        )
    stale = replace(_record(9_999), expires_at_step=8_999, verification_root="")
    with pytest.raises(ValueError, match="stale"):
        _prepare_verification(records=(stale,))


def test_record_array_and_snapshot_byte_bounds_accept_exact_reject_plus_one() -> None:
    evidence = tuple(
        _root(f"evidence:bound:{index}")
        for index in range(MAX_VERIFICATION_EVIDENCE_ROOTS_V2)
    )
    traces = tuple(
        _root(f"trace:bound:{index}")
        for index in range(MAX_VERIFICATION_SOURCE_TRACE_ROOTS_V2)
    )
    exact_record = replace(
        _record(50_000),
        evidence_roots=evidence,
        source_trace_roots=traces,
        verification_root="",
    )
    assert len(exact_record.evidence_roots) == MAX_VERIFICATION_EVIDENCE_ROOTS_V2
    with pytest.raises(ValueError, match="count"):
        replace(
            exact_record,
            evidence_roots=(*evidence, _root("evidence:over")),
            verification_root="",
        )
    with pytest.raises(ValueError, match="count"):
        replace(
            exact_record,
            source_trace_roots=(*traces, _root("trace:over")),
            verification_root="",
        )

    def padded_records(padding: int) -> tuple[PrincipalVerificationRecordV2, ...]:
        result: list[PrincipalVerificationRecordV2] = []
        remaining = padding
        for index in range(MAX_PRINCIPAL_VERIFICATIONS_V2):
            amount = min(remaining, 4095)
            remaining -= amount
            result.append(
                replace(
                    _record(
                        index, cluster=f"cluster:{index % MAX_MEMBERSHIP_CLUSTERS_V2}"
                    ),
                    verification_method="m" + ("x" * amount),
                    verification_root="",
                )
            )
        assert remaining == 0
        return tuple(result)

    base, _ = _prepare_verification(records=padded_records(0))
    padding = MAX_PRINCIPAL_VERIFICATION_SET_BYTES_V2 - len(
        base.snapshot.canonical_bytes()
    )
    assert 0 < padding < MAX_PRINCIPAL_VERIFICATIONS_V2 * 4095
    exact, _ = _prepare_verification(records=padded_records(padding))
    assert len(exact.snapshot.canonical_bytes()) == (
        MAX_PRINCIPAL_VERIFICATION_SET_BYTES_V2
    )
    with pytest.raises(ValueError, match="snapshot exceeds"):
        _prepare_verification(records=padded_records(padding + 1))


def test_portable_verification_request_cannot_create_authority() -> None:
    request, source = _prepare_verification(records=(_record(1),))
    attempt = advance_principal_verification_set_v2(
        request,
        source=source,
        authority_session=None,
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.DENIED
    with pytest.raises(TypeError, match="cannot be constructed"):
        VerifiedPrincipalVerificationSetStateV2()


def test_private_owner_has_no_v1_principal_or_process_local_authority() -> None:
    files = tuple(
        (ROOT / "pheroos/governance/_support_v2" / name).read_text()
        for name in (
            "durable_context.py",
            "principal_verification_records.py",
            "principal_verification_contracts.py",
            "principal_verification_source.py",
            "principal_verification_operations.py",
            "principal_verification_state.py",
            "membership_records.py",
            "membership_contracts.py",
            "membership_source.py",
            "membership_operations.py",
            "membership_state.py",
        )
    )
    text = "\n".join(files)
    assert "from pheroos.governance.principal" not in text
    assert "PrincipalVerification," not in text
    assert "principal_verification_is_authoritative" not in text
    assert "_ISSUANCE" not in text
    assert "RLock" not in text
    assert "principal_verification_set_advanced" in text
    assert "membership_epoch_committed" in text
    assert "verification_read_precondition" in text
    assert "_validate_verification_history" in text
    assert "_scoped_manifest_authority_matches_domain_v2" in text


def test_genesis_constants_and_transition_formula_are_closed() -> None:
    request, _ = _prepare_verification()
    assert request.snapshot.parent_transition_id == (
        PRINCIPAL_VERIFICATION_GENESIS_TRANSITION_ID_V2
    )
    assert request.snapshot.parent_snapshot_root == (
        PRINCIPAL_VERIFICATION_GENESIS_SNAPSHOT_ROOT_V2
    )
    assert request.transition_id == principal_verification_transition_id_v2(
        request.stream_ref, request.advance_ref
    )
