from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from .e2_config import CONFIG_PATH, load_e2_config
from .e2_simulation import run_once
from .e2_stats import summarize_admission, summarize_treatment


ROOT = Path(__file__).resolve().parents[2]


def _code_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in sorted((ROOT / "src" / "pheroos_bench").glob("e2_*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _task(args: tuple[str, int, float, int, int]) -> dict[str, Any]:
    arm, population, fraction, seed, steps = args
    return run_once(
        arm=arm,
        population=population,
        informed_fraction=fraction,
        seed=seed,
        steps=steps,
    ).to_dict()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _write_raw(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")


def _run_tasks(config: Any, arms: tuple[str, ...], workers: int) -> list[dict[str, Any]]:
    tasks = [
        (arm, population, fraction, seed, config.steps)
        for population in config.populations
        for fraction in config.informed_fractions
        for seed in config.seeds
        for arm in arms
    ]
    if workers <= 1:
        rows = list(map(_task, tasks))
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            rows = list(executor.map(_task, tasks, chunksize=1))
    rows.sort(key=lambda row: (int(row["N"]), float(row["informed_fraction"]), int(row["seed"]), str(row["arm"])))
    return rows


def _admission_dir(output: Path) -> Path:
    return output.parent / "admission"


def run(phase: str, output: Path, workers: int, config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = load_e2_config(config_path)
    code_hash = _code_fingerprint()
    config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()
    if phase == "admission":
        arms = tuple(config.raw["admission"]["arms"])
    elif phase == "treatment":
        admission_path = _admission_dir(output) / "admission.json"
        metadata_path = _admission_dir(output) / "metadata.json"
        if not admission_path.exists() or not metadata_path.exists():
            raise RuntimeError("treatment requires a completed admission phase")
        admission = json.loads(admission_path.read_text(encoding="utf-8"))
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if admission.get("status") != "PASS_ADMISSION":
            raise RuntimeError("admission did not pass; treatment is aborted")
        if metadata.get("config_sha256") != config_hash or metadata.get("code_sha256") != code_hash:
            raise RuntimeError("code or frozen config changed after admission; treatment is aborted")
        arms = ("solitary", "naive_gossip", "couzin")
    else:
        raise ValueError(f"unsupported E2 phase: {phase}")

    output.mkdir(parents=True, exist_ok=True)
    rows = _run_tasks(config, arms, max(1, int(workers)))
    _write_raw(output / "raw.ndjson", rows)
    metadata = {
        "experiment": config.raw["experiment"],
        "phase": phase,
        "config_sha256": config_hash,
        "code_sha256": code_hash,
        "arms": arms,
        "populations": config.populations,
        "informed_fractions": config.informed_fractions,
        "seeds": config.seeds,
        "workers": max(1, int(workers)),
        "raw_record_count": len(rows),
        "treatment_executed": phase == "treatment",
    }
    _write_json(output / "metadata.json", metadata)

    if phase == "admission":
        summary, admission = summarize_admission(rows, config.raw)
        _write_summary(output / "summary.csv", summary)
        if admission["status"] != "PASS_ADMISSION":
            _write_json(output / "admission.json", admission)
            # Do not create a verdict.json on failure: treatment has not run,
            # and the preregistered semantics say no verdict is produced.
            raise SystemExit(1)
        _write_json(output / "admission.json", admission)
        return admission

    summary, verdict = summarize_treatment(rows, config.raw)
    _write_summary(output / "summary.csv", summary)
    _write_json(output / "verdict.json", verdict)
    return verdict


def _write_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "N",
        "informed_fraction",
        "arm",
        "n",
        "median_global_regret",
        "median_steps_to_first_r_star_adoption",
        "median_messages",
        "median_bytes",
        "admission_pass_at_cell",
        "primary_pass_at_cell",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the preregistered PheroOS Couzin E2 benchmark")
    parser.add_argument("--phase", choices=("admission", "treatment"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    args = parser.parse_args(argv)
    result = run(args.phase, args.output, args.workers, args.config)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
