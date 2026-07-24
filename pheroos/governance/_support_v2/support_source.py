"""Compatibility aggregate for the split durable Support v2 source owner."""

from pheroos.governance._support_v2.support_prepare import (
    _child_request as _child_request,
    prepare_support_initialize_v2,
    prepare_support_issue_v2,
    prepare_support_revoke_v2,
    prepare_support_switch_v2,
)
from pheroos.governance._support_v2.support_source_proof import (
    VerifiedSupportSourceV2,
    _expected_source_roots as _expected_source_roots,
    _expected_source_roots_from_request as _expected_source_roots_from_request,
    _verified_source_manifest_v2 as _verified_source_manifest_v2,
    verify_support_request_source_v2,
)


__all__ = [
    "VerifiedSupportSourceV2",
    "prepare_support_initialize_v2",
    "prepare_support_issue_v2",
    "prepare_support_revoke_v2",
    "prepare_support_switch_v2",
    "verify_support_request_source_v2",
]
