from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, cast

import pytest

import pheroos.trace._contracts.commit_certificate_authority as certificate_contract
import pheroos.trace._contracts.commit_decision_authority as decision_contract
import pheroos.trace._contracts.commit_evidence_authority as evidence_contract
import pheroos.trace._contracts.commit_gate_authority as gate_contract
import pheroos.trace._contracts.distributed_authority as distributed_contract
import pheroos.trace._contracts.distributed_authority_support as distributed_support
from pheroos.trace import TraceEvent
from pheroos.trace._contracts.authority import (
    _authority_stream_ref,
    _require_text_value,
)
from pheroos.trace._contracts.base import TraceEventContract, contract_map
from tests.trace.test_commit_certificate_v2_trace_contract import (
    certificate_event as certificate_event_fixture,
)
from tests.trace.test_commit_decision_v2_trace_contract import (
    _event_variant as decision_event_variant,
)
from tests.trace.test_commit_decision_v2_trace_contract import (
    initialized_event as initialized_event_fixture,
)
from tests.trace.test_commit_evidence_v2_trace_contract import (
    evidence_event as evidence_event_fixture,
)
from tests.trace.test_distributed_commit_v2_trace_contract import (
    distributed_epoch_event as distributed_epoch_event_fixture,
)
from tests.trace.test_trace_store import valid_event_context, valid_lineage


ROOT_A = "sha256:" + "a" * 64
ROOT_B = "sha256:" + "b" * 64
TRANSITION_A = "transition:test:" + "a" * 64


def _fixture_value(factory: Any) -> Any:
    return factory.__wrapped__()


@pytest.fixture(scope="module")
def certificate_event() -> TraceEvent:
    return cast(TraceEvent, _fixture_value(certificate_event_fixture))


@pytest.fixture(scope="module")
def initialized_event() -> TraceEvent:
    return cast(TraceEvent, _fixture_value(initialized_event_fixture))


@pytest.fixture(scope="module")
def evidence_event() -> TraceEvent:
    return cast(TraceEvent, _fixture_value(evidence_event_fixture))


@pytest.fixture(scope="module")
def distributed_epoch_event() -> TraceEvent:
    return cast(TraceEvent, _fixture_value(distributed_epoch_event_fixture))


def _event(
    event_type: str,
    lineage: dict[str, object],
    *,
    target: str | None = None,
    protocol_id: str | None = None,
) -> TraceEvent:
    expected_protocol, expected_target = valid_event_context(event_type)
    return TraceEvent(
        event_type=event_type,
        protocol_id=expected_protocol if protocol_id is None else protocol_id,
        target=expected_target if target is None else target,
        reason="authority totality",
        lineage=lineage,
    )


def _clone_event(
    event: TraceEvent,
    *,
    event_type: str | None = None,
    target: str | None = None,
    lineage: dict[str, object] | None = None,
) -> TraceEvent:
    return TraceEvent(
        event_type=event.event_type if event_type is None else event_type,
        protocol_id=event.protocol_id,
        target=event.target if target is None else target,
        reason=event.reason,
        lineage=deepcopy(event.lineage) if lineage is None else lineage,
    )


def _validate(event: TraceEvent) -> None:
    event.validate()


