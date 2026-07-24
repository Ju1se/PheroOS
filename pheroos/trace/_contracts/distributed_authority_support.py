"""Independent canonical helpers for the Distributed Commit Trace ABI."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import cast

from pheroos.trace._contracts.authority import _authority_stream_ref


_CANONICAL_VERSION = "pheroos-authority-canonical-v2"
_SNAPSHOT_SCHEMA = "pheroos-distributed-lane-snapshot-v2"
_STATE_SCHEMA = "pheroos-distributed-lane-state-v2"
_REQUEST_SCHEMA = "pheroos-distributed-advance-request-v2"
_READ_SET_SCHEMA = "pheroos-governance-authority-read-set-v2"
_LIFECYCLE_STREAM = "authority:domain-lifecycle"


def _snapshot_body(
    lineage: dict[str, object],
    lane: str,
    dependencies: list[dict[str, object]],
    counts: dict[str, int],
) -> dict[str, object]:
    return {
        "schema": _SNAPSHOT_SCHEMA,
        "state_schema": _STATE_SCHEMA,
        "canonical_version": _CANONICAL_VERSION,
        "domain_root": lineage["domain_root"],
        "scope_ref": lineage["scope_ref"],
        "protocol_ref": lineage["protocol_ref"],
        "run_ref": lineage["run_ref"],
        "target_ref": lineage["target_ref"],
        "lane": lane,
        "stream_ref": lineage["stream_ref"],
        "mutation_ref": lineage["request_ref"],
        "mutation_issuer_ref": lineage["mutation_issuer_ref"],
        "mutation_kind": lineage["mutation_kind"],
        "transition_id": lineage["transition_id"],
        "revision": counts["revision"],
        "parent_revision": counts["parent_revision"],
        "parent_transition_id": lineage["parent_transition_id"],
        "parent_snapshot_root": lineage["parent_snapshot_root"],
        "current_epoch": counts["current_epoch"],
        "current_step": counts["current_step"],
        "status": lineage["status"],
        "lane_state_root": lineage["lane_state_root"],
        "dependency_roots": [item["dependency_root"] for item in dependencies],
        "dependency_set_root": lineage["dependency_set_root"],
        "reason_codes": lineage["reason_codes"],
        "source_context_root": lineage["source_context_root"],
        "parent_history_root": lineage["parent_history_root"],
        "parent_history_count": counts["parent_history_count"],
        "history_root": lineage["history_root"],
        "history_count": counts["history_count"],
        "snapshot_state_root": lineage["snapshot_state_root"],
    }


def _request_body(
    lineage: dict[str, object], counts: dict[str, int]
) -> dict[str, object]:
    return {
        "schema": _REQUEST_SCHEMA,
        "canonical_version": _CANONICAL_VERSION,
        "domain_root": lineage["domain_root"],
        "scope_ref": lineage["scope_ref"],
        "protocol_ref": lineage["protocol_ref"],
        "run_ref": lineage["run_ref"],
        "target_ref": lineage["target_ref"],
        "observed_epoch": counts["current_epoch"],
        "mutation_ref": lineage["request_ref"],
        "mutation_issuer_ref": lineage["mutation_issuer_ref"],
        "current_step": counts["current_step"],
        "parent_revision": counts["parent_revision"],
        "parent_transition_id": lineage["parent_transition_id"],
        "parent_snapshot_root": lineage["parent_snapshot_root"],
        "snapshot_root": lineage["snapshot_root"],
        "stream_ref": lineage["stream_ref"],
        "transition_id": lineage["transition_id"],
    }


def _read_set_root(
    lineage: dict[str, object], dependencies: list[dict[str, object]]
) -> str:
    binding = cast(dict[str, object], lineage["session_binding"])
    entries = [
        _precondition(
            cast(str, lineage["stream_ref"]),
            cast(int, lineage["parent_revision"]),
            cast(str, lineage["parent_head_root"]),
        ),
        *[
            _precondition(
                cast(str, item["stream_ref"]),
                cast(int, item["revision"]),
                cast(str, item["head_root"]),
            )
            for item in dependencies
        ],
        _precondition(
            _authority_stream_ref(
                "issuer-grant",
                (cast(str, lineage["scope_ref"]), cast(str, lineage["grant_ref"])),
            ),
            cast(int, binding["grant_expected_revision"]),
            cast(str, binding["grant_expected_root"]),
        ),
        _precondition(
            _LIFECYCLE_STREAM,
            cast(int, binding["lifecycle_expected_revision"]),
            cast(str, binding["lifecycle_expected_root"]),
        ),
    ]
    entries.sort(key=lambda item: cast(str, item["stream_ref"]).encode("utf-8"))
    if len({item["stream_ref"] for item in entries}) != len(entries):
        raise ValueError("distributed trace read set streams collide")
    body = {
        "canonical_version": _CANONICAL_VERSION,
        "entries": entries,
        "schema": _READ_SET_SCHEMA,
    }
    return "sha256:" + sha256(_canonical_bytes(body)).hexdigest()


def _required_roles(lane: str) -> frozenset[str]:
    if lane == "epoch":
        return frozenset(
            {
                "membership",
                "principal_verification",
                "proposal",
                "witness",
                "certificate",
            }
        )
    common = {
        "epoch",
        "decision",
        "central_certificate",
        "membership",
        "principal_verification",
    }
    if lane == "proposal":
        return frozenset(common)
    if lane == "witness":
        return frozenset({*common, "proposal"})
    return frozenset({*common, "proposal", "witness"})


def _precondition(stream: str, revision: int, root: str) -> dict[str, object]:
    return {
        "expected_revision": revision,
        "expected_root": root,
        "stream_ref": stream,
    }


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


__all__: tuple[str, ...] = ()
