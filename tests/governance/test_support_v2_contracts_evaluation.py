from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import inspect
import json
from pathlib import Path
import pickle

import pytest

import pheroos.governance._support_v2.support_source_proof as support_source_proof

from pheroos.governance._support_v2.evaluation import (
    SupportEvaluationV2,
    _equivocations,
)
from pheroos.governance._support_v2.support_equivocation_contracts import (
    SupportEquivocationV2,
)
from pheroos.governance._support_v2.durable_context import (
    durable_support_context_v2,
)
from pheroos.governance._support_v2.membership_contracts import (
    MEMBERSHIP_GENESIS_SNAPSHOT_ROOT_V2,
    MEMBERSHIP_GENESIS_TRANSITION_ID_V2,
    MembershipClusterV2,
    MembershipPrincipalV2,
    MembershipSnapshotV2,
    membership_stream_ref_v2,
    membership_transition_id_v2,
)
from pheroos.governance._support_v2.principal_verification_contracts import (
    principal_verification_stream_ref_v2,
    principal_verification_transition_id_v2,
)
from pheroos.governance._support_v2.support_lease_contracts import (
    SupportLeaseProposalV2,
    SupportObservationV2,
)
from pheroos.governance._support_v2.support_source import (
    VerifiedSupportSourceV2,
    _child_request,
    _expected_source_roots_from_request,
    prepare_support_initialize_v2,
    prepare_support_issue_v2,
    prepare_support_revoke_v2,
    prepare_support_switch_v2,
    verify_support_request_source_v2,
)
from pheroos.governance._support_v2.support_source_proof import (
    _issue_source,
    _verified_source,
)
from pheroos.governance._support_v2.support_state_contracts import (
    replacement_matches_prior_v2,
    revocation_matches_lease_v2,
    support_history_advance_v2,
    support_event_lineage_v2,
    support_mutation_delta_root_v2,
    support_stream_ref_v2,
    support_switch_lineage_v2,
    support_transition_id_v2,
)
from pheroos.governance._support_v2.support_operations import (
    _decode_state_records,
    _state_records,
    _support_events,
    advance_support_state_v2,
    open_support_authority_session_v2,
)
from pheroos.governance._support_v2.support_projection import (
    _validate_transition_delta,
)
from pheroos.governance._support_v2.support_verification import (
    project_support_lease_v2,
    project_support_revocation_v2,
)
from pheroos.protocol import COMMIT_INTEGRITY_PROFILE_VERSION
from pheroos.protocol.authority_manifest_v2 import (
    ScopedProtocolManifestV2,
    scoped_capability_manifest_v2_from_dict,
)
from pheroos.governance._authority_session_v2.operations import _session_binding
from pheroos.governance._authority_v2 import InMemoryGovernanceStateStoreV2
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
)
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    AuthorityDomainV2,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    AuthorityDiagnosticCodeV2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    GovernanceReadPreconditionV2,
)
from pheroos.protocol.commit_models import (
    CollectiveCommitPolicy,
    CommitAssurance,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from pheroos.protocol.loader import load_capability_manifest


ROOT = Path(__file__).resolve().parents[2]
PROFILE = COMMIT_INTEGRITY_PROFILE_VERSION
TARGET = "decision:review"
RUN_REF = "run:support-v2"
EPOCH = 11


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode()).hexdigest()


def _manifest() -> ScopedProtocolManifestV2:
    scoped_payload = json.loads(
        (ROOT / "examples/scoped-output-protocol/capability.json").read_text()
    )
    scoped = scoped_capability_manifest_v2_from_dict(scoped_payload).protocol
    legacy = load_capability_manifest(
        ROOT / "examples/hybrid-commit-protocol/capability.json"
    )
    policy = legacy.protocol.collective_commit_policy
    assert type(policy) is CollectiveCommitPolicy
    return replace(scoped, collective_commit_policy=replace(policy, target=TARGET))


def _policy(manifest: ScopedProtocolManifestV2) -> CollectiveCommitPolicy:
    policy = manifest.collective_commit_policy
    assert type(policy) is CollectiveCommitPolicy
    return policy


def _membership(
    manifest: ScopedProtocolManifestV2,
    *,
    clusters: tuple[str, ...] = ("cluster:alpha", "cluster:beta"),
) -> MembershipSnapshotV2:
    context = durable_support_context_v2(
        manifest,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        target_ref=TARGET,
    )
    principal_clusters = tuple(
        MembershipClusterV2(
            cluster_ref=cluster,
            principals=(
                MembershipPrincipalV2(
                    principal_ref=f"principal:{cluster.rsplit(':', 1)[-1]}",
                    verification_root=_root(f"verification:{cluster}"),
                    verified_issuer_ref="issuer:identity",
                    verification_method="store-backed-verification-set-v2",
                    failure_domain_ref=f"failure:{cluster}",
                ),
            ),
        )
        for cluster in clusters
    )
    stream_ref = membership_stream_ref_v2(
        "scope:support-v2",
        PROFILE,
        CommitAssurance.EVIDENCE_BOUND,
        context.manifest_root,
        context.commit_policy_root,
        context.membership_policy_root,
        manifest.id,
        RUN_REF,
        TARGET,
    )
    request_ref = "request:membership:support-v2"
    verification_request_ref = "request:verification:support-v2"
    verification_stream_ref = principal_verification_stream_ref_v2(
        "scope:support-v2",
        PROFILE,
        CommitAssurance.EVIDENCE_BOUND,
        context.manifest_root,
        context.commit_policy_root,
        context.principal_verification_policy_root,
        manifest.id,
        RUN_REF,
        TARGET,
    )
    return MembershipSnapshotV2(
        domain_root=_root("domain:support-v2"),
        scope_ref="scope:support-v2",
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        authority_policy_root=context.authority_policy_root,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        membership_policy_root=context.membership_policy_root,
        protocol_ref=manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET,
        epoch=EPOCH,
        observed_epoch=20,
        request_ref=request_ref,
        stream_ref=stream_ref,
        transition_id=membership_transition_id_v2(stream_ref, request_ref),
        snapshot_ref="membership:support-v2",
        revision=1,
        parent_revision=0,
        parent_epoch=None,
        parent_transition_id=MEMBERSHIP_GENESIS_TRANSITION_ID_V2,
        parent_snapshot_root=MEMBERSHIP_GENESIS_SNAPSHOT_ROOT_V2,
        issued_at_step=1,
        expires_at_step=80,
        mutation_issuer_ref="issuer:membership",
        membership_method="store-current-projection-v2",
        provenance_ref="urn:test:membership:support-v2",
        source_trace_roots=(_root("trace:membership:support-v2"),),
        verification_stream_ref=verification_stream_ref,
        verification_transition_id=principal_verification_transition_id_v2(
            verification_stream_ref,
            verification_request_ref,
        ),
        verification_policy_root=context.principal_verification_policy_root,
        verification_request_ref=verification_request_ref,
        verification_revision=1,
        verification_head_root=_root("verification:head:support-v2"),
        verification_snapshot_root=_root("verification:snapshot:support-v2"),
        verification_set_root=_root("verification:set:support-v2"),
        verification_current_step=0,
        verification_expires_at_step=100,
        verification_record_count=len(principal_clusters),
        clusters=principal_clusters,
        cluster_count=len(principal_clusters),
        principal_count=len(principal_clusters),
    )


def _initialized(manifest: ScopedProtocolManifestV2):
    return prepare_support_initialize_v2(
        domain_root=_root("domain:support-v2"),
        scope_ref="scope:support-v2",
        manifest=manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        issuer_ref="issuer:support-v2",
        observed_epoch=20,
        mutation_ref="mutation:support:init",
        current_step=2,
        provenance_root=_root("provenance:support:init"),
        source_trace_roots=(_root("trace:support:init"),),
    )


