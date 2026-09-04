from __future__ import annotations

import json
from pathlib import Path

from pheroos_bench.codec import encode
from pheroos_bench.config import load_config
from pheroos_bench.simulation import run_once
from pheroos_bench.stats import summarize


ROOT = Path(__file__).resolve().parents[1]


def test_config_freezes_density_codec_and_void_pilot() -> None:
    config = load_config(ROOT / "experiment.json")
    assert config.densities == (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35)
    assert config.raw["codec"]["name"] == "canonical-json-v1"
    assert config.raw["pilot"]["counts_toward_verdict"] is False
    assert config.raw["pilot"]["must_be_discarded"] is True


def test_codec_is_canonical_and_all_event_fields_are_present() -> None:
    value = {"value": 1.0, "kind": "observation", "agent": 1, "route": 2, "step": 0, "target": None, "cost": 0.5}
    assert encode(value) == encode({key: value[key] for key in reversed(tuple(value))})
    assert b"\n" not in encode(value)


def test_wire_values_use_one_route_value_granularity() -> None:
    from pheroos_bench.simulation import _event, _wire_value

    event = _event(kind="field_write", step=1, agent=2, value=_wire_value(3, 0.5))
    assert set(event) == {"agent", "cost", "kind", "route", "step", "target", "value"}
    assert event["route"] is None
    assert event["value"] == [[3, 0.5]]


def test_run_is_deterministic_and_counts_field_writes() -> None:
    first = run_once(arm="field_local", density=0.10, seed=11, steps=40)
    second = run_once(arm="field_local", density=0.10, seed=11, steps=40)
    assert first.to_dict() == second.to_dict()
    assert first.writes > 0
    assert first.reads > 0
    assert first.failed_writes == 0


def test_summarizer_requires_quality_and_primary_ablation_gate() -> None:
    rows = []
    config = load_config(ROOT / "experiment.json").raw
    for density in config["density"]["values"]:
        for seed in range(4):
            common = {"density": density, "seed": seed, "agent_count": 20, "messages": 100, "bytes": 1000, "reads": 1, "writes": 1, "failed_writes": 0, "shock_recovery_steps": 2, "spof_recovery_steps": 2, "final_best_share": 0.9}
            rows.append({**common, "arm": "centralized_online", "final_regret": 0.08})
            rows.append({**common, "arm": "field_local", "final_regret": 0.07, "bytes": 600, "spof_recovery_steps": 1})
            rows.append({**common, "arm": "stateless_local_aggregate", "final_regret": 0.10})
            rows.append({**common, "arm": "random_local", "final_regret": 0.4})
            rows.append({**common, "arm": "greedy_local", "final_regret": 0.12})
    summary, verdict = summarize(rows, config)
    assert summary
    assert verdict["status"] == "PASS_SWARM_CLAIM"
