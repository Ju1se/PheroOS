from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "experiment-e2.json"


@dataclass(frozen=True)
class E2Config:
    raw: dict[str, Any]

    @property
    def route_count(self) -> int:
        return int(self.raw["geometry"]["route_count"])

    @property
    def window_width(self) -> int:
        return int(self.raw["geometry"]["window_width"])

    @property
    def window_offsets(self) -> tuple[int, ...]:
        lo, hi = (int(v) for v in self.raw["geometry"]["window_offsets"])
        return tuple(range(lo, hi + 1))

    @property
    def steps(self) -> int:
        return int(self.raw["timing"]["steps"])

    @property
    def populations(self) -> tuple[int, ...]:
        return tuple(int(v) for v in self.raw["scan"]["N"])

    @property
    def informed_fractions(self) -> tuple[float, ...]:
        return tuple(float(v) for v in self.raw["scan"]["informed_fraction"])

    @property
    def seeds(self) -> tuple[int, ...]:
        start = 1000
        return tuple(range(start, start + int(self.raw["seeds"]["count"])))

    @property
    def degree(self) -> int:
        return int(self.raw["topology"]["degree"])

    @property
    def bootstrap_resamples(self) -> int:
        return int(self.raw["seeds"]["bootstrap_resamples"])

    def validate(self) -> None:
        geometry = self.raw["geometry"]
        if geometry != {
            "kind": "line",
            "wraparound": False,
            "route_count": 128,
            "route_count_rationale": "64 caused window clipping at the right edge once agents spread to r*+55; clipping is position-dependent bias. Window width and cost distribution unchanged.",
            "window_width": 16,
            "window_offsets": [-7, 8],
            "window_clipping": "none_by_construction",
            "position_bounds": [7, 119],
            "boundary": "absorbing",
        }:
            raise ValueError("E2 line geometry drifted")
        costs = self.raw["costs"]
        if costs != {
            "optimum": 0.80,
            "others": "Uniform(0.95, 1.05)",
            "unique_optimum": True,
            "r_star": "uniform_per_seed in [16, 24]",
            "noise": "none",
            "static_across_run": True,
        }:
            raise ValueError("E2 route-cost distribution drifted")
        initialization = self.raw["initialization"]
        if initialization["rule"] != "one_sided_line_v1" or initialization["M"] != 48:
            raise ValueError("E2 initialization or M drifted")
        if self.window_width != len(self.window_offsets) or self.window_offsets != tuple(range(-7, 9)):
            raise ValueError("window width and offsets must describe exactly 16 routes")
        direction = self.raw["direction"]
        if direction != {
            "definition": "sign(target_position - own_position)",
            "informed_target": "r* (hidden hint)",
            "uninformed_target": "argmin cost over own visible window",
            "zero_allowed": True,
        }:
            raise ValueError("E2 direction semantics drifted")
        topology = self.raw["topology"]
        if topology["kind"] != "random_4_regular" or topology["degree"] != 4:
            raise ValueError("E2 topology must remain a static random 4-regular graph")
        if not topology["static"] or not topology["connected"] or topology["graph_seed"] != "seed ^ 0x4E1607":
            raise ValueError("E2 graph construction drifted")
        if topology["retry_on"] != ["self_loop", "multi_edge", "disconnected"]:
            raise ValueError("E2 graph retry rules drifted")
        if self.raw["omega"] != {"informed": 0.8, "uninformed": 0.2}:
            raise ValueError("E2 omega values drifted")
        if self.steps != 500 or self.raw["timing"]["update"] != "synchronous_snapshot":
            raise ValueError("E2 timing is not frozen")
        if self.populations != (100, 400, 1600) or self.informed_fractions != (0.02, 0.05, 0.10, 0.20):
            raise ValueError("E2 population/fraction sweep drifted")
        seeds = self.raw["seeds"]
        if seeds["count"] != 40 or not seeds["paired_across_arms"]:
            raise ValueError("E2 paired seed count is not frozen")
        if seeds["bootstrap_resamples"] != 10000 or seeds["confidence"] != 0.95 or seeds["method"] != "paired_percentile_bootstrap":
            raise ValueError("E2 bootstrap configuration drifted")
        codec = self.raw["codec"]
        if codec["id"] != "fixed-width-binary-v1" or codec["record"] != "sender:uint16 | step:uint16 | value:uint16":
            raise ValueError("E2 codec identity drifted")
        if codec["bytes_per_record"] != 6 or not codec["all_neighbor_messages_counted"] or codec["free_writes"] != "none":
            raise ValueError("E2 communication accounting drifted")
        admission = self.raw["admission"]
        if admission["arms"] != ["solitary", "oracle"] or not admission["per_cell"]:
            raise ValueError("E2 admission arms drifted")
        if admission["on_fail"] != "sys.exit(1)":
            raise ValueError("admission must abort with sys.exit(1)")
        if admission["abort_means"] != "treatment arms not executed, no verdict produced":
            raise ValueError("admission abort semantics drifted")
        if self.raw["gate"]["primary"] != "upper bound of 95% CI of paired(couzin - gossip) < 0 in at least 2 adjacent informed_fraction cells at the same N":
            raise ValueError("E2 primary gate drifted")
        discipline = self.raw["discipline"]
        if discipline != {
            "single_run": True,
            "thresholds_frozen_before_run": True,
            "prediction_frozen_before_run": True,
            "treatment_arms_never_simulated_during_design": True,
        }:
            raise ValueError("E2 design discipline drifted")


def load_e2_config(path: Path = CONFIG_PATH) -> E2Config:
    config = E2Config(json.loads(path.read_text(encoding="utf-8")))
    config.validate()
    return config