def _observation(
    manifest: ScopedProtocolManifestV2,
    *,
    candidate_ref: str,
    claim_root: str,
    suffix: str,
    expires_at_step: int = 70,
) -> SupportObservationV2:
    policy = _policy(manifest)
    return SupportObservationV2(
        observation_ref=f"observation:{suffix}",
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=manifest.manifest_root,
        commit_policy_root=commit_policy_fingerprint(policy, profile=PROFILE),
        protocol_ref=manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET,
        candidate_ref=candidate_ref,
        claim_root=claim_root,
        epoch=EPOCH,
        source_ref=f"source:{suffix}",
        evidence_root=_root(f"evidence:{suffix}"),
        observed_at_step=3,
        expires_at_step=expires_at_step,
        provenance_root=_root(f"provenance:observation:{suffix}"),
        source_trace_roots=(
            _root(f"trace:observation:{suffix}:b"),
            _root(f"trace:observation:{suffix}:a"),
        ),
    )


def _proposal(
    manifest: ScopedProtocolManifestV2,
    observation: SupportObservationV2,
    *,
    candidate_ref: str,
    claim_root: str,
    principal_ref: str = "principal:alpha",
    nonce: str | None = None,
    suffix: str,
) -> SupportLeaseProposalV2:
    policy = _policy(manifest)
    return SupportLeaseProposalV2(
        proposal_ref=f"proposal:{suffix}",
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=manifest.manifest_root,
        commit_policy_root=commit_policy_fingerprint(policy, profile=PROFILE),
        protocol_ref=manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET,
        candidate_ref=candidate_ref,
        claim_root=claim_root,
        epoch=EPOCH,
        principal_ref=principal_ref,
        positive_observation_roots=(observation.observation_root,),
        nonce=f"nonce:{suffix}" if nonce is None else nonce,
        proposed_at_step=4,
        provenance_root=_root(f"provenance:proposal:{suffix}"),
        source_trace_roots=(_root(f"trace:proposal:{suffix}"),),
    )


def _lease(
    manifest: ScopedProtocolManifestV2,
    parent,
    membership: MembershipSnapshotV2,
    *,
    candidate_ref: str,
    claim_root: str,
    suffix: str,
    current_step: int,
    prior=None,
    principal_ref: str = "principal:alpha",
    nonce: str | None = None,
    issuance_issuer_ref: str = "issuer:support-v2",
    expires_at_step: int = 70,
):
    observation = _observation(
        manifest,
        candidate_ref=candidate_ref,
        claim_root=claim_root,
        suffix=suffix,
        expires_at_step=expires_at_step,
    )
    proposal = _proposal(
        manifest,
        observation,
        candidate_ref=candidate_ref,
        claim_root=claim_root,
        principal_ref=principal_ref,
        nonce=nonce,
        suffix=suffix,
    )
    lease = project_support_lease_v2(
        parent=parent,
        membership=membership,
        proposal=proposal,
        positive_observations=(observation,),
        manifest=manifest,
        mutation_transition_id=support_transition_id_v2(
            parent.stream_ref,
            f"mutation:{suffix}",
        ),
        issuance_issuer_ref=issuance_issuer_ref,
        current_step=current_step,
        prior_lease=prior,
        issuance_provenance_root=_root(f"provenance:issuance:{suffix}"),
        issuance_trace_roots=(_root(f"trace:issuance:{suffix}"),),
    )
    return lease, proposal, observation


def test_portable_observation_is_canonical_but_confers_no_authority() -> None:
    manifest = _manifest()
    claim = _root("claim:portable")
    first = _observation(
        manifest,
        candidate_ref="candidate:a",
        claim_root=claim,
        suffix="portable",
    )
    reversed_roots = replace(
        first,
        source_trace_roots=tuple(reversed(first.source_trace_roots)),
        observation_root="",
    )

    assert reversed_roots == first
    assert SupportObservationV2.from_dict(first.to_dict()) == first
    assert "authority" not in first.to_dict()
    assert "verification" not in first.to_dict()
    tampered = first.to_dict()
    tampered["evidence_root"] = _root("evidence:tampered")
    with pytest.raises(ValueError, match="mismatched"):
        SupportObservationV2.from_dict(tampered)


def test_initialize_binds_source_and_delta_inside_portable_snapshot() -> None:
    request, source = _initialized(_manifest())

    verify_support_request_source_v2(request, source=source)
    assert request.snapshot.source_context_root == source.context_root
    assert request.snapshot.mutation_delta_root.startswith("sha256:")
    assert request.snapshot.mutation_trace_roots == (_root("trace:support:init"),)
    assert request.snapshot.assurance is CommitAssurance.EVIDENCE_BOUND
    assert request.snapshot.manifest_root == _manifest().manifest_root
    assert request.snapshot.commit_policy_root == commit_policy_fingerprint(
        _policy(_manifest()),
        profile=PROFILE,
    )
    assert request.snapshot.authority_policy_root == _manifest().authority_policy.root()
    assert request.snapshot.target_ref == TARGET == request.target_ref
    assert request.snapshot.mutation_issuer_ref == request.mutation_issuer_ref
    assert type(source) is VerifiedSupportSourceV2
    assert type(request).from_dict(request.to_dict()) == request
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(source)


def test_source_verification_reads_each_upstream_once(monkeypatch) -> None:
    manifest = _manifest()
    membership = _membership(manifest)
    initialized, _ = _initialized(manifest)
    lease, proposal, observation = _lease(
        manifest,
        initialized.snapshot,
        membership,
        candidate_ref="candidate:a",
        claim_root=_root("claim:source-read-count"),
        suffix="source-read-count",
        current_step=5,
    )
    request = _child_request(
        initialized.snapshot,
        kind=type(initialized.mutation_kind).ISSUE,
        issuer_ref="issuer:support-v2",
        observed_epoch=21,
        mutation_ref="mutation:source-read-count",
        current_step=5,
        provenance_root=lease.issuance_provenance_root,
        trace_roots=tuple(lease.issuance_trace_roots),
        issued_lease=lease,
        membership=membership,
    )
    source = _issue_source(
        request=request,
        manifest=manifest,
        parent_state=object(),
        membership_state=object(),
        proposal=proposal,
        observations=(observation,),
    )
    calls = {"parent": 0, "membership": 0}
    parent_precondition = GovernanceReadPreconditionV2(
        stream_ref=initialized.stream_ref,
        expected_revision=initialized.snapshot.revision,
        expected_root=_root("head:source-read-count:parent"),
    )
    membership_precondition = GovernanceReadPreconditionV2(
        stream_ref=membership.stream_ref,
        expected_revision=membership.revision,
        expected_root=_root("head:source-read-count:membership"),
    )

    def support_parent(_state):
        calls["parent"] += 1
        return initialized.snapshot, parent_precondition

    def membership_parent(_state):
        calls["membership"] += 1
        return membership, membership_precondition

    monkeypatch.setattr(support_source_proof, "_support_parent", support_parent)
    monkeypatch.setattr(
        support_source_proof,
        "_membership_parent",
        membership_parent,
    )

    material = _verified_source(source)

    assert calls == {"parent": 1, "membership": 1}
    assert material.parent_precondition == parent_precondition
    assert material.membership_precondition == membership_precondition


