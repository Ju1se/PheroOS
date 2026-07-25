"""Private Commit TCK reference operations handlers."""

from __future__ import annotations

from typing import Any

from pheroos.conformance._commit_tck.models import (
    integer_value as _integer,
    object_value as _object,
    result as _result,
    text_value as _text,
)

from pheroos.conformance.commit_tck_v2_protocol import (
    CommitTckRequest as _CommitTckRequest,
)

from pheroos.governance.commit_numeric import (
    multiply_scaled,
    scaled_ratio,
)

from pheroos.governance.commit_state import (
    select_terminal_outcome_kind,
)

from pheroos.protocol.commit_wire import (
    canonical_commit_set,
    commit_payload_fingerprint,
)

from pheroos.protocol.manifest import capability_manifest_from_dict

from pheroos.protocol.validation import validate_capability_manifest

from pheroos.trace import (
    make_commit_trace_event,
    replay_commit_trace,
)


def _canonical_fingerprint(vector: _CommitTckRequest) -> dict[str, Any]:
    payload = _object(vector.inputs.get("payload"), "canonical payload")
    schema = _text(vector.inputs.get("schema"), "canonical schema")
    root = commit_payload_fingerprint(
        payload,
        schema=schema,
        profile=vector.profile,
    )
    return _result(roots={"fingerprint": root})


def _canonical_set_fingerprint(vector: _CommitTckRequest) -> dict[str, Any]:
    values = vector.inputs.get("values")
    if not isinstance(values, list):
        raise ValueError("canonical set values must be an array")
    normalized = canonical_commit_set(values)
    root = commit_payload_fingerprint(
        {"values": normalized},
        schema=_text(vector.inputs.get("schema"), "canonical set schema"),
        profile=vector.profile,
    )
    return _result(
        roots={"fingerprint": root},
        outcome={"canonical_values": list(normalized)},
    )


def _fixed_point_multiply(vector: _CommitTckRequest) -> dict[str, Any]:
    left = _integer(vector.inputs.get("left"), "multiply left")
    right = _integer(vector.inputs.get("right"), "multiply right")
    scale = _integer(vector.inputs.get("scale"), "multiply scale")
    return _result(metrics={"value": multiply_scaled(left, right, scale=scale)})


def _fixed_point_ratio(vector: _CommitTckRequest) -> dict[str, Any]:
    numerator = _integer(vector.inputs.get("numerator"), "ratio numerator")
    denominator = _integer(vector.inputs.get("denominator"), "ratio denominator")
    scale = _integer(vector.inputs.get("scale"), "ratio scale")
    return _result(
        metrics={
            "value": scaled_ratio(
                numerator,
                denominator,
                scale=scale,
            )
        }
    )


def _manifest_validation(vector: _CommitTckRequest) -> dict[str, Any]:
    if vector.manifest is None:
        raise ValueError("manifest_validation vector requires manifest")
    try:
        manifest = capability_manifest_from_dict(vector.manifest)
    except Exception as exc:
        return _result(failure_code=f"load:{type(exc).__name__}")
    diagnostics = validate_capability_manifest(manifest)
    errors = sorted(item.code for item in diagnostics if item.level == "error")
    return _result(
        outcome={"valid": not errors, "diagnostic_codes": errors},
        failure_code=(errors[0] if errors else None),
    )


def _terminal_priority(vector: _CommitTckRequest) -> dict[str, Any]:
    inputs = vector.inputs
    kind = select_terminal_outcome_kind(
        invalid=bool(inputs.get("invalid", False)),
        safety_violation=bool(inputs.get("safety_violation", False)),
        blocked=bool(inputs.get("blocked", False)),
        evidence_commit_ready=bool(inputs.get("evidence_commit", False)),
        finality_unavailable=bool(inputs.get("finality_unavailable", False)),
        deadline_reached=bool(inputs.get("deadline_reached", False)),
        deadline_outcome=_text(inputs.get("deadline_outcome"), "deadline outcome"),
    )
    return _result(outcome={"kind": kind.value if kind is not None else None})


def _trace_replay(vector: _CommitTckRequest) -> dict[str, Any]:
    specs = vector.inputs.get("events")
    if not isinstance(specs, list):
        raise ValueError("trace_replay events must be an array")
    aliases: dict[str, Any] = {}
    events: list[Any] = []
    for index, raw in enumerate(specs):
        spec = _object(raw, f"trace event {index}")
        alias = _text(spec.get("alias"), f"trace event {index} alias")
        if alias in aliases:
            raise ValueError("trace replay contains a duplicate alias")
        predecessor_aliases = spec.get("previous", [])
        if not isinstance(predecessor_aliases, list):
            raise ValueError("trace event previous must be an array")
        try:
            previous_ids = [
                aliases[name].lineage["event_id"] for name in predecessor_aliases
            ]
        except KeyError as exc:
            raise ValueError(
                f"trace event references an unseen alias: {exc.args[0]}"
            ) from exc
        event = make_commit_trace_event(
            event_type=_text(spec.get("event_type"), "trace event type"),
            protocol_id=_text(spec.get("protocol_id"), "trace event protocol_id"),
            target=_text(spec.get("target"), "trace event target"),
            reason=_text(spec.get("reason"), "trace event reason"),
            profile=vector.profile,
            assurance=_text(spec.get("assurance"), "trace event assurance"),
            manifest_root=_text(spec.get("manifest_root"), "trace event manifest_root"),
            commit_policy_root=_text(
                spec.get("commit_policy_root"),
                "trace event commit_policy_root",
            ),
            run_id=_text(spec.get("run_id"), "trace event run_id"),
            epoch=_integer(spec.get("epoch"), "trace event epoch"),
            step=_integer(spec.get("step"), "trace event step"),
            record_schema=_text(spec.get("record_schema"), "trace event record_schema"),
            record_payload=_object(
                spec.get("record_payload"), "trace event record_payload"
            ),
            previous_event_ids=previous_ids,
            details=_object(spec.get("details"), "trace event details"),
            extensions=(
                _object(spec["extensions"], "trace event extensions")
                if "extensions" in spec
                else None
            ),
        )
        aliases[alias] = event
        events.append(event)
    replay = replay_commit_trace(
        events,
        require_complete=bool(vector.inputs.get("require_complete", True)),
    )
    return _result(
        roots={
            "event_ids": list(replay.event_ids),
            "record_refs": list(replay.record_refs),
            "outcome_ref": replay.outcome_ref,
            "output_ref": replay.output_ref,
            "certificate_refs": list(replay.certificate_refs),
        },
        outcome={
            "kind": replay.outcome_kind,
            "complete": replay.complete,
        },
        trace_sequence=list(replay.event_types),
    )
