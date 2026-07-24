"""Exact StateStore records for Commit Evidence v2 transitions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from pheroos.protocol.authority_v2 import GovernanceReadPreconditionV2

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceIssuerOperationV2,
    governance_issuer_grant_stream_ref_v2,
)
from pheroos.governance._authority_session_v2.operations import _portable_projection
from pheroos.governance._commit_evidence_owner_v2.contracts import (
    COMMIT_EVIDENCE_STATE_SCHEMA_V2,
    CommitEvidenceAdvanceRequestV2,
    CommitEvidenceSnapshotV2,
)
from pheroos.governance._commit_evidence_owner_v2.source_proof import (
    _source_context_root_from_request_v2,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    AuthorityDomainV2,
)


_STATE_FIELDS = frozenset(
    {
        "schema",
        "domain_root",
        "scope_ref",
        "stream_ref",
        "transition_id",
        "request_root",
        "request",
        "snapshot_root",
        "snapshot",
        "source_context_root",
        "session_binding",
    }
)
_SESSION_FIELDS = frozenset(
    {
        "domain_root",
        "scope_ref",
        "run_ref",
        "request_ref",
        "request_root",
        "operation",
        "observed_epoch",
        "grant_ref",
        "grant_root",
        "grant_binding_ref",
        "grant_expected_revision",
        "grant_expected_root",
        "lifecycle_expected_revision",
        "lifecycle_expected_root",
        "target_refs",
        "action_refs",
    }
)


def _state_records(
    request: CommitEvidenceAdvanceRequestV2,
    session_binding: Mapping[str, object],
    *,
    source_context_root: str,
) -> dict[str, object]:
    return {
        "schema": COMMIT_EVIDENCE_STATE_SCHEMA_V2,
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.stream_ref,
        "transition_id": request.transition_id,
        "request_root": request.request_root,
        "request": request.to_dict(),
        "snapshot_root": request.snapshot.snapshot_root,
        "snapshot": request.snapshot.to_dict(),
        "source_context_root": source_context_root,
        "session_binding": _portable_projection(session_binding),
    }


def _decode_state_records(
    value: object,
    domain: AuthorityDomainV2,
) -> tuple[CommitEvidenceAdvanceRequestV2, dict[str, object], str]:
    state = _string_object(
        _portable_projection(value),
        "commit evidence state",
    )
    if set(state) != _STATE_FIELDS:
        raise ValueError("commit evidence committed state fields are invalid")
    if (
        state["schema"] != COMMIT_EVIDENCE_STATE_SCHEMA_V2
        or state["domain_root"] != domain.domain_root
        or state["scope_ref"] != domain.scope_ref
    ):
        raise ValueError("commit evidence committed state domain is mismatched")
    request = CommitEvidenceAdvanceRequestV2.from_dict(state["request"])
    snapshot = CommitEvidenceSnapshotV2.from_dict(state["snapshot"])
    if (
        request.domain_root != domain.domain_root
        or request.scope_ref != domain.scope_ref
        or state["stream_ref"] != request.stream_ref
        or state["transition_id"] != request.transition_id
        or state["request_root"] != request.request_root
        or state["snapshot_root"] != request.snapshot.snapshot_root
        or snapshot.to_dict() != request.snapshot.to_dict()
        or state["source_context_root"] != _source_context_root_from_request_v2(request)
    ):
        raise ValueError("commit evidence committed state payload is mismatched")
    source_root = state["source_context_root"]
    if type(source_root) is not str:
        raise ValueError("commit evidence source context root is invalid")
    binding = _validate_session_binding(state["session_binding"], request)
    return request, binding, source_root


def _validate_session_binding(
    value: object,
    request: CommitEvidenceAdvanceRequestV2,
) -> dict[str, object]:
    binding = _string_object(
        _portable_projection(value),
        "commit evidence session binding",
    )
    if set(binding) != _SESSION_FIELDS:
        raise ValueError("commit evidence session binding fields are invalid")
    observed = (
        binding["domain_root"],
        binding["scope_ref"],
        binding["run_ref"],
        binding["request_ref"],
        binding["request_root"],
        binding["operation"],
        binding["observed_epoch"],
        binding["target_refs"],
        binding["action_refs"],
    )
    expected: tuple[object, ...] = (
        request.domain_root,
        request.scope_ref,
        request.run_ref,
        request.advance_ref,
        request.request_root,
        GovernanceIssuerOperationV2.QUALIFY_EVIDENCE.value,
        request.observed_epoch,
        [request.target_ref],
        [],
    )
    if observed != expected:
        raise ValueError("commit evidence stored session binding is mismatched")
    for field in ("grant_ref", "grant_root", "grant_binding_ref"):
        if type(binding[field]) is not str or not binding[field]:
            raise ValueError("commit evidence stored grant binding is invalid")
    grant_ref = _text_field(binding, "grant_ref")
    GovernanceReadPreconditionV2(
        stream_ref=governance_issuer_grant_stream_ref_v2(
            request.scope_ref,
            grant_ref,
        ),
        expected_revision=_integer_field(binding, "grant_expected_revision"),
        expected_root=_text_field(binding, "grant_expected_root"),
    )
    GovernanceReadPreconditionV2(
        stream_ref=GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        expected_revision=_integer_field(binding, "lifecycle_expected_revision"),
        expected_root=_text_field(binding, "lifecycle_expected_root"),
    )
    return binding


def _string_object(value: object, label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise TypeError(f"{label} must be an exact object")
    raw = cast(dict[object, object], value)
    if any(type(key) is not str for key in raw):
        raise ValueError(f"{label} keys must be exact strings")
    return {cast(str, key): item for key, item in raw.items()}


def _text_field(value: Mapping[str, object], field: str) -> str:
    item = value[field]
    if type(item) is not str or not item:
        raise ValueError(f"commit evidence session {field} is invalid")
    return item


def _integer_field(value: Mapping[str, object], field: str) -> int:
    item = value[field]
    if type(item) is not int:
        raise ValueError(f"commit evidence session {field} is invalid")
    return item


__all__: tuple[str, ...] = ()
