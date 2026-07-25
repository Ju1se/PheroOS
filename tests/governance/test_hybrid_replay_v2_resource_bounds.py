from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy
import json
import pickle
from typing import Any, cast

import pytest

from pheroos.governance._hybrid_replay_v2 import contracts
from pheroos.governance._hybrid_replay_v2.contracts import HybridReplaySnapshotV2
from pheroos.trace import canonical_pheromone_clip_payload
from tests.governance.test_hybrid_replay_v2_contracts import (
    _diffusion_source_trail,
    _snapshot,
    _snapshot_kwargs,
    _snapshot_kwargs_with_diffusion,
)


def _raw_diffusion_receipt(canonical: str) -> dict[str, object]:
    return {
        "kind": "diffusion",
        "event_id": "event-diffusion",
        "payload": {"canonical_causal_payload": canonical},
        "payload_root": "",
    }


def test_resource_constants_close_the_previous_multiplicative_gap() -> None:
    assert contracts.MAX_HYBRID_REPLAY_CAUSAL_PAYLOAD_BYTES_V2 == 256 * 1024
    assert contracts.MAX_HYBRID_REPLAY_TOTAL_CAUSAL_PAYLOAD_BYTES_V2 == 8 * 1024 * 1024
    assert contracts.MAX_HYBRID_REPLAY_TOTAL_LINEAGE_BYTES_V2 == 4 * 1024 * 1024
    assert contracts.MAX_HYBRID_REPLAY_RESOURCE_TEXT_BYTES_V2 == 12 * 1024 * 1024
    assert contracts.MAX_HYBRID_REPLAY_SNAPSHOT_BYTES_V2 == 16 * 1024 * 1024
    assert (
        contracts.MAX_HYBRID_REPLAY_TOTAL_CAUSAL_PAYLOAD_BYTES_V2
        < contracts.MAX_HYBRID_REPLAY_RECEIPTS_V2
        * contracts.MAX_HYBRID_REPLAY_CAUSAL_PAYLOAD_BYTES_V2
    )


def test_single_causal_payload_accepts_exact_bound_before_json_validation() -> None:
    exact = "x" * contracts.MAX_HYBRID_REPLAY_CAUSAL_PAYLOAD_BYTES_V2
    with pytest.raises(ValueError, match="invalid JSON"):
        contracts._load_diffusion_causal_payload(exact)

    over = exact + "x"
    with pytest.raises(ValueError, match="outside its byte bound"):
        contracts._load_diffusion_causal_payload(over)


def test_causal_payload_aggregation_rejects_item_times_size_amplification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_CAUSAL_PAYLOAD_BYTES_V2", 4)
    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_TOTAL_CAUSAL_PAYLOAD_BYTES_V2", 6)
    exact = [_raw_diffusion_receipt("abc"), _raw_diffusion_receipt("def")]
    assert contracts._preflight_causal_payload_bytes_v2(exact) == 6

    over = [_raw_diffusion_receipt("abc"), _raw_diffusion_receipt("defg")]
    with pytest.raises(ValueError, match="aggregate causal payload"):
        contracts._preflight_causal_payload_bytes_v2(over)

    def fail_if_parsed(value: object) -> dict[str, object]:
        del value
        raise AssertionError("aggregate preflight must run before JSON parsing")

    monkeypatch.setattr(contracts, "_load_diffusion_causal_payload", fail_if_parsed)
    empty_index = contracts._TopologyIndexV2(
        subject_keys=frozenset(), subjects_by_key={}, edges_by_key={}
    )
    with pytest.raises(ValueError, match="aggregate causal payload"):
        contracts._freeze_receipts(
            over,
            target_ref="target-a",
            candidates=frozenset(),
            topology_index=empty_index,
            policy={},
        )


