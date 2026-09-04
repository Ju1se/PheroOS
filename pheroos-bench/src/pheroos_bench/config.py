from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "experiment.json"


@dataclass(frozen=True)
class Config:
    raw: dict[str, Any]

    @property
    def graph_nodes(self) -> int:
        return int(self.raw["environment"]["graph_nodes"])

    @property
    def route_cells(self) -> int:
        return int(self.raw["environment"]["route_cells"])

    @property
    def steps(self) -> int:
        return int(self.raw["environment"]["steps"])

    @property
    def shock_step(self) -> int:
        return int(self.raw["environment"]["shock_step"])

    @property
    def densities(self) -> tuple[float, ...]:
        return tuple(float(x) for x in self.raw["density"]["values"])

    @property
    def confirmatory_seeds(self) -> tuple[int, ...]:
        start = int(self.raw["seeds"]["confirmatory_start"])
        count = int(self.raw["seeds"]["confirmatory_count"])
        return tuple(range(start, start + count))

    @property
    def pilot_seeds(self) -> tuple[int, ...]:
        return tuple(int(x) for x in self.raw["seeds"]["pilot"])

    @property
    def arms(self) -> tuple[str, ...]:
        return tuple(str(x) for x in self.raw["arms"])

    def validate(self) -> None:
        env = self.raw["environment"]
        if env["steps"] <= env["shock_step"]:
            raise ValueError("shock_step must precede the end of the run")
        if env["resource_fault"] != {"start": 300, "steps": 30, "agent_fraction": 0.25}:
            raise ValueError("the symmetric resource fault is frozen")
        if env["coordinator_outage"] != {"start": 330, "steps": 30}:
            raise ValueError("the coordinator outage window is frozen")
        if env["field_store_outage"] != {"start": 330, "steps": 30, "failed_shards": [0]}:
            raise ValueError("the field-store outage window is frozen")
        if env["local_control_outage"] != {"start": 330, "steps": 30, "failed_resource_fraction": 0.25}:
            raise ValueError("the local-control outage window is frozen")
        if len(self.densities) != 7 or self.densities != tuple(sorted(self.densities)):
            raise ValueError("the seven-point density sweep is frozen")
        if self.raw["exploration"] != {"policy": "none", "epsilon": 0.0, "applies_to": "all_arms"}:
            raise ValueError("exploration epsilon must be zero and arm-symmetric")
        if self.raw["codec"] != {
            "name": "canonical-json-v1",
            "sort_keys": True,
            "separators": [",", ":"],
            "ensure_ascii": True,
            "count": "every encoded observation, action, field deposit, field read, and coordinator message",
        }:
            raise ValueError("codec configuration drifted")
        rule = self.raw["decision_rule"]
        if rule["quality_absolute_floor"] <= 0 or rule["quality_absolute_floor"] >= 1:
            raise ValueError("absolute quality floor must be in (0, 1)")
        if rule["required_adjacent_passing_density_points"] != 2:
            raise ValueError("adjacent density gate must remain two points")
        if self.raw["pilot"]["counts_toward_verdict"]:
            raise ValueError("pilot cannot count toward verdict")
        if not self.raw["pilot"]["must_be_discarded"]:
            raise ValueError("pilot must be discarded")


def load_config(path: Path = CONFIG_PATH) -> Config:
    config = Config(json.loads(path.read_text(encoding="utf-8")))
    config.validate()
    return config
