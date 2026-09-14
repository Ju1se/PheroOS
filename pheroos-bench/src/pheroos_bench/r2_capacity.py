"""Retrospective capacity accounting for frozen R2 v1; no new trials."""

from __future__ import annotations

import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import platform
from statistics import fmean

from . import r2_scheduling as r2


METHOD = "r2_capacity_audit_v1"
CONFIG_FIELDS = {"method", "phase", "counts_toward_verdict", "base_commit",
                 "source_results", "source_artifact_sha256"}


def _load(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique)


def _hash(path):
    return sha256(path.read_bytes()).hexdigest()


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def capacity(spec: dict, trace: list[dict]) -> dict:
    """One execute_unit occupies one worker for [tick, tick + 1).

    At each tick the frozen runner removes expired outages, then applies that
    tick's failures, then dispatches/executes. Idle is available minus occupied;
    no worker is held in a dedicated reserve by any frozen policy.
    """
    horizon, workers = spec["horizon"], len(r2.WORKERS)
    _require(type(horizon) is int and horizon > 0, "invalid horizon")
    jobs = {job["id"] for job in spec["jobs"]}
    offline, occupancy, failures, recoveries, ticks = {}, defaultdict(set), [], [], []
    for event in trace:
        kind = event["kind"]
        if kind == "execute_unit":
            tick, worker = event["tick"], event["worker"]
            _require(type(tick) is int and 0 <= tick < horizon, "execution outside horizon")
            _require(type(worker) is int and 0 <= worker < workers, "unknown worker")
            _require(event["task"] in jobs, "unknown task")
            _require(worker not in occupancy[tick], "duplicate worker execution in tick")
            occupancy[tick].add(worker)
        elif kind == "worker_failed":
            failures.append((event["tick"], event["worker"], event["recover_at"]))
        elif kind == "worker_recovered":
            recoveries.append((event["tick"], event["worker"]))
    expected_failures, expected_recoveries = [], []
    for tick in range(horizon):
        for worker, until in list(offline.items()):
            if tick >= until:
                del offline[worker]
                expected_recoveries.append((tick, worker))
        for failed_at, worker, until in spec["failures"]:
            if failed_at == tick:
                _require(type(worker) is int and 0 <= worker < workers, "unknown failed worker")
                offline[worker] = until
                expected_failures.append((tick, worker, until))
        _require(not (set(offline) & occupancy[tick]), "unavailable worker executed")
        available = workers - len(offline)
        busy = len(occupancy[tick])
        ticks.append({"tick": tick, "available": available, "busy": busy,
                      "idle": available - busy, "unavailable": len(offline)})
    _require(failures == expected_failures, "failure trace differs from declared schedule")
    _require(recoveries == expected_recoveries, "recovery trace differs from declared schedule")
    totals = {f"{key}_worker_ticks": sum(tick[key] for tick in ticks)
              for key in ("available", "busy", "idle", "unavailable")}
    total = workers * horizon
    _require(totals["available_worker_ticks"] + totals["unavailable_worker_ticks"] == total,
             "available capacity does not reconcile")
    _require(totals["busy_worker_ticks"] + totals["idle_worker_ticks"] == totals["available_worker_ticks"],
             "occupied capacity does not reconcile")
    return {**totals, "total_worker_ticks": total, "workers": workers,
            "reserve_policy": "none", "dedicated_reserve_worker_ticks": 0,
            "ticks": ticks}


def audit_episode(source: dict) -> dict:
    """Require exact historical episode and trace reproduction before adding metrics."""
    _require(source["status"] == "VALID_DESCRIPTIVE_EPISODE", "invalid historical episode")
    reproduced = r2.run_episode(source["seed"], source["arm"], source["world"], include_trace=True)
    trace = reproduced.pop("trace")
    reproduced["cohort"] = source["cohort"]
    _require(reproduced == source, "historical episode does not reproduce exactly")
    trace_hash = sha256(r2._wire(trace)).hexdigest()
    _require(trace_hash == source["trace_sha256"], "historical trace hash mismatch")
    result = capacity(r2.workload(source["seed"], source["world"]), trace)
    _require(result["busy_worker_ticks"] == source["costs"]["execution_units"],
             "execution cost and occupied capacity disagree")
    _require(source["llm_calls"] == source["input_tokens"] == source["output_tokens"] == 0,
             "source was not provider free")
    return {"method": METHOD, "status": "VALID_CAPACITY_AUDIT", "counts_toward_verdict": False,
            **{key: source[key] for key in ("cohort", "seed", "world", "arm", "trace_sha256", "workload_sha256")},
            "capacity": result, "source_costs": source["costs"], "llm_calls": 0,
            "input_tokens": 0, "output_tokens": 0, "paid_calls": 0,
            "additional_independent_worlds": 0}


