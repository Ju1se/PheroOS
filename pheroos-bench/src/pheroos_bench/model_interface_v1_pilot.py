"""Prepared, separately authorized single-model interface diagnostic.

This is developmental, not a new collaboration admission gate. Paid/remote
models, automatic retries and reuse of the closed campaign are not supported.
"""

import argparse
from copy import deepcopy
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import sys

from .coordination_repair_v1 import digest, save, wire
from .coordination_repair_v2_pilot import source_identity as previous_sources
from . import coordination_repair_v1_tasks as tasks
from . import model_interface_v1 as diagnostic


PRIOR_FILES = {
    "combined-accounting.json": "a4af32996530b8213dd36df620beb30f5b8f3fd897c39c0cc25850b5d201c47f",
    "accounting.json": "250b6f7d9ab9442c2893bff77a6c5de45fee7de0f7cd81f6ba2a3607b6bbebe9",
    "campaign-completion.json": "dd321b8e8e3d96d93f48407b246c8c01c31c95b0fbf7d39371a7422e60e2ef5c",
    "records.json": "4ec40cc9938f713799bf1dc0f2ca83230783ebdda1bb05339890cb7f731a65fc",
}


def configuration():
    return dict(config_version="model_interface_local_diagnostic_v1", counts_toward_verdict=False,
        worlds=tasks.worlds("development"), seed_bases=[1729, 2718], arms=deepcopy(diagnostic.ARMS),
        base_arm_order=list(diagnostic.ARMS), arm_order="rotate_by_world_index_plus_seed_index", n=1, responses_per_episode=1,
        context_tokens=2048, episode_token_cap=2048, campaign_token_cap=131072,
        campaign_dispatch_cap=64, preparation="charged_required_current_sources_at_step_2",
        model=dict(repository="Qwen/Qwen2.5-Coder-3B-Instruct",
            revision="488639f1ff808d1d3d0ba301aef8c11461451ec5",
            manifest_sha256="cf4593f14704152d28ea15c6630ee7abaca52580973524a386e05ba217391777"),
        provider="existing_local_cuda", runtime_version="0.1.0.dev4", bench_version="0.1.1.dev5",
        adapter="pheroos_runtime.recorded_local_v3.RecordedLocalModelAdapter",
        generation=dict(do_sample=True, temperature=0.7, top_p=0.9, top_k=50),
        stop_rule="one returned response and public validation; hidden scoring only after terminal cleanup",
        automatic_retry=False, collaboration_admitted=False, admission_thresholds=None,
        continuation=dict(prior_files=deepcopy(PRIOR_FILES), prior_tokens=65662, prior_intent_slots=114,
            total_token_cap=500000, total_intent_cap=1000,
            separate_authorization_required=True, additional_campaigns_requested=1),
        contrasts=[dict(a="direct_json_256", b="compact_action_256", interpretation="answer-only versus model-produced action and citations"),
                   dict(a="compact_action_256", b="envelope_256", interpretation="whole presentation change at the same output bound"),
                   dict(a="envelope_256", b="envelope_1024", interpretation="output allowance; byte-identical messages and same model")],
        limitations=["Eight already observed development worlds; no new heldout or confirmatory evidence.",
                     "Two seeds are repeats inside each world, not independent task samples.",
                     "Direct answer JSON still has an answer schema; it is not unrestricted prose.",
                     "Runtime-supplied citations in direct mode do not measure model citation selection.",
                     "Compact view changes a presentation bundle; prompt length alone is not isolated.",
                     "Interface-by-output-budget interaction is not measured by this four-arm design.",
                     "New reserved worlds and independent stronger-model calibration remain separate future gates."])


def expected_grid(config):
    names = config["base_arm_order"]
    grid = []
    for world_index, world in enumerate(config["worlds"]):
        for seed_index, base in enumerate(config["seed_bases"]):
            offset = (world_index + seed_index) % len(names)
            for arm in names[offset:] + names[:offset]:
                grid.append(dict(world=world, arm=arm, seed=base + 100 * world_index))
    return grid


def verify_predecessor(root):
    root = Path(root)
    for name, expected in PRIOR_FILES.items():
        if sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("closed diagnostic evidence identity mismatch: " + name)
    combined = json.loads((root / "combined-accounting.json").read_text())
    prior = combined["current"]
    completion = json.loads((root / "campaign-completion.json").read_text())
    if (completion["status"] != "COMPLETE" or completion["executed"] != 28 or completion["declared"] != 28
            or completion["unstarted"] or completion["failure"] is not None
            or prior["violation"] is not None or prior["known_tokens_complete"] is not True
            or any(a["state"] != "terminal" or a["unknown_tokens"] for a in prior["allotments"])
            or combined["held_token_upper_bound"] != 65662 or combined["held_intent_slots"] != 114):
        raise ValueError("closed diagnostic accounting is not the declared known predecessor")
    return dict(known_tokens=65662, retained_intent_slots=114,
                predecessor_combined_sha256=PRIOR_FILES["combined-accounting.json"])


