"""Race-only helpers for Commit Certificate v2 Store tests."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from tests.governance._commit_certificate_v2_store_support import (
    ASSURANCE,
    PROFILE,
    RUN_REF,
    TARGET,
    _capability,
    _root,
)

from pheroos.governance.authority_store_v2 import (
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.support_v2 import (
    PrincipalVerificationRecordV2,
    VerifiedPrincipalVerificationSetStateV2,
    advance_principal_verification_set_v2,
    open_principal_verification_authority_session_v2,
    prepare_principal_verification_set_v2,
)
from pheroos.protocol.commit_models import CommitAssurance


class DependencyRaceStoreV2:
    def __init__(self, store: GovernanceStateStoreV2) -> None:
        self.store = store
        self.armed_stream_ref = ""
        self.before_atomic: Callable[[], None] | None = None

    @property
    def state_store_version(self) -> str:
        return self.store.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        return self.store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(self, scope_ref: str, stream_ref: str) -> Mapping[str, object]:
        return self.store.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        return self.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    def atomic_commit_v2(
        self, batch: GovernanceCommitBatchV2
    ) -> GovernanceCommitAttemptV2:
        callback = self.before_atomic
        if batch.stream_ref == self.armed_stream_ref and callback is not None:
            self.before_atomic = None
            callback()
        return self.store.atomic_commit_v2(batch)


def advance_principal_verification_only_v2(
    context,
    parent_state: VerifiedPrincipalVerificationSetStateV2,
    *,
    profile: str = PROFILE,
    assurance: CommitAssurance = ASSURANCE,
) -> GovernanceCommitAttemptV2:
    if type(profile) is not str or not profile:
        raise TypeError("race verification profile must be non-empty text")
    if type(assurance) is not CommitAssurance:
        raise TypeError("race verification assurance must be exact CommitAssurance")
    record = PrincipalVerificationRecordV2(
        principal_ref="principal:alpha",
        cluster_ref="cluster:alpha",
        failure_domain_ref="failure-domain:alpha",
        verification_method="external-attestation-v2",
        verification_issuer_ref="identity:verifier",
        attestation_root=_root("certificate:verification:race:attestation"),
        evidence_roots=(_root("certificate:verification:race:evidence"),),
        issued_at_step=5,
        expires_at_step=90_000,
        provenance_ref="urn:test:certificate:verification:race",
        source_trace_roots=(_root("certificate:verification:race:trace"),),
    )
    request, source = prepare_principal_verification_set_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=profile,
        assurance=assurance,
        run_ref=RUN_REF,
        target_ref=TARGET,
        epoch=2,
        observed_epoch=12,
        advance_ref="advance:certificate:verification:race",
        snapshot_ref="snapshot:certificate:verification:race",
        current_step=5,
        expires_at_step=90_000,
        mutation_issuer_ref=context.grant.issuer_ref,
        records=(record,),
        parent_snapshot=parent_state.snapshot,
    )
    attempt = advance_principal_verification_set_v2(
        request,
        source=source,
        authority_session=open_principal_verification_authority_session_v2(
            _capability(context, request.observed_epoch), request
        ),
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    return attempt


__all__: tuple[str, ...] = ()