@pytest.mark.parametrize(
    ("kwargs", "error", "message"),
    (
        (
            {
                "event_type": "",
                "required_fields": frozenset(),
                "validator": _validate,
                "authority_relevant": False,
                "schema_condition": False,
            },
            ValueError,
            "type must be non-empty",
        ),
        (
            {
                "event_type": "x",
                "required_fields": cast(Any, {"field"}),
                "validator": _validate,
                "authority_relevant": False,
                "schema_condition": True,
            },
            TypeError,
            "fields must be a frozenset",
        ),
        (
            {
                "event_type": "x",
                "required_fields": frozenset({""}),
                "validator": _validate,
                "authority_relevant": False,
                "schema_condition": True,
            },
            TypeError,
            "fields must be a frozenset",
        ),
        (
            {
                "event_type": "x",
                "required_fields": frozenset(),
                "validator": cast(Any, None),
                "authority_relevant": False,
                "schema_condition": False,
            },
            TypeError,
            "exactly one validator",
        ),
        (
            {
                "event_type": "x",
                "required_fields": frozenset({"field"}),
                "validator": _validate,
                "authority_relevant": True,
                "schema_condition": False,
            },
            ValueError,
            "require a schema condition",
        ),
    ),
)
def test_trace_event_contract_rejects_invalid_static_declarations(
    kwargs: dict[str, object],
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        TraceEventContract(**cast(Any, kwargs))


def test_contract_map_rejects_duplicate_static_event_types() -> None:
    contract = TraceEventContract(
        event_type="duplicate",
        required_fields=frozenset(),
        validator=_validate,
        authority_relevant=False,
        schema_condition=False,
    )

    with pytest.raises(RuntimeError, match="duplicate static trace event contract"):
        contract_map((contract, contract))


class _LineageDictionary(dict[str, object]):
    pass


def test_authority_envelope_requires_an_exact_dictionary() -> None:
    lineage = _LineageDictionary(valid_lineage("signal_verified"))
    event = _event("signal_verified", lineage)

    with pytest.raises(ValueError, match="exact object"):
        event.validate()


def test_authority_text_rejects_unencodable_unicode() -> None:
    with pytest.raises(ValueError, match="encode as UTF-8"):
        _require_text_value("signal_verified", "signal_ref", "\ud800")


def test_authority_stream_rejects_ambiguous_nul_bindings() -> None:
    with pytest.raises(ValueError, match="U\\+0000"):
        _authority_stream_ref("signal", ("scope:test", "signal:\x00test"))


@pytest.mark.parametrize(
    ("event_type", "mutation", "message"),
    (
        ("signal_verified", "stream", "stream_ref is not canonical"),
        ("signal_verified", "target", "target must match"),
        ("domain_retired", "target", "target must match"),
        ("issuer_grant_activated", "profile", "profile is unsupported"),
        ("issuer_grant_activated", "target", "target must match"),
        ("hybrid_replay_advanced", "request", "request_ref must match"),
        ("commit_replay_advanced", "revision", "revision must be positive"),
        ("commit_replay_advanced", "target", "target must match"),
        ("commit_replay_advanced", "request", "request_ref must match"),
    ),
)
def test_authority_bindings_fail_at_their_declared_semantic_boundary(
    event_type: str,
    mutation: str,
    message: str,
) -> None:
    lineage = deepcopy(valid_lineage(event_type))
    target: str | None = None
    if mutation == "stream":
        lineage["stream_ref"] = "authority:forged"
    elif mutation == "target":
        target = "target:forged"
    elif mutation == "profile":
        lineage["profile"] = "pheroos-unsupported"
    elif mutation == "revision":
        lineage["revision"] = 0
    else:
        lineage["request_ref"] = "request:other"
        binding = cast(dict[str, object], lineage["session_binding"])
        binding["request_ref"] = "request:other"

    with pytest.raises(ValueError, match=message):
        _event(event_type, lineage, target=target).validate()


def _hybrid_successor(*, parent_transition: object) -> TraceEvent:
    lineage = deepcopy(valid_lineage("hybrid_replay_advanced"))
    lineage["revision"] = 2
    lineage["parent_transition_id"] = parent_transition
    lineage["parent_snapshot_root"] = ROOT_A
    return _event("hybrid_replay_advanced", lineage)


def _commit_replay_successor(*, parent_transition: str) -> TraceEvent:
    lineage = deepcopy(valid_lineage("commit_replay_advanced"))
    lineage["revision"] = 2
    lineage["parent_transition_id"] = parent_transition
    return _event("commit_replay_advanced", lineage)


@pytest.mark.parametrize(
    ("event", "message"),
    (
        (
            _hybrid_successor(parent_transition="transition:hybrid-replay-v2:bad"),
            "parent_transition_id is not canonical",
        ),
        (
            _hybrid_successor(
                parent_transition="transition:hybrid-replay-v2:" + "a" * 64
            ),
            "",
        ),
        (
            _commit_replay_successor(
                parent_transition="transition:commit-replay-v2:bad"
            ),
            "parent_transition_id is not canonical",
        ),
        (
            _commit_replay_successor(
                parent_transition="transition:commit-replay-v2:" + "a" * 64
            ),
            "",
        ),
    ),
)
def test_replay_successor_parent_contract_is_total(
    event: TraceEvent,
    message: str,
) -> None:
    if message:
        with pytest.raises(ValueError, match=message):
            event.validate()
    else:
        event.validate()


@pytest.mark.parametrize(
    ("event_type", "field", "value", "message"),
    (
        ("risk_state_advanced", "revision", 0, "revision must be positive"),
        ("risk_state_advanced", "observed_epoch", 2, "epoch must match"),
        ("risk_state_advanced", "parent_epoch", 0, "genesis parent epoch"),
        ("risk_state_advanced", "parent_transition_id", "parent:bad", "genesis parent"),
        ("risk_state_advanced", "parent_snapshot_root", ROOT_A, "genesis parent root"),
        (
            "risk_assessed_v2",
            "window_reset_required",
            1,
            "window_reset_required must be an exact bool",
        ),
        (
            "risk_assessed_v2",
            "risk_input_roots",
            ["sha256:bad"],
            "contains an invalid root",
        ),
        ("risk_assessed_v2", "rationale_codes", [], "count is invalid"),
        (
            "risk_assessed_v2",
            "rationale_codes",
            [cast(Any, 1)],
            "contains invalid text",
        ),
    ),
)
def test_durable_risk_contract_rejects_each_exact_semantic_violation(
    event_type: str,
    field: str,
    value: object,
    message: str,
) -> None:
    lineage = deepcopy(valid_lineage(event_type))
    lineage[field] = value
    if field == "observed_epoch":
        binding = cast(dict[str, object], lineage["session_binding"])
        binding["observed_epoch"] = value

    with pytest.raises(ValueError, match=message):
        _event(event_type, lineage).validate()


def test_durable_risk_rejects_target_and_advance_substitution() -> None:
    target_lineage = deepcopy(valid_lineage("risk_state_advanced"))
    with pytest.raises(ValueError, match="target must match"):
        _event("risk_state_advanced", target_lineage, target="target:forged").validate()

    request_lineage = deepcopy(valid_lineage("risk_state_advanced"))
    request_lineage["request_ref"] = "advance:forged"
    binding = cast(dict[str, object], request_lineage["session_binding"])
    binding["request_ref"] = "advance:forged"
    with pytest.raises(ValueError, match="request_ref must match"):
        _event("risk_state_advanced", request_lineage).validate()


def _risk_successor(
    event_type: str,
    *,
    epoch: int = 1,
    parent_epoch: object = 1,
    parent_transition: str | None = None,
    reset: bool = False,
) -> TraceEvent:
    lineage = deepcopy(valid_lineage(event_type))
    lineage.update(
        {
            "revision": 2,
            "epoch": epoch,
            "parent_epoch": parent_epoch,
            "parent_transition_id": (
                "transition:risk-v2:" + "a" * 64
                if parent_transition is None
                else parent_transition
            ),
            "observed_epoch": epoch,
        }
    )
    binding = cast(dict[str, object], lineage["session_binding"])
    binding["observed_epoch"] = epoch
    if event_type == "risk_assessed_v2":
        lineage["previous_assessment_root"] = ROOT_A
        lineage["window_reset_required"] = reset
    return _event(event_type, lineage)


def test_durable_risk_successor_accepts_canonical_parent() -> None:
    _risk_successor("risk_state_advanced").validate()
    _risk_successor("risk_assessed_v2").validate()


@pytest.mark.parametrize(
    ("event", "message"),
    (
        (
            _risk_successor("risk_state_advanced", epoch=1, parent_epoch=2),
            "epoch cannot move backwards",
        ),
        (
            _risk_successor(
                "risk_state_advanced",
                parent_transition="transition:risk-v2:bad",
            ),
            "parent_transition_id is not canonical",
        ),
        (
            _risk_successor(
                "risk_assessed_v2",
                epoch=2,
                parent_epoch=1,
                reset=False,
            ),
            "epoch change requires window reset",
        ),
    ),
)
def test_durable_risk_successor_rejects_invalid_parent_semantics(
    event: TraceEvent,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        event.validate()


@pytest.mark.parametrize(
    ("event_type", "field", "value", "message"),
    (
        (
            "principal_verification_set_advanced",
            "record_count",
            4097,
            "record_count exceeds",
        ),
        (
            "principal_verification_set_advanced",
            "expires_at_step",
            2,
            "verification set is not fresh",
        ),
        (
            "membership_epoch_committed",
            "expires_at_step",
            2,
            "membership is not fresh",
        ),
        (
            "membership_epoch_committed",
            "revision",
            0,
            "revision must be positive",
        ),
        (
            "membership_epoch_committed",
            "profile",
            "pheroos-certified-commit-v1",
            "profile and assurance",
        ),
        (
            "membership_epoch_committed",
            "parent_transition_id",
            "parent:bad",
            "genesis parent is invalid",
        ),
        (
            "membership_epoch_committed",
            "parent_snapshot_root",
            ROOT_A,
            "genesis parent root",
        ),
        (
            "membership_epoch_committed",
            "cluster_count",
            1025,
            "cluster_count exceeds",
        ),
        (
            "membership_epoch_committed",
            "principal_count",
            4097,
            "principal_count exceeds",
        ),
    ),
)
def test_membership_contract_rejects_declared_resource_and_parent_violations(
    event_type: str,
    field: str,
    value: object,
    message: str,
) -> None:
    lineage = deepcopy(valid_lineage(event_type))
    lineage[field] = value

    with pytest.raises(ValueError, match=message):
        _event(event_type, lineage).validate()


def test_membership_contract_rejects_target_substitution() -> None:
    lineage = deepcopy(valid_lineage("membership_epoch_committed"))

    with pytest.raises(ValueError, match="target must match"):
        _event(
            "membership_epoch_committed",
            lineage,
            target="target:forged",
        ).validate()


def test_membership_successor_rejects_noncanonical_parent_transition() -> None:
    lineage = deepcopy(valid_lineage("membership_epoch_committed"))
    lineage.update(
        {
            "revision": 2,
            "parent_revision": 1,
            "epoch": 2,
            "parent_epoch": 1,
            "parent_transition_id": "transition:membership-v2:bad",
        }
    )

    with pytest.raises(ValueError, match="parent_transition_id is not canonical"):
        _event("membership_epoch_committed", lineage).validate()


def test_membership_root_lists_reject_duplicate_roots() -> None:
    lineage = deepcopy(valid_lineage("membership_epoch_committed"))
    root = cast(list[str], lineage["source_trace_roots"])[0]
    lineage["source_trace_roots"] = [root, root]

    with pytest.raises(ValueError, match="source_trace_roots count is invalid"):
        _event("membership_epoch_committed", lineage).validate()


@pytest.mark.parametrize(
    ("event_type", "field", "value", "message"),
    (
        ("support_state_advanced", "revision", 0, "revision is invalid"),
        (
            "support_state_advanced",
            "transition_id",
            "transition:support-v2:" + "0" * 64,
            "transition_id is not canonical",
        ),
        (
            "support_state_advanced",
            "parent_snapshot_root",
            ROOT_A,
            "genesis parent is invalid",
        ),
        (
            "support_lease_issued_v2",
            "membership_transition_id",
            "transition:membership-v2:bad",
            "membership transition is not canonical",
        ),
        (
            "support_lease_revoked_v2",
            "reason_codes",
            ["reason:z", "reason:a"],
            "reason_codes is not canonical",
        ),
    ),
)
def test_support_contract_rejects_static_identity_and_collection_violations(
    event_type: str,
    field: str,
    value: object,
    message: str,
) -> None:
    lineage = deepcopy(valid_lineage(event_type))
    lineage[field] = value

    with pytest.raises(ValueError, match=message):
        _event(event_type, lineage).validate()


def test_support_contract_rejects_target_substitution() -> None:
    lineage = deepcopy(valid_lineage("support_state_advanced"))

    with pytest.raises(ValueError, match="target must match"):
        _event("support_state_advanced", lineage, target="target:forged").validate()


def test_support_state_successor_cannot_reinitialize() -> None:
    from tests.trace.test_support_v2_trace_contract import _state_for_kind

    payload = _state_for_kind("issue")
    lineage = cast(dict[str, object], payload["lineage"])
    lineage["mutation_kind"] = "initialize"

    with pytest.raises(ValueError, match="parent lineage is invalid"):
        TraceEvent(**cast(Any, payload)).validate()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (("evicted_lease_roots", [ROOT_A], "initialization cannot evict"),),
)
def test_support_state_rejects_incomplete_or_forbidden_genesis_mutation(
    field: str,
    value: object,
    message: str,
) -> None:
    lineage = deepcopy(valid_lineage("support_state_advanced"))
    lineage[field] = value

    with pytest.raises(ValueError, match=message):
        _event("support_state_advanced", lineage).validate()


def test_support_state_rejects_incomplete_issue_projection() -> None:
    from tests.trace.test_support_v2_trace_contract import _state_for_kind

    payload = _state_for_kind("issue")
    lineage = cast(dict[str, object], payload["lineage"])
    lineage["issued_lease_root"] = ""

    with pytest.raises(ValueError, match="mutation delta is incomplete"):
        TraceEvent(**cast(Any, payload)).validate()


@pytest.mark.parametrize(
    ("kind", "root_field", "message"),
    (
        ("revoke", "revoked_lease_root", "revoked lease is also evicted"),
        ("issue", "issued_lease_root", "issued lease is also evicted"),
    ),
)
def test_support_state_rejects_a_lease_that_is_also_evicted(
    kind: str,
    root_field: str,
    message: str,
) -> None:
    from tests.trace.test_support_v2_trace_contract import _state_for_kind

    payload = _state_for_kind(kind)
    lineage = cast(dict[str, object], payload["lineage"])
    lineage["evicted_lease_roots"] = [lineage[root_field]]

    with pytest.raises(ValueError, match=message):
        TraceEvent(**cast(Any, payload)).validate()


def test_support_optional_membership_binding_rejects_falsy_partial_shape() -> None:
    lineage = deepcopy(valid_lineage("support_state_advanced"))
    lineage["membership_stream_ref"] = 0

    with pytest.raises(ValueError, match="membership binding is invalid"):
        _event("support_state_advanced", lineage).validate()


def _certificate_recommit_leaves(lineage: dict[str, object]) -> None:
    leaves = cast(list[dict[str, object]], lineage["authority_leaves"])
    for leaf in leaves:
        body = {
            key: leaf[key]
            for key in certificate_contract._LEAF_FIELDS
            if key != "leaf_root"
        }
        leaf["leaf_root"] = certificate_contract._root("authority-leaf", body)
    lineage["authority_leaf_set_root"] = certificate_contract._root(
        "authority-leaf-set",
        {
            "leaves": [
                {"role": leaf["role"], "leaf_root": leaf["leaf_root"]}
                for leaf in leaves
            ]
        },
    )


def _certificate_successor(event: TraceEvent, *, parent_transition: str) -> TraceEvent:
    lineage = deepcopy(event.lineage)
    lineage.update(
        {
            "revision": 2,
            "parent_revision": 1,
            "history_count": 2,
            "parent_transition_id": parent_transition,
            "parent_snapshot_root": ROOT_A,
        }
    )
    lineage["source_context_root"] = certificate_contract._root(
        "source-context",
        {
            "request_root": lineage["request_root"],
            "manifest_root": lineage["manifest_root"],
            "decision_snapshot_root": lineage["decision_snapshot_root"],
            "decision_head_root": lineage["decision_head_root"],
            "seal_inclusion_root": lineage["seal_inclusion_root"],
            "parent_snapshot_root": lineage["parent_snapshot_root"],
        },
    )
    leaves = cast(list[dict[str, object]], lineage["authority_leaves"])
    lineage["read_set_root"] = certificate_contract._read_set_root(lineage, leaves)
    return _clone_event(event, lineage=lineage)


def test_certificate_contract_accepts_conflict_and_successor_shapes(
    certificate_event: TraceEvent,
) -> None:
    conflict = _clone_event(
        certificate_event,
        event_type="commit_certificate_conflict_v2",
    )
    conflict.lineage["mutation_kind"] = "conflict"
    conflict.lineage["status"] = "conflict"
    conflict.validate()

    successor = _certificate_successor(
        certificate_event,
        parent_transition="transition:commit-certificate-v2:" + "a" * 64,
    )
    successor.validate()


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("target", "target is mismatched"),
        ("genesis_parent", "genesis parent is invalid"),
        ("successor_parent", "parent is invalid"),
    ),
)
def test_certificate_parent_and_target_bindings_fail_closed(
    certificate_event: TraceEvent,
    mutation: str,
    message: str,
) -> None:
    if mutation == "target":
        event = _clone_event(certificate_event, target="target:forged")
    elif mutation == "genesis_parent":
        lineage = deepcopy(certificate_event.lineage)
        lineage["parent_transition_id"] = "parent:forged"
        event = _clone_event(certificate_event, lineage=lineage)
    else:
        event = _certificate_successor(
            certificate_event,
            parent_transition="transition:commit-certificate-v2:bad",
        )

    with pytest.raises(ValueError, match=message):
        event.validate()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("schema", "schema:forged", "leaf version is invalid"),
        ("revision", 0, "leaf revision is invalid"),
        ("revision", True, "authority_leaves.revision is invalid"),
        ("stream_ref", "", "authority_leaves.stream_ref is invalid"),
        ("transition_id", "x" * 4097, "exceeds its bound"),
        ("head_root", "sha256:bad", "authority_leaves.head_root is invalid"),
    ),
)
def test_certificate_leaf_scalar_contract_is_total(
    certificate_event: TraceEvent,
    field: str,
    value: object,
    message: str,
) -> None:
    lineage = deepcopy(certificate_event.lineage)
    leaves = cast(list[dict[str, object]], lineage["authority_leaves"])
    leaves[0][field] = value

    with pytest.raises(ValueError, match=message):
        _clone_event(certificate_event, lineage=lineage).validate()