def sources():
    import pheroos_runtime
    paths = [*Path(__file__).parent.glob("model_interface_v1*.py"),
             Path(pheroos_runtime.__file__).parent / "recorded_local_v3.py"]
    return previous_sources() | {str(p): sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def collect(config, output, model_path, predecessor_root, *, authorized=False, instrument_model=None):
    if authorized is not True:
        raise PermissionError("The closed campaign authorization is consumed; this new diagnostic needs separate authorization")
    if wire(config) != wire(configuration()):
        raise ValueError("configuration differs from the unexecuted versioned diagnostic")
    prior = verify_predecessor(predecessor_root)
    for package, key in (("pheroos-runtime", "runtime_version"), ("pheroos-bench", "bench_version")):
        if importlib.metadata.version(package) != config[key]:
            raise ValueError("required installed package identity mismatch: " + package)
    model_path, output = Path(model_path), Path(output)
    if sha256((model_path / "manifest.json").read_bytes()).hexdigest() != config["model"]["manifest_sha256"]:
        raise ValueError("model manifest identity mismatch")
    if output.exists():
        raise FileExistsError("fresh output required; no automatic retry")
    from pheroos_runtime.campaign_v1 import CampaignBudget
    from pheroos_runtime.recorded_local_v3 import RecordedLocalModelAdapter

    output.mkdir(parents=True)
    budget = CampaignBudget.create(output / "campaign.sqlite", token_cap=config["campaign_token_cap"],
        dispatch_cap=config["campaign_dispatch_cap"], config_digest=digest(config))
    grid, identity = expected_grid(config), sources()
    save(output / "frozen-config.json", config)
    save(output / "expected-grid.json", grid)
    save(output / "freeze.json", dict(config_sha256=digest(config), sources=identity,
        python=sys.version, executable=sys.executable, predecessor=prior, instrument_only=instrument_model is not None,
        operator_asserted_authorization=True, operator_assertion_is_runtime_authority=False, counts_toward_verdict=False))
    records, failure, active = [], None, None
    try:
        model = RecordedLocalModelAdapter(model_path) if instrument_model is None else instrument_model
        save(output / "model-identity.json", model.identity)
        for index, item in enumerate(grid):
            if sources() != identity:
                raise RuntimeError("source changed after freeze")
            active = (item, f"episode-{index:03d}-{item['arm']}")
            record = diagnostic.run_episode(**item, output=output / active[1], model=model,
                campaign=budget, allocation_id=active[1], instrument_only=instrument_model is not None)
            records.append(record)
            active = None
            with (output / "completed.jsonl").open("a") as stream:
                stream.write(wire(record) + "\n")
            if sources() != identity:
                raise RuntimeError("source changed after episode")
            if record["status"] != "VALID_KNOWN" or record["complete"] is not True:
                failure = dict(stage="episode", status=record["status"], index=index)
                break
    except Exception as exc:
        failure = dict(stage="collection", type=type(exc).__name__, message=str(exc))
        if active:
            item, name = active
            records.append(dict(world_id=item["world"], arm=item["arm"], seed=item["seed"], status="INVALID_ABORT",
                complete=False, objective_success=None, public_accepted=None, metrics=None, error=failure,
                raw_episode_directory=name, counts_toward_verdict=False))
    finally:
        save(output / "records.json", records)
        try:
            accounting = budget.snapshot()
        except Exception as exc:
            accounting = dict(known_tokens_complete=False, held_token_upper_bound=None, held_call_slots=None,
                              violation=None, error=dict(type=type(exc).__name__, message=str(exc)))
            failure = failure or dict(stage="accounting", error=accounting["error"])
        save(output / "accounting.json", accounting)
        current_tokens, current_slots = accounting["held_token_upper_bound"], accounting["held_call_slots"]
        save(output / "combined-accounting.json", dict(current=accounting, predecessor=prior,
            held_token_upper_bound=current_tokens + prior["known_tokens"] if current_tokens is not None else None,
            held_intent_slots=current_slots + prior["retained_intent_slots"] if current_slots is not None else None,
            total_token_cap=500000, total_intent_cap=1000, counts_toward_verdict=False))
        settled = (accounting["known_tokens_complete"] is True and accounting["violation"] is None
                   and all(a["state"] == "terminal" and a["unknown_tokens"] == 0 for a in accounting.get("allotments", [])))
        complete = failure is None and len(records) == len(grid) and settled
        completion = dict(status="COMPLETE" if complete else "INVALID_ABORT", declared=len(grid), executed=len(records),
            failure=failure, records_sha256=digest(records), unstarted=[{**item, "outcome": None, "cost": None} for item in grid[len(records):]],
            counts_toward_verdict=False)
        save(output / "campaign-completion.json", completion)
    report = diagnostic.summarize(records, grid) if complete else dict(status="INVALID", effects=None,
        reason="incomplete or unresolved declared campaign", counts_toward_verdict=False, collaboration_admitted=False)
    report["instrument_only"] = instrument_model is not None
    save(output / "summary.json", report)
    code = 0 if complete and report["status"] == "VALID_KNOWN" else 2
    return {**report, "cli": dict(profile="model_interface_cli_v1", status="COMPLETE" if code == 0 else "INVALID_ABORT", exit_code=code)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--predecessor-root", type=Path, required=True)
    parser.add_argument("--authorized-diagnostic", action="store_true")
    args = parser.parse_args()
    report = collect(json.loads(args.config.read_text()), args.output, args.model_path,
                     args.predecessor_root, authorized=args.authorized_diagnostic)
    print(wire(report))
    return report["cli"]["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
