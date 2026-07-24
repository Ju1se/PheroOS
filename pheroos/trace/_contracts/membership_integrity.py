"""Independent integrity derivations for durable membership Trace events.

The helpers intentionally duplicate the frozen portable hashing rules instead
of importing Governance.  Trace can therefore reject a producer that supplies
well-shaped but internally unrelated source or read-set commitments.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, cast


_AUTHORITY_CANONICAL_VERSION = "pheroos-authority-canonical-v2"
_AUTHORITY_READ_SET_SCHEMA = "pheroos-governance-authority-read-set-v2"
_AUTHORITY_ROOT_PREFIX = "pheroos-governance-authority-v2:"
_DOMAIN_LIFECYCLE_STREAM = "authority:domain-lifecycle"


def _expected_membership_source_context_root(
    event_type: str,
    lineage: dict[str, Any],
) -> str:
    if event_type == "principal_verification_set_advanced":
        kind = "principal-verification-v2:source-context"
        body = {
            "version": "pheroos-principal-verification-source-v2",
            "request_root": lineage["request_root"],
            "manifest_root": lineage["manifest_root"],
            "authority_policy_root": lineage["authority_policy_root"],
            "commit_policy_root": lineage["commit_policy_root"],
            "verification_policy_root": lineage["verification_policy_root"],
            "verification_set_root": lineage["verification_set_root"],
        }
    else:
        kind = "membership-v2:source-context"
        body = {
            "version": "pheroos-membership-source-v2",
            "request_root": lineage["request_root"],
            "manifest_root": lineage["manifest_root"],
            "authority_policy_root": lineage["authority_policy_root"],
            "commit_policy_root": lineage["commit_policy_root"],
            "membership_policy_root": lineage["membership_policy_root"],
            "verification_set_root": lineage["verification_set_root"],
            "membership_root": lineage["membership_root"],
        }
    return _authority_root(kind, body)


def _expected_membership_read_set_root(
    event_type: str,
    lineage: dict[str, Any],
) -> str:
    binding = lineage["session_binding"]
    entries = [
        _read_precondition(
            lineage["stream_ref"],
            lineage["parent_revision"],
            lineage["parent_head_root"],
        ),
        _read_precondition(
            _authority_stream_ref(
                "issuer-grant",
                (lineage["scope_ref"], lineage["grant_ref"]),
            ),
            binding["grant_expected_revision"],
            binding["grant_expected_root"],
        ),
        _read_precondition(
            _DOMAIN_LIFECYCLE_STREAM,
            binding["lifecycle_expected_revision"],
            binding["lifecycle_expected_root"],
        ),
    ]
    if event_type == "membership_epoch_committed":
        entries.append(
            _read_precondition(
                lineage["verification_stream_ref"],
                lineage["verification_revision"],
                lineage["verification_head_root"],
            )
        )
    entries.sort(key=lambda item: cast(str, item["stream_ref"]).encode("utf-8"))
    payload = {
        "canonical_version": _AUTHORITY_CANONICAL_VERSION,
        "entries": entries,
        "schema": _AUTHORITY_READ_SET_SCHEMA,
    }
    return "sha256:" + sha256(_canonical_bytes(payload)).hexdigest()


def _read_precondition(
    stream_ref: str,
    expected_revision: int,
    expected_root: str,
) -> dict[str, object]:
    return {
        "expected_revision": expected_revision,
        "expected_root": expected_root,
        "stream_ref": stream_ref,
    }


def _authority_stream_ref(kind: str, bindings: tuple[str, ...]) -> str:
    payload = b"\x00".join(binding.encode("utf-8") for binding in bindings)
    return f"authority:{kind}:{sha256(payload).hexdigest()}"


def _authority_root(kind: str, body: object) -> str:
    prefix = (_AUTHORITY_ROOT_PREFIX + kind).encode("utf-8")
    return "sha256:" + sha256(prefix + b"\x00" + _canonical_bytes(body)).hexdigest()


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


__all__: tuple[str, ...] = ()