def test_certificate_leaf_requires_exact_fields_and_distinct_streams(
    certificate_event: TraceEvent,
) -> None:
    malformed = deepcopy(certificate_event.lineage)
    leaves = cast(list[dict[str, object]], malformed["authority_leaves"])
    leaves[0] = {}
    with pytest.raises(ValueError, match="leaf fields are invalid"):
        _clone_event(certificate_event, lineage=malformed).validate()

    collided = deepcopy(certificate_event.lineage)
    collided_leaves = cast(
        list[dict[str, object]],
        collided["authority_leaves"],
    )
    collided_leaves[1]["stream_ref"] = collided_leaves[0]["stream_ref"]
    _certificate_recommit_leaves(collided)
    with pytest.raises(ValueError, match="authority leaves collide"):
        _clone_event(certificate_event, lineage=collided).validate()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("attestation_refs", cast(Any, "attestation:test"), "is not bounded"),
        ("reason_codes", ["reason:z", "reason:a"], "order is invalid"),
    ),
)
def test_certificate_text_arrays_are_exact_and_canonical(
    certificate_event: TraceEvent,
    field: str,
    value: object,
    message: str,
) -> None:
    lineage = deepcopy(certificate_event.lineage)
    lineage[field] = value

    with pytest.raises(ValueError, match=message):
        _clone_event(certificate_event, lineage=lineage).validate()