def test_stream_is_one_target_run_policy_ledger_across_issuer_and_epoch() -> None:
    manifest = _manifest()
    first, _ = _initialized(manifest)
    second, _ = prepare_support_initialize_v2(
        domain_root=_root("domain:support-v2"),
        scope_ref="scope:support-v2",
        manifest=manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        issuer_ref="issuer:successor",
        observed_epoch=99,
        mutation_ref="mutation:support:other-init",
        current_step=7,
        provenance_root=_root("provenance:support:other-init"),
        source_trace_roots=(_root("trace:support:other-init"),),
    )

    assert first.stream_ref == second.stream_ref
    assert first.snapshot.mutation_issuer_ref != second.snapshot.mutation_issuer_ref
    assert first.observed_epoch != second.observed_epoch
    assert tuple(inspect.signature(support_stream_ref_v2).parameters) == (
        "scope_ref",
        "profile",
        "assurance",
        "manifest_root",
        "commit_policy_root",
        "protocol_ref",
        "run_ref",
        "target_ref",
    )
    context = first.snapshot
    base = support_stream_ref_v2(
        context.scope_ref,
        context.profile,
        context.assurance,
        context.manifest_root,
        context.commit_policy_root,
        context.protocol_ref,
        context.run_ref,
        context.target_ref,
    )
    variants = (
        support_stream_ref_v2(
            context.scope_ref,
            "profile:other",
            context.assurance,
            context.manifest_root,
            context.commit_policy_root,
            context.protocol_ref,
            context.run_ref,
            context.target_ref,
        ),
        support_stream_ref_v2(
            context.scope_ref,
            context.profile,
            CommitAssurance.CERTIFIED,
            context.manifest_root,
            context.commit_policy_root,
            context.protocol_ref,
            context.run_ref,
            context.target_ref,
        ),
        support_stream_ref_v2(
            "scope:other",
            context.profile,
            context.assurance,
            context.manifest_root,
            context.commit_policy_root,
            context.protocol_ref,
            context.run_ref,
            context.target_ref,
        ),
        support_stream_ref_v2(
            context.scope_ref,
            context.profile,
            context.assurance,
            _root("manifest:other"),
            context.commit_policy_root,
            context.protocol_ref,
            context.run_ref,
            context.target_ref,
        ),
        support_stream_ref_v2(
            context.scope_ref,
            context.profile,
            context.assurance,
            context.manifest_root,
            _root("policy:other"),
            context.protocol_ref,
            context.run_ref,
            context.target_ref,
        ),
        support_stream_ref_v2(
            context.scope_ref,
            context.profile,
            context.assurance,
            context.manifest_root,
            context.commit_policy_root,
            "protocol:other",
            context.run_ref,
            context.target_ref,
        ),
        support_stream_ref_v2(
            context.scope_ref,
            context.profile,
            context.assurance,
            context.manifest_root,
            context.commit_policy_root,
            context.protocol_ref,
            "run:other",
            context.target_ref,
        ),
        support_stream_ref_v2(
            context.scope_ref,
            context.profile,
            context.assurance,
            context.manifest_root,
            context.commit_policy_root,
            context.protocol_ref,
            context.run_ref,
            "target:other",
        ),
    )
    assert base == first.stream_ref
    assert base not in variants
    assert len(set(variants)) == len(variants)


def test_history_delta_binds_epoch_step_and_complete_mutation_lineage() -> None:
    manifest = _manifest()
    variants = (
        (20, 2, _root("provenance:lineage:a"), (_root("trace:lineage:a"),)),
        (21, 2, _root("provenance:lineage:a"), (_root("trace:lineage:a"),)),
        (20, 3, _root("provenance:lineage:a"), (_root("trace:lineage:a"),)),
        (20, 2, _root("provenance:lineage:b"), (_root("trace:lineage:a"),)),
        (20, 2, _root("provenance:lineage:a"), (_root("trace:lineage:b"),)),
    )
    requests = tuple(
        prepare_support_initialize_v2(
            domain_root=_root("domain:support-v2"),
            scope_ref="scope:support-v2",
            manifest=manifest,
            profile=PROFILE,
            run_ref=RUN_REF,
            target_ref=TARGET,
            issuer_ref="issuer:support-v2",
            observed_epoch=epoch,
            mutation_ref="mutation:support:lineage-binding",
            current_step=step,
            provenance_root=provenance,
            source_trace_roots=traces,
        )[0]
        for epoch, step, provenance, traces in variants
    )

    assert len({item.transition_id for item in requests}) == 1
    assert len({item.snapshot.mutation_delta_root for item in requests}) == len(
        requests
    )
    assert len({item.snapshot.history_root for item in requests}) == len(requests)
    assert len({item.snapshot.source_context_root for item in requests}) == len(
        requests
    )


def test_request_wire_rejects_bool_observed_epoch() -> None:
    request, _ = prepare_support_initialize_v2(
        domain_root=_root("domain:bool-epoch"),
        scope_ref="scope:bool-epoch",
        manifest=_manifest(),
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        issuer_ref="issuer:support-v2",
        observed_epoch=1,
        mutation_ref="mutation:bool-epoch",
        current_step=1,
        provenance_root=_root("provenance:bool-epoch"),
        source_trace_roots=(_root("trace:bool-epoch"),),
    )
    payload = request.to_dict()
    payload["observed_epoch"] = True

    with pytest.raises(ValueError, match="observed_epoch"):
        type(request).from_dict(payload)


def test_all_prepare_entrypoints_reject_nonexact_manifest_before_upstreams() -> None:
    assert "lease_ref" not in inspect.signature(prepare_support_issue_v2).parameters
    assert (
        "revocation_ref" not in inspect.signature(prepare_support_revoke_v2).parameters
    )
    switch_parameters = inspect.signature(prepare_support_switch_v2).parameters
    assert "revocation_ref" not in switch_parameters
    assert "replacement_lease_ref" not in switch_parameters
    with pytest.raises(TypeError, match="ScopedProtocolManifestV2"):
        prepare_support_initialize_v2(
            domain_root=_root("domain:invalid-manifest"),
            scope_ref="scope:invalid-manifest",
            manifest=object(),  # type: ignore[arg-type]
            profile=PROFILE,
            run_ref=RUN_REF,
            target_ref=TARGET,
            issuer_ref="issuer:test",
            observed_epoch=1,
            mutation_ref="mutation:test",
            current_step=1,
            provenance_root=_root("provenance:test"),
            source_trace_roots=(_root("trace:test"),),
        )

    calls = (
        lambda: prepare_support_issue_v2(
            manifest=object(),  # type: ignore[arg-type]
            parent_state=object(),
            membership_state=object(),
            proposal=object(),  # type: ignore[arg-type]
            positive_observations=(),
            issuer_ref="issuer:test",
            observed_epoch=1,
            mutation_ref="mutation:test",
            current_step=1,
            issuance_provenance_root=_root("issuance:test"),
            issuance_trace_roots=(_root("trace:test"),),
        ),
        lambda: prepare_support_revoke_v2(
            manifest=object(),  # type: ignore[arg-type]
            parent_state=object(),
            lease_root=_root("lease:test"),
            reason_codes=("test",),
            issuer_ref="issuer:test",
            observed_epoch=1,
            mutation_ref="mutation:test",
            current_step=1,
            provenance_root=_root("provenance:test"),
            source_trace_roots=(_root("trace:test"),),
        ),
        lambda: prepare_support_switch_v2(
            manifest=object(),  # type: ignore[arg-type]
            parent_state=object(),
            membership_state=object(),
            prior_lease_root=_root("lease:test"),
            proposal=object(),  # type: ignore[arg-type]
            positive_observations=(),
            issuer_ref="issuer:test",
            revocation_reason_codes=("test",),
            observed_epoch=1,
            mutation_ref="mutation:test",
            current_step=1,
            revocation_provenance_root=_root("revoke:test"),
            revocation_trace_roots=(_root("trace:revoke"),),
            issuance_provenance_root=_root("issue:test"),
            issuance_trace_roots=(_root("trace:issue"),),
        ),
    )
    for call in calls:
        with pytest.raises(TypeError, match="ScopedProtocolManifestV2"):
            call()


def test_lease_derives_principal_only_from_current_membership_projection() -> None:
    manifest = _manifest()
    membership = _membership(manifest)
    initialized, _ = _initialized(manifest)
    claim = _root("claim:membership-derived")
    lease, proposal, observation = _lease(
        manifest,
        initialized.snapshot,
        membership,
        candidate_ref="candidate:a",
        claim_root=claim,
        suffix="membership-derived",
        current_step=5,
    )
    alpha = membership.clusters[0].principals[0]

    assert lease.principal_ref == proposal.principal_ref
    assert lease.principal_cluster_ref == membership.clusters[0].cluster_ref
    assert lease.membership_principal_root == alpha.principal_root
    assert lease.principal_verification_root == alpha.verification_root
    assert lease.positive_observations == (observation,)
    assert lease.positive_observation_roots == (observation.observation_root,)
    assert lease.positive_observation_set_root.startswith("sha256:")
    assert type(lease).from_dict(lease.to_dict()) == lease

    absent = replace(proposal, principal_ref="principal:absent", proposal_root="")
    with pytest.raises(ValueError, match="absent"):
        project_support_lease_v2(
            parent=initialized.snapshot,
            membership=membership,
            proposal=absent,
            positive_observations=(observation,),
            manifest=manifest,
            mutation_transition_id=support_transition_id_v2(
                initialized.stream_ref,
                "mutation:absent",
            ),
            issuance_issuer_ref="issuer:support-v2",
            current_step=5,
            prior_lease=None,
            issuance_provenance_root=_root("provenance:absent"),
            issuance_trace_roots=(_root("trace:absent"),),
        )


