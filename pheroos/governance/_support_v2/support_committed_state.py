"""Exact portable StateStore records for durable Support v2 transitions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from pheroos.protocol.authority_v2 import GovernanceReadPreconditionV2

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceIssuerOperationV2,
    governance_issuer_grant_stream_ref_v2,
)
from pheroos.governance._authority_session_v2.operations import _portable_projection
from pheroos.governance._authority_store_v2_contracts.foundation import _require_root
from pheroos.governance._support_v2.support_source_binding import (
    _source_roots_from_request,
)
from pheroos.governance._support_v2.support_state_contracts import (
    SUPPORT_STATE_SCHEMA_V2,
    SupportAdvanceRequestV2,
    SupportMutationKindV2,
    SupportSnapshotV2,
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
        "source_verification_root",
        "membership_read_precondition",
        "session_binding",
    }
)
_SESSION_BINDING_FIELDS = frozenset(
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


def _validate_membership_precondition(
    request: SupportAdvanceRequestV2,
    precondition: GovernanceReadPreconditionV2 | None,
) -> None:
    needs_membership = request.mutation_kind in (
        SupportMutationKindV2.ISSUE,
        SupportMutationKindV2.SWITCH,
    )
    if needs_membership:
        if type(precondition) is not GovernanceReadPreconditionV2:
            raise ValueError("support issuance is missing its membership head")
        if precondition.stream_ref != request.membership_stream_ref:
            raise ValueError("support membership head is cross-bound")
    elif precondition is not None:
        raise ValueError("support mutation has an undeclared membership head")


def _state_records(
    request: SupportAdvanceRequestV2,
    session_binding: Mapping[str, Any],
    *,
    source_context_root: str,
    source_verification_root: str,
    membership_precondition: GovernanceReadPreconditionV2 | None,
) -> dict[str, Any]:
    return {
        "schema": SUPPORT_STATE_SCHEMA_V2,
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.stream_ref,
        "transition_id": request.transition_id,
        "request_root": request.request_root,
        "request": request.to_dict(),
        "snapshot_root": request.snapshot.snapshot_root,
        "snapshot": request.snapshot.to_dict(),
        "source_context_root": source_context_root,
        "source_verification_root": source_verification_root,
        "membership_read_precondition": (
            None
            if membership_precondition is None
            else membership_precondition.to_dict()
        ),
        "session_binding": _portable_projection(session_binding),
    }


def _decode_state_records(
    value: object,
    domain: AuthorityDomainV2,
) -> tuple[
    SupportAdvanceRequestV2,
    dict[str, Any],
    str,
    str,
    GovernanceReadPreconditionV2 | None,
]:
    projected = _portable_projection(value)
    if type(projected) is not dict:
        raise TypeError("support state must be an exact object")
    state = cast(dict[str, Any], projected)
    if set(state) != _STATE_FIELDS:
        raise ValueError("support committed state fields are invalid")
    if (
        state["schema"] != SUPPORT_STATE_SCHEMA_V2
        or state["domain_root"] != domain.domain_root
        or state["scope_ref"] != domain.scope_ref
    ):
        raise ValueError("support committed state domain is mismatched")
    request = SupportAdvanceRequestV2.from_dict(state["request"])
    snapshot = SupportSnapshotV2.from_dict(state["snapshot"])
    if (
        state["stream_ref"] != request.stream_ref
        or state["transition_id"] != request.transition_id
        or state["request_root"] != request.request_root
        or state["snapshot_root"] != request.snapshot.snapshot_root
        or snapshot.to_dict() != request.snapshot.to_dict()
        or request.domain_root != domain.domain_root
        or request.scope_ref != domain.scope_ref
    ):
        raise ValueError("support committed state payload is mismatched")
    _require_root(state["source_context_root"], "support source_context_root")
    _require_root(
        state["source_verification_root"],
        "support source_verification_root",
    )
    expected_source = _source_roots_from_request(request)
    observed_source = (
        state["source_context_root"],
        state["source_verification_root"],
    )
    if observed_source != expected_source:
        raise ValueError("support committed source lineage is mismatched")
    membership = _decode_membership_precondition(
        state["membership_read_precondition"],
        request,
    )
    binding = _validate_stored_session_binding(state["session_binding"], request)
    return (
        request,
        binding,
        cast(str, state["source_context_root"]),
        cast(str, state["source_verification_root"]),
        membership,
    )


def _decode_membership_precondition(
    value: object,
    request: SupportAdvanceRequestV2,
) -> GovernanceReadPreconditionV2 | None:
    precondition = (
        None if value is None else GovernanceReadPreconditionV2.from_dict(value)
    )
    _validate_membership_precondition(request, precondition)
    return precondition


def _validate_stored_session_binding(
    value: object,
    request: SupportAdvanceRequestV2,
) -> dict[str, Any]:
    projected = _portable_projection(value)
    if type(projected) is not dict or set(projected) != _SESSION_BINDING_FIELDS:
        raise ValueError("support session binding fields are invalid")
    binding = cast(dict[str, Any], projected)
    observed: tuple[object, ...] = (
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
        request.mutation_ref,
        request.request_root,
        GovernanceIssuerOperationV2.QUALIFY_EVIDENCE.value,
        request.observed_epoch,
        [request.target_ref],
        [],
    )
    if observed != expected:
        raise ValueError("support stored session binding is mismatched")
    for field in ("grant_ref", "grant_root", "grant_binding_ref"):
        if type(binding[field]) is not str or not binding[field]:
            raise ValueError("support stored grant binding is invalid")
    GovernanceReadPreconditionV2(
        stream_ref=governance_issuer_grant_stream_ref_v2(
            request.scope_ref,
            cast(str, binding["grant_ref"]),
        ),
        expected_revision=binding["grant_expected_revision"],
        expected_root=binding["grant_expected_root"],
    )
    GovernanceReadPreconditionV2(
        stream_ref=GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        expected_revision=binding["lifecycle_expected_revision"],
        expected_root=binding["lifecycle_expected_root"],
    )
    return binding


__all__: tuple[str, ...] = ()
