"""Frozen provider-free installed-Session instrument campaign, no model dispatch."""

from collections import Counter, defaultdict
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import sys
import time

from pheroos_bench.coordination_repair_v1 import run_episode, digest, save
from pheroos_bench import coordination_repair_v1_tasks as tasks
from pheroos_bench.coordination_repair_v1_forks import full_rollouts
from pheroos_bench.coordination_repair_v1_measurement import analyze_forks
import pheroos_runtime.coordination_v1 as installed_runtime


ROOT = Path(__file__).resolve().parent
BENCH = ROOT.parents[2]
SOURCES = [BENCH / "src/pheroos_bench" / name for name in (
    "coordination_repair_v1.py", "coordination_repair_v1_tasks.py",
    "coordination_repair_v1_forks.py", "coordination_repair_v1_measurement.py")]
SOURCES += [Path(installed_runtime.__file__).parent / name for name in (
    "coordination_v1.py", "campaign_v1.py", "session_v1.py", "session_driver_v1.py")]
SOURCES += [Path(__file__).resolve()]


def hashes():
    return {str(path): sha256(path.read_bytes()).hexdigest() for path in SOURCES}


def compact(row, relative):
    return {"path": relative, **{key: row.get(key) for key in (
        "world_id", "arm", "n", "condition", "status", "success", "stop",
        "primary_failure_stage", "metrics", "errors", "error", "scope_id")}}


