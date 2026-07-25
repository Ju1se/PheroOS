from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy
from enum import Enum
from types import SimpleNamespace
from typing import cast

import pytest

from pheroos.trace import (
    TraceEvent,
    canonical_pheromone_clip_payload,
    commit_trace_event_id,
    make_commit_trace_event,
    replay_commit_trace,
)
from pheroos.trace.commit_contracts import (
    commit_trace_required_fields,
    validate_commit_trace_event,
)
from tests.trace.test_commit_trace_contract import make_event, root
from tests.trace.test_trace_store import valid_event_context, valid_lineage


PROFILE = "pheroos-certified-commit-v1"
ASSURANCE = "certified"
PROTOCOL = "protocol:commit-trace"
RUN = "run:commit-trace"
TARGET = "decision:commit-trace"
EPOCH = 1
REMOVE = object()


def _trace_event(event_type: str, lineage: dict[str, object]) -> TraceEvent:
    protocol_id, target = valid_event_context(event_type)
    return TraceEvent(
        event_type=event_type,
        protocol_id=protocol_id,
        target=target,
        reason="adversarial lineage must fail closed",
        lineage=lineage,
    )


def test_pheromone_clip_canonical_payload_requires_an_object() -> None:
    with pytest.raises(TypeError, match="causal payload must be an object"):
        canonical_pheromone_clip_payload(
            cast(Mapping[str, object], ["not", "an", "object"])
        )


@pytest.mark.parametrize(
    ("event_type", "updates", "error"),
    [
        (
            "pheromone_deposit",
            {"source_strength": 1.0},
            "start from zero",
        ),
        (
            "pheromone_deposit",
            {"applied_strength": 1.1},
            "exceeds its request",
        ),
        (
            "pheromone_deposit",
            {"new_strength": 0.5},
            "reconstruct new strength",
        ),
        (
            "pheromone_deposit",
            {"source_kind": "negative"},
            "preserve pheromone kind",
        ),
        (
            "pheromone_deposit",
            {"trace_event_id": "trace:deposit:other"},
            "match its deposit source",
        ),
        (
            "pheromone_deposit",
            {"updated_at_step": 2},
            "updated step",
        ),
        (
            "pheromone_deposit",
            {"deposited_at_step": 2},
            "deposit step",
        ),
        (
            "pheromone_evaporate",
            {"new_strength": 1.1},
            "must not exceed old strength",
        ),
        (
            "pheromone_evaporate",
            {"strength_delta": 0.0},
            "do not reconstruct transition",
        ),
        (
            "pheromone_evaporate",
            {"source_kind": "negative"},
            "preserve pheromone kind",
        ),
        (
            "pheromone_evaporate",
            {"trace_event_id": "trace:evaporate:other"},
            "update its source trail in place",
        ),
        (
            "pheromone_evaporate",
            {"elapsed_steps": 2},
            "elapsed steps do not reconstruct",
        ),
        (
            "pheromone_evaporate",
            {"deposited_at_step": 2},
            "source update precedes deposit",
        ),
        (
            "pheromone_diffuse",
            {"attenuation": 1.1},
            "attenuation must be between",
        ),
        (
            "pheromone_diffuse",
            {"policy_attenuation": 1.1},
            "policy and edge attenuation",
        ),
        (
            "pheromone_diffuse",
            {"attenuation": 0.4},
            "attenuation factors do not reconstruct",
        ),
        (
            "pheromone_diffuse",
            {"requested_strength": 0.4},
            "request must equal attenuated",
        ),
        (
            "pheromone_diffuse",
            {"applied_strength": 0.6},
            "exceeds its request",
        ),
        (
            "pheromone_diffuse",
            {"new_strength": 0.4},
            "must equal new strength",
        ),
        (
            "pheromone_diffuse",
            {"source_kind": "negative"},
            "preserve pheromone kind",
        ),
        (
            "pheromone_diffuse",
            {"trace_event_id": "trace:deposit:a"},
            "derived trail id",
        ),
        (
            "pheromone_reinforce",
            {"new_strength": 1.4},
            "delta must reconstruct",
        ),
        (
            "pheromone_reinforce",
            {"applied_strength": 0.4},
            "equal delta magnitude",
        ),
        (
            "pheromone_reinforce",
            {"requested_strength": 0.4},
            "exceeds its request",
        ),
        (
            "pheromone_reinforce",
            {"feedback_source": "runtime:other"},
            "source identity is inconsistent",
        ),
        (
            "pheromone_reinforce",
            {
                "delta": -0.5,
                "new_strength": 0.5,
            },
            "explicit stale transition",
        ),
        (
            "pheromone_expire",
            {"action": "retain"},
            "expire transition to stale",
        ),
        (
            "pheromone_expire",
            {"target": "decision:other"},
            "target must match",
        ),
        (
            "pheromone_expire",
            {"new_strength": 1.1},
            "must not exceed old strength",
        ),
        (
            "pheromone_expire",
            {"strength_delta": 0.0},
            "do not reconstruct transition",
        ),
        (
            "pheromone_expire",
            {"trace_event_id": "trace:expire:other"},
            "update its source trail in place",
        ),
        (
            "pheromone_expire",
            {"elapsed_steps": 2},
            "elapsed steps do not reconstruct",
        ),
        (
            "pheromone_expire",
            {"ttl_steps": 2},
            "precedes its declared TTL",
        ),
        (
            "pheromone_normalize",
            {"post_scores": {"candidate:other": 1.0}},
            "cover exactly the declared candidates",
        ),
        (
            "pheromone_normalize",
            {"response_model": "sigmoid"},
            "response_model is unsupported",
        ),
        (
            "pheromone_normalize",
            {"competition_mode": "winner_take_all"},
            "competition_mode is unsupported",
        ),
    ],
)
def test_pheromone_transition_mutations_fail_closed(
    event_type: str,
    updates: dict[str, object],
    error: str,
) -> None:
    lineage = deepcopy(valid_lineage(event_type))
    lineage.update(updates)

    with pytest.raises(ValueError, match=error):
        _trace_event(event_type, lineage).validate()


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("not-an-array", "active_trails must be an array"),
        ("missing-breakdown-candidate", "cover exactly the scored candidates"),
        ("non-object-category", "must be an object"),
        ("incomplete-trail", "active_trails\\[0\\] is incomplete"),
        ("duplicate-trail", "trail ids must be unique"),
        ("update-before-deposit", "update precedes deposit"),
        ("update-after-current", "update exceeds current step"),
        ("boolean-ttl", "ttl_steps must be null or a non-negative integer"),
        ("expired-live-trail", "expired non-stale"),
    ],
)
def test_pheromone_score_rejects_ambiguous_active_memory(
    mutation: str,
    error: str,
) -> None:
    lineage = deepcopy(valid_lineage("pheromone_score"))
    trail = lineage["active_trails"][0]
    if mutation == "not-an-array":
        lineage["active_trails"] = {}
    elif mutation == "missing-breakdown-candidate":
        lineage["score_breakdown"] = {}
    elif mutation == "non-object-category":
        lineage["kind_breakdown"] = {"candidate:alpha": []}
    elif mutation == "incomplete-trail":
        del trail["source_id"]
    elif mutation == "duplicate-trail":
        lineage["active_trails"].append(deepcopy(trail))
    elif mutation == "update-before-deposit":
        trail["deposited_at_step"] = 2
    elif mutation == "update-after-current":
        trail["updated_at_step"] = 2
    elif mutation == "boolean-ttl":
        trail["ttl_steps"] = True
    else:
        trail["ttl_steps"] = 1
        lineage["current_step"] = 2

    with pytest.raises(ValueError, match=error):
        _trace_event("pheromone_score", lineage).validate()


