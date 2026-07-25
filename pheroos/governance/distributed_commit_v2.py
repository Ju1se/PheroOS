"""Durable Distributed Commit v2 ABI.

Portable proposals, witnesses, and certificates never confer authority.  Only
opaque handles revalidated against StateStore v2 may advance or finalize.
"""

from pheroos.governance._distributed_v2.certificate_contracts import (
    DISTRIBUTED_COMMIT_CERTIFICATE_SCHEMA_V2,
    DistributedCommitCertificateV2,
)
from pheroos.governance._distributed_v2.conflict_contracts import (
    DISTRIBUTED_WITNESS_CONFLICT_OBSERVATION_SCHEMA_V2,
    DistributedWitnessConflictObservationV2,
)
from pheroos.governance._distributed_v2.dependency_contracts import (
    DISTRIBUTED_DEPENDENCY_SCHEMA_V2,
    DistributedDependencyV2,
    canonical_distributed_dependencies_v2,
    distributed_dependency_set_root_v2,
)
from pheroos.governance._distributed_v2.enums import (
    DistributedCertificateStatusV2,
    DistributedDependencyRoleV2,
    DistributedLaneStatusV2,
    DistributedLaneV2,
    DistributedMutationKindV2,
)
from pheroos.governance._distributed_v2.epoch_contracts import (
    DISTRIBUTED_EPOCH_TRANSITION_CERTIFICATE_SCHEMA_V2,
    DistributedEpochTransitionCertificateV2,
)
from pheroos.governance._distributed_v2.lane_states import (
    DistributedCertificateStateV2,
    DistributedEpochStateV2,
    DistributedEquivocationFindingV2,
    DistributedProposalStateV2,
    DistributedWitnessStateV2,
)
from pheroos.governance._distributed_v2.operations import (
    advance_distributed_commit_v2,
    open_distributed_authority_session_v2,
)
from pheroos.governance._distributed_v2.policy import (
    DistributedPolicyBindingV2,
    distributed_policy_binding_v2,
    validate_distributed_membership_v2,
)
from pheroos.governance._distributed_v2.proposal_contracts import (
    DISTRIBUTED_COMMIT_PROPOSAL_SCHEMA_V2,
    DISTRIBUTED_COMMIT_VALUE_SCHEMA_V2,
    DistributedCommitProposalV2,
    DistributedCommitValueV2,
)
from pheroos.governance._distributed_v2.request import (
    DISTRIBUTED_ADVANCE_REQUEST_SCHEMA_V2,
    DistributedAdvanceRequestV2,
)
from pheroos.governance._distributed_v2.source import (
    VerifiedDistributedAdvanceSourceV2,
    prepare_distributed_certificate_v2,
    prepare_distributed_epoch_v2,
    prepare_distributed_proposal_v2,
    prepare_distributed_witness_conflict_observation_v2,
    prepare_distributed_witness_v2,
)
from pheroos.governance._distributed_v2.state_contracts import (
    DISTRIBUTED_GENESIS_TRANSITION_ID_V2,
    DISTRIBUTED_LANE_SNAPSHOT_SCHEMA_V2,
    DISTRIBUTED_LANE_STATE_SCHEMA_V2,
    DistributedLaneSnapshotV2,
    distributed_genesis_history_root_v2,
    distributed_genesis_snapshot_root_v2,
    distributed_lane_stream_ref_v2,
    distributed_lane_transition_id_v2,
)
from pheroos.governance._distributed_v2.state_handle import (
    VerifiedDistributedCertificateStateV2,
    VerifiedDistributedEpochStateV2,
    VerifiedDistributedProposalStateV2,
    VerifiedDistributedStateV2,
    VerifiedDistributedWitnessStateV2,
    distributed_state_is_current_v2,
    rehydrate_distributed_state_v2,
    require_current_distributed_state_v2,
    verified_distributed_commit_finality_input_v2 as _owner_finality_input_v2,
)
from pheroos.governance._distributed_v2.witness_contracts import (
    DISTRIBUTED_QUORUM_WITNESS_SCHEMA_V2,
    DistributedQuorumWitnessV2,
    DistributedWitnessAttestationVerifierV2,
    verify_distributed_witness_v2,
)
from pheroos.governance.commit_finality_v2 import (
    VerifiedCommitFinalityInputV2 as _VerifiedCommitFinalityInputV2,
)


def verified_distributed_commit_finality_input_v2(
    certificate_state: object,
    *,
    proposal_state: object,
    witness_state: object,
    epoch_state: object,
    sealed_decision_state: object,
    central_certificate_state: object,
    membership_state: object,
    manifest: object,
    current_step: int,
) -> _VerifiedCommitFinalityInputV2:
    """Return an opaque finality handle after all current Store checks."""

    return _owner_finality_input_v2(
        certificate_state,
        proposal_state=proposal_state,
        witness_state=witness_state,
        epoch_state=epoch_state,
        sealed_decision_state=sealed_decision_state,
        central_certificate_state=central_certificate_state,
        membership_state=membership_state,
        manifest=manifest,
        current_step=current_step,
    )


