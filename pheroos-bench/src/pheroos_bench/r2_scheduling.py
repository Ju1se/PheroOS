"""Finite R2 scheduling pilot; logical time/costs, no models or runtime claims."""

from __future__ import annotations

import argparse
from collections import defaultdict
from hashlib import sha256
import json
import math
import platform
from pathlib import Path
from random import Random
from statistics import fmean


VERSION = "r2_scheduling_pilot_v1"
ARMS = (
    "capability_fifo", "work_stealing", "priority_queue", "central_manager",
    "congestion_backpressure", "no_backpressure",
)
WORLDS = ("bottleneck_with_failures", "no_contention_no_failure")
WORKERS = ({"compute", "inspect"}, {"compute"}, {"inspect"}, {"compute"})


def _wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def workload(seed: int, world: str) -> dict:
    if type(seed) is not int or seed < 0 or world not in WORLDS:
        raise ValueError("invalid seed or undeclared world")
    random = Random(seed)
    jobs = []
    for chain in range(8):
        arrival = chain * (2 if world == WORLDS[0] else 10)
        arrival += random.randrange(2)
        deadline = arrival + random.randint(9, 15)
        for stage, capability in enumerate(("compute", "inspect", "compute")):
            job_id = f"j{chain:02d}.{stage}"
            jobs.append({
                "id": job_id, "arrival": arrival, "deadline": deadline,
                "capability": capability, "tool": stage == 1,
                "duration": random.randint(2, 4) if stage == 1 else random.randint(1, 2),
                "dependencies": [] if stage == 0 else [f"j{chain:02d}.{stage - 1}"],
                "value": random.randint(1, 9), "feeds_tool": stage == 0,
            })
    return {
        "jobs": jobs, "horizon": 36 if world == WORLDS[0] else 90,
        "tool_capacity": 1,
        "failures": [(7, 0, 12), (17, 2, 21)] if world == WORLDS[0] else [],
    }


def check_results(jobs: list[dict], results: dict) -> bool:
    """Independently recompute exact dependency results, never used by a policy."""
    declarations = {job["id"]: job for job in jobs}
    def expected(job_id):
        job = declarations[job_id]
        return job["value"] + sum(expected(dep) for dep in job["dependencies"])
    return all(
        job_id in declarations and type(value) is int and value == expected(job_id)
        and all(dep in results for dep in declarations[job_id]["dependencies"])
        for job_id, value in results.items()
    )