def test_observation_records_roots_and_policy_ttl_are_bidirectionally_bound() -> None:
    manifest = _manifest()
    membership = _membership(manifest)
    initialized, _ = _initialized(manifest)
    claim = _root("claim:observation-binding")
    observation = _observation(
        manifest,
        candidate_ref="candidate:a",
        claim_root=claim,
        suffix="observation-binding",
    )
    proposal = _proposal(
        manifest,
        observation,
        candidate_ref="candidate:a",
        claim_root=claim,
        suffix="observation-binding",
    )
    other = _observation(
        manifest,
        candidate_ref="candidate:a",
        claim_root=claim,
        suffix="other",
    )
    with pytest.raises(ValueError, match="roots are incomplete"):
        project_support_lease_v2(
            parent=initialized.snapshot,
            membership=membership,
            proposal=proposal,
            positive_observations=(other,),
            manifest=manifest,
            mutation_transition_id=support_transition_id_v2(
                initialized.stream_ref,
                "mutation:wrong-observation",
            ),
            issuance_issuer_ref="issuer:support-v2",
            current_step=5,
            prior_lease=None,
            issuance_provenance_root=_root("provenance:wrong-observation"),
            issuance_trace_roots=(_root("trace:wrong-observation"),),
        )
    short = replace(observation, expires_at_step=10, observation_root="")
    short_proposal = replace(
        proposal,
        positive_observation_roots=(short.observation_root,),
        proposal_root="",
    )
    with pytest.raises(ValueError, match="observation freshness"):
        project_support_lease_v2(
            parent=initialized.snapshot,
            membership=membership,
            proposal=short_proposal,
            positive_observations=(short,),
            manifest=manifest,
            mutation_transition_id=support_transition_id_v2(
                initialized.stream_ref,
                "mutation:short-observation",
            ),
            issuance_issuer_ref="issuer:support-v2",
            current_step=5,
            prior_lease=None,
            issuance_provenance_root=_root("provenance:short-observation"),
            issuance_trace_roots=(_root("trace:short-observation"),),
        )


def test_cross_claim_does_not_create_equivocation() -> None:
    manifest = _manifest()
    membership = _membership(manifest)
    initialized, _ = _initialized(manifest)
    first, _, _ = _lease(
        manifest,
        initialized.snapshot,
        membership,
        candidate_ref="candidate:a",
        claim_root=_root("claim:a"),
        suffix="cross-claim-a",
        current_step=5,
    )
    first_request = _child_request(
        initialized.snapshot,
        kind=type(initialized.mutation_kind).ISSUE,
        issuer_ref="issuer:support-v2",
        observed_epoch=21,
        mutation_ref="mutation:cross-claim-a",
        current_step=5,
        provenance_root=first.issuance_provenance_root,
        trace_roots=tuple(first.issuance_trace_roots),
        issued_lease=first,
        membership=membership,
    )
    second, _, _ = _lease(
        manifest,
        first_request.snapshot,
        membership,
        candidate_ref="candidate:b",
        claim_root=_root("claim:b"),
        suffix="cross-claim-b",
        current_step=6,
    )
    second_request = _child_request(
        first_request.snapshot,
        kind=type(initialized.mutation_kind).ISSUE,
        issuer_ref="issuer:support-v2",
        observed_epoch=22,
        mutation_ref="mutation:cross-claim-b",
        current_step=6,
        provenance_root=second.issuance_provenance_root,
        trace_roots=tuple(second.issuance_trace_roots),
        issued_lease=second,
        membership=membership,
    )

    assert (
        _equivocations(
            second_request.snapshot,
            tuple(second_request.snapshot.leases),
            current_step=7,
        )
        == ()
    )


def test_nonce_replay_scope_is_cluster_local_like_v1_evaluation() -> None:
    legacy_evaluation = (ROOT / "pheroos/governance/_support/evaluation.py").read_text()
    assert (
        'replay_key = f"{lease.principal_cluster_id}\\x00{lease.nonce}"'
        in legacy_evaluation
    )
    manifest = _manifest()
    membership = _membership(manifest)
    initialized, _ = _initialized(manifest)
    shared_nonce = "nonce:shared-across-clusters"
    alpha, _, _ = _lease(
        manifest,
        initialized.snapshot,
        membership,
        candidate_ref="candidate:a",
        claim_root=_root("claim:cluster-local-nonce"),
        suffix="cluster-local-nonce:alpha",
        current_step=5,
        principal_ref="principal:alpha",
        nonce=shared_nonce,
    )
    first = _child_request(
        initialized.snapshot,
        kind=type(initialized.mutation_kind).ISSUE,
        issuer_ref="issuer:support-v2",
        observed_epoch=21,
        mutation_ref="mutation:cluster-local-nonce:alpha",
        current_step=5,
        provenance_root=alpha.issuance_provenance_root,
        trace_roots=tuple(alpha.issuance_trace_roots),
        issued_lease=alpha,
        membership=membership,
    )
    beta, _, _ = _lease(
        manifest,
        first.snapshot,
        membership,
        candidate_ref="candidate:a",
        claim_root=_root("claim:cluster-local-nonce"),
        suffix="cluster-local-nonce:beta",
        current_step=6,
        principal_ref="principal:beta",
        nonce=shared_nonce,
    )
    second = _child_request(
        first.snapshot,
        kind=type(initialized.mutation_kind).ISSUE,
        issuer_ref="issuer:support-v2",
        observed_epoch=22,
        mutation_ref="mutation:cluster-local-nonce:beta",
        current_step=6,
        provenance_root=beta.issuance_provenance_root,
        trace_roots=tuple(beta.issuance_trace_roots),
        issued_lease=beta,
        membership=membership,
    )

    assert {item.principal_cluster_ref for item in second.snapshot.leases} == {
        "cluster:alpha",
        "cluster:beta",
    }
    assert {item.nonce for item in second.snapshot.leases} == {shared_nonce}


def test_mutation_issuer_cannot_misattribute_an_issued_lease() -> None:
    manifest = _manifest()
    membership = _membership(manifest)
    initialized, _ = _initialized(manifest)
    lease, _, _ = _lease(
        manifest,
        initialized.snapshot,
        membership,
        candidate_ref="candidate:a",
        claim_root=_root("claim:issuer-binding"),
        suffix="issuer-binding",
        current_step=5,
        issuance_issuer_ref="issuer:original",
    )

    with pytest.raises(ValueError, match="another mutation issuer"):
        _child_request(
            initialized.snapshot,
            kind=type(initialized.mutation_kind).ISSUE,
            issuer_ref="issuer:successor",
            observed_epoch=21,
            mutation_ref="mutation:issuer-binding",
            current_step=5,
            provenance_root=_root("provenance:issuer-binding"),
            trace_roots=(_root("trace:issuer-binding"),),
            issued_lease=lease,
            membership=membership,
        )