def test_certificate_read_set_rejects_cross_role_stream_collision(
    certificate_event: TraceEvent,
) -> None:
    lineage = deepcopy(certificate_event.lineage)
    leaves = cast(list[dict[str, object]], lineage["authority_leaves"])
    leaves[0]["stream_ref"] = lineage["decision_stream_ref"]
    _certificate_recommit_leaves(lineage)

    with pytest.raises(ValueError, match="read-set streams collide"):
        _clone_event(certificate_event, lineage=lineage).validate()


def _decision_recommit_dependencies(
    lineage: dict[str, object],
    *,
    read_set: bool = True,
) -> None:
    dependencies = cast(list[dict[str, object]], lineage["dependencies"])
    for item in dependencies:
        body = {
            key: item[key]
            for key in decision_contract._DEPENDENCY_FIELDS
            if key != "dependency_root"
        }
        item["dependency_root"] = decision_contract._root("dependency", body)
    lineage["dependency_set_root"] = decision_contract._root(
        "dependency-set",
        {
            "dependencies": [
                {"role": item["role"], "root": item["dependency_root"]}
                for item in dependencies
            ]
        },
    )
    if read_set:
        lineage["read_set_root"] = decision_contract._read_set_root(
            lineage,
            dependencies,
        )


def _decision_successor(event: TraceEvent, *, parent_transition: str) -> TraceEvent:
    lineage = deepcopy(event.lineage)
    lineage.update(
        {
            "revision": 2,
            "parent_revision": 1,
            "history_count": 2,
            "parent_transition_id": parent_transition,
            "parent_snapshot_root": ROOT_A,
        }
    )
    dependencies = cast(list[dict[str, object]], lineage["dependencies"])
    parent = next(item for item in dependencies if item["role"] == "parent")
    parent.update(
        {
            "revision": 1,
            "transition_id": parent_transition,
            "snapshot_root": ROOT_A,
        }
    )
    _decision_recommit_dependencies(lineage)
    return _clone_event(event, lineage=lineage)


def test_decision_contract_accepts_a_canonical_successor(
    initialized_event: TraceEvent,
) -> None:
    _decision_successor(
        initialized_event,
        parent_transition="transition:commit-decision-v2:" + "a" * 64,
    ).validate()


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("revision", "revision lineage is invalid"),
        ("deadline", "deadline lineage is invalid"),
        ("target", "target/request binding is invalid"),
        ("request", "target/request binding is invalid"),
        ("profile", "profile is mismatched"),
        ("genesis", "genesis parent is invalid"),
        ("successor", "parent transition is invalid"),
    ),
)
def test_decision_identity_and_time_contract_is_total(
    initialized_event: TraceEvent,
    mutation: str,
    message: str,
) -> None:
    lineage = deepcopy(initialized_event.lineage)
    target: str | None = None
    if mutation == "revision":
        lineage["history_count"] = 2
    elif mutation == "deadline":
        lineage["evidence_deadline_step"] = (
            cast(int, lineage["finality_deadline_step"]) + 1
        )
    elif mutation == "target":
        target = "target:forged"
    elif mutation == "request":
        lineage["mutation_ref"] = "mutation:forged"
    elif mutation == "profile":
        lineage["assurance"] = "unknown"
    elif mutation == "genesis":
        lineage["parent_transition_id"] = "parent:forged"
    else:
        event = _decision_successor(
            initialized_event,
            parent_transition="transition:commit-decision-v2:bad",
        )
        with pytest.raises(ValueError, match=message):
            event.validate()
        return

    with pytest.raises(ValueError, match=message):
        _clone_event(initialized_event, target=target, lineage=lineage).validate()


@pytest.mark.parametrize(
    ("event_type", "mutation", "message"),
    (
        (
            "commit_window_advanced_v2",
            "event_mutation",
            "event mutation is invalid",
        ),
        (
            "commit_decision_initialized_v2",
            "both_terminal",
            "terminal projection is invalid",
        ),
        (
            "commit_window_sealed_v2",
            "missing_seal",
            "omits its seal",
        ),
        (
            "commit_decision_progressed_v2",
            "missing_progress",
            "omits its progress",
        ),
        (
            "commit_decision_outcome_committed_v2",
            "missing_outcome",
            "omits its outcome",
        ),
    ),
)
def test_decision_event_projection_rejects_semantic_relabelling(
    initialized_event: TraceEvent,
    event_type: str,
    mutation: str,
    message: str,
) -> None:
    event = decision_event_variant(initialized_event, event_type)
    lineage = deepcopy(event.lineage)
    if mutation == "event_mutation":
        lineage["mutation_kind"] = "window_reset"
    elif mutation == "both_terminal":
        lineage["outcome_root"] = ROOT_A
    elif mutation == "missing_seal":
        lineage["seal_root"] = ""
    elif mutation == "missing_progress":
        lineage["progress_root"] = ""
        lineage["outcome_root"] = ROOT_A
    else:
        lineage["outcome_root"] = ""
        lineage["progress_root"] = ROOT_A

    with pytest.raises(ValueError, match=message):
        _clone_event(event, lineage=lineage).validate()


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("not_list", "dependencies are not bounded"),
        ("order", "dependency order is invalid"),
        ("fields", "dependency fields are invalid"),
        ("schema", "dependency version is invalid"),
        ("position", "dependency is not current"),
        ("genesis", "genesis dependency is invalid"),
    ),
)
def test_decision_dependency_shape_contract_is_total(
    initialized_event: TraceEvent,
    mutation: str,
    message: str,
) -> None:
    lineage = deepcopy(initialized_event.lineage)
    dependencies = cast(list[dict[str, object]], lineage["dependencies"])
    if mutation == "not_list":
        lineage["dependencies"] = cast(Any, {})
    elif mutation == "order":
        second = deepcopy(dependencies[0])
        second["role"] = "risk"
        second["stream_ref"] = "authority:dependency:risk"
        body = {
            key: second[key]
            for key in decision_contract._DEPENDENCY_FIELDS
            if key != "dependency_root"
        }
        second["dependency_root"] = decision_contract._root("dependency", body)
        lineage["dependencies"] = [second, dependencies[0]]
    elif mutation == "fields":
        dependencies[0].pop("receipt_root")
    elif mutation == "schema":
        dependencies[0]["schema"] = "schema:forged"
    elif mutation == "position":
        dependencies[0]["observed_position"] = "stale"
    elif mutation == "genesis":
        dependencies[0]["revision"] = 0
        dependencies[0]["transition_id"] = "transition:not-genesis"

    with pytest.raises((TypeError, ValueError), match=message):
        _clone_event(initialized_event, lineage=lineage).validate()


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("parent", "parent dependency is mismatched"),
        ("nested_text", "dependencies.stream_ref is invalid"),
        ("nested_text_bound", "dependencies.transition_id exceeds"),
        ("nested_integer", "dependencies.revision is invalid"),
        ("nested_root", "dependencies.head_root is invalid"),
        ("read_collision", "read-set streams collide"),
    ),
)
def test_decision_dependency_value_contract_is_total(
    initialized_event: TraceEvent,
    mutation: str,
    message: str,
) -> None:
    lineage = deepcopy(initialized_event.lineage)
    dependencies = cast(list[dict[str, object]], lineage["dependencies"])
    if mutation == "parent":
        parent = next(item for item in dependencies if item["role"] == "parent")
        parent["snapshot_root"] = ROOT_A
        _decision_recommit_dependencies(lineage, read_set=False)
    elif mutation == "nested_text":
        dependencies[0]["stream_ref"] = ""
    elif mutation == "nested_text_bound":
        dependencies[0]["transition_id"] = "x" * 4097
    elif mutation == "nested_integer":
        dependencies[0]["revision"] = True
    elif mutation == "nested_root":
        dependencies[0]["head_root"] = "sha256:bad"
    else:
        binding = cast(dict[str, object], lineage["session_binding"])
        dependencies[0]["stream_ref"] = _authority_stream_ref(
            "issuer-grant",
            (cast(str, lineage["scope_ref"]), cast(str, lineage["grant_ref"])),
        )
        assert dependencies[0]["stream_ref"] != lineage["stream_ref"]
        assert dependencies[0]["stream_ref"] != binding["lifecycle_expected_root"]
        _decision_recommit_dependencies(lineage, read_set=False)

    with pytest.raises((TypeError, ValueError), match=message):
        _clone_event(initialized_event, lineage=lineage).validate()