_PUBLIC_MODULE = __name__
_PUBLIC_OBJECTS = (
    DistributedAdvanceRequestV2,
    DistributedCertificateStateV2,
    DistributedCertificateStatusV2,
    DistributedCommitCertificateV2,
    DistributedCommitProposalV2,
    DistributedCommitValueV2,
    DistributedDependencyRoleV2,
    DistributedDependencyV2,
    DistributedEpochStateV2,
    DistributedEpochTransitionCertificateV2,
    DistributedEquivocationFindingV2,
    DistributedLaneSnapshotV2,
    DistributedLaneStatusV2,
    DistributedLaneV2,
    DistributedMutationKindV2,
    DistributedPolicyBindingV2,
    DistributedProposalStateV2,
    DistributedQuorumWitnessV2,
    DistributedWitnessAttestationVerifierV2,
    DistributedWitnessConflictObservationV2,
    DistributedWitnessStateV2,
    VerifiedDistributedAdvanceSourceV2,
    VerifiedDistributedCertificateStateV2,
    VerifiedDistributedEpochStateV2,
    VerifiedDistributedProposalStateV2,
    VerifiedDistributedStateV2,
    VerifiedDistributedWitnessStateV2,
    advance_distributed_commit_v2,
    canonical_distributed_dependencies_v2,
    distributed_dependency_set_root_v2,
    distributed_genesis_history_root_v2,
    distributed_genesis_snapshot_root_v2,
    distributed_lane_stream_ref_v2,
    distributed_lane_transition_id_v2,
    distributed_policy_binding_v2,
    distributed_state_is_current_v2,
    open_distributed_authority_session_v2,
    prepare_distributed_certificate_v2,
    prepare_distributed_epoch_v2,
    prepare_distributed_proposal_v2,
    prepare_distributed_witness_conflict_observation_v2,
    prepare_distributed_witness_v2,
    rehydrate_distributed_state_v2,
    require_current_distributed_state_v2,
    validate_distributed_membership_v2,
    verified_distributed_commit_finality_input_v2,
    verify_distributed_witness_v2,
)
for _item in _PUBLIC_OBJECTS:
    _item.__module__ = _PUBLIC_MODULE
del _item


__all__ = [
    "DISTRIBUTED_ADVANCE_REQUEST_SCHEMA_V2",
    "DISTRIBUTED_COMMIT_CERTIFICATE_SCHEMA_V2",
    "DISTRIBUTED_COMMIT_PROPOSAL_SCHEMA_V2",
    "DISTRIBUTED_COMMIT_VALUE_SCHEMA_V2",
    "DISTRIBUTED_DEPENDENCY_SCHEMA_V2",
    "DISTRIBUTED_EPOCH_TRANSITION_CERTIFICATE_SCHEMA_V2",
    "DISTRIBUTED_GENESIS_TRANSITION_ID_V2",
    "DISTRIBUTED_LANE_SNAPSHOT_SCHEMA_V2",
    "DISTRIBUTED_LANE_STATE_SCHEMA_V2",
    "DISTRIBUTED_QUORUM_WITNESS_SCHEMA_V2",
    "DISTRIBUTED_WITNESS_CONFLICT_OBSERVATION_SCHEMA_V2",
    "DistributedAdvanceRequestV2",
    "DistributedCertificateStateV2",
    "DistributedCertificateStatusV2",
    "DistributedCommitCertificateV2",
    "DistributedCommitProposalV2",
    "DistributedCommitValueV2",
    "DistributedDependencyRoleV2",
    "DistributedDependencyV2",
    "DistributedEpochStateV2",
    "DistributedEpochTransitionCertificateV2",
    "DistributedEquivocationFindingV2",
    "DistributedLaneSnapshotV2",
    "DistributedLaneStatusV2",
    "DistributedLaneV2",
    "DistributedMutationKindV2",
    "DistributedPolicyBindingV2",
    "DistributedProposalStateV2",
    "DistributedQuorumWitnessV2",
    "DistributedWitnessAttestationVerifierV2",
    "DistributedWitnessConflictObservationV2",
    "DistributedWitnessStateV2",
    "VerifiedDistributedAdvanceSourceV2",
    "VerifiedDistributedCertificateStateV2",
    "VerifiedDistributedEpochStateV2",
    "VerifiedDistributedProposalStateV2",
    "VerifiedDistributedStateV2",
    "VerifiedDistributedWitnessStateV2",
    "advance_distributed_commit_v2",
    "canonical_distributed_dependencies_v2",
    "distributed_dependency_set_root_v2",
    "distributed_genesis_history_root_v2",
    "distributed_genesis_snapshot_root_v2",
    "distributed_lane_stream_ref_v2",
    "distributed_lane_transition_id_v2",
    "distributed_policy_binding_v2",
    "distributed_state_is_current_v2",
    "open_distributed_authority_session_v2",
    "prepare_distributed_certificate_v2",
    "prepare_distributed_epoch_v2",
    "prepare_distributed_proposal_v2",
    "prepare_distributed_witness_conflict_observation_v2",
    "prepare_distributed_witness_v2",
    "rehydrate_distributed_state_v2",
    "require_current_distributed_state_v2",
    "validate_distributed_membership_v2",
    "verified_distributed_commit_finality_input_v2",
    "verify_distributed_witness_v2",
]
