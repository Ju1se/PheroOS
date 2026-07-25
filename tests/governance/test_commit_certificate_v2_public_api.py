from __future__ import annotations

import inspect
import json
from pathlib import Path
import subprocess
import sys

import pheroos.governance.commit_certificate_v2 as api


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_PUBLIC = frozenset(
    """
    COMMIT_CERTIFICATE_AUTHORITY_LEAF_SCHEMA_V2
    COMMIT_CERTIFICATE_BODY_SCHEMA_V2
    COMMIT_CERTIFICATE_ENVELOPE_SCHEMA_V2
    COMMIT_CERTIFICATE_GENESIS_HISTORY_ROOT_V2
    COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2
    COMMIT_CERTIFICATE_GENESIS_TRANSITION_ID_V2
    COMMIT_CERTIFICATE_IDENTITY_BINDING_SCHEMA_V2
    COMMIT_CERTIFICATE_REQUEST_SCHEMA_V2
    COMMIT_CERTIFICATE_SNAPSHOT_SCHEMA_V2
    COMMIT_CERTIFICATE_STATE_SCHEMA_V2
    CommitCertificateAuthorityLeafV2
    CommitCertificateAuthorityRoleV2
    CommitCertificateBodyV2
    CommitCertificateIdentityBindingV2
    CommitCertificateIssuerAttestationVerifierV2
    CommitCertificateMutationKindV2
    CommitCertificateRequestV2
    CommitCertificateSnapshotV2
    CommitCertificateStatusV2
    PortableCommitCertificateV2
    VerifiedCommitCertificateSourceV2
    VerifiedCommitCertificateStateV2
    advance_commit_certificate_v2
    canonical_commit_certificate_authority_leaves_v2
    commit_certificate_authority_leaf_set_root_v2
    commit_certificate_state_is_current_v2
    commit_certificate_stream_ref_v2
    commit_certificate_transition_id_v2
    open_commit_certificate_authority_session_v2
    prepare_commit_certificate_v2
    rehydrate_commit_certificate_state_v2
    require_current_commit_certificate_state_v2
    verified_commit_certificate_finality_input_v2
    verify_portable_commit_certificate_v2
    """.split()
)


def test_commit_certificate_v2_public_surface_is_exact_and_native() -> None:
    assert frozenset(api.__all__) == EXPECTED_PUBLIC
    assert len(api.__all__) == len(EXPECTED_PUBLIC)
    assert all(not name.startswith("_") for name in api.__all__)
    for name in api.__all__:
        value = getattr(api, name)
        if inspect.isclass(value) or inspect.isfunction(value):
            assert value.__module__ == "pheroos.governance.commit_certificate_v2"


def test_standalone_facade_preserves_neutral_handle_identity_and_has_no_issuer() -> (
    None
):
    script = """
import inspect
import json
import sys

from pheroos.governance import _commit_finality_v2 as neutral

before = neutral.VerifiedCommitFinalityInputV2.__module__
import pheroos.governance.commit_certificate_v2 as facade
after = neutral.VerifiedCommitFinalityInputV2.__module__
result = {
    "before": before,
    "after": after,
    "decision_facade_loaded": (
        "pheroos.governance.commit_decision_v2" in sys.modules
    ),
    "distributed_facade_loaded": (
        "pheroos.governance.distributed_commit_v2" in sys.modules
    ),
    "finality_facade_loaded": (
        "pheroos.governance.commit_finality_v2" in sys.modules
    ),
    "function_module": (
        facade.verified_commit_certificate_finality_input_v2.__module__
    ),
    "return_type_is_neutral": (
        inspect.signature(
            facade.verified_commit_certificate_finality_input_v2
        ).return_annotation
        is neutral.VerifiedCommitFinalityInputV2
    ),
    "issuer_exposed": (
        "_issue_verified_commit_finality_input_v2" in facade.__dict__
        or "_issue_verified_commit_finality_input_v2" in facade.__all__
    ),
    "neutral_type_reexported": (
        "VerifiedCommitFinalityInputV2" in facade.__all__
    ),
}
print(json.dumps(result, sort_keys=True))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result == {
        "after": "pheroos.governance.commit_finality_v2",
        "before": "pheroos.governance._commit_finality_v2",
        "decision_facade_loaded": False,
        "distributed_facade_loaded": False,
        "finality_facade_loaded": True,
        "function_module": "pheroos.governance.commit_certificate_v2",
        "issuer_exposed": False,
        "neutral_type_reexported": False,
        "return_type_is_neutral": True,
    }


def test_certificate_finality_entrypoint_is_owner_adapter_only() -> None:
    assert callable(api.verified_commit_certificate_finality_input_v2)
    assert not hasattr(api, "_issue_verified_commit_finality_input_v2")
    assert not hasattr(api, "VerifiedCommitFinalityInputV2")