def test_each_mutation_kind_requires_exact_step_and_lineage() -> None:
    manifest = _manifest()
    membership = _membership(manifest)
    initialized, _ = _initialized(manifest)
    lease, _, _ = _lease(
        manifest,
        initialized.snapshot,
        membership,
        candidate_ref="candidate:a",
        claim_root=_root("claim:exact-mutation"),
        suffix="exact-mutation:issue",
        current_step=5,
    )
    issue_args = {
        "kind": type(initialized.mutation_kind).ISSUE,
        "issuer_ref": "issuer:support-v2",
        "observed_epoch": 21,
        "mutation_ref": "mutation:exact-mutation:issue",
        "issued_lease": lease,
        "membership": membership,
    }
    with pytest.raises(ValueError, match="issued lease step"):
        _child_request(
            initialized.snapshot,
            **issue_args,
            current_step=6,
            provenance_root=lease.issuance_provenance_root,
            trace_roots=tuple(lease.issuance_trace_roots),
        )
    with pytest.raises(ValueError, match="mutation lineage"):
        _child_request(
            initialized.snapshot,
            **issue_args,
            current_step=5,
            provenance_root=_root("provenance:wrong-issue-lineage"),
            trace_roots=tuple(lease.issuance_trace_roots),
        )
    issued = _child_request(
        initialized.snapshot,
        **issue_args,
        current_step=5,
        provenance_root=lease.issuance_provenance_root,
        trace_roots=tuple(lease.issuance_trace_roots),
    )
    revocation = project_support_revocation_v2(
        lease,
        mutation_transition_id=support_transition_id_v2(
            issued.stream_ref,
            "mutation:exact-mutation:revoke",
        ),
        reason_codes=("exact-mutation",),
        revocation_issuer_ref="issuer:successor",
        current_step=6,
        provenance_root=_root("provenance:exact-mutation:revoke"),
        source_trace_roots=(_root("trace:exact-mutation:revoke"),),
    )
    revoke_args = {
        "kind": type(initialized.mutation_kind).REVOKE,
        "issuer_ref": "issuer:successor",
        "observed_epoch": 22,
        "mutation_ref": "mutation:exact-mutation:revoke",
        "revoked_lease": lease,
        "revocation": revocation,
    }
    with pytest.raises(ValueError, match="revocation step"):
        _child_request(
            issued.snapshot,
            **revoke_args,
            current_step=7,
            provenance_root=revocation.provenance_root,
            trace_roots=tuple(revocation.source_trace_roots),
        )
    with pytest.raises(ValueError, match="mutation lineage"):
        _child_request(
            issued.snapshot,
            **revoke_args,
            current_step=6,
            provenance_root=_root("provenance:wrong-revoke-lineage"),
            trace_roots=tuple(revocation.source_trace_roots),
        )
    replacement, _, _ = _lease(
        manifest,
        issued.snapshot,
        membership,
        candidate_ref="candidate:b",
        claim_root=lease.claim_root,
        suffix="exact-mutation:switch",
        current_step=6,
        prior=lease,
        issuance_issuer_ref="issuer:successor",
    )
    switch_revocation = project_support_revocation_v2(
        lease,
        mutation_transition_id=support_transition_id_v2(
            issued.stream_ref,
            "mutation:exact-mutation:switch",
        ),
        reason_codes=("exact-switch",),
        revocation_issuer_ref="issuer:successor",
        current_step=6,
        provenance_root=_root("provenance:exact-mutation:switch-revoke"),
        source_trace_roots=(_root("trace:exact-mutation:switch-revoke"),),
    )
    with pytest.raises(ValueError, match="mutation lineage"):
        _child_request(
            issued.snapshot,
            kind=type(initialized.mutation_kind).SWITCH,
            issuer_ref="issuer:successor",
            observed_epoch=22,
            mutation_ref="mutation:exact-mutation:switch",
            current_step=6,
            provenance_root=_root("provenance:wrong-switch-lineage"),
            trace_roots=(_root("trace:wrong-switch-lineage"),),
            issued_lease=replacement,
            revoked_lease=lease,
            revocation=switch_revocation,
            membership=membership,
        )


def test_same_claim_overlap_is_bound_to_snapshot_and_lease_set() -> None:
    manifest = _manifest()
    membership = _membership(manifest)
    initialized, _ = _initialized(manifest)
    claim = _root("claim:equivocation")
    first, _, _ = _lease(
        manifest,
        initialized.snapshot,
        membership,
        candidate_ref="candidate:a",
        claim_root=claim,
        suffix="equivocation-a",
        current_step=5,
    )
    first_request = _child_request(
        initialized.snapshot,
        kind=type(initialized.mutation_kind).ISSUE,
        issuer_ref="issuer:support-v2",
        observed_epoch=21,
        mutation_ref="mutation:equivocation-a",
        current_step=5,
        provenance_root=first.issuance_provenance_root,
        trace_roots=tuple(first.issuance_trace_roots),
        issued_lease=first,
        membership=membership,
    )
    second, _, _ = _lease(
        manifest,
        first_request.snapshot,
        membership,
        candidate_ref="candidate:b",
        claim_root=claim,
        suffix="equivocation-b",
        current_step=6,
    )
    second_request = _child_request(
        first_request.snapshot,
        kind=type(initialized.mutation_kind).ISSUE,
        issuer_ref="issuer:support-v2",
        observed_epoch=22,
        mutation_ref="mutation:equivocation-b",
        current_step=6,
        provenance_root=second.issuance_provenance_root,
        trace_roots=tuple(second.issuance_trace_roots),
        issued_lease=second,
        membership=membership,
    )
    findings = _equivocations(
        second_request.snapshot,
        tuple(second_request.snapshot.leases),
        current_step=7,
    )

    assert len(findings) == 1
    assert findings[0].claim_root == claim
    assert findings[0].support_snapshot_root == second_request.snapshot.snapshot_root
    assert findings[0].lease_set_root == second_request.snapshot.lease_set_root
    assert set(findings[0].conflicting_candidate_refs) == {
        "candidate:a",
        "candidate:b",
    }


def test_switch_at_revocation_step_has_no_overlap() -> None:
    manifest = _manifest()
    membership = _membership(manifest)
    initialized, _ = _initialized(manifest)
    claim = _root("claim:switch")
    first, _, _ = _lease(
        manifest,
        initialized.snapshot,
        membership,
        candidate_ref="candidate:a",
        claim_root=claim,
        suffix="switch-a",
        current_step=5,
    )
    first_request = _child_request(
        initialized.snapshot,
        kind=type(initialized.mutation_kind).ISSUE,
        issuer_ref="issuer:support-v2",
        observed_epoch=21,
        mutation_ref="mutation:switch-a",
        current_step=5,
        provenance_root=first.issuance_provenance_root,
        trace_roots=tuple(first.issuance_trace_roots),
        issued_lease=first,
        membership=membership,
    )
    revocation = project_support_revocation_v2(
        first,
        mutation_transition_id=support_transition_id_v2(
            first_request.stream_ref,
            "mutation:switch-b",
        ),
        reason_codes=("candidate-switch",),
        revocation_issuer_ref="issuer:successor",
        current_step=6,
        provenance_root=_root("provenance:revocation:switch:a"),
        source_trace_roots=(_root("trace:revocation:switch:a"),),
    )
    replacement, _, _ = _lease(
        manifest,
        first_request.snapshot,
        membership,
        candidate_ref="candidate:b",
        claim_root=claim,
        suffix="switch-b",
        current_step=6,
        prior=first,
        issuance_issuer_ref="issuer:successor",
    )
    switch_provenance, switch_traces = support_switch_lineage_v2(
        revocation_provenance_root=revocation.provenance_root,
        revocation_trace_roots=revocation.source_trace_roots,
        issuance_provenance_root=replacement.issuance_provenance_root,
        issuance_trace_roots=replacement.issuance_trace_roots,
    )
    switched = _child_request(
        first_request.snapshot,
        kind=type(initialized.mutation_kind).SWITCH,
        issuer_ref="issuer:successor",
        observed_epoch=22,
        mutation_ref="mutation:switch-b",
        current_step=6,
        provenance_root=switch_provenance,
        trace_roots=switch_traces,
        issued_lease=replacement,
        revoked_lease=first,
        revocation=revocation,
        membership=membership,
    )

    assert (
        _equivocations(
            switched.snapshot,
            tuple(switched.snapshot.leases),
            current_step=7,
        )
        == ()
    )
    assert replacement.issuance_issuer_ref == "issuer:successor"
    assert revocation.lease_issuance_issuer_ref == first.issuance_issuer_ref
    assert revocation.revocation_issuer_ref == "issuer:successor"
    assert revocation_matches_lease_v2(revocation, first)
    assert replacement_matches_prior_v2(replacement, first)
    assert switched.snapshot.stream_ref == first_request.snapshot.stream_ref
    assert switched.snapshot.mutation_issuer_ref == "issuer:successor"