def test_decision_top_level_text_bound_is_enforced(
    initialized_event: TraceEvent,
) -> None:
    lineage = deepcopy(initialized_event.lineage)
    lineage["mutation_ref"] = "x" * 4097
    lineage["request_ref"] = lineage["mutation_ref"]
    binding = cast(dict[str, object], lineage["session_binding"])
    binding["request_ref"] = lineage["mutation_ref"]

    with pytest.raises(ValueError, match="mutation_ref exceeds"):
        _clone_event(initialized_event, lineage=lineage).validate()


def _evidence_successor(event: TraceEvent, *, parent_transition: str) -> TraceEvent:
    lineage = deepcopy(event.lineage)
    lineage.update(
        {
            "revision": 2,
            "parent_revision": 1,
            "parent_history_count": 1,
            "history_count": 2,
            "parent_epoch": lineage["epoch"],
            "parent_transition_id": parent_transition,
            "parent_snapshot_root": ROOT_A,
            "parent_history_root": ROOT_B,
        }
    )
    lineage["history_root"] = evidence_contract._evidence_root(
        "history-successor",
        {
            "parent_history_root": lineage["parent_history_root"],
            "parent_history_count": lineage["parent_history_count"],
            "transition_id": lineage["transition_id"],
            "mutation_delta_root": lineage["mutation_delta_root"],
        },
    )
    lineage["read_set_root"] = evidence_contract._read_set_root(lineage)
    return _clone_event(event, lineage=lineage)


def test_evidence_contract_accepts_a_canonical_successor(
    evidence_event: TraceEvent,
) -> None:
    _evidence_successor(
        evidence_event,
        parent_transition="transition:commit-evidence-v2:" + "a" * 64,
    ).validate()


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("target", "target is mismatched"),
        ("stream", "stream_ref is not canonical"),
        ("parent_epoch_type", "parent_epoch"),
        ("genesis", "genesis parent is invalid"),
        ("successor", "successor parent is invalid"),
    ),
)
def test_evidence_identity_and_parent_substitution_fail_closed(
    evidence_event: TraceEvent,
    mutation: str,
    message: str,
) -> None:
    lineage = deepcopy(evidence_event.lineage)
    target: str | None = None
    if mutation == "target":
        target = "target:forged"
    elif mutation == "stream":
        lineage["stream_ref"] = "authority:forged"
    elif mutation == "parent_epoch_type":
        lineage["parent_epoch"] = True
    elif mutation == "genesis":
        lineage["parent_transition_id"] = "parent:forged"
    else:
        event = _evidence_successor(
            evidence_event,
            parent_transition="transition:commit-evidence-v2:bad",
        )
        with pytest.raises(ValueError, match=message):
            event.validate()
        return

    with pytest.raises(ValueError, match=message):
        _clone_event(evidence_event, target=target, lineage=lineage).validate()


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("array_type", "attestation_roots is not canonical"),
        ("empty_trace", "requires mutation trace lineage"),
        ("history", "history roots are mismatched"),
        ("source", "source root is mismatched"),
        ("read_set", "read set root is mismatched"),
        ("stream_collision", "dependency streams overlap"),
    ),
)
def test_evidence_projection_substitution_fails_closed(
    evidence_event: TraceEvent,
    mutation: str,
    message: str,
) -> None:
    lineage = deepcopy(evidence_event.lineage)
    if mutation == "array_type":
        lineage["attestation_roots"] = cast(Any, "not-an-array")
    elif mutation == "empty_trace":
        lineage["mutation_trace_roots"] = []
    elif mutation == "history":
        lineage["history_root"] = ROOT_A
    elif mutation == "source":
        lineage["source_context_root"] = ROOT_A
    elif mutation == "read_set":
        lineage["read_set_root"] = ROOT_A
    else:
        lineage["replay_stream_ref"] = lineage["membership_stream_ref"]

    with pytest.raises(ValueError, match=message):
        _clone_event(evidence_event, lineage=lineage).validate()


def test_evidence_read_set_scalar_helpers_reject_non_wire_values() -> None:
    with pytest.raises(ValueError, match="session_binding is not an object"):
        evidence_contract._string_object([], "session_binding")
    with pytest.raises(ValueError, match="session_binding keys are invalid"):
        evidence_contract._string_object({1: "value"}, "session_binding")
    with pytest.raises(ValueError, match="stream_ref is invalid"):
        evidence_contract._text({"stream_ref": 1}, "stream_ref")
    with pytest.raises(ValueError, match="revision is invalid"):
        evidence_contract._count({"revision": True}, "revision")


def _gate_dependency_body(lineage: dict[str, object]) -> dict[str, object]:
    body: dict[str, object] = {
        "schema": "pheroos-commit-gate-dependencies-v2",
        "canonical_version": "pheroos-authority-canonical-v2",
    }
    for name in gate_contract._DEPENDENCY_NAMES:
        for suffix in (
            "stream_ref",
            "revision",
            "transition_id",
            "snapshot_root",
            "head_root",
        ):
            body[f"{name}_{suffix}"] = lineage[f"{name}_{suffix}"]
    return body


