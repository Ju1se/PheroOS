"""Compatibility aggregate for split Support v2 state contracts."""

from pheroos.governance._support_v2.support_event_lineage import (
    support_event_lineage_v2,
    support_issued_event_lineage_v2,
    support_revoked_event_lineage_v2,
)
from pheroos.governance._support_v2.support_request_contracts import (
    SUPPORT_ADVANCE_REQUEST_SCHEMA_V2,
    SupportAdvanceRequestV2,
)
from pheroos.governance._support_v2.support_snapshot_contracts import (
    MAX_SUPPORT_SNAPSHOT_BYTES_V2,
    SUPPORT_GENESIS_SNAPSHOT_ROOT_V2,
    SUPPORT_SNAPSHOT_SCHEMA_V2,
    SUPPORT_STATE_SCHEMA_V2,
    SupportSnapshotV2,
    replacement_matches_prior_v2,
    revocation_matches_lease_v2,
)
from pheroos.governance._support_v2.support_stream_contracts import (
    SUPPORT_GENESIS_HISTORY_ROOT_V2,
    SUPPORT_GENESIS_TRANSITION_ID_V2,
    SupportMutationKindV2,
    support_history_advance_v2,
    support_lease_ref_v2,
    support_mutation_delta_root_v2,
    support_revocation_ref_v2,
    support_stream_ref_v2,
    support_switch_lineage_v2,
    support_transition_id_v2,
)


__all__ = [
    "MAX_SUPPORT_SNAPSHOT_BYTES_V2",
    "SUPPORT_ADVANCE_REQUEST_SCHEMA_V2",
    "SUPPORT_GENESIS_HISTORY_ROOT_V2",
    "SUPPORT_GENESIS_SNAPSHOT_ROOT_V2",
    "SUPPORT_GENESIS_TRANSITION_ID_V2",
    "SUPPORT_SNAPSHOT_SCHEMA_V2",
    "SUPPORT_STATE_SCHEMA_V2",
    "SupportAdvanceRequestV2",
    "SupportMutationKindV2",
    "SupportSnapshotV2",
    "replacement_matches_prior_v2",
    "revocation_matches_lease_v2",
    "support_event_lineage_v2",
    "support_history_advance_v2",
    "support_issued_event_lineage_v2",
    "support_lease_ref_v2",
    "support_mutation_delta_root_v2",
    "support_revocation_ref_v2",
    "support_revoked_event_lineage_v2",
    "support_stream_ref_v2",
    "support_switch_lineage_v2",
    "support_transition_id_v2",
]
