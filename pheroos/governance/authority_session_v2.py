"""Public scoped-authority grant, capability, and session ABI.

Portable grants and requests remain deterministic records.  Capability and
session objects are opaque local handles issued only by the trusted
StateStore-backed operations in this facade.
"""

from __future__ import annotations

from pheroos.governance._authority_session_v2.contracts import (
    GOVERNANCE_DOMAIN_RETIREMENT_REQUEST_SCHEMA_V2,
    GOVERNANCE_ISSUER_GRANT_SCHEMA_V2,
    GOVERNANCE_VERIFIED_SIGNAL_REQUEST_SCHEMA_V2,
    ISSUER_GRANT_VERIFICATION_SCHEMA_V2,
    GovernanceAuthorityBindingErrorV2,
    GovernanceAuthoritySessionV2,
    GovernanceDomainRetirementRequestV2,
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    GovernanceVerifiedSignalRequestV2,
    IssuerGrantVerificationV2,
    IssuerGrantVerifierV2,
    governance_issuer_grant_stream_ref_v2,
    governance_verified_signal_stream_ref_v2,
)
from pheroos.governance._authority_session_v2.operations import (
    GOVERNANCE_ISSUER_GRANT_STATE_SCHEMA_V2,
    GOVERNANCE_VERIFIED_SIGNAL_STATE_SCHEMA_V2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    commit_verified_signal_v2,
    open_governance_authority_session_v2,
    retire_governance_domain_v2,
    revoke_governance_issuer_grant_v2,
)


_PUBLIC_MODULE = __name__
_NATIVE_PUBLIC_OBJECTS = (
    GovernanceAuthorityBindingErrorV2,
    GovernanceIssuerOperationV2,
    GovernanceIssuerGrantV2,
    IssuerGrantVerificationV2,
    IssuerGrantVerifierV2,
    GovernanceVerifiedSignalRequestV2,
    GovernanceDomainRetirementRequestV2,
    GovernanceIssuerCapabilityV2,
    GovernanceAuthoritySessionV2,
    governance_issuer_grant_stream_ref_v2,
    governance_verified_signal_stream_ref_v2,
    activate_governance_issuer_grant_v2,
    revoke_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    open_governance_authority_session_v2,
    commit_verified_signal_v2,
    retire_governance_domain_v2,
)
for _public_object in _NATIVE_PUBLIC_OBJECTS:
    _public_object.__module__ = _PUBLIC_MODULE
del _public_object


__all__ = [
    "GOVERNANCE_DOMAIN_RETIREMENT_REQUEST_SCHEMA_V2",
    "GOVERNANCE_ISSUER_GRANT_SCHEMA_V2",
    "GOVERNANCE_ISSUER_GRANT_STATE_SCHEMA_V2",
    "GOVERNANCE_VERIFIED_SIGNAL_REQUEST_SCHEMA_V2",
    "GOVERNANCE_VERIFIED_SIGNAL_STATE_SCHEMA_V2",
    "ISSUER_GRANT_VERIFICATION_SCHEMA_V2",
    "GovernanceAuthorityBindingErrorV2",
    "GovernanceAuthoritySessionV2",
    "GovernanceDomainRetirementRequestV2",
    "GovernanceIssuerCapabilityV2",
    "GovernanceIssuerGrantV2",
    "GovernanceIssuerOperationV2",
    "GovernanceVerifiedSignalRequestV2",
    "IssuerGrantVerificationV2",
    "IssuerGrantVerifierV2",
    "activate_governance_issuer_grant_v2",
    "bind_governance_issuer_capability_v2",
    "commit_verified_signal_v2",
    "governance_issuer_grant_stream_ref_v2",
    "governance_verified_signal_stream_ref_v2",
    "open_governance_authority_session_v2",
    "retire_governance_domain_v2",
    "revoke_governance_issuer_grant_v2",
]
