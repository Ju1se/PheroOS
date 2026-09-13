"""Private R1 finite signal experiment; no core ABI and no model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path


ARMS = ("full_relevant", "matched_sparse_random", "source_version_ttl",
        "candidate", "no_reactivation")
CASES = ("no_update", "source_update", "constraint_update", "mixed")


def encoded(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True)
class Signal:
    signal_id: str
    origin_event_id: str
    causal_parent_ids: tuple[str, ...]
    scope_ref: str
    task_ref: int
    task_version: int
    subject_ref: str
    source_ref: str
    source_version: int
    dependence_group: str
    kind: str
    strength: int
    expires_at: int
    supersedes: str | None
    artifact_ref: str | None
    outcome_ref: str | None
    value: int


class Meter:
    def __init__(self) -> None:
        self.counts = {f"{name}_{suffix}": 0 for name in
                       ("delivered", "routing", "encoding", "state_read", "state_write")
                       for suffix in ("operations", "bytes")}

    def add(self, name: str, value: object) -> None:
        self.counts[f"{name}_operations"] += 1
        self.counts[f"{name}_bytes"] += len(encoded(value))

    def read(self, state: dict, key: tuple, default=None):
        value = state.get(key, default)
        self.add("state_read", [key, value])
        return value

    def write(self, state: dict, key: tuple, value: object) -> None:
        self.add("state_write", [key, value])
        state[key] = value

    def report(self) -> dict:
        return {**self.counts, "total_accounted_bytes": sum(
            v for k, v in self.counts.items() if k.endswith("_bytes"))}


class Policy:
    """Only provenance, versions, logical time, and declared task relevance."""

    def __init__(self, arm: str, ttl: int, meter: Meter) -> None:
        self.arm, self.ttl, self.meter = arm, ttl, meter
        self.seen: dict = {}
        self.latest: dict = {}

    def admit(self, event: Signal, agent: int, tick: int, tasks: int) -> bool:
        relevant = agent % tasks == event.task_ref
        self.meter.add("routing", [event.signal_id, agent, relevant])
        if not relevant:
            return False
        if event.kind != "evidence" or self.arm in ARMS[:2]:
            return True
        key = (agent, event.task_ref, event.source_ref, event.subject_ref)
        if self.arm != "no_reactivation":
            key += (event.task_version, event.source_version, event.origin_event_id)
        if self.arm in ("candidate", "no_reactivation"):
            source = (agent, event.task_ref, event.source_ref)
            version = [event.task_version, event.source_version]
            latest = self.meter.read(self.latest, source, [0, 0])
            if version < latest:
                return False
            if version > latest:
                self.meter.write(self.latest, source, version)
        last = self.meter.read(self.seen, key, -self.ttl)
        if tick - last < self.ttl:
            return False
        self.meter.write(self.seen, key, tick)
        return True


class Receiver:
    """All arms use identical independent-source voting and stale guards."""

    def __init__(self, meter: Meter) -> None:
        self.meter, self.sources, self.controls = meter, {}, {}
        self.task_version, self.blocked = 1, False

    def receive(self, event: Signal, tick: int) -> None:
        if event.kind != "evidence":
            self.meter.write(self.controls, (event.signal_id,), event.kind)
            if event.kind == "constraint":
                self.task_version = max(self.task_version, event.task_version)
            else:
                self.blocked = True
            self.meter.add("state_write", ["receiver_status", self.task_version, self.blocked])
            return
        self.meter.add("state_read", ["receiver_status", self.task_version, self.blocked])
        if event.task_version != self.task_version or event.expires_at < tick:
            return
        key = (event.dependence_group,)
        old = self.meter.read(self.sources, key)
        version = [event.task_version, event.source_version]
        if old is None or version > old[:2]:
            self.meter.write(self.sources, key, [*version, event.value, event.origin_event_id])

    def answer(self) -> int | None:
        self.meter.add("state_read", ["receiver_status", self.task_version, self.blocked])
        values = []
        for key in sorted(self.sources):
            value = self.meter.read(self.sources, key)
            if value[0] == self.task_version:
                values.append(value[2])
        if self.blocked or not values or 2 * sum(values) == len(values):
            return None
        return int(2 * sum(values) > len(values))


def world(seed: int, config: dict) -> tuple[list[list[Signal]], list[list[int]], dict]:
    rng = random.Random(seed)
    tasks, steps = config["tasks"], config["steps"]
    case = CASES[seed % len(CASES)]
    truth = [rng.randrange(2) for _ in range(tasks)]
    versions = [[1, 1] for _ in range(tasks)]
    history, current, timeline, truths, updates = [], [], [], [], {}

    def evidence(task: int, source: int, tick: int) -> Signal:
        task_v, source_v = versions[task]
        origin = f"t{task}:s{source}:tv{task_v}:sv{source_v}"
        previous = next((e.origin_event_id for e in reversed(history)
                         if e.task_ref == task and e.source_ref == f"source:{source}"), None)
        value = truth[task] if rng.random() < config["source_accuracy"] else 1 - truth[task]
        return Signal(origin, origin, (), "r1", task, task_v, "binary_state",
                      f"source:{source}", source_v, f"source:{source}", "evidence",
                      1, steps, previous, origin, None, value)

    for tick in range(steps):
        events = []
        changed = list(range(tasks)) if tick == 0 else []
        if tick == 6 and case in ("source_update", "mixed"):
            changed = [1]
            truth[1] = 1 - truth[1]
            versions[1][1] += 1
            updates[1] = tick
        if tick == 8 and case in ("constraint_update", "mixed"):
            changed = [2]
            truth[2] = 1 - truth[2]
            versions[2][0] += 1
            updates[2] = tick
            events.append(Signal("constraint", "constraint", (), "r1", 2, 2,
                                 "constraint", "environment", 1, "environment",
                                 "constraint", 1, steps, None, None, None, 0))
        for task in changed:
            current = [event for event in current if event.task_ref != task]
            fresh = [evidence(task, source, tick) for source in range(config["sources"])]
            current.extend(fresh)
            history.extend(fresh)
            events.extend(fresh)
        # Exposures, order and corruption are fixed before any policy runs.
        for replica in range(config["replicas_per_step"]):
            pool = history if rng.random() < config["stale_probability"] else current
            original = rng.choice(pool)
            events.append(Signal(**{**asdict(original), "signal_id": f"copy:{tick}:{replica}",
                                   "causal_parent_ids": (original.origin_event_id,)}))
        if tick in (12, 13, 14):
            kind = ("stop", "cancel", "denied")[tick - 12]
            events.append(Signal(kind, kind, (), "r1", 0, 1, kind, "authority", 1,
                                 "authority", kind, 1, steps, None, None, None, 0))
        timeline.append(events)
        truths.append(truth.copy())
    return timeline, truths, {"case": case, "updates": updates}


def episode(seed: int, arm: str, config: dict, quotas: list[int] | None = None) -> dict:
    timeline, scoring_truth, metadata = world(seed, config)
    meter = Meter()
    policy = Policy(arm, config["ttl"], meter)
    receivers = [Receiver(meter) for _ in range(config["agents"])]
    rng, counts, trajectory, controls = random.Random(seed + 90000), [], [], 0
    delivered_origins = set()
    for tick, events in enumerate(timeline):
        data, reliable = [], []
        for event in events:
            meter.add("encoding", asdict(event))
            for agent in range(config["agents"]):
                if policy.admit(event, agent, tick, config["tasks"]):
                    (data if event.kind == "evidence" else reliable).append((agent, event))
        if arm == "matched_sparse_random":
            if quotas is None:
                raise ValueError("matched sparse arm requires candidate delivery quotas")
            # Charge serialized index/selection traffic, including rejected edges.
            meter.add("routing", ["sample", [[a, e.signal_id] for a, e in data], quotas[tick]])
            data = rng.sample(data, min(quotas[tick], len(data)))
        data = data[:config["data_delivery_cap_per_step"]]
        counts.append(len(data))
        for agent, event in reliable + data:
            meter.add("delivered", {"recipient": agent, "tick": tick, "signal": asdict(event)})
            receivers[agent].receive(event, tick)
            if event.kind == "evidence":
                delivered_origins.add((agent, event.origin_event_id))
        controls += len(reliable)
        trajectory.append([receiver.answer() for receiver in receivers])
    # Only the scorer below this boundary reads truth; policy/receivers never do.
    quality = [answer is None if agent % config["tasks"] == 0
               else answer == scoring_truth[-1][agent % config["tasks"]]
               for agent, answer in enumerate(trajectory[-1])]
    delays = {}
    for task, changed_at in metadata["updates"].items():
        valid = [tick - changed_at for tick in range(changed_at, config["steps"])
                 if all(trajectory[tick][a] == scoring_truth[tick][task]
                        for a in range(task, config["agents"], config["tasks"]))]
        delays[str(task)] = min(valid) if valid else None
    return {"seed": seed, "arm": arm, **metadata, "status": "complete",
            "success": int(all(quality)), "agent_accuracy": statistics.mean(quality),
            "final_answers": trajectory[-1], "correction_delays": delays,
            "missed_corrections": sum(v is None for v in delays.values()),
            "controls_delivered": controls, "data_deliveries_per_step": counts,
            "duplicate_deliveries": sum(counts) - len(delivered_origins),
            "replicated_delivery_factor": sum(counts) / len(delivered_origins) if delivered_origins else 0,
            "independent_support": [len(r.sources) for r in receivers],
            "cost": meter.report(), "llm_calls": 0, "input_tokens": 0, "output_tokens": 0}


def analyze(rows: list[dict], config: dict | None = None) -> dict:
    keys = [(r["split"], r["seed"], r["arm"]) for r in rows]
    if len(keys) != len(set(keys)):
        return {"status": "INVALID", "reason": "duplicate episode"}
    if config is not None:
        expected = {(split, seed, arm) for split in ("pilot", "evaluation")
                    for seed in config[f"{split}_seeds"] for arm in ARMS}
        if set(keys) != expected:
            return {"status": "INVALID", "reason": "missing or unexpected episode"}
    if any(r["status"] != "complete" for r in rows):
        return {"status": "INVALID", "reason": "episode measurement failed",
                "episodes": len(rows), "errors": sum(r["status"] != "complete" for r in rows)}
    summaries = {}
    for split in ("pilot", "evaluation"):
        selected = [r for r in rows if r["split"] == split]
        summaries[split] = {}
        for case in ("all", *CASES):
            cells = [r for r in selected if case == "all" or r["case"] == case]
            per_arm = {}
            for arm in ARMS:
                arm_rows = [r for r in cells if r["arm"] == arm]
                completed = [r for r in arm_rows if r["status"] == "complete"]
                per_arm[arm] = {"episodes": len(arm_rows), "errors": len(arm_rows) - len(completed),
                    "success_rate": statistics.mean(r["success"] for r in arm_rows),
                    "mean_accounted_bytes": statistics.mean(r["cost"]["total_accounted_bytes"]
                                                           for r in completed) if completed else None,
                    "mean_data_deliveries": statistics.mean(sum(r["data_deliveries_per_step"])
                                                             for r in completed) if completed else None,
                    "mean_duplicate_deliveries": statistics.mean(r["duplicate_deliveries"] for r in completed),
                    "correction_delays_observed": [d for r in completed for d in r["correction_delays"].values()
                                                   if d is not None],
                    "missed_corrections": sum(r["missed_corrections"] for r in completed)}
            candidate = {r["seed"]: r for r in cells if r["arm"] == "candidate"}
            pairs = {}
            for arm in ARMS:
                controls = [r for r in cells if r["arm"] == arm]
                pairs[arm] = {"mean_world_success_difference": statistics.mean(
                    candidate[r["seed"]]["success"] - r["success"] for r in controls),
                    "mean_world_bytes_difference": statistics.mean(
                    candidate[r["seed"]]["cost"]["total_accounted_bytes"] - r["cost"]["total_accounted_bytes"]
                    for r in controls) if all(r["status"] == "complete" and
                    candidate[r["seed"]]["status"] == "complete" for r in controls) else None}
            summaries[split][case] = {"arms": per_arm, "candidate_minus_control": pairs}
    return {"status": "descriptive_frozen_evaluation_not_confirmatory",
            "independent_unit": "world_seed", "summaries": summaries}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.config = args.config.resolve()
    config = json.loads(args.config.read_text())
    if set(config["pilot_seeds"]) & set(config["evaluation_seeds"]):
        raise ValueError("pilot and evaluation seeds overlap")
    if config["agents"] % config["tasks"] or config["tasks"] < 3 or config["steps"] < 15:
        raise ValueError("world dimensions violate the frozen task/control schedule")
    args.output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[2]
    paths = [Path(__file__), args.config, root / "tests/test_r1_signals.py", root / "R1-data-contract.md"]
    frozen = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    freeze = {"schema": "r1_signals_freeze_v1", "sha256": frozen, "config": config,
              "python": platform.python_version(), "platform": platform.platform(),
              "result_class": "pilot_plus_independent_frozen_descriptive_evaluation"}
    with (args.output / "freeze.json").open("x") as stream:
        stream.write(json.dumps(freeze, indent=2) + "\n")
    rows = []
    with (args.output / "episodes.jsonl").open("x") as stream:
        for split in ("pilot", "evaluation"):
            for seed in config[f"{split}_seeds"]:
                candidate = None
                for arm in ("candidate", *[a for a in ARMS if a != "candidate"]):
                    try:
                        row = episode(seed, arm, config, candidate)
                        if arm == "candidate":
                            candidate = row["data_deliveries_per_step"]
                    except Exception as exc:  # Preserve failed pre-registered episodes.
                        row = {"seed": seed, "arm": arm, "case": CASES[seed % 4],
                               "status": "error", "success": 0, "error": repr(exc)}
                    row["split"] = split
                    rows.append(row)
                    stream.write(json.dumps(row, sort_keys=True) + "\n")
                    stream.flush()
    report = analyze(rows, config)
    report["freeze_hashes_unchanged"] = all(hashlib.sha256(p.read_bytes()).hexdigest() ==
                                          frozen[str(p.relative_to(root))] for p in paths)
    report["complete_measurement"] = all(r["status"] == "complete" for r in rows)
    if not report["complete_measurement"] or not report["freeze_hashes_unchanged"]:
        report["status"] = "INVALID"
    with (args.output / "summary.json").open("x") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    return 0 if report["status"] != "INVALID" else 2


if __name__ == "__main__":
    raise SystemExit(main())