def test_valid_causal_envelope_can_exceed_generic_text_leaf_bound() -> None:
    kwargs = _snapshot_kwargs_with_diffusion()
    receipt = kwargs["replay_receipts"][1]["payload"]
    envelope = json.loads(receipt["canonical_causal_payload"])
    source_trail = envelope["payload"]["input"]["source_trail"]
    source_trail["lineage_event_ids"] = [
        f"lineage-{index:03d}-" + ("x" * 96) for index in range(64)
    ]
    canonical = canonical_pheromone_clip_payload(envelope["payload"])
    assert len(canonical.encode("utf-8")) > contracts.MAX_HYBRID_REPLAY_TEXT_BYTES_V2
    assert (
        len(canonical.encode("utf-8"))
        < contracts.MAX_HYBRID_REPLAY_CAUSAL_PAYLOAD_BYTES_V2
    )
    receipt["canonical_causal_payload"] = canonical
    receipt["source_trail_root"] = (
        contracts.hybrid_replay_diffusion_source_trail_root_v2(source_trail)
    )

    snapshot = HybridReplaySnapshotV2(**kwargs)

    frozen_payload = cast(Mapping[str, object], snapshot.replay_receipts[1]["payload"])
    assert frozen_payload["canonical_causal_payload"] == canonical


def test_structural_preflight_accepts_exact_depth_and_node_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nested: object = [[None]]
    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_RESOURCE_DEPTH_V2", 2)
    usage = contracts._preflight_portable_resources_v2(nested)
    assert usage.nodes == 3

    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_RESOURCE_DEPTH_V2", 1)
    with pytest.raises(ValueError, match="depth bound"):
        contracts._preflight_portable_resources_v2(nested)

    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_RESOURCE_DEPTH_V2", 64)
    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_RESOURCE_NODES_V2", 3)
    assert contracts._preflight_portable_resources_v2([None, None]).nodes == 3
    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_RESOURCE_NODES_V2", 2)
    with pytest.raises(ValueError, match="node bound"):
        contracts._preflight_portable_resources_v2([None, None])


def test_frozen_portable_object_honors_the_read_only_mapping_contract() -> None:
    frozen = contracts._FrozenJsonObject((("alpha", ("one", "two")), ("beta", True)))

    assert len(frozen) == 2
    assert tuple(frozen) == ("alpha", "beta")
    assert frozen["alpha"] == ("one", "two")
    with pytest.raises(KeyError, match="missing"):
        frozen["missing"]
    assert deepcopy(frozen) is frozen

    restored = pickle.loads(pickle.dumps(frozen))
    assert type(restored) is contracts._FrozenJsonObject
    assert dict(restored) == dict(frozen)
    with pytest.raises(AttributeError, match="immutable"):
        del restored._items


def test_structural_preflight_counts_non_text_keys_and_rejects_invalid_utf8() -> None:
    usage = contracts._preflight_portable_resources_v2({1: "value"})
    assert usage.nodes == 3
    assert usage.text_bytes == len("value")

    with pytest.raises(ValueError, match="valid UTF-8"):
        contracts._preflight_portable_resources_v2(
            {"lineage_event_refs": ["invalid-\ud800"]}
        )


def test_portable_leaf_validators_reject_exact_type_and_numeric_bound_attacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_TEXT_BYTES_V2", 1)
    with pytest.raises(ValueError, match="text bound"):
        contracts._require_bounded_text("é", "bounded text")
    with pytest.raises(TypeError, match="exact object"):
        contracts._require_exact_mapping([], frozenset(), "mapping")
    with pytest.raises(TypeError, match="exact array"):
        contracts._require_sequence({}, "sequence", maximum=1)
    with pytest.raises(ValueError, match="below its declared bound"):
        contracts._require_binary64((-1.0).hex(), "number", minimum=0.0)
    with pytest.raises(ValueError, match="exceeds its declared bound"):
        contracts._require_binary64((2.0).hex(), "number", maximum=1.0)
    with pytest.raises(ValueError, match="text bound"):
        contracts._freeze_json("é", "leaf")
    with pytest.raises(TypeError, match="canonical hexadecimal text"):
        contracts._freeze_json(1.0, "leaf")
    with pytest.raises(TypeError, match="unsupported portable value"):
        contracts._freeze_json({"unsupported"}, "leaf")

    frozen = contracts._freeze_json({"a": [True, None]}, "mapping")
    assert isinstance(frozen, contracts._FrozenJsonObject)
    assert contracts._thaw_json(frozen) == {"a": [True, None]}