def _gate_decision(lineage: dict[str, object], kind: str) -> dict[str, object]:
    if kind == "stop":
        return {
            "resolution_ref": lineage["resolution_ref"],
            "blocked": lineage["blocked"],
            "reason_codes": lineage["reason_codes"],
            "reason_root": lineage["reason_root"],
        }
    return {
        "permission_ref": lineage["permission_ref"],
        "allowed": lineage["allowed"],
        "candidate_refs": lineage["candidate_refs"],
        "candidate_set_root": lineage["candidate_set_root"],
        "claim_roots": lineage["claim_roots"],
        "claims_root": lineage["claims_root"],
    }


def _recommit_gate(lineage: dict[str, object], kind: str) -> None:
    dependency = _gate_dependency_body(lineage)
    snapshot = gate_contract._snapshot_wire(
        lineage,
        dependency,
        _gate_decision(lineage, kind),
        kind=kind,
    )
    lineage["snapshot_root"] = snapshot["snapshot_root"]
    request = gate_contract._request_wire(lineage, snapshot, kind=kind)
    lineage["request_root"] = request["request_root"]
    binding = cast(dict[str, object], lineage["session_binding"])
    binding["request_root"] = request["request_root"]
    lineage["source_context_root"] = gate_contract._root(
        "source-context",
        {
            "kind": kind,
            "request_root": request["request_root"],
            "evaluation_context_root": lineage["evaluation_context_root"],
            "dependency_root": lineage["dependency_root"],
        },
    )
    lineage["read_set_root"] = gate_contract._expected_read_set_root(lineage)


def _gate_successor(kind: str, *, parent_transition: str) -> TraceEvent:
    event_type = (
        "commit_stop_resolved_v2" if kind == "stop" else "commit_permission_issued_v2"
    )
    lineage = deepcopy(valid_lineage(event_type))
    lineage.update(
        {
            "revision": 2,
            "parent_revision": 1,
            "parent_transition_id": parent_transition,
            "parent_snapshot_root": ROOT_A,
        }
    )
    _recommit_gate(lineage, kind)
    return _event(event_type, lineage)


def test_gate_contract_accepts_canonical_successors() -> None:
    _gate_successor(
        "stop",
        parent_transition="transition:commit-stop-v2:" + "a" * 64,
    ).validate()
    _gate_successor(
        "permission",
        parent_transition="transition:commit-permission-v2:" + "a" * 64,
    ).validate()


@pytest.mark.parametrize(
    ("event_type", "mutation", "message"),
    (
        ("commit_stop_resolved_v2", "revision", "revision lineage is invalid"),
        ("commit_stop_resolved_v2", "target", "target is mismatched"),
        ("commit_stop_resolved_v2", "profile", "profile is mismatched"),
        ("commit_stop_resolved_v2", "request", "request_ref is mismatched"),
        ("commit_stop_resolved_v2", "genesis", "genesis parent is invalid"),
        ("commit_stop_resolved_v2", "successor", "parent transition is invalid"),
        (
            "commit_stop_resolved_v2",
            "dependency_revision",
            "dependency revision is invalid",
        ),
        (
            "commit_stop_resolved_v2",
            "dependency_collision",
            "dependency streams collide",
        ),
    ),
)
def test_gate_identity_parent_and_dependency_semantics_are_total(
    event_type: str,
    mutation: str,
    message: str,
) -> None:
    lineage = deepcopy(valid_lineage(event_type))
    target: str | None = None
    if mutation == "revision":
        lineage["revision"] = 0
    elif mutation == "target":
        target = "target:forged"
    elif mutation == "profile":
        lineage["assurance"] = "unknown"
    elif mutation == "request":
        lineage["request_ref"] = "resolution:other"
        binding = cast(dict[str, object], lineage["session_binding"])
        binding["request_ref"] = "resolution:other"
    elif mutation == "genesis":
        lineage["parent_transition_id"] = "parent:forged"
    elif mutation == "successor":
        with pytest.raises(ValueError, match=message):
            _gate_successor(
                "stop", parent_transition="transition:commit-stop-v2:bad"
            ).validate()
        return
    elif mutation == "dependency_revision":
        lineage["replay_revision"] = 0
    else:
        lineage["replay_stream_ref"] = lineage["risk_stream_ref"]

    with pytest.raises(ValueError, match=message):
        _event(event_type, lineage, target=target).validate()


def test_gate_request_root_is_recomputed_after_source_binding() -> None:
    lineage = deepcopy(valid_lineage("commit_stop_resolved_v2"))
    lineage["request_root"] = ROOT_A
    binding = cast(dict[str, object], lineage["session_binding"])
    binding["request_root"] = ROOT_A
    lineage["source_context_root"] = gate_contract._root(
        "source-context",
        {
            "kind": "stop",
            "request_root": ROOT_A,
            "evaluation_context_root": lineage["evaluation_context_root"],
            "dependency_root": lineage["dependency_root"],
        },
    )

    with pytest.raises(ValueError, match="request_root is mismatched"):
        _event("commit_stop_resolved_v2", lineage).validate()


@pytest.mark.parametrize(
    ("event_type", "field", "value", "message"),
    (
        (
            "commit_stop_resolved_v2",
            "blocked",
            1,
            "blocked must be an exact bool",
        ),
        (
            "commit_stop_resolved_v2",
            "reason_codes",
            cast(Any, "reason"),
            "must be a bounded array",
        ),
        (
            "commit_stop_resolved_v2",
            "reason_codes",
            ["x" * 4097],
            "text is invalid",
        ),
        (
            "commit_permission_issued_v2",
            "candidate_refs",
            [],
            "cardinality is invalid",
        ),
        (
            "commit_permission_issued_v2",
            "claim_roots",
            ["not-a-root"],
            "root is invalid",
        ),
    ),
)
def test_gate_decision_collections_reject_noncanonical_wire_values(
    event_type: str,
    field: str,
    value: object,
    message: str,
) -> None:
    lineage = deepcopy(valid_lineage(event_type))
    lineage[field] = value

    with pytest.raises(ValueError, match=message):
        _event(event_type, lineage).validate()


def test_blocked_gate_requires_a_reason() -> None:
    lineage = deepcopy(valid_lineage("commit_stop_resolved_v2"))
    lineage["blocked"] = True
    lineage["reason_codes"] = []

    with pytest.raises(ValueError, match="requires reasons"):
        _event("commit_stop_resolved_v2", lineage).validate()


_DISTRIBUTED_SHAPES: dict[
    str,
    tuple[str, str, str, dict[str, object]],
] = {
    "distributed_epoch_advanced_v2": (
        "epoch",
        "epoch_initialized",
        "active",
        {
            "transition_certificate_root": ROOT_A,
            "conflict_history_roots": [],
        },
    ),
    "distributed_proposal_advanced_v2": (
        "proposal",
        "proposal_recorded",
        "active",
        {"epoch": 1, "proposal_digests": [ROOT_A]},
    ),
    "distributed_witness_advanced_v2": (
        "witness",
        "witness_recorded",
        "active",
        {"epoch": 1, "witness_roots": [ROOT_A], "finding_roots": []},
    ),
    "distributed_witness_conflict_v2": (
        "witness",
        "equivocation_frozen",
        "frozen",
        {"epoch": 1, "witness_roots": [ROOT_A], "finding_roots": [ROOT_B]},
    ),
    "distributed_certificate_advanced_v2": (
        "certificate",
        "certificate_verified",
        "verified",
        {"epoch": 1, "certificate_roots": [ROOT_A], "conflict_roots": []},
    ),
    "distributed_certificate_conflict_v2": (
        "certificate",
        "certificate_conflict_frozen",
        "frozen",
        {"epoch": 1, "certificate_roots": [ROOT_A], "conflict_roots": [ROOT_B]},
    ),
}