@pytest.mark.parametrize(
    ("lineage", "error"),
    [
        ({}, "does not match a supported observation variant"),
        (
            {
                "lifecycle": "deposit",
                "source_trace_event_id": "trace:deposit:a",
            },
            "missing required fields",
        ),
        (
            {
                "lifecycle": "deposit",
                "source_trace_event_id": "trace:deposit:a",
                "result": "applied",
                "replay_payload": {},
                "replay_payload_fingerprint": "sha256:" + ("0" * 64),
                "processed_payload_fingerprint": "sha256:" + ("0" * 64),
            },
            "result must be replay_ignored",
        ),
        (
            {
                "lifecycle": "expire",
                "source_trace_event_id": "trace:deposit:a",
                "result": "replay_ignored",
                "replay_payload": {},
                "replay_payload_fingerprint": "sha256:" + ("0" * 64),
                "processed_payload_fingerprint": "sha256:" + ("0" * 64),
            },
            "unsupported lifecycle",
        ),
        (
            {
                "lifecycle": "deposit",
                "source_trace_event_id": "trace:deposit:a",
                "result": "replay_ignored",
                "replay_payload": {},
                "replay_payload_fingerprint": "sha256:" + ("0" * 64),
                "processed_payload_fingerprint": "sha256:" + ("0" * 64),
                "unexpected": True,
            },
            "exactly the replay receipt fields",
        ),
        (
            {
                "candidate_id": "candidate:alpha",
                "subject_type": "route",
                "subject_id": "route:alpha",
                "novelty_pressure": 0.1,
                "reopen_eligible": True,
            },
            "missing required fields",
        ),
        (
            {
                "candidate_id": "candidate:alpha",
                "subject_type": "route",
                "subject_id": "route:alpha",
                "novelty_pressure": 0.1,
                "reopen_eligible": True,
                "source_trace_event_id": "trace:deposit:a",
                "unexpected": True,
            },
            "exactly the state fields",
        ),
        (
            {"exploration_floor": 0.1},
            "missing required fields",
        ),
        (
            {
                "exploration_floor": 0.1,
                "candidate_ids": ["candidate:alpha"],
                "unexpected": True,
            },
            "exactly the floor fields",
        ),
    ],
)
def test_pheromone_observation_variants_are_exact_and_fail_closed(
    lineage: dict[str, object],
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        _trace_event("pheromone_observe", deepcopy(lineage)).validate()


def _rebind_commit_event(
    event: TraceEvent,
    updates: Mapping[str, object],
) -> TraceEvent:
    lineage = deepcopy(event.lineage)
    for name, value in updates.items():
        if value is REMOVE:
            lineage.pop(name, None)
        else:
            lineage[name] = value
    lineage["event_id"] = commit_trace_event_id(
        event_type=event.event_type,
        protocol_id=event.protocol_id,
        target=event.target,
        reason=event.reason,
        lineage=lineage,
    )
    return TraceEvent(
        event_type=event.event_type,
        protocol_id=event.protocol_id,
        target=event.target,
        reason=event.reason,
        lineage=lineage,
    )


@pytest.mark.parametrize(
    ("event_type", "updates", "error"),
    [
        (
            "commit_window_advanced",
            {"required_stability_steps": 0},
            "required_stability_steps must be positive",
        ),
        (
            "commit_window_advanced",
            {"leader_candidate_id": "", "stability_count": 1},
            "non-ready commit window stability_count must be zero",
        ),
        (
            "commit_window_reset",
            {"reset_count": 0},
            "reset_count must be positive",
        ),
        (
            "commit_provisional",
            {"final": True},
            "cannot claim finality",
        ),
        (
            "commit_provisional",
            {"witness_count": 3, "witness_quorum": 3},
            "must remain below witness quorum",
        ),
        (
            "commit_provisional",
            {"witness_count": 0},
            "zero-witness provisional trace",
        ),
        (
            "commit_provisional",
            {"proposal_digest": REMOVE},
            "witness-bearing provisional trace",
        ),
        (
            "certificate_conflict",
            {"frozen": False},
            "must freeze the epoch",
        ),
        (
            "certificate_conflict",
            {"commit_value_roots": [root("commit-value:only")]},
            "requires distinct commit values",
        ),
        (
            "quorum_witness",
            {"verified": False},
            "must contain a verified witness",
        ),
        (
            "commit_certificate_issued",
            {"claim_fingerprint": "not-a-root"},
            "claim must be empty or a canonical root",
        ),
        (
            "commit_certificate_issued",
            {"candidate_id": ""},
            "requires a substantive candidate and claim",
        ),
        (
            "commit_certificate_issued",
            {"commit_value_root": root("commit-value:unexpected")},
            "exclusively bind a commit value root",
        ),
        (
            "commit_certificate_issued",
            {
                "certificate_kind": "distributed_commit",
            },
            "exclusively bind a commit value root",
        ),
        (
            "decision_outcome",
            {"authoritative_commit": True},
            "authoritative_commit is inconsistent",
        ),
        (
            "decision_outcome",
            {"epistemically_committed": True},
            "epistemically_committed is inconsistent",
        ),
        (
            "decision_outcome",
            {
                "kind": "evidence_commit",
                "authoritative_commit": True,
                "epistemically_committed": True,
                "certificate_ref": REMOVE,
            },
            "requires certificate_ref",
        ),
        (
            "decision_outcome",
            {"certificate_ref": root("certificate:unexpected")},
            "non-commit outcome cannot carry",
        ),
    ],
)
def test_commit_semantic_thresholds_fail_closed(
    event_type: str,
    updates: dict[str, object],
    error: str,
) -> None:
    malformed = _rebind_commit_event(make_event(event_type), updates)

    with pytest.raises(ValueError, match=error):
        malformed.validate()


def test_ready_commit_window_requires_positive_stability_count() -> None:
    malformed = _rebind_commit_event(
        make_event("commit_window_advanced"),
        {"stability_count": 0},
    )

    with pytest.raises(ValueError, match="stability_count must be positive"):
        malformed.validate()


def test_commit_window_reset_cannot_reuse_its_prior_state_reference() -> None:
    event = make_event("commit_window_reset")
    malformed = _rebind_commit_event(
        event,
        {"prior_window_ref": event.lineage["window_ref"]},
    )

    with pytest.raises(ValueError, match="must issue a new window state"):
        malformed.validate()


def _commit_record_payload(
    event_type: str,
    *,
    run_id: str,
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "assurance": ASSURANCE,
        "commit_policy_root": root("policy"),
        "epoch": EPOCH,
        "event_record_kind": event_type,
        "manifest_root": root("manifest"),
        "profile": PROFILE,
        "protocol_id": PROTOCOL,
        "run_id": run_id,
        "target": TARGET,
    }
    payload.update(extra or {})
    return payload


def _build_commit_event(
    event_type: str,
    *,
    details: Mapping[str, object],
    previous: tuple[TraceEvent, ...] = (),
    step: int = 1,
    run_id: str = RUN,
    record_tag: str = "",
    payload_updates: Mapping[str, object] | None = None,
    extensions: Mapping[str, object] | None = None,
    reason_tag: str = "",
) -> TraceEvent:
    extra: dict[str, object] = {}
    if record_tag:
        extra["record_tag"] = record_tag
    extra.update(payload_updates or {})
    return make_commit_trace_event(
        event_type=event_type,
        protocol_id=PROTOCOL,
        target=TARGET,
        reason=f"recorded {event_type}{reason_tag}",
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=root("manifest"),
        commit_policy_root=root("policy"),
        run_id=run_id,
        epoch=EPOCH,
        step=step,
        record_schema=f"pheroos-test-{event_type}-v1",
        record_payload=_commit_record_payload(
            event_type,
            run_id=run_id,
            extra=extra,
        ),
        previous_event_ids=tuple(item.lineage["event_id"] for item in previous),
        details=details,
        extensions=extensions,
    )


def _attested(
    *,
    step: int = 1,
    run_id: str = RUN,
    nonce: str = "nonce:principal:a",
    extensions: Mapping[str, object] | None = None,
    payload_updates: Mapping[str, object] | None = None,
    reason_tag: str = "",
) -> TraceEvent:
    return _build_commit_event(
        "principal_attested",
        details={"principal_id": "principal:a", "nonce": nonce},
        step=step,
        run_id=run_id,
        extensions=extensions,
        payload_updates=payload_updates,
        reason_tag=reason_tag,
    )


@pytest.mark.parametrize(
    ("updates", "error"),
    [
        ({"protocol_id": "protocol:other"}, "protocol_id does not match"),
        ({"run_id": "run:other"}, "run_id does not match"),
        ({"epoch": 2}, "epoch does not match"),
    ],
)
def test_commit_record_payload_envelope_mismatch_fails_closed(
    updates: dict[str, object],
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        _attested(payload_updates=updates)


@pytest.mark.parametrize(
    ("payload_value", "error"),
    [
        (0.5, "floating-point"),
        ("e\u0301", "canonical NFC"),
        ((2**53), "bounded exact integer"),
        (object(), "unsupported JSON value"),
    ],
)
def test_commit_builder_rejects_nonportable_record_payload_values(
    payload_value: object,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        _attested(payload_updates={"adversarial": payload_value})


def test_commit_builder_rejects_unsupported_type_nonobjects_and_wrong_self_ref() -> (
    None
):
    with pytest.raises(ValueError, match="unsupported commit trace event type"):
        _build_commit_event("commit:unknown", details={})

    common = {
        "event_type": "principal_attested",
        "protocol_id": PROTOCOL,
        "target": TARGET,
        "reason": "malformed public builder input",
        "profile": PROFILE,
        "assurance": ASSURANCE,
        "manifest_root": root("manifest"),
        "commit_policy_root": root("policy"),
        "run_id": RUN,
        "epoch": EPOCH,
        "step": 1,
        "record_schema": "pheroos-test-principal-attested-v1",
        "previous_event_ids": (),
        "extensions": None,
    }
    with pytest.raises(ValueError, match="record_payload must be an object"):
        make_commit_trace_event(
            **common,
            record_payload=cast(Mapping[str, object], []),
            details={"principal_id": "principal:a", "nonce": "nonce:a"},
        )
    with pytest.raises(ValueError, match="details must be an object"):
        make_commit_trace_event(
            **common,
            record_payload=_commit_record_payload(
                "principal_attested",
                run_id=RUN,
            ),
            details=cast(Mapping[str, object], []),
        )
    with pytest.raises(ValueError, match="must match its record fingerprint"):
        make_commit_trace_event(
            **common,
            record_payload=_commit_record_payload(
                "principal_attested",
                run_id=RUN,
            ),
            details={
                "principal_id": "principal:a",
                "nonce": "nonce:a",
                "attestation_fingerprint": root("attestation:forged"),
            },
        )


def test_commit_builder_wraps_invalid_record_schema_as_record_payload_error() -> None:
    with pytest.raises(ValueError, match="invalid commit trace record payload"):
        make_commit_trace_event(
            event_type="principal_attested",
            protocol_id=PROTOCOL,
            target=TARGET,
            reason="blank schema is not portable",
            profile=PROFILE,
            assurance=ASSURANCE,
            manifest_root=root("manifest"),
            commit_policy_root=root("policy"),
            run_id=RUN,
            epoch=EPOCH,
            step=1,
            record_schema="",
            record_payload=_commit_record_payload(
                "principal_attested",
                run_id=RUN,
            ),
            details={"principal_id": "principal:a", "nonce": "nonce:a"},
        )


class _DuplicateKeyMapping(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        if key != "same":
            raise KeyError(key)
        return 1

    def __iter__(self) -> Iterator[str]:
        return iter(("same",))

    def __len__(self) -> int:
        return 1

    def items(self) -> tuple[tuple[str, object], ...]:
        return (("same", 1), ("same", 2))


class _WireAssurance(Enum):
    CERTIFIED = "certified"


def test_public_canonicalizers_reject_duplicate_mapping_keys() -> None:
    common = {
        "event_type": "principal_attested",
        "protocol_id": PROTOCOL,
        "target": TARGET,
        "reason": "duplicate record keys are ambiguous",
        "profile": PROFILE,
        "assurance": ASSURANCE,
        "manifest_root": root("manifest"),
        "commit_policy_root": root("policy"),
        "run_id": RUN,
        "epoch": EPOCH,
        "step": 1,
        "record_schema": "pheroos-test-principal-attested-v1",
        "record_payload": _DuplicateKeyMapping(),
        "details": {"principal_id": "principal:a", "nonce": "nonce:a"},
    }

    with pytest.raises(ValueError, match="duplicate keys"):
        make_commit_trace_event(**common)
    with pytest.raises(ValueError, match="duplicate keys"):
        canonical_pheromone_clip_payload(_DuplicateKeyMapping())


def test_commit_event_id_wire_codec_rejects_duplicate_mapping_keys() -> None:
    lineage: dict[str, object] = {
        "profile": PROFILE,
        "record_payload": _DuplicateKeyMapping(),
    }

    with pytest.raises(ValueError, match="duplicate keys"):
        commit_trace_event_id(
            event_type="principal_attested",
            protocol_id=PROTOCOL,
            target=TARGET,
            reason="duplicate wire keys are ambiguous",
            lineage=lineage,
        )


def test_commit_event_id_wire_codec_canonicalizes_enum_values() -> None:
    event = _attested()
    lineage = deepcopy(event.lineage)
    lineage["assurance"] = _WireAssurance.CERTIFIED

    assert (
        commit_trace_event_id(
            event_type=event.event_type,
            protocol_id=event.protocol_id,
            target=event.target,
            reason=event.reason,
            lineage=lineage,
        )
        == event.lineage["event_id"]
    )


@pytest.mark.parametrize(
    ("wire_value", "error"),
    [
        ("e\u0301", "NFC normalization"),
        ((2**53), "authority integer bound"),
        (0.5, "floating-point"),
        (object(), "unsupported wire value"),
    ],
)
def test_commit_event_id_rejects_noncanonical_wire_values(
    wire_value: object,
    error: str,
) -> None:
    event = _attested()
    lineage = deepcopy(event.lineage)
    lineage["record_payload"]["adversarial"] = wire_value

    with pytest.raises(ValueError, match=error):
        commit_trace_event_id(
            event_type=event.event_type,
            protocol_id=event.protocol_id,
            target=event.target,
            reason=event.reason,
            lineage=lineage,
        )


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("payload-version", "unsupported value"),
        ("record-ref", "record_ref does not bind"),
        ("self-reference", "attestation_fingerprint does not bind"),
        ("event-id", "event_id does not bind"),
    ],
)
def test_commit_version_and_fingerprint_bindings_fail_closed(
    mutation: str,
    error: str,
) -> None:
    event = _attested()
    if mutation == "payload-version":
        malformed = _rebind_commit_event(
            event,
            {"payload_version": "pheroos-commit-trace-payload-v999"},
        )
    elif mutation == "record-ref":
        malformed = _rebind_commit_event(
            event,
            {"record_ref": root("record:forged")},
        )
    elif mutation == "self-reference":
        malformed = _rebind_commit_event(
            event,
            {"attestation_fingerprint": root("attestation:forged")},
        )
    else:
        lineage = deepcopy(event.lineage)
        lineage["event_id"] = root("event:forged")
        malformed = TraceEvent(
            event_type=event.event_type,
            protocol_id=event.protocol_id,
            target=event.target,
            reason=event.reason,
            lineage=lineage,
        )

    with pytest.raises(ValueError, match=error):
        malformed.validate()


def test_commit_record_binding_wraps_noncanonical_wire_payload() -> None:
    event = _attested()
    lineage = deepcopy(event.lineage)
    lineage["record_payload"]["adversarial"] = 0.5
    malformed = TraceEvent(
        event_type=event.event_type,
        protocol_id=event.protocol_id,
        target=event.target,
        reason=event.reason,
        lineage=lineage,
    )

    with pytest.raises(ValueError, match="record payload is invalid.*floating-point"):
        malformed.validate()


@pytest.mark.parametrize(
    ("event_type", "updates", "error"),
    [
        ("action_permission_issued", {"allowed": 1}, "must be a boolean"),
        ("principal_attested", {"principal_id": ""}, "non-blank NFC string"),
        ("principal_attested", {"manifest_root": "not-a-root"}, "sha256 fingerprint"),
        ("principal_attested", {"step": True}, "nonnegative exact integer"),
        (
            "commit_metrics",
            {"margin": 2**53},
            "bounded exact integer",
        ),
        (
            "decision_outcome",
            {"reason_codes": ("not", "a", "json-array")},
            "must be a JSON array",
        ),
        ("principal_attested", {"record_payload": []}, "must be a JSON object"),
        ("principal_attested", {"extensions": []}, "extensions must be an object"),
        (
            "principal_attested",
            {"extensions": {"observer": "unknown"}},
            "extension key must be namespaced",
        ),
    ],
)
def test_commit_declared_field_types_are_exact_and_fail_closed(
    event_type: str,
    updates: dict[str, object],
    error: str,
) -> None:
    event = make_event(event_type)
    lineage = deepcopy(event.lineage)
    lineage.update(updates)
    malformed = TraceEvent(
        event_type=event.event_type,
        protocol_id=event.protocol_id,
        target=event.target,
        reason=event.reason,
        lineage=lineage,
    )

    with pytest.raises(ValueError, match=error):
        malformed.validate()


def test_commit_public_validators_fail_closed_for_unknown_or_nonobject_lineage() -> (
    None
):
    assert commit_trace_required_fields("commit:unknown") == frozenset()

    with pytest.raises(ValueError, match="unsupported commit trace event type"):
        validate_commit_trace_event(
            event_type="commit:unknown",
            protocol_id=PROTOCOL,
            target=TARGET,
            reason="unknown contract",
            lineage={},
        )
    with pytest.raises(ValueError, match="lineage must be a JSON object"):
        validate_commit_trace_event(
            event_type="principal_attested",
            protocol_id=PROTOCOL,
            target=TARGET,
            reason="non-object lineage",
            lineage=cast(Mapping[str, object], []),
        )


@pytest.mark.parametrize(
    ("protocol_id", "target", "reason", "error"),
    [
        ("", TARGET, "reason", "protocol_id is required"),
        (PROTOCOL, "", "reason", "target is required"),
        (PROTOCOL, TARGET, "", "reason is required"),
    ],
)
def test_commit_trace_envelope_text_is_mandatory(
    protocol_id: str,
    target: str,
    reason: str,
    error: str,
) -> None:
    event = _attested()

    with pytest.raises(ValueError, match=error):
        validate_commit_trace_event(
            event_type=event.event_type,
            protocol_id=protocol_id,
            target=target,
            reason=reason,
            lineage=event.lineage,
        )


def test_commit_record_payload_detail_mismatch_fails_closed() -> None:
    with pytest.raises(ValueError, match="risk_band does not match record_payload"):
        _build_commit_event(
            "risk_assessed",
            details={
                "risk_band": "HIGH",
                "threshold_ref": root("threshold:high"),
                "risk_chain_revision": 1,
            },
            payload_updates={"risk_band": "LOW"},
        )


def test_commit_canonical_sequence_order_is_mandatory() -> None:
    event = make_event("certificate_conflict")
    reversed_roots = list(reversed(event.lineage["commit_value_roots"]))
    malformed = _rebind_commit_event(
        event,
        {"commit_value_roots": reversed_roots},
    )

    with pytest.raises(ValueError, match="canonical set ordering|canonical ordering"):
        malformed.validate()


def test_commit_replay_requires_canonical_events_and_one_identity() -> None:
    with pytest.raises(ValueError, match="canonical TraceEvent"):
        replay_commit_trace(
            (SimpleNamespace(event_type="principal_attested"),),
            require_complete=False,
        )

    first = _attested(run_id="run:first", nonce="nonce:first")
    second = _attested(run_id="run:second", nonce="nonce:second")
    with pytest.raises(ValueError, match="mixes protocol/run/target/profile/epoch"):
        replay_commit_trace((first, second), require_complete=False)


def test_commit_replay_rejects_step_regression_and_missing_predecessors() -> None:
    later = _attested(step=2, nonce="nonce:later")
    earlier = _attested(step=1, nonce="nonce:earlier")
    with pytest.raises(ValueError, match="steps must be nondecreasing"):
        replay_commit_trace((later, earlier), require_complete=False)

    unseen = make_event(
        "principal_verified",
        previous=(),
    )
    unseen = _rebind_commit_event(
        unseen,
        {"previous_event_ids": [root("event:unseen")]},
    )
    with pytest.raises(ValueError, match="unseen predecessor"):
        replay_commit_trace((unseen,), require_complete=False)

    risk = make_event("risk_assessed")
    wrong_predecessor = make_event("principal_verified", previous=(risk,))
    with pytest.raises(ValueError, match="lacks required predecessor type"):
        replay_commit_trace((risk, wrong_predecessor), require_complete=False)


def test_commit_replay_rejects_same_id_with_changed_extensions() -> None:
    first = _attested(extensions={"x-observer": "one"})
    changed = _attested(extensions={"x-observer": "two"})
    assert first.lineage["event_id"] == changed.lineage["event_id"]

    with pytest.raises(ValueError, match="event id replay changed its payload"):
        replay_commit_trace((first, changed), require_complete=False)


def test_commit_replay_is_idempotent_for_exact_duplicate_events() -> None:
    event = _attested()

    replay = replay_commit_trace((event, event), require_complete=False)

    assert replay.event_ids == (event.lineage["event_id"],)


def test_commit_replay_requires_a_commit_record_and_terminal_completion() -> None:
    with pytest.raises(ValueError, match="requires at least one commit event"):
        replay_commit_trace(
            (SimpleNamespace(event_type="diagnostic"),),
            require_complete=False,
        )

    with pytest.raises(ValueError, match="not terminally complete"):
        replay_commit_trace((_attested(),))


def _window_chain() -> tuple[TraceEvent, ...]:
    attested = make_event("principal_attested")
    verified = make_event("principal_verified", previous=(attested,))
    risk = make_event("risk_assessed")
    membership = make_event("membership_snapshot", previous=(verified,))
    recorded = make_event("observation_recorded", previous=(attested,))
    observation = make_event("observation_verified", previous=(recorded, verified))
    challenge = make_event("challenge_recorded", previous=(verified,))
    evidence = make_event("evidence_bound", previous=(observation, challenge))
    lease = make_event(
        "support_lease_issued",
        previous=(evidence, verified, membership),
    )
    stop = make_event("stop_resolution_verified")
    permission = make_event("action_permission_issued")
    metrics = make_event(
        "commit_metrics",
        previous=(evidence, lease, risk, membership, stop, permission),
    )
    window = make_event("commit_window_advanced", previous=(metrics,), step=2)
    return (
        attested,
        verified,
        risk,
        membership,
        recorded,
        observation,
        challenge,
        evidence,
        lease,
        stop,
        permission,
        metrics,
        window,
    )


def _certificate(
    window: TraceEvent,
    *,
    tag: str,
    kind: str = "evidence_commit",
    commit_value_root: str | None = None,
) -> TraceEvent:
    details: dict[str, object] = {
        "certificate_kind": kind,
        "candidate_id": "candidate:alpha",
        "claim_fingerprint": root(f"claim:{tag}"),
        "output_fingerprint": root(f"output:{tag}"),
        "final": True,
    }
    if commit_value_root is not None:
        details["commit_value_root"] = commit_value_root
    return _build_commit_event(
        "commit_certificate_issued",
        details=details,
        previous=(window,),
        step=2,
        record_tag=tag,
    )


def _witness(
    certificate: TraceEvent,
    *,
    proposal: str,
    value: str,
) -> TraceEvent:
    return _build_commit_event(
        "quorum_witness",
        details={
            "commit_value_root": value,
            "proposal_digest": proposal,
            "principal_cluster_id": "cluster:a",
            "failure_domain": "domain:a",
            "verified": True,
            "expires_at_step": 10,
        },
        previous=(certificate,),
        step=2,
        record_tag=f"witness:{proposal}",
    )


def _provisional(
    previous: TraceEvent,
    *,
    portable_ref: str,
    witness_count: int,
    proposal: str | None = None,
    value: str | None = None,
) -> TraceEvent:
    details: dict[str, object] = {
        "portable_certificate_ref": portable_ref,
        "candidate_id": "candidate:alpha",
        "witness_count": witness_count,
        "witness_quorum": 3,
        "final": False,
    }
    if proposal is not None:
        details["proposal_digest"] = proposal
    if value is not None:
        details["commit_value_root"] = value
    return _build_commit_event(
        "commit_provisional",
        details=details,
        previous=(previous,),
        step=2,
        record_tag=f"provisional:{witness_count}:{proposal}",
    )


def test_provisional_replay_requires_witness_predecessor_for_witness_count() -> None:
    chain = _window_chain()
    certificate = _certificate(chain[-1], tag="portable")
    provisional = _provisional(
        certificate,
        portable_ref=certificate.lineage["certificate_ref"],
        witness_count=1,
        proposal=root("proposal:alpha"),
        value=root("value:alpha"),
    )

    with pytest.raises(ValueError, match="requires a quorum witness predecessor"):
        replay_commit_trace((*chain, certificate, provisional), require_complete=False)


def test_provisional_replay_binds_exact_witness_value_and_portable_certificate() -> (
    None
):
    chain = _window_chain()
    certificate = _certificate(chain[-1], tag="portable")
    proposal = root("proposal:alpha")
    value = root("value:alpha")
    witness = _witness(certificate, proposal=proposal, value=value)
    mismatched = _provisional(
        witness,
        portable_ref=certificate.lineage["certificate_ref"],
        witness_count=1,
        proposal=root("proposal:other"),
        value=value,
    )
    with pytest.raises(ValueError, match="lacks its exact proposal/value witness"):
        replay_commit_trace(
            (*chain, certificate, witness, mismatched),
            require_complete=False,
        )

    missing_portable = _provisional(
        witness,
        portable_ref=root("certificate:missing"),
        witness_count=1,
        proposal=proposal,
        value=value,
    )
    with pytest.raises(ValueError, match="lacks its exact portable certificate"):
        replay_commit_trace(
            (*chain, certificate, witness, missing_portable),
            require_complete=False,
        )


def test_zero_witness_provisional_must_directly_bind_its_portable_certificate() -> None:
    chain = _window_chain()
    portable = _certificate(chain[-1], tag="portable")
    other = _certificate(chain[-1], tag="other")
    provisional = _provisional(
        other,
        portable_ref=portable.lineage["certificate_ref"],
        witness_count=0,
    )

    with pytest.raises(ValueError, match="must directly depend"):
        replay_commit_trace(
            (*chain, portable, other, provisional),
            require_complete=False,
        )


def _distributed_conflict(
    certificates: tuple[TraceEvent, ...],
    *,
    roots: list[str],
) -> TraceEvent:
    return _build_commit_event(
        "certificate_conflict",
        details={
            "finding_id": "conflict:adversarial",
            "commit_value_roots": roots,
            "left_certificate_ref": certificates[0].lineage["certificate_ref"],
            "right_certificate_ref": certificates[1].lineage["certificate_ref"],
            "distributed_state_ref": root("distributed:frozen"),
            "frozen": True,
        },
        previous=certificates,
        step=2,
        record_tag="conflict",
    )


def test_conflict_replay_requires_both_certificate_lineages_and_exact_values() -> None:
    chain = _window_chain()
    left_value = root("commit-value:left")
    right_value = root("commit-value:right")
    left = _certificate(
        chain[-1],
        tag="left",
        kind="distributed_commit",
        commit_value_root=left_value,
    )
    right = _certificate(
        chain[-1],
        tag="right",
        kind="distributed_commit",
        commit_value_root=right_value,
    )
    missing_lineage = _distributed_conflict(
        (left, right),
        roots=sorted([left_value, right_value]),
    )
    missing_lineage = _rebind_commit_event(
        missing_lineage,
        {"previous_event_ids": [left.lineage["event_id"]]},
    )
    with pytest.raises(ValueError, match="lacks both distributed certificate lineages"):
        replay_commit_trace(
            (*chain, left, right, missing_lineage),
            require_complete=False,
        )

    wrong_values = _distributed_conflict(
        (left, right),
        roots=sorted([left_value, root("commit-value:third")]),
    )
    with pytest.raises(ValueError, match="commit values do not match"):
        replay_commit_trace(
            (*chain, left, right, wrong_values),
            require_complete=False,
        )


def _terminal_pair(
    *,
    kind: str = "safe_fallback",
    deliver: bool = True,
    publish: bool = False,
    execute: bool = False,
    outcome_ref: str | None = None,
    outcome_tag: str = "",
    output_tag: str = "",
) -> tuple[TraceEvent, TraceEvent]:
    outcome = make_event(
        "decision_outcome",
        details={
            "kind": kind,
            "authoritative_commit": False,
            "epistemically_committed": False,
            "candidate_id": "candidate:safe",
            "reason_codes": [f"terminal_{kind}{outcome_tag}"],
        },
    )
    output = make_event(
        "output_decided",
        previous=(outcome,),
        details={
            "outcome_ref": outcome_ref or outcome.lineage["outcome_ref"],
            "deliver": deliver,
            "publish": publish,
            "execute": execute,
            "reason_codes": [f"deliver_{kind}{output_tag}"],
        },
    )
    return outcome, output


@pytest.mark.parametrize(
    ("kind", "deliver", "publish", "execute", "error"),
    [
        (
            "safe_fallback",
            False,
            False,
            False,
            "terminal commit outcome must be deliverable",
        ),
        (
            "safe_fallback",
            True,
            False,
            True,
            "non-commit terminal outcome cannot authorize execute",
        ),
        (
            "blocked",
            True,
            True,
            False,
            "cannot publish an authoritative result",
        ),
    ],
)
def test_terminal_output_authority_fails_closed(
    kind: str,
    deliver: bool,
    publish: bool,
    execute: bool,
    error: str,
) -> None:
    outcome, output = _terminal_pair(
        kind=kind,
        deliver=deliver,
        publish=publish,
        execute=execute,
    )

    with pytest.raises(ValueError, match=error):
        replay_commit_trace((outcome, output))


def test_terminal_replay_rejects_wrong_reference_nonfinal_output_and_duplicates() -> (
    None
):
    outcome, wrong_ref = _terminal_pair(outcome_ref=root("outcome:other"))
    with pytest.raises(ValueError, match="does not reference the terminal outcome"):
        replay_commit_trace((outcome, wrong_ref))

    outcome, output = _terminal_pair()
    trailing = _attested(reason_tag=":trailing")
    with pytest.raises(ValueError, match="must be the final commit trace event"):
        replay_commit_trace((outcome, output, trailing))

    first_outcome, _ = _terminal_pair(outcome_tag=":one")
    second_outcome, _ = _terminal_pair(outcome_tag=":two")
    with pytest.raises(ValueError, match="multiple terminal outcomes"):
        replay_commit_trace(
            (first_outcome, second_outcome),
            require_complete=False,
        )

    outcome, first_output = _terminal_pair(output_tag=":one")
    _, second_output = _terminal_pair(output_tag=":two")
    second_output = _rebind_commit_event(
        second_output,
        {
            "outcome_ref": outcome.lineage["outcome_ref"],
            "previous_event_ids": [outcome.lineage["event_id"]],
        },
    )
    with pytest.raises(ValueError, match="multiple terminal outputs"):
        replay_commit_trace((outcome, first_output, second_output))


@pytest.mark.parametrize(
    ("kind", "error"),
    [
        ("evidence_commit", "lacks a stable window"),
        ("safety_violation", "lacks a certificate conflict"),
        ("finality_unavailable", "lacks pending finality lineage"),
    ],
)
def test_terminal_outcomes_require_declared_authority_lineage(
    kind: str,
    error: str,
) -> None:
    details: dict[str, object] = {
        "kind": kind,
        "authoritative_commit": kind == "evidence_commit",
        "epistemically_committed": kind == "evidence_commit",
        "candidate_id": "candidate:alpha",
        "reason_codes": [f"terminal_{kind}"],
    }
    if kind == "evidence_commit":
        details["certificate_ref"] = root("certificate:untraced")
    outcome = make_event("decision_outcome", details=details)

    with pytest.raises(ValueError, match=error):
        replay_commit_trace((outcome,), require_complete=False)


def _evidence_outcome(
    certificate_ref: str,
    *,
    step: int = 2,
) -> TraceEvent:
    return make_event(
        "decision_outcome",
        step=step,
        details={
            "kind": "evidence_commit",
            "authoritative_commit": True,
            "epistemically_committed": True,
            "candidate_id": "candidate:alpha",
            "reason_codes": ["stable_evidence_commit"],
            "certificate_ref": certificate_ref,
        },
    )


def test_evidence_terminal_path_requires_certificate_and_traced_reference() -> None:
    chain = _window_chain()
    untraced_ref = root("certificate:untraced")
    without_certificate = _evidence_outcome(untraced_ref)
    with pytest.raises(ValueError, match="lacks a certificate"):
        replay_commit_trace(
            (*chain, without_certificate),
            require_complete=False,
        )

    certificate = _certificate(chain[-1], tag="traced")
    wrong_reference = _evidence_outcome(untraced_ref)
    with pytest.raises(ValueError, match="references an untraced certificate"):
        replay_commit_trace(
            (*chain, certificate, wrong_reference),
            require_complete=False,
        )


def test_evidence_output_certificate_must_match_terminal_outcome() -> None:
    chain = _window_chain()
    certificate = _certificate(chain[-1], tag="terminal")
    outcome = _evidence_outcome(certificate.lineage["certificate_ref"])
    output = make_event(
        "output_decided",
        previous=(outcome,),
        step=2,
        details={
            "outcome_ref": outcome.lineage["outcome_ref"],
            "deliver": True,
            "publish": True,
            "execute": False,
            "reason_codes": ["publish_authorized"],
            "certificate_ref": root("certificate:other"),
        },
    )

    with pytest.raises(ValueError, match="certificate does not match its outcome"):
        replay_commit_trace((*chain, certificate, outcome, output))


def test_replay_ignores_noncommit_records_without_weakening_commit_validation() -> None:
    attested = _attested()

    replay = replay_commit_trace(
        (SimpleNamespace(event_type="diagnostic"), attested),
        require_complete=False,
    )

    assert replay.event_ids == (attested.lineage["event_id"],)