def main():
    assert "/tmp/pheroos-coordination-installed-site/" in installed_runtime.__file__
    assert importlib.metadata.version("pheroos-runtime") == "0.1.0.dev2"
    frozen = hashes()
    config = {
        "config_id": "coordination_repair_provider_free_campaign_v1",
        "method_id": "installed_session_public_tool_reference_instrument_v1",
        "model": None, "model_calls_authorized": 0, "counts_toward_verdict": False,
        "development_worlds": tasks.worlds("development"),
        "pilot_worlds": tasks.worlds("pilot"),
        "diagnostics": [{"condition": condition, "arm": "single", "n": 1,
                         "steps": steps, "token_cap": cap}
                        for condition, steps, cap in (("D0", 1, 2048), ("D1", 4, 6144), ("D2", 8, 10240))],
        "pilot_arms": [{"arm": arm, "n": n, "steps": 8, "token_cap": 8192}
                       for arm, n in (("single", 1), ("blackboard", 2), ("blackboard", 4),
                                      ("candidate", 2), ("candidate", 4),
                                      ("no_ownership", 4), ("no_reuse", 4))],
        "forks": {"parent": "candidate_n2", "capture_step": 1,
                  "branches": ["relevant", "withheld", "irrelevant"],
                  "eligibility": "current optional cross-agent artifact at fixed prefix, before observing branch outcome",
                  "complete_downstream_rollouts": True},
        "seed": 2718, "source_sha256": frozen, "runtime_module": installed_runtime.__file__,
        "runtime_distribution": importlib.metadata.version("pheroos-runtime"),
        "python": sys.version,
        "claims": "Instrument feasibility and intervention behavior only; scripted references establish no learned efficacy.",
    }
    save(ROOT / "config.json", config)
    records, prefixes, branches, episodes_by_world = [], [], [], defaultdict(dict)
    started = time.monotonic_ns()

    def unchanged():
        if hashes() != frozen:
            raise RuntimeError("SOURCE_DRIFT: stop this campaign; preserve existing records")

    def one(world, spec, group):
        unchanged()
        label = f"{spec['condition']}-{spec['arm']}-{spec['n']}" if "condition" in spec else f"{spec['arm']}-{spec['n']}"
        destination = ROOT / group / world / label
        row = run_episode(world=world, output=destination, model=None, seed=config["seed"],
                          capture_step=1 if group == "pilot" and label == "candidate-2" else None,
                          **spec)
        unchanged()
        record = compact(row, str(destination.relative_to(ROOT)))
        records.append(record)
        with (ROOT / "completed.jsonl").open("a") as stream:
            stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
        print(json.dumps({"episode": record["path"], "status": row["status"],
                          "success": row["success"], "stop": row.get("stop")}), flush=True)
        return row

    failure = None
    try:
        for world in config["development_worlds"]:
            for spec in config["diagnostics"]:
                one(world, spec, "development")
        for world in config["pilot_worlds"]:
            for spec in config["pilot_arms"]:
                row = one(world, spec, "pilot")
                episodes_by_world[world][f"{spec['arm']}-{spec['n']}"] = row
            unchanged()
            parent = episodes_by_world[world]["candidate-2"]
            if parent["status"] == "INVALID_ABORT":
                prefix = {"world_id": world, "prefix_id": "step-1", "eligible": False,
                          "reason": "INVALID_PARENT", "prefix_tokens": 0}
                prefixes.append(prefix)
                save(ROOT / "forks" / (world.replace("/", "_") + "-invalid-parent.json"), prefix)
                continue
            prefix, branch_records, branch_episodes = full_rollouts(
                parent, output=ROOT / "forks" / world, model=None)
            unchanged()
            prefixes.append(prefix)
            branches.extend(branch_records)
            for branch, episode in zip(branch_records, branch_episodes):
                records.append(compact(episode, "forks/" + world + "/" + branch["branch"]))
            print(json.dumps({"fork_world": world, "eligible": prefix["eligible"],
                              "branches": len(branch_records),
                              "statuses": [r["status"] for r in branch_records]}), flush=True)
    except Exception as exc:
        failure = {"type": type(exc).__name__, "message": str(exc)}
    diagnostic_rows = [r for r in records if r["path"].startswith("development/")]
    pilot_rows = [r for r in records if r["path"].startswith("pilot/")]
    intervention = []
    for world, values in episodes_by_world.items():
        for n in (2, 4):
            control, candidate = values.get(f"blackboard-{n}"), values.get(f"candidate-{n}")
            if control is None or candidate is None:
                continue
            def actions(episode):
                return [{"agent": t["agent"], "suggested_work": t["suggested_work"],
                         "normalized_action": t["validation"]["normalized_action"] if t["validation"] else None,
                         "materialized_receipts": t["materialized_receipts"]}
                        for t in episode.get("turns", [])]
            ca, ta = actions(control), actions(candidate)
            intervention.append({"world_id": world, "n": n, "behavior_changed": digest(ca) != digest(ta),
                                 "control": ca, "candidate": ta,
                                 "control_success": control["success"], "candidate_success": candidate["success"]})
    invalid = [r for r in records if r["status"] == "INVALID_ABORT"]
    summary = {
        "config_id": config["config_id"], "status": "PASS" if failure is None and not invalid and all(r["success"] for r in diagnostic_rows + pilot_rows) else "INVALID_OR_FAILED",
        "failure": failure, "counts_toward_verdict": False, "model_calls": 0,
        "development_episodes": len(diagnostic_rows), "pilot_parent_episodes": len(pilot_rows),
        "all_episodes_including_branches": len(records),
        "statuses": dict(Counter(r["status"] for r in records)),
        "successes": sum(r["success"] is True for r in records),
        "failure_stages": dict(Counter(r["primary_failure_stage"] for r in records if r["primary_failure_stage"])),
        "invalid_records": invalid,
        "development": {condition: {"episodes": sum(r["condition"] == condition for r in diagnostic_rows),
                                    "successes": sum(r["condition"] == condition and r["success"] is True for r in diagnostic_rows)}
                        for condition in ("D0", "D1", "D2")},
        "intervention_cases": len(intervention),
        "intervention_behavior_changed": sum(r["behavior_changed"] for r in intervention),
        "fork_analysis": analyze_forks(prefixes, branches),
        "source_sha256": frozen, "source_unchanged": hashes() == frozen,
        "elapsed_seconds": (time.monotonic_ns() - started) / 1e9,
        "limits": "All policies are scripted instrument references. No live model efficacy or confirmatory evidence is established.",
    }
    save(ROOT / "records.json", records)
    save(ROOT / "intervention-relevance.json", intervention)
    save(ROOT / "fork-prefixes.json", prefixes)
    save(ROOT / "fork-records.json", branches)
    save(ROOT / "summary.json", summary)
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