def test_evaluation_record_round_trip_rejects_cross_bound_finding() -> None:
    manifest = _manifest()
    membership = _membership(manifest)
    initialized, _ = _initialized(manifest)
    evaluation = SupportEvaluationV2(
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=manifest.manifest_root,
        commit_policy_root=membership.commit_policy_root,
        protocol_ref=manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET,
        candidate_ref="candidate:a",
        claim_root=_root("claim:evaluation"),
        epoch=EPOCH,
        current_step=7,
        membership_snapshot_root=membership.snapshot_root,
        membership_root=membership.membership_root,
        support_snapshot_root=initialized.snapshot.snapshot_root,
        eligible_cluster_count=2,
        active_support_cluster_count=0,
        support_ratio_ppm=0,
        policy_threshold_clusters=1,
        policy_support_met=False,
        active_cluster_refs=(),
        included_lease_roots=(),
        excluded_lease_roots=(),
        equivocations=(),
    )
    assert SupportEvaluationV2.from_dict(evaluation.to_dict()) == evaluation


def test_evaluation_rejects_cross_bound_or_unexcluded_equivocation() -> None:
    manifest = _manifest()
    membership = _membership(manifest)
    initialized, _ = _initialized(manifest)
    claim_root = _root("claim:evaluation-binding")
    conflicting_roots = (
        _root("lease:evaluation-binding:a"),
        _root("lease:evaluation-binding:b"),
    )
    finding = SupportEquivocationV2(
        target_ref=TARGET,
        claim_root=claim_root,
        epoch=EPOCH,
        principal_cluster_ref="cluster:alpha",
        support_snapshot_root=initialized.snapshot.snapshot_root,
        lease_set_root=initialized.snapshot.lease_set_root,
        conflicting_candidate_refs=("candidate:a", "candidate:b"),
        conflicting_lease_roots=conflicting_roots,
        first_overlap_step=6,
    )
    arguments = {
        "profile": PROFILE,
        "assurance": CommitAssurance.EVIDENCE_BOUND,
        "manifest_root": manifest.manifest_root,
        "commit_policy_root": membership.commit_policy_root,
        "protocol_ref": manifest.id,
        "run_ref": RUN_REF,
        "target_ref": TARGET,
        "candidate_ref": "candidate:a",
        "claim_root": claim_root,
        "epoch": EPOCH,
        "current_step": 7,
        "membership_snapshot_root": membership.snapshot_root,
        "membership_root": membership.membership_root,
        "support_snapshot_root": initialized.snapshot.snapshot_root,
        "eligible_cluster_count": 2,
        "active_support_cluster_count": 0,
        "support_ratio_ppm": 0,
        "policy_threshold_clusters": 1,
        "policy_support_met": False,
        "active_cluster_refs": (),
        "included_lease_roots": (),
        "excluded_lease_roots": conflicting_roots,
        "equivocations": (finding,),
    }
    assert SupportEvaluationV2(**arguments).equivocations == (finding,)

    cross_bound = (
        replace(finding, target_ref="decision:other", finding_root=""),
        replace(finding, claim_root=_root("claim:other"), finding_root=""),
        replace(finding, epoch=EPOCH + 1, finding_root=""),
        replace(
            finding,
            support_snapshot_root=_root("support:snapshot:other"),
            finding_root="",
        ),
    )
    for forged in cross_bound:
        with pytest.raises(ValueError, match="cross-bound"):
            SupportEvaluationV2(**{**arguments, "equivocations": (forged,)})

    with pytest.raises(ValueError, match="future step"):
        SupportEvaluationV2(
            **{
                **arguments,
                "equivocations": (
                    replace(finding, first_overlap_step=8, finding_root=""),
                ),
            }
        )
    with pytest.raises(ValueError, match="omits an equivocated"):
        SupportEvaluationV2(
            **{**arguments, "excluded_lease_roots": conflicting_roots[:1]}
        )
    with pytest.raises(ValueError, match="counts an equivocated cluster"):
        SupportEvaluationV2(
            **{
                **arguments,
                "active_support_cluster_count": 1,
                "support_ratio_ppm": 500_000,
                "policy_support_met": True,
                "active_cluster_refs": ("cluster:alpha",),
            }
        )


def test_current_projection_evicts_expiry_and_history_stays_constant_space() -> None:
    manifest = _manifest()
    membership = replace(
        _membership(manifest),
        expires_at_step=1_000_000,
        verification_expires_at_step=1_000_001,
        snapshot_root="",
    )
    initialized, _ = _initialized(manifest)
    parent = initialized.snapshot
    requests = []
    current_step = 5
    snapshot_sizes: list[int] = []
    for index in range(96):
        suffix = f"churn-{index:03d}"
        lease, _, _ = _lease(
            manifest,
            parent,
            membership,
            candidate_ref="candidate:a",
            claim_root=_root("claim:bounded-churn"),
            suffix=suffix,
            current_step=current_step,
            expires_at_step=1_000_000,
        )
        prior_roots = tuple(item.lease_root for item in parent.leases)
        request = _child_request(
            parent,
            kind=type(initialized.mutation_kind).ISSUE,
            issuer_ref="issuer:support-v2",
            observed_epoch=21 + index,
            mutation_ref=f"mutation:{suffix}",
            current_step=current_step,
            provenance_root=lease.issuance_provenance_root,
            trace_roots=tuple(lease.issuance_trace_roots),
            issued_lease=lease,
            membership=membership,
        )
        _validate_transition_delta(request, parent)
        assert len(request.snapshot.leases) == 1
        assert tuple(request.evicted_lease_roots) == prior_roots
        assert request.snapshot.history_count == request.snapshot.revision
        requests.append(request)
        snapshot_sizes.append(len(request.snapshot.canonical_bytes()))
        parent = request.snapshot
        current_step = lease.expires_at_step

    assert requests[-1].snapshot.history_count == 97
    assert requests[-1].snapshot.history_root != initialized.snapshot.history_root
    assert max(snapshot_sizes) - min(snapshot_sizes) < 256
    assert all(not hasattr(item.snapshot, "revocations") for item in requests)
    source_context_root, source_verification_root = _expected_source_roots_from_request(
        requests[-1]
    )
    lineage = support_event_lineage_v2(
        requests[-1],
        {
            "grant_ref": "grant:test",
            "grant_root": _root("grant:test"),
            "grant_binding_ref": _root("grant-binding:test"),
        },
        source_context_root=source_context_root,
        source_verification_root=source_verification_root,
        parent_head_root=_root("head:parent:test"),
        read_set_root=_root("read-set:test"),
    )
    assert lineage["evicted_lease_roots"] == list(requests[-1].evicted_lease_roots)
    assert lineage["parent_history_root"] == requests[-2].snapshot.history_root
    assert lineage["history_root"] == requests[-1].snapshot.history_root


