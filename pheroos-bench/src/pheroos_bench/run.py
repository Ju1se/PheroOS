from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from .config import CONFIG_PATH, load_config
from .plot import write_plot
from .simulation import run_once
from .stats import summarize


def _task(args: tuple[str, float, int, int, int]) -> dict[str, Any]:
    arm, density, seed, steps, graph_nodes = args
    return run_once(arm=arm, density=density, seed=seed, steps=steps, graph_nodes=graph_nodes).to_dict()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(mode: str, output: Path, workers: int) -> dict[str, Any]:
    config = load_config()
    dependency = config.raw["core_dependency"]
    try:
        import pheroos
        import importlib.metadata
        installed_version = importlib.metadata.version("pheroos")
    except Exception as exc:  # pragma: no cover - exercised by installation failures
        raise RuntimeError("the pinned pheroos dependency is not installed") from exc
    if installed_version != dependency["version"]:
        raise RuntimeError(f"expected pheroos {dependency['version']}, found {installed_version}")
    if getattr(pheroos, "__version__", None) != dependency["version"]:
        raise RuntimeError(f"imported pheroos version mismatch: {getattr(pheroos, '__version__', None)}")
    source_root = os.environ.get("PHEROOS_SOURCE_ROOT")
    source_commit = None
    if source_root:
        source_commit = subprocess.check_output(
            ["git", "-C", source_root, "rev-parse", "HEAD"], text=True
        ).strip()
        if source_commit != dependency["git_commit"]:
            raise RuntimeError(f"PheroOS source commit mismatch: {source_commit}")
    if mode == "pilot":
        densities = tuple(float(value) for value in config.raw["pilot"]["densities"])
        seeds = config.pilot_seeds
        counts_toward_verdict = False
    elif mode == "confirmatory":
        densities = config.densities
        seeds = config.confirmatory_seeds
        counts_toward_verdict = True
    else:
        raise ValueError(f"unsupported mode: {mode}")

    output.mkdir(parents=True, exist_ok=True)
    raw_path = output / "raw.ndjson"
    tasks = [
        (arm, density, seed, config.steps, config.graph_nodes)
        for density in densities
        for seed in seeds
        for arm in config.arms
    ]
    rows: list[dict[str, Any]] = []
    executor_workers = max(1, int(workers))
    if executor_workers == 1:
        iterator = map(_task, tasks)
        for batch in iterator:
            rows.append(batch)
    else:
        with ProcessPoolExecutor(max_workers=executor_workers) as executor:
            for batch in executor.map(_task, tasks, chunksize=1):
                rows.append(batch)
    rows.sort(key=lambda row: (float(row["density"]), int(row["seed"]), str(row["arm"])))
    with raw_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    metadata = {
        "experiment_id": config.raw["experiment_id"],
        "mode": mode,
        "counts_toward_verdict": counts_toward_verdict,
        "pilot_is_void": mode == "pilot",
        "config_sha256": hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest(),
        "core_dependency": config.raw["core_dependency"],
        "dependency_verified": True,
        "package_import_verified": True,
        "source_commit_verified": source_commit is not None,
        "density_values": densities,
        "seeds": seeds,
        "workers": executor_workers,
        "raw_record_count": len(rows),
    }
    _write_json(output / "metadata.json", metadata)
    if mode == "pilot":
        verdict = {
            "experiment_id": config.raw["experiment_id"],
            "status": "PILOT_VOID",
            "counts_toward_verdict": False,
            "reason": "pilot is permitted only to calibrate normalized regret scale and must be discarded",
        }
        _write_json(output / "verdict.json", verdict)
        return verdict

    summary, verdict = summarize(rows, config.raw)
    fields = [
        "density", "arm", "n", "median_final_regret", "median_shock_recovery_steps",
        "median_spof_recovery_steps", "median_bytes", "median_messages", "median_final_best_share",
        "gate_pass_at_density",
    ]
    with (output / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary)
    write_plot(summary, output / "density-curve.svg")
    _write_json(output / "verdict.json", verdict)
    return verdict


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the PheroOS field benchmark")
    parser.add_argument("--mode", choices=("pilot", "confirmatory"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    args = parser.parse_args(argv)
    verdict = run(args.mode, args.output, args.workers)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0 if verdict["status"] in {"PILOT_VOID", "PASS_SWARM_CLAIM", "FAIL_RENAME_REQUIRED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