def simulate(spec: dict, arm: str, *, include_trace: bool = False) -> dict:
    """Run matched nonpreemptive policies; only failures interrupt execution.

    Each tick delivers one identical complete scheduling-state snapshot. Policy
    differences do not pretend to measure distributed network architectures.
    Work stealing means own-queue-first selection with deterministic stealing.
    """
    if arm not in ARMS:
        raise ValueError("undeclared arm")
    jobs = {job["id"]: dict(job) for job in spec["jobs"]}
    if len(jobs) != len(spec["jobs"]) or not jobs:
        raise ValueError("unique nonempty task declarations required")
    for job in jobs.values():
        if (job["duration"] < 1 or job["capability"] not in {"compute", "inspect"}
            or any(dep not in jobs for dep in job["dependencies"])):
            raise ValueError("invalid task declaration")
    state = {key: {"status": "pending", "remaining": job["duration"], "spent": 0,
                  "attempts": 0, "lease": 0, "first_ready": None, "wait": 0,
                  "failed_at": None} for key, job in jobs.items()}
    running, offline, results, completed = {}, {}, {}, {}
    events, costs, recoveries = [], defaultdict(int), []
    pressure_ticks = 0
    horizon = spec["horizon"]
    ordinal = {key: index for index, key in enumerate(sorted(jobs))}

    def emit(kind, tick, **payload):
        event = {"kind": kind, "tick": tick, **payload}
        events.append(event)
        costs["messages"] += 1
        costs["message_bytes"] += len(_wire(event))

    def record_write(value):
        costs["state_record_writes"] += 1
        costs["state_write_bytes"] += len(_wire(value))

    for key, item in state.items():
        record_write([key, item])

    emit("declarations", 0, jobs=list(jobs.values()), workers=[sorted(w) for w in WORKERS],
         horizon=horizon, tool_capacity=spec["tool_capacity"], failures=spec["failures"])
    for tick in range(horizon):
        for worker, until in list(offline.items()):
            if tick >= until:
                del offline[worker]
                record_write(["offline", offline])
                emit("worker_recovered", tick, worker=worker)
        for failure_tick, worker, until in spec["failures"]:
            if failure_tick != tick:
                continue
            offline[worker] = until
            record_write(["offline", offline])
            emit("worker_failed", tick, worker=worker, recover_at=until)
            if worker in running:
                key = running.pop(worker)
                item = state[key]
                costs["duplicate_execution_units"] += item["spent"]
                item.update(status="ready", remaining=jobs[key]["duration"], spent=0,
                            failed_at=tick, lease=item["lease"] + 1)
                record_write([key, item])
                record_write(["running", running])
                emit("lease_revoked", tick, worker=worker, task=key, lease=item["lease"])
        for key, job in jobs.items():
            item = state[key]
            if (item["status"] == "pending" and job["arrival"] <= tick
                and all(dep in results for dep in job["dependencies"])):
                item["status"], item["first_ready"] = "ready", tick
                record_write([key, item])
                emit("task_ready", tick, task=key)
        snapshot = {
            "tick": tick, "offline": sorted(offline), "running": sorted(running.items()),
            "tasks": [{"id": key, "status": item["status"], "remaining": item["remaining"],
                       "lease": item["lease"]} for key, item in state.items()],
        }
        costs["observation_messages"] += 1
        costs["observation_bytes"] += len(_wire(snapshot))
        costs["state_record_reads"] += len(jobs) + len(WORKERS)
        ready = [key for key, item in state.items() if item["status"] == "ready"]
        pressure = False
        if arm == "congestion_backpressure":
            costs["pressure_inspections"] += len(ready)
            pressure = sum(jobs[key]["tool"] for key in ready) >= 2
            pressure_ticks += pressure

        for worker, capabilities in enumerate(WORKERS):
            if worker in offline or worker in running:
                continue
            tool_busy = sum(jobs[key]["tool"] for key in running.values())
            eligible = []
            for key in ready:
                costs["eligibility_inspections"] += 1
                if (jobs[key]["capability"] in capabilities
                    and (not jobs[key]["tool"] or tool_busy < spec["tool_capacity"])):
                    eligible.append(key)
            if not eligible:
                continue
            def priority(key):
                costs["policy_evaluations"] += 1
                job = jobs[key]
                fifo = (job["arrival"], key)
                if arm == "work_stealing":
                    return (ordinal[key] % len(WORKERS) != worker, *fifo)
                if arm == "priority_queue":
                    return (job["deadline"], *fifo)
                if arm == "central_manager":
                    costs["capability_inspections"] += len(WORKERS)
                    scarcity = sum(job["capability"] in c for c in WORKERS)
                    return (scarcity, job["deadline"], *fifo)
                return (bool(pressure and job["feeds_tool"]), *fifo)
            key = min(eligible, key=priority)
            ready.remove(key)
            item = state[key]
            assert key not in running.values()
            assert all(dep in results for dep in jobs[key]["dependencies"])
            item.update(status="running", attempts=item["attempts"] + 1, lease=item["lease"] + 1)
            if item["failed_at"] is not None:
                recoveries.append(tick - item["failed_at"])
                item["failed_at"] = None
            running[worker] = key
            record_write([key, item])
            record_write(["running", running])
            emit("dispatch", tick, worker=worker, task=key, lease=item["lease"])
        # Every idle capable worker must have no currently feasible ready work.
        for worker, capabilities in enumerate(WORKERS):
            if worker not in offline and worker not in running:
                tool_busy = sum(jobs[key]["tool"] for key in running.values())
                assert not any(jobs[key]["capability"] in capabilities and
                               (not jobs[key]["tool"] or tool_busy < spec["tool_capacity"])
                               for key in ready)
        assert len(set(running.values())) == len(running)
        assert sum(jobs[key]["tool"] for key in running.values()) <= spec["tool_capacity"]
        for key in ready:
            state[key]["wait"] += 1
            record_write([key, state[key]])
        for worker, key in list(running.items()):
            item = state[key]
            item["remaining"] -= 1
            item["spent"] += 1
            costs["execution_units"] += 1
            emit("execute_unit", tick, worker=worker, task=key, lease=item["lease"])
            if item["remaining"] == 0:
                value = jobs[key]["value"] + sum(results[dep] for dep in jobs[key]["dependencies"])
                results[key], completed[key] = value, tick + 1
                item["status"] = "done"
                del running[worker]
                record_write(["running", running])
                record_write(["result", key, value, tick + 1])
                emit("completed", tick + 1, worker=worker, task=key, lease=item["lease"], value=value)
            record_write([key, item])
    valid = check_results(list(jobs.values()), results)
    if not valid:
        raise AssertionError("external result verification failed")
    waits = sorted(item["wait"] for item in state.values() if item["first_ready"] is not None)
    late_or_incomplete = sum(key not in completed or completed[key] > job["deadline"] for key, job in jobs.items())
    result = {
        "version": VERSION, "arm": arm, "counts_toward_verdict": False,
        "status": "VALID_DESCRIPTIVE_EPISODE", "declared_tasks": len(jobs),
        "horizon": horizon, "completed_tasks": len(results), "throughput": len(results) / horizon,
        "completion_fraction": len(results) / len(jobs),
        "deadline_completion_fraction": 1 - late_or_incomplete / len(jobs),
        "p95_wait_ticks": waits[math.ceil(len(waits) * .95) - 1] if waits else 0,
        "ready_unfinished_tasks": sum(item["status"] == "ready" for item in state.values()),
        "starvation_proxy_never_started_ready": sum(item["first_ready"] is not None and not item["attempts"] for item in state.values()),
        "blocked_or_unarrived_tasks": sum(item["status"] == "pending" for item in state.values()),
        "duplicate_attempts": sum(max(0, item["attempts"] - 1) for item in state.values()),
        "concurrent_duplicate_work": 0, "pressure_ticks": pressure_ticks,
        "recovery_delay_ticks": recoveries,
        "unrecovered_failed_tasks": sum(item["failed_at"] is not None for item in state.values()),
        "costs": dict(costs), "results": results,
        "workload_sha256": sha256(_wire(spec)).hexdigest(),
        "trace_sha256": sha256(_wire(events)).hexdigest(),
        "input_tokens": 0, "output_tokens": 0, "llm_calls": 0,
    }
    for key in ("duplicate_execution_units", "pressure_inspections", "capability_inspections",
                "policy_evaluations", "eligibility_inspections", "execution_units"):
        result["costs"].setdefault(key, 0)
    result["costs"]["total_logical_scheduler_units"] = sum(result["costs"][key] for key in (
        "state_record_reads", "eligibility_inspections", "policy_evaluations",
        "pressure_inspections", "capability_inspections", "messages", "observation_messages",
        "state_record_writes"))
    result["costs"]["total_communication_bytes"] = costs["message_bytes"] + costs["observation_bytes"]
    result["costs"]["encoding_bytes"] = result["costs"]["total_communication_bytes"] + costs["state_write_bytes"]
    result["costs"]["total_accounted_bytes"] = (result["costs"]["total_communication_bytes"] +
                                                costs["state_write_bytes"] + result["costs"]["encoding_bytes"])
    if include_trace:
        result["trace"] = events
    return result