def test_eviction_delta_and_parent_bound_history_reject_self_reported_tampering() -> (
    None
):
    manifest = _manifest()
    membership = _membership(manifest)
    initialized, _ = _initialized(manifest)
    first, _, _ = _lease(
        manifest,
        initialized.snapshot,
        membership,
        candidate_ref="candidate:a",
        claim_root=_root("claim:history-tamper"),
        suffix="history-first",
        current_step=5,
    )
    first_request = _child_request(
        initialized.snapshot,
        kind=type(initialized.mutation_kind).ISSUE,
        issuer_ref="issuer:support-v2",
        observed_epoch=21,
        mutation_ref="mutation:history-first",
        current_step=5,
        provenance_root=first.issuance_provenance_root,
        trace_roots=tuple(first.issuance_trace_roots),
        issued_lease=first,
        membership=membership,
    )
    second, _, _ = _lease(
        manifest,
        first_request.snapshot,
        membership,
        candidate_ref="candidate:b",
        claim_root=_root("claim:history-tamper:b"),
        suffix="history-second",
        current_step=6,
    )
    second_request = _child_request(
        first_request.snapshot,
        kind=type(initialized.mutation_kind).ISSUE,
        issuer_ref="issuer:support-v2",
        observed_epoch=22,
        mutation_ref="mutation:history-second",
        current_step=6,
        provenance_root=second.issuance_provenance_root,
        trace_roots=tuple(second.issuance_trace_roots),
        issued_lease=second,
        membership=membership,
    )

    rewritten_projection = replace(
        second_request.snapshot,
        leases=(second,),
        lease_set_root="",
        snapshot_root="",
    )
    rewritten_request = replace(
        second_request,
        snapshot=rewritten_projection,
        request_root="",
    )
    with pytest.raises(ValueError, match="projection delta"):
        _validate_transition_delta(rewritten_request, first_request.snapshot)

    fake_parent_history = _root("history:substituted-parent")
    fake_history, fake_count = support_history_advance_v2(
        parent_history_root=fake_parent_history,
        parent_history_count=first_request.snapshot.history_count,
        transition_id=second_request.transition_id,
        mutation_delta_root=second_request.snapshot.mutation_delta_root,
    )
    rewritten_history_snapshot = replace(
        second_request.snapshot,
        parent_history_root=fake_parent_history,
        history_root=fake_history,
        history_count=fake_count,
        snapshot_root="",
    )
    rewritten_history_request = replace(
        second_request,
        snapshot=rewritten_history_snapshot,
        request_root="",
    )
    with pytest.raises(ValueError, match="parent history"):
        _validate_transition_delta(rewritten_history_request, first_request.snapshot)

    eviction_step = first.expires_at_step
    expiring, _, _ = _lease(
        manifest,
        first_request.snapshot,
        membership,
        candidate_ref="candidate:c",
        claim_root=_root("claim:history-tamper:c"),
        suffix="history-eviction",
        current_step=eviction_step,
    )
    eviction_request = _child_request(
        first_request.snapshot,
        kind=type(initialized.mutation_kind).ISSUE,
        issuer_ref="issuer:support-v2",
        observed_epoch=23,
        mutation_ref="mutation:history-eviction",
        current_step=eviction_step,
        provenance_root=expiring.issuance_provenance_root,
        trace_roots=tuple(expiring.issuance_trace_roots),
        issued_lease=expiring,
        membership=membership,
    )
    assert eviction_request.evicted_lease_roots == (first.lease_root,)
    forged_delta = support_mutation_delta_root_v2(
        eviction_request.mutation_kind,
        transition_id=eviction_request.transition_id,
        mutation_issuer_ref=eviction_request.mutation_issuer_ref,
        observed_epoch=eviction_request.observed_epoch,
        current_step=eviction_request.snapshot.current_step,
        mutation_provenance_root=(eviction_request.snapshot.mutation_provenance_root),
        mutation_trace_roots=eviction_request.snapshot.mutation_trace_roots,
        issued_lease_root=eviction_request.issued_lease_root,
        revoked_lease_root="",
        revocation_root="",
        evicted_lease_roots=(),
        membership_stream_ref=eviction_request.membership_stream_ref,
        membership_transition_id=eviction_request.membership_transition_id,
        membership_snapshot_root=eviction_request.membership_snapshot_root,
    )
    forged_history, forged_count = support_history_advance_v2(
        parent_history_root=first_request.snapshot.history_root,
        parent_history_count=first_request.snapshot.history_count,
        transition_id=eviction_request.transition_id,
        mutation_delta_root=forged_delta,
    )
    forged_snapshot = replace(
        eviction_request.snapshot,
        mutation_delta_root=forged_delta,
        history_root=forged_history,
        history_count=forged_count,
        snapshot_root="",
    )
    forged_request = replace(
        eviction_request,
        evicted_lease_roots=(),
        snapshot=forged_snapshot,
        request_root="",
    )
    with pytest.raises(ValueError, match="eviction delta"):
        _validate_transition_delta(forged_request, first_request.snapshot)


def test_mutation_transition_identity_prevents_pruned_reference_reuse() -> None:
    manifest = _manifest()
    membership = _membership(manifest)
    initialized, _ = _initialized(manifest)
    claim_root = _root("claim:transition-identity")
    observation = _observation(
        manifest,
        candidate_ref="candidate:a",
        claim_root=claim_root,
        suffix="transition-identity",
    )
    proposal = _proposal(
        manifest,
        observation,
        candidate_ref="candidate:a",
        claim_root=claim_root,
        suffix="transition-identity",
    )

    def projected(mutation_ref: str):
        return project_support_lease_v2(
            parent=initialized.snapshot,
            membership=membership,
            proposal=proposal,
            positive_observations=(observation,),
            manifest=manifest,
            mutation_transition_id=support_transition_id_v2(
                initialized.stream_ref,
                mutation_ref,
            ),
            issuance_issuer_ref="issuer:support-v2",
            current_step=5,
            prior_lease=None,
            issuance_provenance_root=_root(f"provenance:{mutation_ref}"),
            issuance_trace_roots=(_root(f"trace:{mutation_ref}"),),
        )

    first = projected("mutation:identity:first")
    second = projected("mutation:identity:second")
    assert first.proposal_root == second.proposal_root
    assert first.lease_ref != second.lease_ref
    assert first.lease_root != second.lease_root
    first_revocation = project_support_revocation_v2(
        first,
        mutation_transition_id=support_transition_id_v2(
            initialized.stream_ref,
            "mutation:identity:revoke:first",
        ),
        reason_codes=("identity-test",),
        revocation_issuer_ref="issuer:successor",
        current_step=6,
        provenance_root=_root("provenance:identity:revoke:first"),
        source_trace_roots=(_root("trace:identity:revoke:first"),),
    )
    second_revocation = project_support_revocation_v2(
        first,
        mutation_transition_id=support_transition_id_v2(
            initialized.stream_ref,
            "mutation:identity:revoke:second",
        ),
        reason_codes=("identity-test",),
        revocation_issuer_ref="issuer:successor",
        current_step=6,
        provenance_root=_root("provenance:identity:revoke:second"),
        source_trace_roots=(_root("trace:identity:revoke:second"),),
    )
    assert first_revocation.revocation_ref != second_revocation.revocation_ref
    assert first_revocation.revocation_root != second_revocation.revocation_root


