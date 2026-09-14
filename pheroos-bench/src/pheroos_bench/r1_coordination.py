"""Experimental R1 v2: finite, provider-free coordination; pilot only."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import platform
import random
from statistics import fmean

from .r1_signals import CASES, Meter as StageMeter, Signal, world


ARMS = ("full_relevant", "dedup_ttl", "source_version_ttl", "matched_sparse_random",
        "candidate", "no_dedup", "no_relevance", "no_reactivation")
CONTROL_KINDS = {"constraint", "stop", "cancel", "denied"}
CONFIG_FIELDS = {"schema", "phase", "counts_toward_verdict", "agents", "tasks",
                 "sources", "steps", "ttl", "replicas_per_step", "stale_probability",
                 "source_accuracy", "data_delivery_cap_per_step", "pilot_seeds",
                 "arms", "measurement"}


def validate_config(config: dict) -> None:
    if not isinstance(config, dict) or set(config) != CONFIG_FIELDS:
        raise ValueError("invalid_config_fields")
    if (config["schema"] != "r1_coordination_config_v2" or config["phase"] != "pilot"
            or config["counts_toward_verdict"] is not False):
        raise ValueError("R1 v2 supports non-confirmatory pilot only")
    for key in ("agents", "tasks", "sources", "steps", "ttl"):
        if type(config[key]) is not int or config[key] < 1:
            raise ValueError(f"invalid_{key}")
    if config["tasks"] < 3 or config["steps"] < 15 or config["agents"] % config["tasks"]:
        raise ValueError("dimensions violate task/control schedule")
    for key in ("replicas_per_step", "data_delivery_cap_per_step"):
        if type(config[key]) is not int or config[key] < 0:
            raise ValueError(f"invalid_{key}")
    for key in ("stale_probability", "source_accuracy"):
        if type(config[key]) not in (int, float) or not 0 <= config[key] <= 1:
            raise ValueError(f"invalid_{key}")
    seeds = config["pilot_seeds"]
    if (type(seeds) is not list or not seeds
            or any(type(seed) is not int or seed < 0 for seed in seeds)
            or len(set(seeds)) != len(seeds)):
        raise ValueError("invalid_pilot_seeds")
    if config["arms"] != list(ARMS):
        raise ValueError("all fixed baseline and ablation arms required")
    m = config["measurement"]
    if not isinstance(m, dict) or set(m) != {"confidence", "bootstrap_resamples", "seed", "budget_cap"}:
        raise ValueError("invalid_measurement_fields")
    for key, minimum in (("bootstrap_resamples", 1), ("seed", 0), ("budget_cap", 1)):
        if type(m[key]) is not int or m[key] < minimum:
            raise ValueError(f"invalid_measurement_{key}")
    if (type(m["confidence"]) not in (int, float)
            or not math.isfinite(m["confidence"]) or not 0 < m["confidence"] < 1):
        raise ValueError("invalid_measurement_confidence")


class Meter(StageMeter):
    def report(self) -> dict:
        return {**super().report(), "total_accounted_operations": sum(
            value for key, value in self.counts.items() if key.endswith("_operations"))}


class Policy:
    """Trusted provenance/version metadata only; never reads task truth.

    Admission is read-only. Delivery acknowledges suppression state, so a cap
    cannot make an undelivered claim appear to have been consumed.
    """

    def __init__(self, arm: str, ttl: int, meter: Meter) -> None:
        if arm not in ARMS:
            raise ValueError("unknown arm")
        self.arm, self.ttl, self.meter = arm, ttl, meter
        self.seen, self.latest = {}, {}

    def _claim(self, event: Signal, agent: int) -> tuple:
        return (agent, event.scope_ref, event.task_ref, event.subject_ref,
                event.source_ref, event.dependence_group)

    def _key(self, event: Signal, agent: int) -> tuple:
        if self.arm in ("dedup_ttl", "source_version_ttl"):
            key = (agent, event.scope_ref, event.task_ref, event.origin_event_id)
            return key if self.arm == "dedup_ttl" else key + (event.task_version, event.source_version)
        key = self._claim(event, agent)
        return key if self.arm == "no_reactivation" else key + (event.task_version, event.source_version)

    def admit(self, event: Signal, agent: int, tick: int, tasks: int) -> bool:
        relevant = event.scope_ref == "r1" and agent % tasks == event.task_ref
        self.meter.add("routing", [event.signal_id, agent, relevant])
        if event.kind in CONTROL_KINDS:
            return relevant
        if event.kind != "evidence":
            raise ValueError("unknown signal kind")
        if not relevant and self.arm != "no_relevance":
            return False
        if event.expires_at < tick:
            return False
        if self.arm in ("full_relevant", "matched_sparse_random"):
            return True
        if self.arm in ("candidate", "no_dedup", "no_relevance", "no_reactivation"):
            latest = self.meter.read(self.latest, self._claim(event, agent), [0, 0])
            if [event.task_version, event.source_version] < latest:
                return False
        if self.arm == "no_dedup":
            return True
        last = self.meter.read(self.seen, self._key(event, agent), -self.ttl)
        return tick - last >= self.ttl

    def delivered(self, event: Signal, agent: int, tick: int) -> None:
        if event.kind != "evidence" or self.arm in ("full_relevant", "matched_sparse_random"):
            return
        if self.arm != "no_dedup":
            self.meter.write(self.seen, self._key(event, agent), tick)
        if self.arm in ("candidate", "no_dedup", "no_relevance", "no_reactivation"):
            self.meter.write(self.latest, self._claim(event, agent),
                             [event.task_version, event.source_version])


class Receiver:
    """Shared task-bound voting; forwarding does not add independent support."""

    def __init__(self, task: int, meter: Meter) -> None:
        self.task, self.meter = task, meter
        self.sources, self.controls = {}, {}
        self.task_version, self.blocked = 1, False

    def receive(self, event: Signal, tick: int) -> None:
        self.meter.add("state_read", ["binding", self.task, "r1"])
        if event.task_ref != self.task or event.scope_ref != "r1":
            return
        if event.kind in CONTROL_KINDS:
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
        key = (event.subject_ref, event.dependence_group)
        old = self.meter.read(self.sources, key)
        version = [event.task_version, event.source_version]
        if old is None or version > old[:2]:
            self.meter.write(self.sources, key, [*version, event.value, event.expires_at,
                                               event.origin_event_id])

    def answer(self, tick: int) -> int | None:
        self.meter.add("state_read", ["receiver_status", self.task_version, self.blocked])
        values = []
        for key in sorted(self.sources):
            value = self.meter.read(self.sources, key)
            if value[0] == self.task_version and value[3] >= tick:
                values.append(value[2])
        if self.blocked or not values or 2 * sum(values) == len(values):
            return None
        return int(2 * sum(values) > len(values))


def episode(seed: int, arm: str, config: dict, quotas: list[int] | None = None) -> dict:
    meter = Meter()
    row = {"record_version": "r1_coordination_episode_v2", "phase": "pilot",
           "counts_toward_verdict": False, "seed": seed, "arm": arm,
           "case": CASES[seed % len(CASES)], "llm_calls": 0,
           "input_tokens": 0, "output_tokens": 0}
    counts, trajectory, origins, controls, deferred = [], [], set(), 0, 0
    try:
        validate_config(config)
        timeline, scoring_truth, metadata = world(seed, config)
        policy = Policy(arm, config["ttl"], meter)
        receivers = [Receiver(a % config["tasks"], meter) for a in range(config["agents"])]
        rng = random.Random(seed + 90000)
        if arm == "matched_sparse_random" and (
            not isinstance(quotas, list) or len(quotas) != config["steps"]
            or any(type(q) is not int or q < 0 for q in quotas)
        ):
            raise ValueError("matched sparse arm requires complete candidate quotas")
        for tick, events in enumerate(timeline):
            for event in events:
                meter.add("encoding", asdict(event))
            edges = [(agent, event) for event in events for agent in range(config["agents"])]

            def deliver(agent: int, event: Signal) -> None:
                meter.add("delivered", {"recipient": agent, "tick": tick, "signal": asdict(event)})
                receivers[agent].receive(event, tick)
                policy.delivered(event, agent, tick)
                if event.kind == "evidence":
                    origins.add((agent, event.origin_event_id))

            # Control ordering and recipients are common to every arm; no data cap.
            for agent, event in edges:
                if event.kind != "evidence" and policy.admit(event, agent, tick, config["tasks"]):
                    deliver(agent, event)
                    controls += 1
            data = [(agent, event) for agent, event in edges if event.kind == "evidence"]
            if arm == "matched_sparse_random":
                data = [(agent, event) for agent, event in data
                        if policy.admit(event, agent, tick, config["tasks"])]
                meter.add("routing", ["sample", [[a, e.signal_id] for a, e in data], quotas[tick]])
                data = rng.sample(data, min(quotas[tick], len(data)))
            delivered = 0
            for agent, event in data:
                if arm != "matched_sparse_random" and not policy.admit(event, agent, tick, config["tasks"]):
                    continue
                if delivered >= config["data_delivery_cap_per_step"]:
                    deferred += 1
                    continue
                deliver(agent, event)
                delivered += 1
            counts.append(delivered)
            trajectory.append([receiver.answer(tick) for receiver in receivers])
        # Scoring truth crosses no policy/receiver interface.
        quality = [receivers[agent].blocked and answer is None if agent % config["tasks"] == 0
                   else answer == scoring_truth[-1][agent % config["tasks"]]
                   for agent, answer in enumerate(trajectory[-1])]
        delays = {}
        for task, changed_at in metadata["updates"].items():
            delays[str(task)] = next((tick - changed_at for tick in range(changed_at, config["steps"])
                if all(trajectory[tick][a] == scoring_truth[tick][task]
                       for a in range(task, config["agents"], config["tasks"]))), None)
        row.update(status="complete", success=int(all(quality)), agent_accuracy=fmean(quality),
                   final_answers=trajectory[-1], correction_delays=delays,
                   missed_corrections=sum(delay is None for delay in delays.values()),
                   duplicate_deliveries=sum(counts) - len(origins),
                   retained_source_slots=[len(receiver.sources) for receiver in receivers],
                   unknown_cost_units=0)
    except (Exception, KeyboardInterrupt) as exc:
        # Actual stage costs survive measurement errors; incomplete work is not failure=0.
        row.update(status="INVALID_ABORT", success=None, unknown_cost_units=1,
                   error=f"{type(exc).__name__}: {exc}", abort_requested=isinstance(exc, KeyboardInterrupt))
    return {**row, "cost": meter.report(), "controls_delivered": controls,
            "data_deliveries_per_step": counts, "deferred_data_edges": deferred}


def _save(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def main(argv: list[str] | None = None) -> int:
    from .r1_measurement import export_pair

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    rows, comparisons = [], {}
    summary = {"phase": "pilot", "counts_toward_verdict": False, "status": "INVALID_ABORT"}
    try:
        config = json.loads(args.config.read_text(), object_pairs_hook=_strict_object)
        validate_config(config)
        summary["scheduled_episodes"] = len(config["pilot_seeds"]) * len(ARMS)
        root = Path(__file__).resolve().parents[2]
        paths = {"config": args.config.resolve()}
        for name in ("r1_coordination", "r1_signals", "r1_measurement", "r0_measurement", "e3_verdict"):
            paths[f"src/pheroos_bench/{name}.py"] = Path(__file__).with_name(f"{name}.py")
        for name in ("tests/test_r1_coordination.py", "tests/test_r1_measurement.py", "R1-coordination-v2-contract.md"):
            paths[name] = root / name
        frozen = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
        _save(args.output / "freeze.json", {"schema": "r1_coordination_freeze_v2",
              "sha256": frozen, "config": config, "python": platform.python_version(),
              "platform": platform.platform(), "phase": "pilot", "counts_toward_verdict": False})
        with (args.output / "episodes.jsonl").open("x", encoding="utf-8") as stream:
            for seed in config["pilot_seeds"]:
                quotas = None
                for arm in ("candidate", *(arm for arm in ARMS if arm != "candidate")):
                    row = episode(seed, arm, config, quotas)
                    rows.append(row)
                    stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
                    stream.flush()
                    if row["status"] == "complete" and arm == "candidate":
                        quotas = row["data_deliveries_per_step"]
                    if row.get("abort_requested"):
                        raise KeyboardInterrupt
        if any(hashlib.sha256(path.read_bytes()).hexdigest() != frozen[name]
               for name, path in paths.items()):
            summary["freeze_hashes_unchanged"] = False
            raise ValueError("changed frozen inputs")
        for control in ARMS:
            if control == "candidate":
                continue
            bundle = export_pair(rows, config, control)
            directory = args.output / control
            directory.mkdir()
            _save(directory / "config.json", bundle["config"])
            with (directory / "records.jsonl").open("x", encoding="utf-8") as stream:
                for record in bundle["records"]:
                    stream.write(json.dumps(record, sort_keys=True) + "\n")
            _save(directory / "report.json", bundle["report"])
            comparisons[control] = {key: value for key, value in bundle["report"].items()
                                    if key != "source_accounting"}
        unchanged = all(hashlib.sha256(path.read_bytes()).hexdigest() == frozen[name]
                        for name, path in paths.items())
        summary.update(freeze_hashes_unchanged=unchanged, comparisons=comparisons)
        if unchanged and all(report["status"] == "VALID_MEASUREMENT" for report in comparisons.values()):
            summary["arms"] = {}
            for arm in ARMS:
                selected = [row for row in rows if row["arm"] == arm]
                summary["arms"][arm] = {
                    "episodes": len(selected), "successes": sum(row["success"] for row in selected),
                    "mean_data_deliveries": fmean(sum(row["data_deliveries_per_step"]) for row in selected),
                    "mean_duplicate_deliveries": fmean(row["duplicate_deliveries"] for row in selected),
                    "mean_accounted_operations": fmean(row["cost"]["total_accounted_operations"] for row in selected),
                    "mean_accounted_bytes": fmean(row["cost"]["total_accounted_bytes"] for row in selected),
                    "missed_corrections": sum(row["missed_corrections"] for row in selected),
                    "observed_correction_delays": [delay for row in selected
                        for delay in row["correction_delays"].values() if delay is not None],
                }
            summary["status"] = "PILOT_COMPLETE"
        else:
            summary["reason"] = "invalid measurement or changed frozen inputs"
    except (Exception, KeyboardInterrupt) as exc:
        summary["status"] = "INVALID_ABORT"
        summary["reason"] = f"{type(exc).__name__}: {exc}"
    summary.update(episodes=len(rows), invalid_episodes=sum(r["status"] != "complete" for r in rows),
                   known_accounted_operations=sum(r["cost"]["total_accounted_operations"] for r in rows),
                   unknown_cost_units=sum(r["unknown_cost_units"] for r in rows))
    _save(args.output / "summary.json", summary)
    print(json.dumps({key: value for key, value in summary.items() if key not in ("comparisons", "arms")}, sort_keys=True))
    return 0 if summary["status"] == "PILOT_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