def run_episode(seed: int, arm: str, world: str = WORLDS[0], *, include_trace=False) -> dict:
    return {**simulate(workload(seed, world), arm, include_trace=include_trace), "seed": seed, "world": world}


def summarize(rows: list[dict], config: dict | None = None) -> dict:
    keys = [(r["cohort"], r["seed"], r["world"], r["arm"]) for r in rows]
    if len(keys) != len(set(keys)) or any(r["status"] != "VALID_DESCRIPTIVE_EPISODE" for r in rows):
        return {"status": "INVALID", "reason": "duplicate or failed measurement", "counts_toward_verdict": False}
    if config is not None:
        expected = {(cohort, seed, world, arm) for cohort in ("pilot", "evaluation")
                    for seed in config[f"{cohort}_seeds"] for world in WORLDS for arm in ARMS}
        if set(keys) != expected:
            return {"status": "INVALID", "reason": "missing or unexpected episode", "counts_toward_verdict": False}
    groups = defaultdict(list)
    for row in rows:
        groups[(row["cohort"], row["world"], row["arm"])].append(row)
    fields = ("throughput", "completion_fraction", "deadline_completion_fraction", "p95_wait_ticks",
              "duplicate_attempts", "starvation_proxy_never_started_ready", "unrecovered_failed_tasks")
    summary = []
    paired = []
    for (cohort, world, arm), values in sorted(groups.items()):
        recovery = [delay for row in values for delay in row["recovery_delay_ticks"]]
        summary.append({
            "cohort": cohort, "world": world, "arm": arm, "n_world_seeds": len(values),
            **{key: fmean(row[key] for row in values) for key in fields},
            "mean_recovery_delay_ticks": fmean(recovery) if recovery else None,
            "reclaimed_task_failures": len(recovery),
            "cost_means": {key: fmean(row["costs"][key] for row in values) for key in values[0]["costs"]},
        })
        candidate = {r["seed"]: r for r in groups[(cohort, world, "congestion_backpressure")]}
        paired.append({"cohort": cohort, "world": world, "control": arm,
                       **{f"mean_difference_{key}": fmean(candidate[r["seed"]][key] - r[key]
                                                         for r in values) for key in fields},
                       "mean_difference_accounted_bytes": fmean(candidate[r["seed"]]["costs"]["total_accounted_bytes"]
                                                                - r["costs"]["total_accounted_bytes"] for r in values)})
    return {"version": VERSION, "status": "DESCRIPTIVE_ONLY", "counts_toward_verdict": False,
            "groups": summary, "paired_candidate_minus_control": paired}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.config = args.config.resolve()
    config = json.loads(args.config.read_text())
    if (config["version"] != VERSION or config["arms"] != list(ARMS)
        or config["worlds"] != list(WORLDS) or config["counts_toward_verdict"] is not False
        or config["pilot_seeds"] != list(range(8)) or config["evaluation_seeds"] != list(range(100, 132))):
        raise ValueError("configuration does not match the frozen pilot contract")
    args.output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[2]
    paths = [Path(__file__), args.config, root / "tests/test_r2_scheduling.py", root / "R2-data-contract.md"]
    hashes = {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest() for p in paths}
    freeze = {"version": VERSION, "sha256": hashes, "config": config,
              "python": platform.python_version(), "platform": platform.platform()}
    with (args.output / "freeze.json").open("x") as stream:
        stream.write(json.dumps(freeze, indent=2) + "\n")
    rows, traces = [], []
    with (args.output / "episodes.jsonl").open("x") as stream:
        for cohort, seeds in (("pilot", config["pilot_seeds"]), ("evaluation", config["evaluation_seeds"])):
            for seed in seeds:
                for world in WORLDS:
                    for arm in ARMS:
                        try:
                            row = run_episode(seed, arm, world, include_trace=seed == seeds[0])
                        except Exception as exc:
                            row = {"seed": seed, "world": world, "arm": arm, "status": "ERROR", "error": repr(exc)}
                        row["cohort"] = cohort
                        if "trace" in row:
                            traces.append({"cohort": cohort, "seed": seed, "world": world, "arm": arm,
                                           "trace": row.pop("trace")})
                        rows.append(row)
                        stream.write(json.dumps(row, sort_keys=True) + "\n")
                        stream.flush()
    report = summarize(rows, config)
    report["frozen_hashes_unchanged"] = all(sha256(p.read_bytes()).hexdigest() == hashes[str(p.relative_to(root))] for p in paths)
    if not report["frozen_hashes_unchanged"]:
        report["status"] = "INVALID"
    for filename, value in (("summary.json", report), ("sample-traces.json", traces)):
        with (args.output / filename).open("x") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
    print(json.dumps({"status": report["status"], "episodes": len(rows), "output": str(args.output)}))
    return 0 if report["status"] != "INVALID" else 2


if __name__ == "__main__":
    raise SystemExit(main())
