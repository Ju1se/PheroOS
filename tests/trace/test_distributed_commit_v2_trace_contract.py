from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
import pytest

from tests.governance._commit_certificate_v2_store_support import (
    _capability,
    _root,
    certified_inputs,
)
from tests.governance._distributed_v2_store_support import (
    ASSURANCE,
    PROFILE,
    distributed_context,
)

from pheroos.governance._authority_session_v2.contracts import (
    _governance_authority_session_state_v2,
)
from pheroos.governance._authority_session_v2.operations import (
    _read_set,
    _session_binding,
    _session_domain,
    _session_grant_precondition,
    _session_lifecycle_precondition,
)
from pheroos.governance._distributed_v2.events import _distributed_event_v2
from pheroos.governance._distributed_v2.operations import (
    _load_dependency_heads,
    _load_parent,
)
from pheroos.governance.authority_store_v2 import GovernanceCommitAttemptV2
from pheroos.governance.authority_store_v2 import GovernanceHeadV2
from pheroos.protocol.authority_v2 import GovernanceReadPreconditionV2
from pheroos.governance.distributed_commit_v2 import (
    open_distributed_authority_session_v2,
    prepare_distributed_epoch_v2,
)
from pheroos.trace import InMemoryTraceStore, TraceEvent
from pheroos.trace._contracts.distributed_authority import (
    DISTRIBUTED_AUTHORITY_TRACE_EVENT_CONTRACTS,
)
from pheroos.trace.schema import trace_schema


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "pheroos/trace/_contracts/distributed_authority.py"
SUPPORT = ROOT / "pheroos/trace/_contracts/distributed_authority_support.py"


@pytest.fixture(scope="module")
def distributed_epoch_event() -> TraceEvent:
    context = distributed_context("scope:distributed-v2:trace")
    inputs = certified_inputs(
        context,
        _root("claim:distributed:trace"),
        profile=PROFILE,
        assurance=ASSURANCE,
    )
    request, _ = prepare_distributed_epoch_v2(
        membership_state=inputs.membership,
        manifest=context.manifest,
        transition_certificate_ref="certificate:distributed:trace:epoch",
        mutation_ref="mutation:distributed:trace:epoch",
        mutation_issuer_ref=context.grant.issuer_ref,
        current_step=10,
        provenance_ref="urn:test:distributed:trace:epoch",
        source_trace_roots=(_root("trace:distributed:trace:epoch"),),
    )
    session = open_distributed_authority_session_v2(
        _capability(context, request.observed_epoch), request
    )
    state = _governance_authority_session_state_v2(session)
    domain = _session_domain(state)
    parent = _load_parent(context.store, domain, request)
    dependencies = _load_dependency_heads(context.store, domain, request)
    assert not isinstance(parent, GovernanceCommitAttemptV2)
    assert not isinstance(dependencies, GovernanceCommitAttemptV2)
    _, parent_head = parent
    observed: tuple[GovernanceHeadV2 | GovernanceReadPreconditionV2, ...] = (
        parent_head,
        *dependencies,
        _session_grant_precondition(state),
        _session_lifecycle_precondition(state),
    )
    return _distributed_event_v2(
        request,
        _session_binding(state),
        parent_head_root=parent_head.head_root,
        read_set_root=_read_set(observed).root(),
    )


def _contract(event: TraceEvent):
    return next(
        item
        for item in DISTRIBUTED_AUTHORITY_TRACE_EVENT_CONTRACTS
        if item.event_type == event.event_type
    )


def _payload(event: TraceEvent) -> dict[str, object]:
    return {
        "event_type": event.event_type,
        "protocol_id": event.protocol_id,
        "target": event.target,
        "reason": event.reason,
        "lineage": deepcopy(event.lineage),
    }


def _mutated(event: TraceEvent, mutation: str) -> TraceEvent:
    lineage = deepcopy(event.lineage)
    _mutate_distributed_lineage(lineage, mutation)
    return TraceEvent(
        event_type=event.event_type,
        protocol_id=event.protocol_id,
        target=event.target,
        reason=event.reason,
        lineage=lineage,
    )


