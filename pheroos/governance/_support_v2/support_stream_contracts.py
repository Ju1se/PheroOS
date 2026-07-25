"""Stream, mutation identity, and constant-space history roots for Support v2."""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
from collections.abc import Sequence

from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    MAX_AUTHORITY_REVISION_V2,
)
from pheroos.protocol.commit_models import CommitAssurance

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _compute_root,
    _require_root,
)
from pheroos.governance._support_v2.common import (
    _require_bounded_text_v2,
    _require_count_v2,
)


class SupportMutationKindV2(StrEnum):
    INITIALIZE = "initialize"
    ISSUE = "issue"
    REVOKE = "revoke"
    SWITCH = "switch"


def _root(kind: str, body: object) -> str:
    return _compute_root(f"support-v2:{kind}", body)


SUPPORT_GENESIS_TRANSITION_ID_V2 = "genesis"
MAX_SUPPORT_EVICTIONS_V2 = 16_384
_MAX_SUPPORT_MUTATION_TRACE_ROOTS_V2 = 1_024
SUPPORT_GENESIS_HISTORY_ROOT_V2 = _root(
    "history-genesis",
    {"canonical_version": AUTHORITY_CANONICAL_VERSION_V2},
)


def support_stream_ref_v2(
    scope_ref: str,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_ref: str,
    run_ref: str,
    target_ref: str,
) -> str:
    """Return the sole ledger for one exact target/run/policy context."""

    texts = tuple(
        _require_bounded_text_v2(value, f"support stream {label}")
        for label, value in (
            ("scope_ref", scope_ref),
            ("profile", profile),
            ("protocol_ref", protocol_ref),
            ("run_ref", run_ref),
            ("target_ref", target_ref),
        )
    )
    if type(assurance) is not CommitAssurance:
        raise TypeError("support stream assurance is invalid")
    _require_root(manifest_root, "support stream manifest_root")
    _require_root(commit_policy_root, "support stream commit_policy_root")
    parts = (
        texts[0],
        texts[1],
        assurance.value,
        manifest_root,
        commit_policy_root,
        texts[2],
        texts[3],
        texts[4],
    )
    digest = sha256("\x00".join(parts).encode("utf-8")).hexdigest()
    return f"authority:support-v2:{digest}"


def support_transition_id_v2(stream_ref: str, mutation_ref: str) -> str:
    stream = _require_bounded_text_v2(stream_ref, "support transition stream_ref")
    mutation = _require_bounded_text_v2(mutation_ref, "support mutation_ref")
    digest = sha256(stream.encode() + b"\x00" + mutation.encode()).hexdigest()
    return f"transition:support-v2:{digest}"


def support_lease_ref_v2(transition_id: str, proposal_root: str) -> str:
    transition = _require_bounded_text_v2(
        transition_id,
        "support lease transition_id",
    )
    _require_root(proposal_root, "support lease proposal_root")
    digest = sha256(
        transition.encode("utf-8") + b"\x00" + proposal_root.encode("ascii")
    ).hexdigest()
    return f"lease:support-v2:{digest}"


def support_revocation_ref_v2(transition_id: str, lease_root: str) -> str:
    transition = _require_bounded_text_v2(
        transition_id,
        "support revocation transition_id",
    )
    _require_root(lease_root, "support revocation lease_root")
    digest = sha256(
        transition.encode("utf-8") + b"\x00" + lease_root.encode("ascii")
    ).hexdigest()
    return f"revocation:support-v2:{digest}"


