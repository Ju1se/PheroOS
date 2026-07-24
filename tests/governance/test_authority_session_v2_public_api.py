from __future__ import annotations

from importlib import import_module
import inspect
import pickle

import pheroos.governance as governance
from pheroos.governance import authority_session_v2


EXPECTED_PUBLIC_NAMES = (
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
)


def test_authority_session_v2_facade_has_one_exact_public_surface() -> None:
    assert tuple(authority_session_v2.__all__) == EXPECTED_PUBLIC_NAMES
    assert len(EXPECTED_PUBLIC_NAMES) == len(set(EXPECTED_PUBLIC_NAMES)) == 23
    assert all(not name.startswith("_") for name in EXPECTED_PUBLIC_NAMES)
    assert not hasattr(authority_session_v2, "_make_governance_authority_session_v2")
    assert not hasattr(authority_session_v2, "_make_governance_issuer_capability_v2")


def test_root_and_compatibility_module_preserve_exact_object_identity() -> None:
    canonical = import_module("pheroos.governance.authority_session_v2")
    assert authority_session_v2 is canonical
    assert governance.authority_session_v2 is canonical

    for name in EXPECTED_PUBLIC_NAMES:
        assert getattr(governance, name) is getattr(canonical, name)


def test_public_types_and_functions_have_canonical_module_and_signatures() -> None:
    for name in EXPECTED_PUBLIC_NAMES:
        value = getattr(authority_session_v2, name)
        if inspect.isclass(value) or inspect.isfunction(value):
            assert value.__module__ == "pheroos.governance.authority_session_v2"
            assert inspect.signature(getattr(governance, name)) == inspect.signature(
                value
            )


def test_portable_type_and_enum_pickle_through_the_public_owner() -> None:
    grant_type = authority_session_v2.GovernanceIssuerGrantV2
    operation = authority_session_v2.GovernanceIssuerOperationV2.VERIFY_SIGNAL

    assert pickle.loads(pickle.dumps(grant_type)) is grant_type
    assert pickle.loads(pickle.dumps(operation)) is operation
