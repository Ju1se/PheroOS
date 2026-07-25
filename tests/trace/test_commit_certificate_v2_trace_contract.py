from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
import pytest

from tests.governance._commit_certificate_v2_decision_support import (
    sealed_certified_decision,
)
from tests.governance._commit_certificate_v2_store_support import (
    _root,
    certified_context,
)
from tests.governance.test_commit_certificate_v2_operations import (
    _commit_certificate,
    _prepared_certificate,
)

from pheroos.governance.authority_store_v2 import GovernanceCommitDispositionV2
from pheroos.trace import InMemoryTraceStore, TraceEvent
from pheroos.trace.schema import trace_schema


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "pheroos/trace/_contracts/commit_certificate_authority.py"


@pytest.fixture(scope="module")
def certificate_event() -> TraceEvent:
    context = certified_context("scope:certificate-v2:trace")
    decision_state, _ = sealed_certified_decision(
        context, _root("claim:certificate:trace")
    )
    request, source = _prepared_certificate(
        context,
        decision_state,
        mutation_ref="mutation:certificate:trace",
    )
    attempt, _ = _commit_certificate(context, request, source)
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert attempt.committed_transition is not None
    return attempt.committed_transition.batch.trace_batch.events[0]


def _mutated(event: TraceEvent, mutation: str) -> TraceEvent:
    lineage = deepcopy(event.lineage)
    if not (
        _mutate_roots(lineage, mutation)
        or _mutate_leaves(lineage, mutation)
        or _mutate_values(lineage, mutation)
        or _mutate_collections(lineage, mutation)
    ):  # pragma: no cover - closed test mutation declaration
        raise AssertionError(mutation)
    return TraceEvent(
        event_type=event.event_type,
        protocol_id=event.protocol_id,
        target=event.target,
        reason=event.reason,
        lineage=lineage,
    )


def _payload(event: TraceEvent) -> dict[str, object]:
    return {
        "event_type": event.event_type,
        "protocol_id": event.protocol_id,
        "target": event.target,
        "reason": event.reason,
        "lineage": deepcopy(event.lineage),
    }


def _mutate_roots(lineage: dict[str, object], mutation: str) -> bool:
    replacements = {
        "stream_ref": (
            "stream_ref",
            "authority:commit-certificate-v2:" + "0" * 64,
        ),
        "transition_id": (
            "transition_id",
            "transition:commit-certificate-v2:" + "0" * 64,
        ),
        "request_root": ("request_root", _root("trace:forged:request")),
        "source_context_root": (
            "source_context_root",
            _root("trace:forged:source"),
        ),
        "read_set_root": ("read_set_root", _root("trace:forged:read-set")),
        "leaf_set_root": (
            "authority_leaf_set_root",
            _root("trace:forged:leaf-set"),
        ),
    }
    selected = replacements.get(mutation)
    if selected is None:
        return False
    field, replacement = selected
    lineage[field] = replacement
    return True


def _mutate_leaves(lineage: dict[str, object], mutation: str) -> bool:
    if mutation not in {"leaf_missing", "leaf_head", "leaf_root", "leaf_role"}:
        return False
    leaves = cast(list[dict[str, object]], lineage["authority_leaves"])
    if mutation == "leaf_missing":
        lineage["authority_leaves"] = leaves[:-1]
    elif mutation == "leaf_head":
        leaves[0]["head_root"] = _root("trace:forged:leaf-head")
    elif mutation == "leaf_root":
        leaves[0]["leaf_root"] = _root("trace:forged:leaf-root")
    else:
        leaves[0]["role"] = "risk"
    return True


def _mutate_values(lineage: dict[str, object], mutation: str) -> bool:
    replacements = {
        "boolean_revision": ("decision_revision", True),
        "profile": ("profile", "pheroos-commit-integrity-v1"),
        "status": ("status", "conflict"),
        "issuer": ("mutation_issuer_ref", "issuer:forged"),
        "overbyte": ("candidate_ref", "界" * 4_097),
        "unknown": ("portable_authority", True),
    }
    selected = replacements.get(mutation)
    if selected is not None:
        field, replacement = selected
        lineage[field] = replacement
        return True
    if mutation == "seal_revision":
        decision_revision = cast(int, lineage["decision_revision"])
        lineage["seal_revision"] = decision_revision + 1
        return True
    if mutation == "missing":
        del lineage["seal_inclusion_root"]
        return True
    return False


def _mutate_collections(lineage: dict[str, object], mutation: str) -> bool:
    if mutation == "session_action":
        session = cast(dict[str, object], lineage["session_binding"])
        session["action_refs"] = ["commit"]
        return True
    selected = {
        "attestation_duplicate": "attestation_refs",
        "reason_duplicate": "reason_codes",
    }.get(mutation)
    if selected is None:
        return False
    values = cast(list[object], lineage[selected])
    lineage[selected] = [values[0], values[0]]
    return True


@pytest.mark.parametrize(
    "mutation",
    (
        "stream_ref",
        "transition_id",
        "request_root",
        "source_context_root",
        "read_set_root",
        "leaf_missing",
        "leaf_head",
        "leaf_root",
        "leaf_role",
        "leaf_set_root",
        "seal_revision",
        "boolean_revision",
        "profile",
        "status",
        "issuer",
        "session_action",
        "attestation_duplicate",
        "reason_duplicate",
        "overbyte",
        "unknown",
        "missing",
    ),
)
def test_trace_rejects_each_detached_lineage_substitution(
    certificate_event: TraceEvent,
    mutation: str,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        InMemoryTraceStore().append(_mutated(certificate_event, mutation))


def test_trace_event_type_cannot_relabel_verified_truth_as_conflict(
    certificate_event: TraceEvent,
) -> None:
    relabeled = TraceEvent(
        event_type="commit_certificate_conflict_v2",
        protocol_id=certificate_event.protocol_id,
        target=certificate_event.target,
        reason=certificate_event.reason,
        lineage=certificate_event.lineage,
    )
    with pytest.raises(ValueError, match="conflict trace"):
        InMemoryTraceStore().append(relabeled)


def test_real_certificate_event_is_accepted_by_independent_trace_validation(
    certificate_event: TraceEvent,
) -> None:
    record = InMemoryTraceStore().append(certificate_event)
    assert record.sequence == 0
    assert record.event.event_type == "commit_certificate_verified_v2"


def test_real_certificate_event_is_accepted_by_closed_trace_schema(
    certificate_event: TraceEvent,
) -> None:
    Draft202012Validator(trace_schema()).validate(_payload(certificate_event))


@pytest.mark.parametrize(
    "mutation",
    ("boolean_revision", "leaf_role", "overbyte", "unknown"),
)
def test_trace_schema_rejects_certificate_lineage_shape_mutations(
    certificate_event: TraceEvent,
    mutation: str,
) -> None:
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(
            _payload(_mutated(certificate_event, mutation))
        )


def test_trace_schema_rejects_verified_certificate_relabelled_as_conflict(
    certificate_event: TraceEvent,
) -> None:
    payload = _payload(certificate_event)
    payload["event_type"] = "commit_certificate_conflict_v2"
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)


def test_trace_contract_is_independent_and_below_structure_limit() -> None:
    source = CONTRACT.read_text(encoding="utf-8")
    assert "pheroos.governance" not in source
    assert "tests." not in source
    assert len(source.splitlines()) < 600
