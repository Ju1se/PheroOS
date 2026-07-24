"""Public, provider-neutral Governance StateStore v2 contracts.

The ABI remains deliberately flat at this import boundary.  Its implementation
is split into private, one-way dependency layers so callers retain the original
names, signatures, wire values, roots, pickling paths, and runtime identities.
"""

from __future__ import annotations

from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2 as AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2 as GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    MAX_AUTHORITY_REVISION_V2 as MAX_AUTHORITY_REVISION_V2,
    AuthorityDiagnosticCodeV2,
    GovernanceAuthorityReadSetV2,
)
from pheroos.trace import TraceEvent as TraceEvent

from pheroos.governance._authority_store_v2_contracts.batch import (
    GovernanceCommitBatchV2,
    GovernanceDomainSealV2,
    GovernanceTraceBatchV2,
)
from pheroos.governance._authority_store_v2_contracts.domain import (
    GOVERNANCE_GENESIS_PARENT_ROOT_V2,
    AuthorityDomainV2,
    GovernanceHeadV2,
    PreparedGovernanceTransitionV2,
    governance_authority_state_root_v2,
)
from pheroos.governance._authority_store_v2_contracts.foundation import (
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
    AUTHORITY_DOMAIN_SCHEMA_V2,
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_COMMITTED_TRANSITION_SCHEMA_V2,
    GOVERNANCE_COMMIT_ATTEMPT_SCHEMA_V2,
    GOVERNANCE_COMMIT_BATCH_SCHEMA_V2,
    GOVERNANCE_COMMIT_INCLUSION_PROOF_SCHEMA_V2,
    GOVERNANCE_COMMIT_POSITION_OBSERVATION_SCHEMA_V2,
    GOVERNANCE_COMMIT_RECEIPT_SCHEMA_V2,
    GOVERNANCE_COMMIT_VIEW_SCHEMA_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GOVERNANCE_DOMAIN_SEAL_SCHEMA_V2,
    GOVERNANCE_FAILURE_SCHEMA_V2,
    GOVERNANCE_HEAD_SCHEMA_V2,
    GOVERNANCE_STATE_SCHEMA_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    MAX_GOVERNANCE_NON_LIFECYCLE_STREAMS_V2,
    MAX_GOVERNANCE_TRACE_EVENTS_V2,
    PREPARED_GOVERNANCE_TRANSITION_SCHEMA_V2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceFailureStageV2,
)
from pheroos.governance._authority_store_v2_contracts.receipt import (
    GovernanceCommitInclusionProofV2,
    GovernanceCommitPositionObservationV2,
    GovernanceCommitReceiptV2,
    GovernanceCommittedTransitionV2,
)
from pheroos.governance._authority_store_v2_contracts.results import (
    GovernanceCommitAttemptV2,
    GovernanceCommitViewV2,
    GovernanceFailureV2,
    GovernanceStateReaderV2,
    GovernanceStateStoreV2,
    GovernanceStateWriterV2,
    _governance_disposition_for_diagnostic_v2 as _governance_disposition_for_diagnostic_v2,
)


_PUBLIC_MODULE = __name__
_NATIVE_PUBLIC_OBJECTS = (
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceFailureStageV2,
    AuthorityDomainV2,
    GovernanceHeadV2,
    PreparedGovernanceTransitionV2,
    GovernanceTraceBatchV2,
    GovernanceDomainSealV2,
    GovernanceCommitBatchV2,
    GovernanceCommitReceiptV2,
    GovernanceCommitInclusionProofV2,
    GovernanceCommittedTransitionV2,
    GovernanceCommitPositionObservationV2,
    GovernanceFailureV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitViewV2,
    GovernanceStateReaderV2,
    GovernanceStateWriterV2,
    GovernanceStateStoreV2,
    governance_authority_state_root_v2,
    _governance_disposition_for_diagnostic_v2,
)
for _public_object in _NATIVE_PUBLIC_OBJECTS:
    _public_object.__module__ = _PUBLIC_MODULE
del _public_object


__all__ = [
    "AUTHORITY_AUTHENTICATED_PROFILE_V2",
    "AUTHORITY_DOMAIN_SCHEMA_V2",
    "AUTHORITY_LEDGER_VERSION_V2",
    "AUTHORITY_LOCAL_PROFILE_V2",
    "AUTHORITY_POLICY_VERSION_V2",
    "AUTHORITY_WIRE_VERSION_V2",
    "GOVERNANCE_COMMITTED_TRANSITION_SCHEMA_V2",
    "GOVERNANCE_COMMIT_ATTEMPT_SCHEMA_V2",
    "GOVERNANCE_COMMIT_BATCH_SCHEMA_V2",
    "GOVERNANCE_COMMIT_INCLUSION_PROOF_SCHEMA_V2",
    "GOVERNANCE_COMMIT_POSITION_OBSERVATION_SCHEMA_V2",
    "GOVERNANCE_COMMIT_RECEIPT_SCHEMA_V2",
    "GOVERNANCE_COMMIT_VIEW_SCHEMA_V2",
    "GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2",
    "GOVERNANCE_DOMAIN_SEAL_SCHEMA_V2",
    "GOVERNANCE_FAILURE_SCHEMA_V2",
    "GOVERNANCE_GENESIS_PARENT_ROOT_V2",
    "GOVERNANCE_HEAD_SCHEMA_V2",
    "GOVERNANCE_STATE_SCHEMA_V2",
    "GOVERNANCE_STATE_STORE_VERSION_V2",
    "GOVERNANCE_TRACE_BATCH_VERSION_V2",
    "MAX_GOVERNANCE_NON_LIFECYCLE_STREAMS_V2",
    "MAX_GOVERNANCE_TRACE_EVENTS_V2",
    "PREPARED_GOVERNANCE_TRANSITION_SCHEMA_V2",
    "AuthorityDiagnosticCodeV2",
    "AuthorityDomainV2",
    "GovernanceAuthorityReadSetV2",
    "GovernanceCommitAttemptV2",
    "GovernanceCommitBatchV2",
    "GovernanceCommitDispositionV2",
    "GovernanceCommitInclusionProofV2",
    "GovernanceCommitPositionObservationV2",
    "GovernanceCommitPositionV2",
    "GovernanceCommitReceiptV2",
    "GovernanceCommitViewV2",
    "GovernanceCommittedTransitionV2",
    "GovernanceDomainSealV2",
    "GovernanceFailureStageV2",
    "GovernanceFailureV2",
    "GovernanceHeadV2",
    "GovernanceStateReaderV2",
    "GovernanceStateStoreV2",
    "GovernanceStateWriterV2",
    "GovernanceTraceBatchV2",
    "PreparedGovernanceTransitionV2",
    "governance_authority_state_root_v2",
]