def _distributed_dependency(role: str) -> dict[str, object]:
    item: dict[str, object] = {
        "schema": "pheroos-distributed-dependency-v2",
        "role": role,
        "stream_ref": f"authority:dependency:{role}",
        "revision": 1,
        "transition_id": f"transition:dependency:{role}",
        "snapshot_root": "sha256:" + sha256(f"{role}:snapshot".encode()).hexdigest(),
        "head_root": "sha256:" + sha256(f"{role}:head".encode()).hexdigest(),
        "receipt_root": "sha256:" + sha256(f"{role}:receipt".encode()).hexdigest(),
        "inclusion_root": "sha256:" + sha256(f"{role}:inclusion".encode()).hexdigest(),
    }
    body = {
        field: item[field]
        for field in distributed_contract._DEPENDENCY_FIELDS
        if field != "dependency_root"
    }
    item["dependency_root"] = distributed_contract._root("dependency", body)
    return item


def _recommit_distributed(
    lineage: dict[str, object],
    lane: str,
    *,
    read_set: bool = True,
) -> None:
    dependencies = cast(list[dict[str, object]], lineage["dependencies"])
    counts = {
        field: cast(int, lineage[field])
        for field in (
            "revision",
            "parent_revision",
            "current_epoch",
            "current_step",
            "parent_history_count",
            "history_count",
        )
    }
    lineage["source_context_root"] = distributed_contract._root(
        "source-context",
        {
            "lane": lane,
            "mutation_ref": lineage["request_ref"],
            "current_epoch": lineage["current_epoch"],
            "current_step": lineage["current_step"],
            "lane_state_root": lineage["lane_state_root"],
            "dependency_set_root": lineage["dependency_set_root"],
        },
    )
    state = {
        "lane": lane,
        "mutation_kind": lineage["mutation_kind"],
        "current_epoch": lineage["current_epoch"],
        "current_step": lineage["current_step"],
        "status": lineage["status"],
        "lane_state_root": lineage["lane_state_root"],
        "dependency_set_root": lineage["dependency_set_root"],
        "reason_codes": lineage["reason_codes"],
        "source_context_root": lineage["source_context_root"],
    }
    lineage["snapshot_state_root"] = distributed_contract._root(
        "snapshot-state",
        state,
    )
    lineage["history_root"] = distributed_contract._root(
        "history",
        {
            "lane": lane,
            "parent_history_root": lineage["parent_history_root"],
            "parent_history_count": lineage["parent_history_count"],
            "transition_id": lineage["transition_id"],
            "snapshot_state_root": lineage["snapshot_state_root"],
        },
    )
    snapshot = distributed_support._snapshot_body(
        lineage,
        lane,
        dependencies,
        counts,
    )
    lineage["snapshot_root"] = distributed_contract._root("snapshot", snapshot)
    request = distributed_support._request_body(lineage, counts)
    lineage["request_root"] = distributed_contract._root("advance-request", request)
    binding = cast(dict[str, object], lineage["session_binding"])
    binding["request_root"] = lineage["request_root"]
    if read_set:
        lineage["read_set_root"] = distributed_support._read_set_root(
            lineage,
            dependencies,
        )


def _distributed_variant(
    base: TraceEvent,
    event_type: str,
    *,
    successor: bool = False,
    epoch_conflict: bool = False,
) -> TraceEvent:
    lane, mutation, status, material_template = _DISTRIBUTED_SHAPES[event_type]
    lineage = deepcopy(base.lineage)
    material = deepcopy(material_template)
    if successor:
        mutation = "epoch_transitioned" if lane == "epoch" else mutation
        lineage.update(
            {
                "revision": 2,
                "parent_revision": 1,
                "parent_transition_id": "transition:distributed-v2:" + "a" * 64,
                "parent_snapshot_root": ROOT_A,
                "parent_history_root": ROOT_B,
                "parent_history_count": 1,
                "history_count": 2,
            }
        )
    else:
        lineage.update(
            {
                "revision": 1,
                "parent_revision": 0,
                "parent_transition_id": "genesis",
                "parent_snapshot_root": distributed_contract._root(
                    "genesis-snapshot",
                    {"schema": "pheroos-distributed-lane-snapshot-v2", "lane": lane},
                ),
                "parent_history_root": distributed_contract._root(
                    "genesis-history",
                    {"schema": "pheroos-distributed-lane-state-v2", "lane": lane},
                ),
                "parent_history_count": 0,
                "history_count": 1,
            }
        )
    if lane == "epoch" and epoch_conflict:
        material["conflict_history_roots"] = [ROOT_B]
    lineage.update(
        {
            "lane": lane,
            "mutation_kind": mutation,
            "status": status,
            "lane_state_material": material,
            "lane_state_root": distributed_contract._root(
                f"{lane}-state",
                material,
            ),
            "reason_codes": [mutation],
        }
    )
    identity = b"\x00".join(
        cast(str, lineage[field]).encode("utf-8")
        for field in ("scope_ref", "protocol_ref", "run_ref", "target_ref")
    )
    stream = (
        f"authority:distributed-{lane}-v2:"
        + sha256(identity + b"\x00" + lane.encode()).hexdigest()
    )
    lineage["stream_ref"] = stream
    lineage["transition_id"] = (
        "transition:distributed-v2:"
        + sha256(
            stream.encode() + b"\x00" + cast(str, lineage["request_ref"]).encode()
        ).hexdigest()
    )
    roles = distributed_support._required_roles(lane)
    lineage["dependencies"] = [
        _distributed_dependency(role)
        for role in sorted(roles, key=lambda item: item.encode("utf-8"))
    ]
    dependencies = cast(list[dict[str, object]], lineage["dependencies"])
    lineage["dependency_set_root"] = distributed_contract._root(
        "dependency-set",
        {
            "dependencies": [
                {"role": item["role"], "dependency_root": item["dependency_root"]}
                for item in dependencies
            ]
        },
    )
    binding = cast(dict[str, object], lineage["session_binding"])
    binding["action_refs"] = (
        ["epoch_transition", "recovery"]
        if lane == "epoch" and epoch_conflict
        else ["epoch_transition"]
        if lane == "epoch"
        else []
    )
    _recommit_distributed(lineage, lane)
    return _clone_event(base, event_type=event_type, lineage=lineage)


@pytest.mark.parametrize("event_type", tuple(_DISTRIBUTED_SHAPES))
def test_every_distributed_lane_shape_has_a_valid_closed_trace(
    distributed_epoch_event: TraceEvent,
    event_type: str,
) -> None:
    event = _distributed_variant(distributed_epoch_event, event_type)
    event.validate()
    assert event.lineage["lane"] == _DISTRIBUTED_SHAPES[event_type][0]


def test_distributed_epoch_successor_and_recovery_action_are_valid(
    distributed_epoch_event: TraceEvent,
) -> None:
    _distributed_variant(
        distributed_epoch_event,
        "distributed_epoch_advanced_v2",
        successor=True,
    ).validate()
    _distributed_variant(
        distributed_epoch_event,
        "distributed_epoch_advanced_v2",
        epoch_conflict=True,
    ).validate()


