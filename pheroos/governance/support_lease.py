"""Canonical Support Lease ABI facade backed by static lifecycle modules."""

from __future__ import annotations

from pheroos.governance._support.records import (
    EligibleMembershipEpochState as _EligibleMembershipEpochState,
)
from pheroos.governance._support.records import EligiblePrincipal as _EligiblePrincipal
from pheroos.governance._support.records import (
    EligiblePrincipalCluster as _EligiblePrincipalCluster,
)
from pheroos.governance._support.records import (
    EligiblePrincipalSnapshot as _EligiblePrincipalSnapshot,
)
from pheroos.governance._support.records import (
    SupportEquivocationFinding as _SupportEquivocationFinding,
)
from pheroos.governance._support.records import SupportLease as _SupportLease
from pheroos.governance._support.records import (
    SupportLeaseEvaluation as _SupportLeaseEvaluation,
)
from pheroos.governance._support.records import (
    SupportLeaseExpiration as _SupportLeaseExpiration,
)
from pheroos.governance._support.records import (
    SupportLeaseProposal as _SupportLeaseProposal,
)
from pheroos.governance._support.records import (
    SupportLeaseReplayReceipt as _SupportLeaseReplayReceipt,
)
from pheroos.governance._support.records import (
    SupportLeaseReplayState as _SupportLeaseReplayState,
)
from pheroos.governance._support.records import (
    SupportLeaseRevocation as _SupportLeaseRevocation,
)
from pheroos.governance._support.records import (
    SupportLeaseStatus as _SupportLeaseStatus,
)
from pheroos.governance._support.records import (
    SupportLeaseSwitch as _SupportLeaseSwitch,
)
from pheroos.governance._support.records import (
    eligible_membership_epoch_state_fingerprint as _eligible_membership_epoch_state_fingerprint,
)
from pheroos.governance._support.membership import (
    eligible_membership_epoch_state_is_authoritative as _eligible_membership_epoch_state_is_authoritative,
)
from pheroos.governance._support.membership import (
    eligible_membership_epoch_state_is_current as _eligible_membership_epoch_state_is_current,
)
from pheroos.governance._support.records import (
    eligible_membership_epoch_state_payload as _eligible_membership_epoch_state_payload,
)
from pheroos.governance._support.records import (
    eligible_principal_snapshot_fingerprint as _eligible_principal_snapshot_fingerprint,
)
from pheroos.governance._support.membership import (
    eligible_principal_snapshot_is_authoritative as _eligible_principal_snapshot_is_authoritative,
)
from pheroos.governance._support.membership import (
    eligible_principal_snapshot_matches as _eligible_principal_snapshot_matches,
)
from pheroos.governance._support.records import (
    eligible_principal_snapshot_payload as _eligible_principal_snapshot_payload,
)
from pheroos.governance._support.evaluation import (
    evaluate_support_leases as _evaluate_support_leases,
)
from pheroos.governance._support.lease import (
    expire_support_lease as _expire_support_lease,
)
from pheroos.governance._support.membership import (
    issue_eligible_principal_snapshot as _issue_eligible_principal_snapshot,
)
from pheroos.governance._support.lease import (
    issue_support_lease as _issue_support_lease,
)
from pheroos.governance._support.replay import (
    initialize_support_lease_replay_state as _initialize_support_lease_replay_state,
)
from pheroos.governance._support.lease import (
    revoke_support_lease as _revoke_support_lease,
)
from pheroos.governance._support.records import (
    support_lease_fingerprint as _support_lease_fingerprint,
)
from pheroos.governance._support.lease import (
    support_lease_is_authoritative as _support_lease_is_authoritative,
)
from pheroos.governance._support.records import (
    support_lease_payload as _support_lease_payload,
)
from pheroos.governance._support.records import (
    support_lease_proposal_fingerprint as _support_lease_proposal_fingerprint,
)
from pheroos.governance._support.records import (
    support_lease_proposal_payload as _support_lease_proposal_payload,
)
from pheroos.governance._support.records import (
    support_lease_replay_receipt_payload as _support_lease_replay_receipt_payload,
)
from pheroos.governance._support.records import (
    support_lease_replay_state_fingerprint as _support_lease_replay_state_fingerprint,
)
from pheroos.governance._support.replay import (
    support_lease_replay_state_is_authoritative as _support_lease_replay_state_is_authoritative,
)
from pheroos.governance._support.replay import (
    support_lease_replay_state_is_current as _support_lease_replay_state_is_current,
)
from pheroos.governance._support.records import (
    support_lease_replay_state_payload as _support_lease_replay_state_payload,
)
from pheroos.governance._support.records import (
    support_lease_revocation_fingerprint as _support_lease_revocation_fingerprint,
)
from pheroos.governance._support.lease import (
    support_lease_revocation_is_authoritative as _support_lease_revocation_is_authoritative,
)
from pheroos.governance._support.lease import (
    support_lease_revocation_matches as _support_lease_revocation_matches,
)
from pheroos.governance._support.records import (
    support_lease_revocation_payload as _support_lease_revocation_payload,
)
from pheroos.governance._support.lease import (
    support_lease_status as _support_lease_status,
)
from pheroos.governance._support.lease import (
    switch_support_lease as _switch_support_lease,
)