def support_mutation_delta_root_v2(
    mutation_kind: SupportMutationKindV2,
    *,
    transition_id: str,
    mutation_issuer_ref: str,
    observed_epoch: int,
    current_step: int,
    mutation_provenance_root: str,
    mutation_trace_roots: Sequence[str],
    issued_lease_root: str,
    revoked_lease_root: str,
    revocation_root: str,
    evicted_lease_roots: Sequence[str],
    membership_stream_ref: str,
    membership_transition_id: str,
    membership_snapshot_root: str,
) -> str:
    """Bind one complete historical mutation without embedding its records."""

    if type(mutation_kind) is not SupportMutationKindV2:
        raise TypeError("support mutation delta kind is invalid")
    transition = _require_bounded_text_v2(
        transition_id,
        "support mutation delta transition_id",
    )
    issuer = _require_bounded_text_v2(
        mutation_issuer_ref,
        "support mutation delta issuer_ref",
    )
    epoch = _require_count_v2(
        observed_epoch,
        "support mutation delta observed_epoch",
    )
    step = _require_count_v2(
        current_step,
        "support mutation delta current_step",
    )
    _require_root(
        mutation_provenance_root,
        "support mutation delta provenance_root",
    )
    traces = _canonical_roots(
        mutation_trace_roots,
        "support mutation delta trace roots",
        limit=_MAX_SUPPORT_MUTATION_TRACE_ROOTS_V2,
    )
    for value in (
        issued_lease_root,
        revoked_lease_root,
        revocation_root,
        membership_snapshot_root,
    ):
        if value:
            _require_root(value, "support mutation delta root")
    for value in (membership_stream_ref, membership_transition_id):
        _require_bounded_text_v2(
            value,
            "support mutation delta membership binding",
            allow_empty=True,
        )
    evicted = tuple(evicted_lease_roots)
    if len(evicted) > MAX_SUPPORT_EVICTIONS_V2:
        raise ValueError("support eviction count exceeds its active-set bound")
    if any(type(item) is not str for item in evicted):
        raise TypeError("support evicted lease roots must be exact text")
    for item in evicted:
        _require_root(item, "support evicted lease root")
    if evicted != tuple(sorted(set(evicted), key=lambda item: item.encode("ascii"))):
        raise ValueError("support evicted lease roots must be unique canonical roots")
    return _root(
        "mutation-delta",
        {
            "mutation_kind": mutation_kind.value,
            "transition_id": transition,
            "mutation_issuer_ref": issuer,
            "observed_epoch": epoch,
            "current_step": step,
            "mutation_provenance_root": mutation_provenance_root,
            "mutation_trace_roots": list(traces),
            "issued_lease_root": issued_lease_root,
            "revoked_lease_root": revoked_lease_root,
            "revocation_root": revocation_root,
            "evicted_lease_roots": list(evicted),
            "membership_stream_ref": membership_stream_ref,
            "membership_transition_id": membership_transition_id,
            "membership_snapshot_root": membership_snapshot_root,
        },
    )


def support_switch_lineage_v2(
    *,
    revocation_provenance_root: str,
    revocation_trace_roots: Sequence[str],
    issuance_provenance_root: str,
    issuance_trace_roots: Sequence[str],
) -> tuple[str, tuple[str, ...]]:
    """Return the exact aggregate lineage committed by one atomic switch."""

    for root in (revocation_provenance_root, issuance_provenance_root):
        _require_root(root, "support switch provenance root")
    revocation_traces = _canonical_roots(
        revocation_trace_roots,
        "support switch revocation trace roots",
        limit=_MAX_SUPPORT_MUTATION_TRACE_ROOTS_V2,
    )
    issuance_traces = _canonical_roots(
        issuance_trace_roots,
        "support switch issuance trace roots",
        limit=_MAX_SUPPORT_MUTATION_TRACE_ROOTS_V2,
    )
    traces = tuple(
        sorted(
            set((*revocation_traces, *issuance_traces)),
            key=lambda item: item.encode("ascii"),
        )
    )
    if len(traces) > _MAX_SUPPORT_MUTATION_TRACE_ROOTS_V2:
        raise ValueError("support switch trace roots exceed their aggregate bound")
    return (
        _root(
            "switch-provenance",
            {
                "revocation_provenance_root": revocation_provenance_root,
                "issuance_provenance_root": issuance_provenance_root,
            },
        ),
        traces,
    )


def _canonical_roots(
    values: Sequence[str],
    label: str,
    *,
    limit: int,
) -> tuple[str, ...]:
    if type(values) not in (list, tuple):
        raise TypeError(f"{label} must be an exact array or tuple")
    roots = tuple(values)
    if not roots or len(roots) > limit:
        raise ValueError(f"{label} count is outside its bound")
    if any(type(item) is not str for item in roots):
        raise TypeError(f"{label} must contain exact text")
    for root in roots:
        _require_root(root, label)
    canonical = tuple(sorted(set(roots), key=lambda item: item.encode("ascii")))
    if roots != canonical:
        raise ValueError(f"{label} must be unique canonical roots")
    return roots


def support_history_advance_v2(
    *,
    parent_history_root: str,
    parent_history_count: int,
    transition_id: str,
    mutation_delta_root: str,
) -> tuple[str, int]:
    """Extend the append-only history commitment in constant snapshot space."""

    _require_root(parent_history_root, "support parent_history_root")
    _require_root(mutation_delta_root, "support mutation_delta_root")
    transition = _require_bounded_text_v2(
        transition_id,
        "support history transition_id",
    )
    count = _require_count_v2(parent_history_count, "support parent_history_count")
    if count >= MAX_AUTHORITY_REVISION_V2:
        raise ValueError("support history count exceeds the authority integer bound")
    next_count = count + 1
    return (
        _root(
            "history-link",
            {
                "parent_history_root": parent_history_root,
                "parent_history_count": count,
                "transition_id": transition,
                "mutation_delta_root": mutation_delta_root,
                "history_count": next_count,
            },
        ),
        next_count,
    )


__all__: tuple[str, ...] = ()
