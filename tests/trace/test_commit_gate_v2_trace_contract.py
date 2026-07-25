from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any

import pytest

from tests.governance import test_commit_gate_v2_operations as gate_fixture

from pheroos.governance.authority_store_v2 import GovernanceCommitDispositionV2
from pheroos.governance.commit_gate_v2 import (
    issue_commit_permission_v2,
    open_commit_permission_authority_session_v2,
    open_commit_stop_authority_session_v2,
    resolve_commit_stop_v2,
)
from pheroos.trace import InMemoryTraceStore, TraceEvent


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def gate_events() -> dict[str, TraceEvent]:
    environment = gate_fixture._environment("scope:commit-gate:trace-adversarial")
    stop, stop_source = gate_fixture._prepare_stop(
        environment, label="trace", blocked=True
    )
    permission, permission_source = gate_fixture._prepare_permission(
        environment, label="trace"
    )
    stop_attempt = resolve_commit_stop_v2(
        stop,
        source=stop_source,
        authority_session=open_commit_stop_authority_session_v2(
            environment.capability(), stop
        ),
    )
    permission_attempt = issue_commit_permission_v2(
        permission,
        source=permission_source,
        authority_session=open_commit_permission_authority_session_v2(
            environment.capability(), permission
        ),
    )
    assert stop_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert permission_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert stop_attempt.committed_transition is not None
    assert permission_attempt.committed_transition is not None
    return {
        "stop": stop_attempt.committed_transition.batch.trace_batch.events[0],
        "permission": (
            permission_attempt.committed_transition.batch.trace_batch.events[0]
        ),
    }


def _mutated(event: TraceEvent, mutation: str) -> TraceEvent:
    lineage = deepcopy(event.lineage)
    _mutate_stop_lineage(lineage, mutation)
    return TraceEvent(
        event_type=event.event_type,
        protocol_id=event.protocol_id,
        target=event.target,
        reason=event.reason,
        lineage=lineage,
    )


def _mutate_stop_lineage(lineage: dict[str, Any], mutation: str) -> None:
    replacements: dict[str, tuple[str, object]] = {
        "stream_ref": ("stream_ref", "authority:commit-stop-v2:" + "0" * 64),
        "transition_id": (
            "transition_id",
            "transition:commit-stop-v2:" + "0" * 64,
        ),
        "dependency_head": (
            "replay_head_root",
            _root("forged:dependency-head"),
        ),
        "verification_head": (
            "verification_head_root",
            _root("forged:verification-head"),
        ),
        "dependency_root": ("dependency_root", _root("forged:dependency-root")),
        "policy_root": ("policy_root", _root("forged:policy")),
        "evaluation_context_root": (
            "evaluation_context_root",
            _root("forged:evaluation-context"),
        ),
        "source_context_root": (
            "source_context_root",
            _root("forged:source-context"),
        ),
        "snapshot_root": ("snapshot_root", _root("forged:snapshot")),
        "request_root": ("request_root", _root("forged:request")),
        "read_set_root": ("read_set_root", _root("forged:read-set")),
        "issuer": ("grant_issuer_ref", "issuer:forged"),
        "boolean_epoch": ("observed_epoch", True),
        "reason_root": ("reason_root", _root("forged:reasons")),
        "overbyte": ("resolution_ref", "界" * 4097),
        "unknown": ("undeclared", "forged"),
    }
    if mutation in replacements:
        key, value = replacements[mutation]
        lineage[key] = value
    elif mutation == "expired":
        lineage["current_step"] = lineage["expires_at_step"]
    elif mutation == "reason_order":
        lineage["reason_codes"] = ["stop:z", "stop:a"]
    elif mutation == "missing":
        del lineage["policy_root"]
    else:  # pragma: no cover - test declaration owns the closed mutation set
        raise AssertionError(mutation)


@pytest.mark.parametrize(
    "mutation",
    (
        "stream_ref",
        "transition_id",
        "dependency_head",
        "verification_head",
        "dependency_root",
        "policy_root",
        "evaluation_context_root",
        "source_context_root",
        "snapshot_root",
        "request_root",
        "read_set_root",
        "issuer",
        "boolean_epoch",
        "expired",
        "reason_root",
        "reason_order",
        "overbyte",
        "unknown",
        "missing",
    ),
)
def test_stop_trace_rejects_each_detached_lineage_substitution(
    gate_events: dict[str, TraceEvent], mutation: str
) -> None:
    with pytest.raises((TypeError, ValueError)):
        InMemoryTraceStore().append(_mutated(gate_events["stop"], mutation))


@pytest.mark.parametrize(
    "mutation",
    (
        "allowed_bool",
        "candidate_order",
        "candidate_set_root",
        "claim_order",
        "claims_root",
        "action_bounds",
    ),
)
def test_permission_trace_rejects_decision_and_session_substitution(
    gate_events: dict[str, TraceEvent], mutation: str
) -> None:
    event = gate_events["permission"]
    lineage: dict[str, Any] = deepcopy(event.lineage)
    if mutation == "allowed_bool":
        lineage["allowed"] = 1
    elif mutation == "candidate_order":
        lineage["candidate_refs"] = list(reversed(lineage["candidate_refs"]))
    elif mutation == "candidate_set_root":
        lineage["candidate_set_root"] = _root("forged:candidate-set")
    elif mutation == "claim_order":
        claims = sorted(
            (_root("claim:a"), _root("claim:z")),
            key=lambda item: item.encode("utf-8"),
            reverse=True,
        )
        lineage["claim_roots"] = claims
    elif mutation == "claims_root":
        lineage["claims_root"] = _root("forged:claims")
    else:
        session = lineage["session_binding"]
        assert isinstance(session, dict)
        session["action_refs"] = []
    tampered = TraceEvent(
        event_type=event.event_type,
        protocol_id=event.protocol_id,
        target=event.target,
        reason=event.reason,
        lineage=lineage,
    )
    with pytest.raises((TypeError, ValueError)):
        InMemoryTraceStore().append(tampered)


def test_real_gate_events_are_accepted_by_independent_trace_validation(
    gate_events: dict[str, TraceEvent],
) -> None:
    store = InMemoryTraceStore()
    records = tuple(store.append(gate_events[kind]) for kind in ("stop", "permission"))
    assert tuple(record.sequence for record in records) == (0, 1)