EligibleMembershipEpochState = _EligibleMembershipEpochState
EligiblePrincipal = _EligiblePrincipal
EligiblePrincipalCluster = _EligiblePrincipalCluster
EligiblePrincipalSnapshot = _EligiblePrincipalSnapshot
SupportEquivocationFinding = _SupportEquivocationFinding
SupportLease = _SupportLease
SupportLeaseEvaluation = _SupportLeaseEvaluation
SupportLeaseExpiration = _SupportLeaseExpiration
SupportLeaseProposal = _SupportLeaseProposal
SupportLeaseReplayReceipt = _SupportLeaseReplayReceipt
SupportLeaseReplayState = _SupportLeaseReplayState
SupportLeaseRevocation = _SupportLeaseRevocation
SupportLeaseStatus = _SupportLeaseStatus
SupportLeaseSwitch = _SupportLeaseSwitch
eligible_membership_epoch_state_fingerprint = (
    _eligible_membership_epoch_state_fingerprint
)
eligible_membership_epoch_state_is_authoritative = (
    _eligible_membership_epoch_state_is_authoritative
)
eligible_membership_epoch_state_is_current = _eligible_membership_epoch_state_is_current
eligible_membership_epoch_state_payload = _eligible_membership_epoch_state_payload
eligible_principal_snapshot_fingerprint = _eligible_principal_snapshot_fingerprint
eligible_principal_snapshot_is_authoritative = (
    _eligible_principal_snapshot_is_authoritative
)
eligible_principal_snapshot_matches = _eligible_principal_snapshot_matches
eligible_principal_snapshot_payload = _eligible_principal_snapshot_payload
evaluate_support_leases = _evaluate_support_leases
expire_support_lease = _expire_support_lease
issue_eligible_principal_snapshot = _issue_eligible_principal_snapshot
issue_support_lease = _issue_support_lease
initialize_support_lease_replay_state = _initialize_support_lease_replay_state
revoke_support_lease = _revoke_support_lease
support_lease_fingerprint = _support_lease_fingerprint
support_lease_is_authoritative = _support_lease_is_authoritative
support_lease_payload = _support_lease_payload
support_lease_proposal_fingerprint = _support_lease_proposal_fingerprint
support_lease_proposal_payload = _support_lease_proposal_payload
support_lease_replay_receipt_payload = _support_lease_replay_receipt_payload
support_lease_replay_state_fingerprint = _support_lease_replay_state_fingerprint
support_lease_replay_state_is_authoritative = (
    _support_lease_replay_state_is_authoritative
)
support_lease_replay_state_is_current = _support_lease_replay_state_is_current
support_lease_replay_state_payload = _support_lease_replay_state_payload
support_lease_revocation_fingerprint = _support_lease_revocation_fingerprint
support_lease_revocation_is_authoritative = _support_lease_revocation_is_authoritative
support_lease_revocation_matches = _support_lease_revocation_matches
support_lease_revocation_payload = _support_lease_revocation_payload
support_lease_status = _support_lease_status
switch_support_lease = _switch_support_lease

__all__ = [
    "EligibleMembershipEpochState",
    "EligiblePrincipal",
    "EligiblePrincipalCluster",
    "EligiblePrincipalSnapshot",
    "SupportEquivocationFinding",
    "SupportLease",
    "SupportLeaseEvaluation",
    "SupportLeaseExpiration",
    "SupportLeaseProposal",
    "SupportLeaseReplayReceipt",
    "SupportLeaseReplayState",
    "SupportLeaseRevocation",
    "SupportLeaseStatus",
    "SupportLeaseSwitch",
    "eligible_membership_epoch_state_fingerprint",
    "eligible_membership_epoch_state_is_authoritative",
    "eligible_membership_epoch_state_is_current",
    "eligible_membership_epoch_state_payload",
    "eligible_principal_snapshot_fingerprint",
    "eligible_principal_snapshot_is_authoritative",
    "eligible_principal_snapshot_matches",
    "eligible_principal_snapshot_payload",
    "evaluate_support_leases",
    "expire_support_lease",
    "issue_eligible_principal_snapshot",
    "issue_support_lease",
    "initialize_support_lease_replay_state",
    "revoke_support_lease",
    "support_lease_fingerprint",
    "support_lease_is_authoritative",
    "support_lease_payload",
    "support_lease_proposal_fingerprint",
    "support_lease_proposal_payload",
    "support_lease_replay_receipt_payload",
    "support_lease_replay_state_fingerprint",
    "support_lease_replay_state_is_authoritative",
    "support_lease_replay_state_is_current",
    "support_lease_replay_state_payload",
    "support_lease_revocation_fingerprint",
    "support_lease_revocation_is_authoritative",
    "support_lease_revocation_matches",
    "support_lease_revocation_payload",
    "support_lease_status",
    "switch_support_lease",
]
