from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pytest

from tests.governance import test_commit_gate_v2_operations as gate_fixture

from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceIssuerGrantV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.commit_gate_v2 import (
    issue_commit_permission_v2,
    open_commit_permission_authority_session_v2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


class _LifecycleBoundaryStore:
    """Delegate all public Store behavior except one hostile lifecycle read."""

    def __init__(self, delegate: GovernanceStateStoreV2) -> None:
        self.delegate = delegate
        self.fault: str | None = None
        self.foreign_head: GovernanceHeadV2 | None = None

    @property
    def state_store_version(self) -> str:
        return self.delegate.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        value = self.delegate.load_head_v2(scope_ref, stream_ref)
        if stream_ref != GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2:
            return value
        if self.fault == "nonexact":
            return cast(GovernanceHeadV2, object())
        if self.fault == "missing":
            raise KeyError(scope_ref)
        if self.fault == "cross_domain":
            assert self.foreign_head is not None
            return self.foreign_head
        return value

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]:
        return self.delegate.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        return self.delegate.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    def atomic_commit_v2(
        self,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2:
        return self.delegate.atomic_commit_v2(batch)


def test_public_commit_permission_session_enforces_declared_action_bound() -> None:
    environment = gate_fixture._environment(
        "scope:authority-session:cross-facade-action"
    )
    request, _source = gate_fixture._prepare_permission(
        environment,
        label="cross-facade-action",
    )
    payload = environment.grant.to_dict()
    payload["grant_ref"] = "grant:cross-facade:no-actions"
    payload["action_refs"] = []
    payload["grant_root"] = ""
    limited = GovernanceIssuerGrantV2.from_dict(payload)
    activated = activate_governance_issuer_grant_v2(
        environment.store,
        environment.domain,
        limited,
        "transition:cross-facade:no-actions",
        1,
    )
    assert activated.disposition is GovernanceCommitDispositionV2.COMMITTED
    capability = bind_governance_issuer_capability_v2(
        environment.store,
        environment.domain,
        limited,
        gate_fixture.RUN_REF,
        request.observed_epoch,
    )

    with pytest.raises(GovernanceAuthorityBindingErrorV2) as denied:
        open_commit_permission_authority_session_v2(capability, request)
    assert (denied.value.code, denied.value.path) == (
        AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
        "/action_refs",
    )


def test_public_commit_permission_detects_hostile_lifecycle_reader_results() -> None:
    environment = gate_fixture._environment(
        "scope:authority-session:cross-facade-lifecycle"
    )
    request, source = gate_fixture._prepare_permission(
        environment,
        label="cross-facade-lifecycle",
    )
    store = _LifecycleBoundaryStore(environment.store)
    assert isinstance(store, GovernanceStateStoreV2)
    capability = bind_governance_issuer_capability_v2(
        store,
        environment.domain,
        environment.grant,
        gate_fixture.RUN_REF,
        request.observed_epoch,
    )
    foreign = ReferenceGovernanceStateStoreConformanceAdapterV2().create_domain_v2(
        "scope:authority-session:foreign-lifecycle"
    )
    store.foreign_head = GovernanceHeadV2.genesis(
        foreign,
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    )
    cases = (
        (
            "nonexact",
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
        ),
        ("missing", AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH),
        ("cross_domain", AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH),
    )
    for fault, code in cases:
        store.fault = None
        session = open_commit_permission_authority_session_v2(capability, request)
        store.fault = fault
        denied = issue_commit_permission_v2(
            request,
            source=source,
            authority_session=session,
        )
        assert denied.failure is not None
        assert denied.failure.code is code
        assert denied.committed_transition is None