def test_all_portable_support_records_reject_unknown_fields() -> None:
    manifest = _manifest()
    membership = _membership(manifest)
    initialized, _ = _initialized(manifest)
    lease, proposal, observation = _lease(
        manifest,
        initialized.snapshot,
        membership,
        candidate_ref="candidate:a",
        claim_root=_root("claim:exact-records"),
        suffix="exact-records",
        current_step=5,
    )
    issued = _child_request(
        initialized.snapshot,
        kind=type(initialized.mutation_kind).ISSUE,
        issuer_ref="issuer:support-v2",
        observed_epoch=21,
        mutation_ref="mutation:exact-records",
        current_step=5,
        provenance_root=lease.issuance_provenance_root,
        trace_roots=tuple(lease.issuance_trace_roots),
        issued_lease=lease,
        membership=membership,
    )
    revocation = project_support_revocation_v2(
        lease,
        mutation_transition_id=support_transition_id_v2(
            issued.stream_ref,
            "mutation:exact-records:revoke",
        ),
        reason_codes=("exact-record-test",),
        revocation_issuer_ref="issuer:successor",
        current_step=6,
        provenance_root=_root("provenance:exact-records:revoke"),
        source_trace_roots=(_root("trace:exact-records:revoke"),),
    )
    revoked = _child_request(
        issued.snapshot,
        kind=type(initialized.mutation_kind).REVOKE,
        issuer_ref="issuer:successor",
        observed_epoch=22,
        mutation_ref="mutation:exact-records:revoke",
        current_step=6,
        provenance_root=_root("provenance:exact-records:revoke"),
        trace_roots=(_root("trace:exact-records:revoke"),),
        revoked_lease=lease,
        revocation=revocation,
    )
    evaluation = SupportEvaluationV2(
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=manifest.manifest_root,
        commit_policy_root=membership.commit_policy_root,
        protocol_ref=manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET,
        candidate_ref="candidate:a",
        claim_root=_root("claim:exact-evaluation"),
        epoch=EPOCH,
        current_step=7,
        membership_snapshot_root=membership.snapshot_root,
        membership_root=membership.membership_root,
        support_snapshot_root=revoked.snapshot.snapshot_root,
        eligible_cluster_count=2,
        active_support_cluster_count=0,
        support_ratio_ppm=0,
        policy_threshold_clusters=1,
        policy_support_met=False,
        active_cluster_refs=(),
        included_lease_roots=(),
        excluded_lease_roots=(),
        equivocations=(),
    )
    equivocation = SupportEquivocationV2(
        target_ref=TARGET,
        claim_root=_root("claim:exact-equivocation"),
        epoch=EPOCH,
        principal_cluster_ref="cluster:alpha",
        support_snapshot_root=issued.snapshot.snapshot_root,
        lease_set_root=issued.snapshot.lease_set_root,
        conflicting_candidate_refs=("candidate:a", "candidate:b"),
        conflicting_lease_roots=(lease.lease_root, _root("lease:conflicting")),
        first_overlap_step=5,
    )
    records = (
        observation,
        proposal,
        lease,
        revocation,
        issued.snapshot,
        issued,
        equivocation,
        evaluation,
    )
    for record in records:
        payload = record.to_dict()
        payload["unknown_field"] = "forbidden"
        with pytest.raises(ValueError, match="fields"):
            type(record).from_dict(payload)
        noncanonical_root = record.to_dict()
        root_field = getattr(type(record), "_root_field", "finding_root")
        noncanonical_root[root_field] = ""
        with pytest.raises(ValueError, match="canonical wire"):
            type(record).from_dict(noncanonical_root)

    tuple_wire = observation.to_dict()
    tuple_wire["source_trace_roots"] = tuple(tuple_wire["source_trace_roots"])
    with pytest.raises(TypeError, match="non-JSON value"):
        SupportObservationV2.from_dict(tuple_wire)
    reordered_wire = observation.to_dict()
    reordered_wire["source_trace_roots"] = list(
        reversed(reordered_wire["source_trace_roots"])
    )
    with pytest.raises(ValueError, match="canonical wire"):
        SupportObservationV2.from_dict(reordered_wire)
    tuple_evictions = issued.to_dict()
    tuple_evictions["evicted_lease_roots"] = ()
    with pytest.raises(TypeError, match="non-JSON value"):
        type(issued).from_dict(tuple_evictions)


def test_support_owner_has_no_v1_process_local_authority_dependency() -> None:
    owner = ROOT / "pheroos/governance/_support_v2"
    text = "\n".join(
        path.read_text()
        for path in sorted((*owner.glob("support*.py"), owner / "evaluation.py"))
    )
    for forbidden in (
        "PrincipalVerification",
        "VerifiedObservation",
        "pheroos.governance.principal",
        "pheroos.governance.observation",
        "pheroos.governance._support.",
        "LEGACY_AUTHORITY_REGISTRY",
        "RLock",
        "_ISSUANCE = object()",
    ):
        assert forbidden not in text


def _authority_domain() -> AuthorityDomainV2:
    return AuthorityDomainV2(
        policy_version=AUTHORITY_POLICY_VERSION_V2,
        profile=AUTHORITY_LOCAL_PROFILE_V2,
        wire_version=AUTHORITY_WIRE_VERSION_V2,
        canonical_version=AUTHORITY_CANONICAL_VERSION_V2,
        ledger_version=AUTHORITY_LEDGER_VERSION_V2,
        state_store_version=GOVERNANCE_STATE_STORE_VERSION_V2,
        trace_batch_version=GOVERNANCE_TRACE_BATCH_VERSION_V2,
        read_set_version=GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        scope_ref="scope:support-operation",
    )


def _operation_request(domain: AuthorityDomainV2, manifest: ScopedProtocolManifestV2):
    return prepare_support_initialize_v2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        manifest=manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        issuer_ref="issuer:support-v2",
        observed_epoch=20,
        mutation_ref="mutation:support:operation:init",
        current_step=2,
        provenance_root=_root("provenance:support:operation:init"),
        source_trace_roots=(_root("trace:support:operation:init"),),
    )


def _support_session(
    manifest: ScopedProtocolManifestV2 | None = None,
):
    manifest = _manifest() if manifest is None else manifest
    domain = _authority_domain()
    store = InMemoryGovernanceStateStoreV2((domain,))
    grant = GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:support-v2",
        grant_ref="grant:support-v2",
        grant_binding_ref=_root("grant-binding:support-v2"),
        operations=(GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,),
        target_refs=(TARGET,),
        action_refs=(),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100,
        revocation_generation=0,
    )
    activated = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:grant:support-v2",
        1,
    )
    assert activated.committed_transition is not None
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        RUN_REF,
        20,
    )
    request, source = _operation_request(domain, manifest)
    session = open_support_authority_session_v2(capability, request)
    return domain, request, source, session


def test_operation_uses_exact_qualify_evidence_session_and_source() -> None:
    _, request, _, session = _support_session()

    assert session.operation is GovernanceIssuerOperationV2.QUALIFY_EVIDENCE
    assert session.target_refs == (TARGET,)
    rejected = advance_support_state_v2(
        request,
        source=None,
        authority_session=session,
    )
    assert rejected.failure is not None
    assert rejected.failure.path == "/source"


def test_operation_maps_another_request_source_to_binding_mismatch() -> None:
    domain, request, _, session = _support_session()
    _, unrelated_source = prepare_support_initialize_v2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        manifest=_manifest(),
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        issuer_ref="issuer:support-v2",
        observed_epoch=request.observed_epoch,
        mutation_ref="mutation:support:operation:unrelated",
        current_step=request.snapshot.current_step,
        provenance_root=_root("provenance:support:operation:unrelated"),
        source_trace_roots=(_root("trace:support:operation:unrelated"),),
    )

    rejected = advance_support_state_v2(
        request,
        source=unrelated_source,
        authority_session=session,
    )

    assert rejected.failure is not None
    assert rejected.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    assert rejected.failure.path == "/source/request_root"


def test_operation_rejects_manifest_authority_selector_domain_mismatch() -> None:
    manifest = _manifest()
    incompatible = replace(
        manifest,
        authority_policy=replace(
            manifest.authority_policy,
            profile=AUTHORITY_AUTHENTICATED_PROFILE_V2,
        ),
    )
    _, request, source, session = _support_session(incompatible)

    rejected = advance_support_state_v2(
        request,
        source=source,
        authority_session=session,
    )

    assert rejected.failure is not None
    assert rejected.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    assert rejected.failure.path == "/source/manifest/authority_policy"


def test_state_records_and_trace_payloads_bind_full_initialize_lineage() -> None:
    domain, request, source, session = _support_session()
    binding = _session_binding(session)
    expected_context, expected_verification = _expected_source_roots_from_request(
        request
    )
    records = _state_records(
        request,
        binding,
        source_context_root=source.context_root,
        source_verification_root=expected_verification,
        membership_precondition=None,
    )
    decoded, decoded_binding, context_root, verification_root, membership = (
        _decode_state_records(records, domain)
    )
    assert decoded == request
    assert decoded_binding == binding
    assert context_root == expected_context == source.context_root
    assert verification_root == expected_verification
    assert membership is None

    events = _support_events(
        request,
        binding,
        source_context_root=expected_context,
        source_verification_root=expected_verification,
        parent_head_root=_root("support:genesis-head"),
        read_set_root=_root("support:read-set"),
    )
    assert tuple(item.event_type for item in events) == ("support_state_advanced",)
    lineage = events[0].lineage
    assert lineage["profile"] == PROFILE
    assert lineage["protocol_ref"] == request.snapshot.protocol_ref
    assert lineage["mutation_issuer_ref"] == request.mutation_issuer_ref
    assert lineage["mutation_provenance_root"] == (
        request.snapshot.mutation_provenance_root
    )
    assert lineage["mutation_trace_roots"] == list(
        request.snapshot.mutation_trace_roots
    )