def test_utf8_byte_accounting_enforces_post_encoding_text_and_lineage_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_RESOURCE_TEXT_BYTES_V2", 1)
    usage = contracts._ResourceUsageV2()
    with pytest.raises(ValueError, match="aggregate text"):
        contracts._record_resource_text_v2("é", path="text", lineage=False, usage=usage)

    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_RESOURCE_TEXT_BYTES_V2", 10)
    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_TOTAL_LINEAGE_BYTES_V2", 1)
    usage = contracts._ResourceUsageV2()
    with pytest.raises(ValueError, match="aggregate lineage"):
        contracts._record_resource_text_v2(
            "é", path="lineage", lineage=True, usage=usage
        )


def test_diffusion_causal_leaf_validation_rejects_encoding_and_version_attacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(TypeError, match="must be exact text"):
        contracts._load_diffusion_causal_payload(7)
    with pytest.raises(ValueError, match="valid UTF-8"):
        contracts._load_diffusion_causal_payload("invalid-\ud800")

    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_CAUSAL_PAYLOAD_BYTES_V2", 1)
    with pytest.raises(ValueError, match="outside its byte bound"):
        contracts._load_diffusion_causal_payload("é")

    monkeypatch.setattr(
        contracts, "MAX_HYBRID_REPLAY_CAUSAL_PAYLOAD_BYTES_V2", 256 * 1024
    )
    wrong_version = json.dumps(
        {
            "payload": {"effective": {}, "input": {}, "lifecycle": "diffusion"},
            "version": "pheroos-pheromone-clip-payload-v0",
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    with pytest.raises(ValueError, match="payload version is unsupported"):
        contracts._load_diffusion_causal_payload(wrong_version)


def test_causal_payload_preflight_fails_before_json_for_every_byte_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        contracts._preflight_causal_payload_bytes_v2(
            [{"kind": "diffusion", "payload": 7}]
        )
        == 0
    )
    with pytest.raises(ValueError, match="outside its byte bound"):
        contracts._preflight_causal_payload_bytes_v2(
            [
                {
                    "kind": "diffusion",
                    "payload": {"canonical_causal_payload": ""},
                }
            ]
        )
    with pytest.raises(ValueError, match="valid UTF-8"):
        contracts._preflight_causal_payload_bytes_v2(
            [
                {
                    "kind": "diffusion",
                    "payload": {"canonical_causal_payload": "invalid-\ud800"},
                }
            ]
        )

    item = {
        "kind": "diffusion",
        "payload": {"canonical_causal_payload": "é"},
    }
    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_CAUSAL_PAYLOAD_BYTES_V2", 1)
    with pytest.raises(ValueError, match="outside its byte bound"):
        contracts._preflight_causal_payload_bytes_v2([item])

    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_CAUSAL_PAYLOAD_BYTES_V2", 2)
    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_TOTAL_CAUSAL_PAYLOAD_BYTES_V2", 1)
    with pytest.raises(ValueError, match="aggregate causal payload"):
        contracts._preflight_causal_payload_bytes_v2([item])


def test_diffusion_source_trail_validation_closes_lineage_and_subject_fallbacks() -> (
    None
):
    trail = _diffusion_source_trail()
    trail["ttl_steps"] = 1
    assert contracts.hybrid_replay_diffusion_source_trail_root_v2(trail).startswith(
        "sha256:"
    )

    duplicated = _diffusion_source_trail()
    duplicated["lineage_event_ids"] = ["event-deposit", "event-deposit"]
    with pytest.raises(ValueError, match="lineage is duplicated"):
        contracts.hybrid_replay_diffusion_source_trail_root_v2(duplicated)

    by_candidate = _diffusion_source_trail()
    by_candidate["subject_id"] = ""
    assert contracts._source_trail_subject_key(by_candidate) == (
        "candidate",
        "candidate-a",
    )
    by_route = _diffusion_source_trail()
    by_route.update({"subject_id": "", "candidate_id": "", "route_id": "route-a"})
    assert contracts._source_trail_subject_key(by_route) == ("route", "route-a")
    by_tool = _diffusion_source_trail()
    by_tool.update(
        {"subject_id": "", "candidate_id": "", "route_id": "", "tool_id": "tool-a"}
    )
    assert contracts._source_trail_subject_key(by_tool) == ("tool", "tool-a")
    empty = _diffusion_source_trail()
    empty.update({"subject_id": "", "candidate_id": "", "route_id": "", "tool_id": ""})
    assert contracts._source_trail_subject_key(empty) == ("candidate", "")

    with pytest.raises(ValueError, match="below its declared bound"):
        contracts._require_causal_binary64(-1.0, "causal", minimum=0.0)
    with pytest.raises(ValueError, match="exceeds its declared bound"):
        contracts._require_causal_binary64(2.0, "causal", maximum=1.0)


def test_structural_cycle_fails_before_any_root_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kwargs = _snapshot_kwargs()
    cycle: dict[str, Any] = {}
    cycle["self"] = cycle
    kwargs["overlay"] = cycle

    def fail_if_hashed(*args: object, **kwargs: object) -> str:
        del args, kwargs
        raise AssertionError("preflight must run before root hashing")

    monkeypatch.setattr(contracts, "_compute_root", fail_if_hashed)
    with pytest.raises(ValueError, match="container cycle"):
        HybridReplaySnapshotV2(**kwargs)


def test_aggregate_text_and_lineage_accept_exact_bound_then_reject_one_byte_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_RESOURCE_TEXT_BYTES_V2", 100)
    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_TOTAL_LINEAGE_BYTES_V2", 5)
    exact = {"lineage_event_refs": ["abc", "de"]}
    usage = contracts._preflight_portable_resources_v2(exact)
    assert usage.lineage_bytes == 5

    with pytest.raises(ValueError, match="aggregate lineage"):
        contracts._preflight_portable_resources_v2(
            {"lineage_event_refs": ["abc", "def"]}
        )

    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_TOTAL_LINEAGE_BYTES_V2", 100)
    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_RESOURCE_TEXT_BYTES_V2", 5)
    assert contracts._preflight_portable_resources_v2(["ab", "cde"]).text_bytes == 5
    with pytest.raises(ValueError, match="aggregate text"):
        contracts._preflight_portable_resources_v2(["ab", "cdef"])


def test_final_canonical_snapshot_accepts_exact_bound_and_rejects_one_byte_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot()
    payload = snapshot.to_dict()
    exact_size = len(snapshot.canonical_bytes())
    monkeypatch.setattr(contracts, "MAX_HYBRID_REPLAY_SNAPSHOT_BYTES_V2", exact_size)
    assert HybridReplaySnapshotV2.from_dict(payload).canonical_bytes() == (
        snapshot.canonical_bytes()
    )

    monkeypatch.setattr(
        contracts, "MAX_HYBRID_REPLAY_SNAPSHOT_BYTES_V2", exact_size - 1
    )
    with pytest.raises(ValueError, match="canonical snapshot exceeds"):
        HybridReplaySnapshotV2.from_dict(payload)


def test_topology_is_indexed_once_for_trails_and_all_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builds = 0
    original = contracts._build_topology_index_v2

    class LookupOnlyMapping(Mapping[Any, Any]):
        def __init__(self, values: Mapping[Any, Any]) -> None:
            self._values = values

        def __getitem__(self, key: Any) -> Any:
            return self._values[key]

        def __iter__(self) -> Iterator[Any]:
            raise AssertionError("receipt validation must not scan topology mappings")

        def __len__(self) -> int:
            return len(self._values)

    def counted(
        topology: Mapping[str, object],
    ) -> contracts._TopologyIndexV2:
        nonlocal builds
        builds += 1
        index = original(topology)
        return contracts._TopologyIndexV2(
            subject_keys=index.subject_keys,
            subjects_by_key=LookupOnlyMapping(index.subjects_by_key),
            edges_by_key=LookupOnlyMapping(index.edges_by_key),
        )

    monkeypatch.setattr(contracts, "_build_topology_index_v2", counted)

    HybridReplaySnapshotV2(**_snapshot_kwargs_with_diffusion())

    assert builds == 1