def test_distributed_event_lane_fails_closed_for_unknown_event() -> None:
    with pytest.raises(ValueError, match="unsupported distributed event"):
        distributed_contract._event_lane("distributed_unknown_v2")


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("lane", "lane is unsupported"),
        ("reason", "reasons are inconsistent"),
        ("identity", "identity is inconsistent"),
        ("genesis", "genesis is invalid"),
        ("successor_parent", "parent is invalid"),
        ("successor_mutation", "epoch mutation is invalid"),
    ),
)
def test_distributed_identity_and_parent_contract_is_total(
    distributed_epoch_event: TraceEvent,
    mutation: str,
    message: str,
) -> None:
    event = _distributed_variant(
        distributed_epoch_event,
        "distributed_epoch_advanced_v2",
    )
    lineage = deepcopy(event.lineage)
    target: str | None = None
    if mutation == "lane":
        lineage["lane"] = "unknown"
    elif mutation == "reason":
        lineage["reason_codes"] = ["other"]
    elif mutation == "identity":
        target = "target:forged"
    elif mutation == "genesis":
        lineage["parent_snapshot_root"] = ROOT_A
    else:
        successor = _distributed_variant(
            distributed_epoch_event,
            "distributed_epoch_advanced_v2",
            successor=True,
        )
        lineage = deepcopy(successor.lineage)
        if mutation == "successor_parent":
            lineage["parent_transition_id"] = "genesis"
        else:
            lineage["mutation_kind"] = "epoch_initialized"
            lineage["reason_codes"] = ["epoch_initialized"]

    with pytest.raises(ValueError, match=message):
        _clone_event(event, target=target, lineage=lineage).validate()


@pytest.mark.parametrize(
    ("event_type", "mutation", "message"),
    (
        (
            "distributed_epoch_advanced_v2",
            "type",
            "lane material is invalid",
        ),
        (
            "distributed_epoch_advanced_v2",
            "fields",
            "lane material fields are invalid",
        ),
        (
            "distributed_proposal_advanced_v2",
            "epoch",
            "material epoch is mismatched",
        ),
        (
            "distributed_proposal_advanced_v2",
            "empty",
            "proposal_digests is not bounded",
        ),
        (
            "distributed_proposal_advanced_v2",
            "root",
            "nested proposal_digests is invalid",
        ),
        (
            "distributed_proposal_advanced_v2",
            "order",
            "proposal_digests is not canonical",
        ),
        (
            "distributed_witness_advanced_v2",
            "freeze",
            "witness freeze is invalid",
        ),
        (
            "distributed_certificate_advanced_v2",
            "freeze",
            "certificate freeze is invalid",
        ),
    ),
)
def test_distributed_lane_material_contract_is_total(
    distributed_epoch_event: TraceEvent,
    event_type: str,
    mutation: str,
    message: str,
) -> None:
    event = _distributed_variant(distributed_epoch_event, event_type)
    lineage = deepcopy(event.lineage)
    material = cast(dict[str, object], lineage["lane_state_material"])
    if mutation == "type":
        lineage["lane_state_material"] = cast(Any, [])
    elif mutation == "fields":
        material["unexpected"] = ROOT_A
    elif mutation == "epoch":
        material["epoch"] = 2
    elif mutation == "empty":
        material["proposal_digests"] = []
    elif mutation == "root":
        material["proposal_digests"] = ["sha256:bad"]
    elif mutation == "order":
        material["proposal_digests"] = [ROOT_B, ROOT_A]
    elif event_type == "distributed_witness_advanced_v2":
        material["finding_roots"] = [ROOT_B]
    else:
        material["conflict_roots"] = [ROOT_B]
    if isinstance(lineage["lane_state_material"], dict):
        lane = cast(str, lineage["lane"])
        lineage["lane_state_root"] = distributed_contract._root(
            f"{lane}-state",
            lineage["lane_state_material"],
        )

    with pytest.raises((TypeError, ValueError), match=message):
        _clone_event(event, lineage=lineage).validate()


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("type", "dependencies are invalid"),
        ("roles", "dependency set is invalid"),
        ("fields", "dependency fields are invalid"),
        ("schema", "dependency version is invalid"),
        ("genesis", "genesis dependency is invalid"),
        ("text", "nested stream_ref is invalid"),
        ("integer", "nested revision is invalid"),
        ("root", "nested head_root is invalid"),
        ("read_collision", "read set streams collide"),
    ),
)
def test_distributed_dependency_contract_is_total(
    distributed_epoch_event: TraceEvent,
    mutation: str,
    message: str,
) -> None:
    event = _distributed_variant(
        distributed_epoch_event,
        "distributed_proposal_advanced_v2",
    )
    lineage = deepcopy(event.lineage)
    dependencies = cast(list[dict[str, object]], lineage["dependencies"])
    if mutation == "type":
        lineage["dependencies"] = cast(Any, {})
    elif mutation == "roles":
        dependencies[0]["role"] = dependencies[1]["role"]
        body = {
            field: dependencies[0][field]
            for field in distributed_contract._DEPENDENCY_FIELDS
            if field != "dependency_root"
        }
        dependencies[0]["dependency_root"] = distributed_contract._root(
            "dependency",
            body,
        )
    elif mutation == "fields":
        dependencies[0].pop("receipt_root")
    elif mutation == "schema":
        dependencies[0]["schema"] = "schema:forged"
    elif mutation == "genesis":
        dependencies[0]["revision"] = 0
    elif mutation == "text":
        dependencies[0]["stream_ref"] = ""
    elif mutation == "integer":
        dependencies[0]["revision"] = True
    elif mutation == "root":
        dependencies[0]["head_root"] = "sha256:bad"
    else:
        dependencies[0]["stream_ref"] = lineage["stream_ref"]
        body = {
            field: dependencies[0][field]
            for field in distributed_contract._DEPENDENCY_FIELDS
            if field != "dependency_root"
        }
        dependencies[0]["dependency_root"] = distributed_contract._root(
            "dependency",
            body,
        )
        lineage["dependency_set_root"] = distributed_contract._root(
            "dependency-set",
            {
                "dependencies": [
                    {
                        "role": item["role"],
                        "dependency_root": item["dependency_root"],
                    }
                    for item in dependencies
                ]
            },
        )
        _recommit_distributed(lineage, "proposal", read_set=False)

    with pytest.raises((TypeError, ValueError), match=message):
        _clone_event(event, lineage=lineage).validate()


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("reasons_type", "reason_codes is not bounded"),
        ("request", "request root is invalid"),
    ),
)
def test_distributed_top_level_collections_and_request_root_are_closed(
    distributed_epoch_event: TraceEvent,
    mutation: str,
    message: str,
) -> None:
    event = _distributed_variant(
        distributed_epoch_event,
        "distributed_proposal_advanced_v2",
    )
    lineage = deepcopy(event.lineage)
    if mutation == "reasons_type":
        lineage["reason_codes"] = cast(Any, "proposal_recorded")
    else:
        lineage["request_root"] = ROOT_A
        binding = cast(dict[str, object], lineage["session_binding"])
        binding["request_root"] = ROOT_A

    with pytest.raises(ValueError, match=message):
        _clone_event(event, lineage=lineage).validate()


def test_distributed_precondition_helper_preserves_wire_field_meaning() -> None:
    assert distributed_contract._precondition("stream:a", 3, ROOT_A) == {
        "expected_revision": 3,
        "expected_root": ROOT_A,
        "stream_ref": "stream:a",
    }