def _save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def _inputs(config, root):
    _require(type(config) is dict and set(config) == CONFIG_FIELDS, "invalid config fields")
    _require(config["method"] == METHOD and config["phase"] == "retrospective_audit"
             and config["counts_toward_verdict"] is False, "unsupported audit method or phase")
    directory = root / config["source_results"]
    hashes = config["source_artifact_sha256"]
    _require(type(hashes) is dict and {"freeze.json", "episodes.jsonl"} <= set(hashes),
             "source freeze and records must be pinned")
    paths = {f"historical/{name}": directory / name for name in hashes}
    for name, digest in hashes.items():
        _require(_hash(directory / name) == digest, f"historical artifact hash mismatch: {name}")
    frozen = _load((directory / "freeze.json").read_text())
    _require(frozen["version"] == r2.VERSION, "unsupported historical method")
    for name, digest in frozen["sha256"].items():
        path = root / name
        _require(_hash(path) == digest, f"frozen source hash mismatch: {name}")
        paths[f"historical_source/{name}"] = path
    source_config = frozen["config"]
    rows = [_load(line) for line in (directory / "episodes.jsonl").read_text().splitlines() if line.strip()]
    _require(r2.summarize(rows, source_config)["status"] == "DESCRIPTIVE_ONLY", "invalid historical grid")
    return rows, source_config, paths


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[2]
    rows = []
    summary = {"method": METHOD, "status": "INVALID_ABORT", "counts_toward_verdict": False,
               "phase": "retrospective_audit", "additional_independent_worlds": 0}
    try:
        config = _load(args.config.read_text())
        source, source_config, paths = _inputs(config, root)
        paths.update({"method": Path(__file__), "config": args.config.resolve(),
                      "tests": root / "tests/test_r2_capacity.py",
                      "contract": root / "R2-capacity-v1-contract.md"})
        hashes = {name: _hash(path) for name, path in paths.items()}
        _save(args.output / "freeze.json", {**summary, "status": "FROZEN_PENDING_AUDIT",
              "base_commit": config["base_commit"],
              "source_method": r2.VERSION, "config": config, "sha256": hashes,
              "python": platform.python_version(), "platform": platform.platform()})
        summary.update(expected_episodes=len(source), base_commit=config["base_commit"],
                       source_method=r2.VERSION,
                       existing_seed_counts={cohort: len(source_config[f"{cohort}_seeds"])
                                             for cohort in ("pilot", "evaluation")})
        with (args.output / "episodes.jsonl").open("x", encoding="utf-8") as stream:
            for original in source:
                try:
                    row = audit_episode(original)
                except (Exception, KeyboardInterrupt) as error:
                    row = {"method": METHOD, "status": "INVALID_ABORT", "counts_toward_verdict": False,
                           **{key: original.get(key) for key in ("cohort", "seed", "world", "arm")},
                           "source_costs": original.get("costs"), "capacity_measurement_unknown": True,
                           "error": f"{type(error).__name__}: {error}"}
                    rows.append(row)
                    stream.write(json.dumps(row, sort_keys=True) + "\n")
                    stream.flush()
                    raise
                rows.append(row)
                stream.write(json.dumps(row, sort_keys=True) + "\n")
                stream.flush()
        unchanged = all(_hash(path) == hashes[name] for name, path in paths.items())
        summary["freeze_hashes_unchanged"] = unchanged
        _require(unchanged, "frozen audit inputs changed")
        grouped = defaultdict(list)
        for row in rows:
            grouped[(row["cohort"], row["world"], row["arm"])].append(row)
        summary["groups"] = [{"cohort": cohort, "world": world, "arm": arm, "episodes": len(values),
            **{f"mean_{key}": fmean(row["capacity"][key] for row in values)
               for key in ("total_worker_ticks", "available_worker_ticks", "busy_worker_ticks",
                           "idle_worker_ticks", "unavailable_worker_ticks", "dedicated_reserve_worker_ticks")}}
            for (cohort, world, arm), values in sorted(grouped.items())]
        summary.update(status="VALID_RETROSPECTIVE_AUDIT", paid_calls=0, llm_calls=0,
                       reserve_policy="none", source_costs_preserved=True)
    except (Exception, KeyboardInterrupt) as error:
        summary.update(status="INVALID_ABORT", reason=f"{type(error).__name__}: {error}")
    summary.update(audited_episodes=len(rows), invalid_episodes=sum(row["status"] == "INVALID_ABORT" for row in rows))
    _save(args.output / "summary.json", summary)
    print(json.dumps({key: value for key, value in summary.items() if key != "groups"}, sort_keys=True))
    return 0 if summary["status"] == "VALID_RETROSPECTIVE_AUDIT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
