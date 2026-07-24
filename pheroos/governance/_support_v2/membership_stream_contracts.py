"""Fixed-lineage stream and projection identifiers for Membership v2."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2
from pheroos.protocol.commit_models import CommitAssurance

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _compute_root,
    _require_root,
)
from pheroos.governance._support_v2.common import _require_bounded_text_v2
from pheroos.governance._support_v2.membership_records import (
    MembershipClusterV2,
    canonical_membership_clusters_v2,
)


MEMBERSHIP_SNAPSHOT_SCHEMA_V2 = "pheroos-membership-snapshot-v2"
MEMBERSHIP_COMMIT_REQUEST_SCHEMA_V2 = "pheroos-membership-commit-request-v2"
MEMBERSHIP_STATE_SCHEMA_V2 = "pheroos-membership-state-v2"


def _root(kind: str, body: object) -> str:
    return _compute_root(f"membership-v2:{kind}", body)


MEMBERSHIP_GENESIS_SNAPSHOT_ROOT_V2 = _root(
    "genesis-parent",
    {
        "schema": MEMBERSHIP_SNAPSHOT_SCHEMA_V2,
        "canonical_version": AUTHORITY_CANONICAL_VERSION_V2,
    },
)
MEMBERSHIP_GENESIS_TRANSITION_ID_V2 = "genesis"


def membership_stream_ref_v2(
    scope_ref: str,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    membership_policy_root: str,
    protocol_ref: str,
    run_ref: str,
    target_ref: str,
) -> str:
    """Return one fixed stream; epoch deliberately remains state."""

    texts = tuple(
        _require_bounded_text_v2(value, f"membership stream {label}")
        for label, value in (
            ("scope_ref", scope_ref),
            ("profile", profile),
            ("protocol_ref", protocol_ref),
            ("run_ref", run_ref),
            ("target_ref", target_ref),
        )
    )
    if type(assurance) is not CommitAssurance:
        raise TypeError("membership stream assurance is invalid")
    for label, value in (
        ("manifest_root", manifest_root),
        ("commit_policy_root", commit_policy_root),
        ("membership_policy_root", membership_policy_root),
    ):
        _require_root(value, f"membership stream {label}")
    material = (
        texts[0],
        texts[1],
        assurance.value,
        manifest_root,
        commit_policy_root,
        membership_policy_root,
        texts[2],
        texts[3],
        texts[4],
    )
    return (
        "authority:membership-v2:"
        + sha256("\x00".join(material).encode("utf-8")).hexdigest()
    )


def membership_transition_id_v2(stream_ref: str, request_ref: str) -> str:
    stream = _require_bounded_text_v2(stream_ref, "membership transition stream_ref")
    request = _require_bounded_text_v2(request_ref, "membership transition request_ref")
    digest = sha256(f"{stream}\x00{request}".encode("utf-8")).hexdigest()
    return f"transition:membership-v2:{digest}"


def membership_projection_root_v2(
    *,
    membership_policy_root: str,
    verification_set_root: str,
    protocol_ref: str,
    run_ref: str,
    target_ref: str,
    epoch: int,
    clusters: Sequence[MembershipClusterV2],
) -> str:
    canonical = canonical_membership_clusters_v2(clusters)
    return _root(
        "projection",
        {
            "membership_policy_root": membership_policy_root,
            "verification_set_root": verification_set_root,
            "protocol_ref": protocol_ref,
            "run_ref": run_ref,
            "target_ref": target_ref,
            "epoch": epoch,
            "clusters": [item.to_dict() for item in canonical],
        },
    )


__all__ = [
    "MEMBERSHIP_COMMIT_REQUEST_SCHEMA_V2",
    "MEMBERSHIP_GENESIS_SNAPSHOT_ROOT_V2",
    "MEMBERSHIP_GENESIS_TRANSITION_ID_V2",
    "MEMBERSHIP_SNAPSHOT_SCHEMA_V2",
    "MEMBERSHIP_STATE_SCHEMA_V2",
    "membership_projection_root_v2",
    "membership_stream_ref_v2",
    "membership_transition_id_v2",
]