def _mutate_distributed_lineage(
    lineage: dict[str, object],
    mutation: str,
) -> None:
    simple_replacements: dict[str, tuple[str, object]] = {
        "unknown": ("portable_authority", True),
        "boolean_revision": ("revision", True),
        "lane": ("lane", "proposal"),
        "mutation_kind": ("mutation_kind", "epoch_transitioned"),
        "status": ("status", "frozen"),
        "stream_ref": ("stream_ref", "authority:distributed-epoch-v2:" + "0" * 64),
        "transition_id": ("transition_id", "transition:distributed-v2:" + "0" * 64),
        "request_root": ("request_root", _root("trace:forged:request")),
        "dependency_set_root": (
            "dependency_set_root",
            _root("trace:forged:dependency-set"),
        ),
        "lane_state_root": ("lane_state_root", _root("trace:forged:lane-state")),
        "source_context_root": (
            "source_context_root",
            _root("trace:forged:source"),
        ),
        "snapshot_state_root": (
            "snapshot_state_root",
            _root("trace:forged:snapshot-state"),
        ),
        "history_root": ("history_root", _root("trace:forged:history")),
        "snapshot_root": ("snapshot_root", _root("trace:forged:snapshot")),
        "read_set_root": ("read_set_root", _root("trace:forged:read-set")),
    }
    if mutation in simple_replacements:
        key, value = simple_replacements[mutation]
        lineage[key] = value
    elif mutation == "missing":
        del lineage["snapshot_root"]
    elif mutation == "session_action":
        binding = cast(dict[str, object], lineage["session_binding"])
        binding["action_refs"] = []
    elif mutation == "reason_duplicate":
        reason = cast(list[object], lineage["reason_codes"])[0]
        lineage["reason_codes"] = [reason, reason]
    elif mutation == "dependency_head":
        dependencies = cast(list[dict[str, object]], lineage["dependencies"])
        dependencies[0]["head_root"] = _root("trace:forged:dependency-head")
    elif mutation == "dependency_root":
        dependencies = cast(list[dict[str, object]], lineage["dependencies"])
        dependencies[0]["dependency_root"] = _root("trace:forged:dependency")
    elif mutation == "dependency_role":
        dependencies = cast(list[dict[str, object]], lineage["dependencies"])
        dependencies[0]["role"] = dependencies[1]["role"]
    elif mutation == "lane_material":
        material = cast(dict[str, object], lineage["lane_state_material"])
        material["transition_certificate_root"] = _root("trace:forged:epoch")
    else:
        raise AssertionError(mutation)


def test_real_prepared_store_event_passes_independent_closed_contract(
    distributed_epoch_event: TraceEvent,
) -> None:
    contract = _contract(distributed_epoch_event)
    assert contract.required_fields == frozenset(distributed_epoch_event.lineage)
    contract.validator(distributed_epoch_event)
    assert InMemoryTraceStore().append(distributed_epoch_event).sequence == 0


def test_real_prepared_store_event_passes_closed_trace_schema(
    distributed_epoch_event: TraceEvent,
) -> None:
    Draft202012Validator(trace_schema()).validate(_payload(distributed_epoch_event))


@pytest.mark.parametrize(
    "mutation",
    (
        "unknown",
        "missing",
        "boolean_revision",
        "lane",
        "mutation_kind",
        "status",
        "session_action",
        "reason_duplicate",
        "dependency_head",
        "dependency_root",
        "dependency_role",
        "lane_material",
        "stream_ref",
        "transition_id",
        "request_root",
        "dependency_set_root",
        "lane_state_root",
        "source_context_root",
        "snapshot_state_root",
        "history_root",
        "snapshot_root",
        "read_set_root",
    ),
)
def test_independent_contract_rejects_each_detached_substitution(
    distributed_epoch_event: TraceEvent,
    mutation: str,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        _contract(distributed_epoch_event).validator(
            _mutated(distributed_epoch_event, mutation)
        )


def test_event_type_cannot_relabel_epoch_truth_as_other_lane(
    distributed_epoch_event: TraceEvent,
) -> None:
    relabeled = TraceEvent(
        event_type="distributed_proposal_advanced_v2",
        protocol_id=distributed_epoch_event.protocol_id,
        target=distributed_epoch_event.target,
        reason=distributed_epoch_event.reason,
        lineage=distributed_epoch_event.lineage,
    )
    with pytest.raises(ValueError, match="event lane"):
        _contract(relabeled).validator(relabeled)


@pytest.mark.parametrize(
    ("value", "error"),
    [
        (1, "lane must be canonical text"),
        ("x" * 4_097, "lane exceeds its bound"),
    ],
)
def test_distributed_bounded_text_remains_fail_closed(
    distributed_epoch_event: TraceEvent,
    value: object,
    error: str,
) -> None:
    lineage = deepcopy(distributed_epoch_event.lineage)
    lineage["lane"] = value
    malformed = TraceEvent(
        event_type=distributed_epoch_event.event_type,
        protocol_id=distributed_epoch_event.protocol_id,
        target=distributed_epoch_event.target,
        reason=distributed_epoch_event.reason,
        lineage=lineage,
    )

    with pytest.raises(ValueError, match=error):
        _contract(malformed).validator(malformed)


@pytest.mark.parametrize(
    "mutation",
    (
        "unknown",
        "boolean_revision",
        "lane",
        "mutation_kind",
        "status",
        "session_action",
        "reason_duplicate",
        "dependency_role",
    ),
)
def test_closed_trace_schema_rejects_distributed_shape_mutations(
    distributed_epoch_event: TraceEvent,
    mutation: str,
) -> None:
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(
            _payload(_mutated(distributed_epoch_event, mutation))
        )


def test_closed_trace_schema_rejects_epoch_truth_relabelled_as_proposal(
    distributed_epoch_event: TraceEvent,
) -> None:
    payload = _payload(distributed_epoch_event)
    payload["event_type"] = "distributed_proposal_advanced_v2"
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)


def test_trace_contract_is_independent_closed_and_below_structure_limit() -> None:
    for path in (CONTRACT, SUPPORT):
        source = path.read_text(encoding="utf-8")
        assert "pheroos.governance" not in source
        assert "tests." not in source
        assert len(source.splitlines()) < 600
