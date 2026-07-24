"""Public test-plumbing factory for an independent stdlib Governance store."""

from __future__ import annotations

from collections.abc import Sequence

from pheroos.conformance.authority_store_v2_spec_adapter import (
    IndependentStdlibGovernanceStateStoreV2Adapter,
)
from pheroos.governance.commit_certificate_v2 import (
    VerifiedCommitCertificateStateV2,
)
from pheroos.governance import (
    AuthorityDomainV2,
    GovernanceStateStoreV2,
)


class IndependentRuntimeIntegrationStoreFactoryV1:
    """Create/restart the independent Store v2 implementation used by fixtures.

    This is Conformance test plumbing, not a runtime persistence recommendation.
    """

    __slots__ = ("_adapter",)

    def __init__(self) -> None:
        self._adapter = IndependentStdlibGovernanceStateStoreV2Adapter()

    def create_governance_store_v2(
        self,
        domains: Sequence[AuthorityDomainV2],
    ) -> GovernanceStateStoreV2:
        return self._adapter.create_store_v2(domains)

    def restart_governance_store_v2(
        self,
        store: GovernanceStateStoreV2,
    ) -> GovernanceStateStoreV2:
        return self._adapter.restart_store_v2(store)

    def build_recovered_certificate_states_v1(
        self,
        *,
        label: str,
        scope_ref: str,
        with_successor: bool,
    ) -> tuple[
        VerifiedCommitCertificateStateV2,
        VerifiedCommitCertificateStateV2 | None,
    ]:
        from pheroos.conformance._runtime_integration_certificate import (
            build_recovered_certificate_states_v1,
        )

        return build_recovered_certificate_states_v1(
            self._adapter,
            label=label,
            scope_ref=scope_ref,
            with_successor=with_successor,
        )

    @staticmethod
    def advance_dependency_head_v1(
        store: GovernanceStateStoreV2,
        domain: AuthorityDomainV2,
        *,
        stream_ref: str,
        transition_id: str,
    ) -> None:
        from pheroos.conformance._runtime_integration_dependency import (
            advance_runtime_dependency_head_v1,
        )

        advance_runtime_dependency_head_v1(
            store,
            domain,
            stream_ref=stream_ref,
            transition_id=transition_id,
        )


__all__ = ["IndependentRuntimeIntegrationStoreFactoryV1"]
