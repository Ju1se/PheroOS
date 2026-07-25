"""Targeted StateStore head advancement for Runtime Integration recovery cases."""

from __future__ import annotations

from hashlib import sha256

from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceStateStoreV2,
    GovernanceTraceBatchV2,
    PreparedGovernanceTransitionV2,
)
from pheroos.protocol.authority_v2 import (
    GovernanceAuthorityReadSetV2,
    GovernanceReadPreconditionV2,
)
from pheroos.trace import TraceEvent


def runtime_recovery_witness_stream_ref_v1(request_root: str) -> str:
    """Derive the TCK-controlled source-only post-checkpoint witness stream."""

    if type(request_root) is not str or not request_root.startswith("sha256:"):
        raise ValueError("runtime recovery witness request_root is invalid")
    digest = sha256(request_root.encode("ascii")).hexdigest()
    return f"authority:runtime-integration-restart-witness-v1:{digest}"


def advance_runtime_recovery_witness_v1(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    *,
    request_root: str,
) -> None:
    """Advance the live source only after its recovery image was reopened."""

    advance_runtime_dependency_head_v1(
        store,
        domain,
        stream_ref=runtime_recovery_witness_stream_ref_v1(request_root),
        transition_id=(
            "transition:runtime:post-checkpoint-witness:"
            + sha256(request_root.encode("ascii")).hexdigest()
        ),
    )


def advance_runtime_dependency_head_v1(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    *,
    stream_ref: str,
    transition_id: str,
) -> None:
    """Append one same-state successor without changing another stream head."""

    head = store.load_head_v2(domain.scope_ref, stream_ref)
    read_set = GovernanceAuthorityReadSetV2(
        entries=(
            GovernanceReadPreconditionV2(
                stream_ref=stream_ref,
                expected_revision=head.revision,
                expected_root=head.head_root,
            ),
        )
    )
    transition = PreparedGovernanceTransitionV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        expected_revision=head.revision,
        expected_root=head.head_root,
        read_set_root=read_set.root(),
        state_records=dict(store.load_state_v2(domain.scope_ref, stream_ref)),
    )
    trace = GovernanceTraceBatchV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        events=(
            TraceEvent(
                event_type="ext.pheroos.runtime_integration_v1.dependency_successor",
                protocol_id="pheroos-runtime-integration-v1",
                target=stream_ref,
                reason="advance one controlled recovery stream",
                lineage={
                    "scope_ref": domain.scope_ref,
                    "stream_ref": stream_ref,
                    "transition_id": transition_id,
                    "predecessor_root": head.head_root,
                },
            ),
        ),
    )
    attempt = store.atomic_commit_v2(
        GovernanceCommitBatchV2(
            domain=domain,
            scope_ref=domain.scope_ref,
            stream_ref=stream_ref,
            transition_id=transition_id,
            kind="transition",
            read_set=read_set,
            trace_batch=trace,
            transition=transition,
        )
    )
    if attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise RuntimeError("targeted recovery dependency successor did not commit")


__all__: tuple[str, ...] = ()
