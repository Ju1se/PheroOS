from __future__ import annotations

import pytest

from pheroos_bench.e2_codec import BYTES_PER_RECORD, encode_direction, encode_record
from pheroos_bench.e2_config import load_e2_config
from pheroos_bench.e2_simulation import (
    assert_initial_invariants,
    gossip_targets_from_snapshot,
    initialize_world,
    run_once,
)
from pheroos_bench.e2_stats import admission_or_abort


def test_e2_freezes_line_graph_scan_and_abort_path() -> None:
    config = load_e2_config()
    assert config.route_count == 128
    assert config.window_offsets == tuple(range(-7, 9))
    assert config.populations == (100, 400, 1600)
    assert config.informed_fractions == (0.02, 0.05, 0.10, 0.20)
    assert config.raw["admission"]["on_fail"] == "sys.exit(1)"


@pytest.mark.parametrize("population", [100, 400, 1600])
@pytest.mark.parametrize("fraction", [0.02, 0.10, 0.20])
def test_one_sided_initialization_invariants(population: int, fraction: float) -> None:
    world = initialize_world(population, fraction, 1007 + population)
    assert_initial_invariants(world)


def test_gossip_uses_synchronous_snapshot() -> None:
    snapshot_best = [10, 20, 30]
    import numpy as np

    best = np.asarray(snapshot_best, dtype=np.int64)
    neighbors = np.asarray([[1, 1, 1, 1], [0, 0, 0, 0], [1, 1, 1, 1]], dtype=np.int64)
    choices = np.zeros(3, dtype=np.int64)
    targets = gossip_targets_from_snapshot(best, neighbors, choices)
    assert targets.tolist() == [20, 10, 20]
    # A caller mutating an output/current state cannot retroactively alter the
    # target selected from the prior snapshot.
    targets[0] = 99
    assert best.tolist() == snapshot_best


def test_e2_codec_is_fixed_width_and_direction_mapping_is_frozen() -> None:
    assert len(encode_record(1599, 499, 127)) == BYTES_PER_RECORD == 6
    assert [encode_direction(value) for value in (-1, 0, 1)] == [0, 1, 2]


def test_treatment_run_is_deterministic_and_counts_each_directed_neighbor_message() -> None:
    first = run_once(arm="couzin", population=100, informed_fraction=0.02, seed=1000, steps=20)
    second = run_once(arm="couzin", population=100, informed_fraction=0.02, seed=1000, steps=20)
    assert first.to_dict() == second.to_dict()
    assert first.messages == 100 * 4 * 20
    assert first.bytes == first.messages * 6


def test_failed_admission_raises_system_exit_before_treatment() -> None:
    config = load_e2_config().raw
    rows = []
    for population in config["scan"]["N"]:
        for fraction in config["scan"]["informed_fraction"]:
            for seed in range(40):
                for arm in ("solitary", "oracle"):
                    rows.append(
                        {
                            "arm": arm,
                            "N": population,
                            "informed_fraction": fraction,
                            "seed": seed,
                            "global_regret": 0.0,
                            "steps_to_first_r_star_adoption": 0,
                            "messages": 0,
                            "bytes": 0,
                        }
                    )
    with pytest.raises(SystemExit) as exc_info:
        admission_or_abort(rows, config)
    assert exc_info.value.code == 1
