"""Draft public Commit Certificate v2 ABI.

Portable certificate bytes are independently verifiable data.  Issuance and
finality authority comes only from the opaque, StateStore-reverified handles
returned by this facade.
"""

from pheroos.governance._commit_certificate_v2 import (
    COMMIT_CERTIFICATE_AUTHORITY_LEAF_SCHEMA_V2,
    COMMIT_CERTIFICATE_BODY_SCHEMA_V2,
    COMMIT_CERTIFICATE_ENVELOPE_SCHEMA_V2,
    COMMIT_CERTIFICATE_GENESIS_HISTORY_ROOT_V2,
    COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2,
    COMMIT_CERTIFICATE_GENESIS_TRANSITION_ID_V2,
    COMMIT_CERTIFICATE_IDENTITY_BINDING_SCHEMA_V2,
    COMMIT_CERTIFICATE_REQUEST_SCHEMA_V2,
    COMMIT_CERTIFICATE_SNAPSHOT_SCHEMA_V2,
    COMMIT_CERTIFICATE_STATE_SCHEMA_V2,
    CommitCertificateAuthorityLeafV2,
    CommitCertificateAuthorityRoleV2,
    CommitCertificateBodyV2,
    CommitCertificateIdentityBindingV2,
    CommitCertificateIssuerAttestationVerifierV2,
    CommitCertificateMutationKindV2,
    CommitCertificateRequestV2,
    CommitCertificateSnapshotV2,
    CommitCertificateStatusV2,
    PortableCommitCertificateV2,
    VerifiedCommitCertificateSourceV2,
    VerifiedCommitCertificateStateV2,
    advance_commit_certificate_v2,
    canonical_commit_certificate_authority_leaves_v2,
    commit_certificate_authority_leaf_set_root_v2,
    commit_certificate_state_is_current_v2,
    commit_certificate_stream_ref_v2,
    commit_certificate_transition_id_v2,
    open_commit_certificate_authority_session_v2,
    prepare_commit_certificate_v2,
    rehydrate_commit_certificate_state_v2,
    require_current_commit_certificate_state_v2,
    verify_portable_commit_certificate_v2,
)
from pheroos.governance._commit_certificate_v2.finality_input import (
    _verified_commit_certificate_finality_input_v2 as _owner_finality_input_v2,
)
from pheroos.governance.commit_finality_v2 import (
    VerifiedCommitFinalityInputV2 as _VerifiedCommitFinalityInputV2,
)


def verified_commit_certificate_finality_input_v2(
    certificate_state: object,
    *,
    sealed_decision_state: object,
    current_step: int,
) -> _VerifiedCommitFinalityInputV2:
    """Return an opaque finality handle after current Store revalidation."""

    return _owner_finality_input_v2(
        certificate_state,
        sealed_decision_state=sealed_decision_state,
        current_step=current_step,
    )


_PUBLIC_MODULE = __name__
_PUBLIC_OBJECTS = (
    CommitCertificateAuthorityLeafV2,
    CommitCertificateAuthorityRoleV2,
    CommitCertificateBodyV2,
    CommitCertificateIdentityBindingV2,
    CommitCertificateIssuerAttestationVerifierV2,
    CommitCertificateMutationKindV2,
    CommitCertificateRequestV2,
    CommitCertificateSnapshotV2,
    CommitCertificateStatusV2,
    PortableCommitCertificateV2,
    VerifiedCommitCertificateSourceV2,
    VerifiedCommitCertificateStateV2,
    advance_commit_certificate_v2,
    canonical_commit_certificate_authority_leaves_v2,
    commit_certificate_authority_leaf_set_root_v2,
    commit_certificate_state_is_current_v2,
    commit_certificate_stream_ref_v2,
    commit_certificate_transition_id_v2,
    open_commit_certificate_authority_session_v2,
    prepare_commit_certificate_v2,
    rehydrate_commit_certificate_state_v2,
    require_current_commit_certificate_state_v2,
    verified_commit_certificate_finality_input_v2,
    verify_portable_commit_certificate_v2,
)
for _item in _PUBLIC_OBJECTS:
    _item.__module__ = _PUBLIC_MODULE
del _item


__all__ = [
    "COMMIT_CERTIFICATE_AUTHORITY_LEAF_SCHEMA_V2",
    "COMMIT_CERTIFICATE_BODY_SCHEMA_V2",
    "COMMIT_CERTIFICATE_ENVELOPE_SCHEMA_V2",
    "COMMIT_CERTIFICATE_GENESIS_HISTORY_ROOT_V2",
    "COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2",
    "COMMIT_CERTIFICATE_GENESIS_TRANSITION_ID_V2",
    "COMMIT_CERTIFICATE_IDENTITY_BINDING_SCHEMA_V2",
    "COMMIT_CERTIFICATE_REQUEST_SCHEMA_V2",
    "COMMIT_CERTIFICATE_SNAPSHOT_SCHEMA_V2",
    "COMMIT_CERTIFICATE_STATE_SCHEMA_V2",
    "CommitCertificateAuthorityLeafV2",
    "CommitCertificateAuthorityRoleV2",
    "CommitCertificateBodyV2",
    "CommitCertificateIdentityBindingV2",
    "CommitCertificateIssuerAttestationVerifierV2",
    "CommitCertificateMutationKindV2",
    "CommitCertificateRequestV2",
    "CommitCertificateSnapshotV2",
    "CommitCertificateStatusV2",
    "PortableCommitCertificateV2",
    "VerifiedCommitCertificateSourceV2",
    "VerifiedCommitCertificateStateV2",
    "advance_commit_certificate_v2",
    "canonical_commit_certificate_authority_leaves_v2",
    "commit_certificate_authority_leaf_set_root_v2",
    "commit_certificate_state_is_current_v2",
    "commit_certificate_stream_ref_v2",
    "commit_certificate_transition_id_v2",
    "open_commit_certificate_authority_session_v2",
    "prepare_commit_certificate_v2",
    "rehydrate_commit_certificate_state_v2",
    "require_current_commit_certificate_state_v2",
    "verified_commit_certificate_finality_input_v2",
    "verify_portable_commit_certificate_v2",
]
