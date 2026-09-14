"""Prepared local retry with explicit authorization and retained predecessor costs.

No collection is authorized by writing this configuration. The frozen v1 runner
remains the reproducer of the original pre-dispatch abort.
"""

import argparse
from copy import deepcopy
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import sys

from . import coordination_repair_v1_tasks as tasks
from .coordination_repair_v1 import digest, save, wire
from .coordination_repair_v1_measurement import analyze_forks, paired_call_export
from .coordination_repair_v1_pilot import configuration as original_configuration
from .coordination_repair_v1_pilot import admit_actionability as original_admission
from .coordination_repair_v1_pilot import source_identity as original_sources


CONFIG_VERSION = "coordination_repair_local_cycle_v2_cli_v1"
PREDECESSOR_FILES = {
    "local-cycle-v1/frozen-config.json": "d7796ac52d5378b502756ba3395f6ef234064815d16a60851d2b585e68295459",
    "local-cycle-v1/actionability/accounting.json": "a92a92aca3658534c19c9f175541f9f33de300a5120b8519a1550c10bc0b52dd",
    "local-cycle-v1/actionability/campaign-completion.json": "94850c3769e69e08bb2fcf4b863aba864031e057fcfe05720f72b1a7acfee036",
    "local-cycle-v1/actionability/actionability-000-single-n1-D0/session-snapshot.json": "f693189c63a0f23dd896509fda8cbf6643bb12d9d6daa2991765278078b84532",
    "local-cycle-v1/actionability/actionability-000-single-n1-D0/episode.json": "0b0505d9897fe569374dbd646d3e8189bea0ae0533d6eef936ffc6c8cc36e45a",
    "provider-free/summary.json": "c0f328400a46ea6b7af650f5a9c7fed34604371f2ae3411b534f7fbcb1739e82",
}


def configuration():
    config = deepcopy(original_configuration())
    config["config_version"] = CONFIG_VERSION
    config["runtime_version"] = "0.1.0.dev3"
    config["bench_version"] = "0.1.1.dev4"
    config["model_adapter"] = "pheroos_runtime.recorded_local_v2.RecordedLocalModelAdapter"
    # Retain the predecessor's one conservative intent slot; never reset it.
    config["cycle_caps"]["model_dispatches"] = 999
    config["continuation"] = dict(
        original_config_version="coordination_repair_local_cycle_v1",
        predecessor_files=deepcopy(PREDECESSOR_FILES),
        original_total_token_cap=500000, original_total_dispatch_intent_cap=1000,
        retained_predecessor_token_upper_bound=0, retained_predecessor_intent_slots=1,
        preceding_actionability_campaigns=1, additional_actionability_campaigns_requested=1,
        separate_authorization_required=True,
        authorization_note="Publication and this proposal do not authorize another model campaign.")
    config["record_profile"] = "coordination_repair_episode_v2"
    return config


def verify_predecessor(root, config):
    root = Path(root)
    for name, expected in config["continuation"]["predecessor_files"].items():
        if sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("predecessor evidence identity mismatch: " + name)
    accounting = json.loads((root / "local-cycle-v1/actionability/accounting.json").read_text())
    snapshot = json.loads((root / "local-cycle-v1/actionability/actionability-000-single-n1-D0/session-snapshot.json").read_text())
    if (accounting["violation"] is not None or not accounting["known_tokens_complete"]
            or accounting["held_token_upper_bound"] != 0 or accounting["held_call_slots"] != 1
            or snapshot["unknown_calls"] != 0 or snapshot["actual_tokens"] != 0):
        raise ValueError("predecessor is not the declared settled pre-dispatch abort")
    return dict(known_tokens=0, token_upper_bound=0, retained_intent_slots=1,
                settled_preparation_tools=3, observed_model_dispatches=0,
                accounting_sha256=config["continuation"]["predecessor_files"]["local-cycle-v1/actionability/accounting.json"])


def source_identity():
    import pheroos_runtime
    paths = [*Path(__file__).parent.glob("coordination_repair_v2*.py"),
             Path(pheroos_runtime.__file__).parent / "recorded_local_v2.py"]
    return original_sources() | {str(p): sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def admission(records, config):
    report = original_admission(records, config)
    expected = [(r["world"], r["arm"], r["n"], r["condition"], r["component"])
                for r in expected_grid(config, "actionability")]
    observed = [(r["world_id"], r["arm"], r.get("n"), r.get("condition"), r.get("campaign_component"))
                for r in records]
    full_grid = (len(observed) == len(set(observed)) and set(observed) == set(expected)
                 and all(r["status"] == "VALID_KNOWN" and r.get("complete_rollout") is True for r in records))
    report["checks"]["full_declared_grid"] = full_grid
    report["admitted"] = report["admitted"] and full_grid
    if report["model_action_denominator"] == 0:
        report["empty_denominator_gate_sentinels"] = dict(
            fractions=report["fractions"], interface_rejection_fraction=report["interface_rejection_fraction"])
        report["fractions"] = {key: None for key in report["fractions"]}
        report["interface_rejection_fraction"] = None
        report["measurement_status"] = "UNMEASURED"
    else:
        report["measurement_status"] = "COMPLETE" if full_grid else "INCOMPLETE"
    return report


def expected_grid(config, phase):
    if phase not in ("actionability", "collaboration"):
        raise ValueError("undeclared collection phase")
    spec = config[phase]
    if phase == "actionability":
        grid = [dict(world=w, arm="single", n=1, condition=c, component="capability", **limits)
                for w in spec["worlds"] for c, limits in spec["conditions"].items()]
        probe = spec["intervention_probes"]
        grid += [dict(world=w, arm=arm, n=probe["n"], condition="D2", component="intervention_probe",
                      steps=probe["steps"], token_cap=probe["token_cap"])
                 for w in probe["worlds"] for arm in probe["policies"]]
        return grid
    return [dict(world=w, arm=arm["policy"], n=arm["n"], condition="D2", component="collaboration",
                 steps=spec["steps"], token_cap=spec["token_cap"])
            for w in spec["worlds"] for arm in spec["arms"]]


def validate_actionability(output, config, predecessor, sources):
    """A copied admission boolean cannot authorize a changed or incomplete cohort."""
    output = Path(output)
    frozen = json.loads((output / "frozen-config.json").read_text())
    phase = output / "actionability"
    freeze = json.loads((phase / "freeze.json").read_text())
    completion = json.loads((phase / "campaign-completion.json").read_text())
    records = json.loads((phase / "records.json").read_text())
    stored_gate = json.loads((phase / "admission.json").read_text())
    if (wire(frozen) != wire(config) or freeze["config_sha256"] != digest(config)
            or freeze["sources"] != sources or freeze["predecessor"] != predecessor
            or freeze["runtime_version"] != config["runtime_version"]
            or freeze["bench_version"] != config["bench_version"]):
        raise ValueError("actionability identity changed before collaboration")
    if (completion["status"] != "COMPLETE" or completion["unstarted"] or completion["failure"] is not None
            or completion["executed"] != completion["declared"]
            or completion["declared"] != len(expected_grid(config, "actionability"))
            or completion["records_sha256"] != digest(records)):
        raise ValueError("actionability campaign is incomplete or inconsistent")
    recomputed = admission(records, config)
    if not recomputed["admitted"] or wire(stored_gate) != wire(recomputed):
        raise ValueError("retained actionability records do not admit collaboration")
    return recomputed


def collaboration_analysis(config, completion, records, prefixes, forks):
    """An incomplete declared phase cannot become a valid observed subset."""
    expected = {(r["world"], r["arm"], r["n"]) for r in expected_grid(config, "collaboration")}
    observed = [(r["world_id"], r["arm"], r["n"]) for r in records]
    prefix_worlds = [p["world_id"] for p in prefixes]
    expected_forks = {(p["world_id"], p["prefix_id"], branch) for p in prefixes if p["eligible"]
                      for branch in config["collaboration"]["fork_branches"]}
    observed_forks = [(r["world_id"], r["prefix_id"], r["branch"]) for r in forks]
    valid_phase = (completion["status"] == "COMPLETE"
        and len(observed) == len(set(observed)) and set(observed) == expected
        and all(r["status"] == "VALID_KNOWN" and r.get("complete_rollout") is True for r in records)
        and len(prefix_worlds) == len(set(prefix_worlds))
        and set(prefix_worlds) == set(config["collaboration"]["worlds"])
        and len(observed_forks) == len(set(observed_forks)) and set(observed_forks) == expected_forks
        and all(r["status"] == "VALID_KNOWN" and r.get("complete_rollout") is True for r in forks))
    if not valid_phase:
        report = dict(status="INVALID", method_id="coordination_repair_nested_forks_v1",
            reason="declared collaboration phase is incomplete, source-invalid, or has missing/invalid rollouts",
            partial_record_count=len(records), retained_prefix_count=len(prefixes), retained_fork_count=len(forks),
            raw_records_retained=True, counts_toward_verdict=False)
        exports = {n:dict(status="INVALID", method_id="r_paired_world_mean_v1", measurement_exported=False,
                         reason=report["reason"], raw_records="../records.json", n=n, counts_toward_verdict=False)
                   for n in (2,4)}
        return report, exports
    report = analyze_forks(prefixes, forks)
    world_ids = {f:[w for w in config["collaboration"]["worlds"] if w.startswith(f + "/")] for f in tasks.FAMILIES}
    exports = {n:paired_call_export([r for r in records if r["n"] == n and r["arm"] in ("blackboard","candidate")],
                                   arms=("blackboard","candidate"), world_ids=world_ids) for n in (2,4)}
    return report, exports


def collect(config, output, model_path, phase, predecessor_root, *, additional_campaign_authorized=False):
    if additional_campaign_authorized is not True:
        raise PermissionError("Another actionability campaign requires explicit separate user authorization")
    if wire(config) != wire(configuration()):
        raise ValueError("configuration differs from declared v2 proposal; do not silently change a cohort")
    grid = expected_grid(config, phase)
    predecessor = verify_predecessor(predecessor_root, config)
    output, model_path = Path(output), Path(model_path)
    if sha256((model_path / "manifest.json").read_bytes()).hexdigest() != config["model"]["manifest_sha256"]:
        raise ValueError("model manifest identity mismatch; no substitution")
    for package, key in (("pheroos-runtime", "runtime_version"), ("pheroos-bench", "bench_version")):
        if importlib.metadata.version(package) != config[key]:
            raise ValueError("required installed experimental package identity mismatch: " + package)
    from pheroos_runtime.campaign_v1 import CampaignBudget
    from pheroos_runtime.recorded_local_v2 import RecordedLocalModelAdapter
    from .coordination_repair_v2 import run_episode, full_rollouts

    phase_path, campaign_path = output / phase, output / "campaign.sqlite"
    if phase_path.exists():
        raise FileExistsError("existing phase cannot be rerun; retain its aborted or completed state")
    if phase == "collaboration":
        validate_actionability(output, config, predecessor, source_identity())
    if not campaign_path.exists():
        if phase != "actionability" or output.exists():
            raise FileExistsError("new actionability cohort requires a fresh output directory")
        output.mkdir(parents=True)
        budget = CampaignBudget.create(campaign_path, token_cap=config["cycle_caps"]["tokens"],
                                       dispatch_cap=config["cycle_caps"]["model_dispatches"], config_digest=digest(config))
        save(output / "frozen-config.json", config)
        save(output / "predecessor-accounting.json", predecessor)
    else:
        if phase == "actionability":
            raise FileExistsError("existing campaign allocation cannot restart actionability")
        budget = CampaignBudget(campaign_path)
        prior_state = budget.snapshot()
        if prior_state["config_digest"] != digest(config):
            raise ValueError("campaign identity mismatch")
        if (prior_state["violation"] is not None or not prior_state["known_tokens_complete"]
                or any(a["state"] != "terminal" or a["unknown_tokens"] for a in prior_state["allotments"])):
            raise ValueError("unresolved or inconsistent campaign accounting cannot admit another phase")
    phase_path.mkdir()
    sources = source_identity()
    def verify_frozen():
        if source_identity() != sources:
            raise RuntimeError("source changed after freeze; stop without restarting")
    save(phase_path / "expected-grid.json", grid)
    save(phase_path / "freeze.json", dict(config_sha256=digest(config), sources=sources,
        python=sys.version, executable=sys.executable, phase=phase,
        runtime_version=config["runtime_version"], bench_version=config["bench_version"],
        predecessor=predecessor, operator_asserted_additional_campaign_authorization=True,
        operator_assertion_is_runtime_authority=False, counts_toward_verdict=False))
    records, prefixes, forks, failure = [], [], [], None
    active_item, active_identity = None, None
    try:
        model = RecordedLocalModelAdapter(model_path)
        save(phase_path / "model-identity.json", model.identity)
        for index, item in enumerate(grid):
            verify_frozen()
            identity = f"{phase}-{index:03d}-{item['arm']}-n{item['n']}-{item['condition']}"
            active_item, active_identity = item, identity
            args = {k: v for k, v in item.items() if k != "component"}
            fork_parent = phase == "collaboration" and item["arm"] == "candidate" and item["n"] == 2
            seed = config["seed"] + (tasks.worlds("development").index(item["world"])*100 if phase == "actionability"
                                     else 10000 + tasks.worlds("pilot").index(item["world"])*100)
            row = run_episode(**args, output=phase_path / identity, model=model, campaign=budget,
                              allocation_id=identity, seed=seed,
                              capture_step=config["collaboration"]["fork_after_turn"] if fork_parent else None)
            records.append({**row, "campaign_component": item["component"]})
            active_item, active_identity = None, None
            with (phase_path / "completed.jsonl").open("a") as journal:
                journal.write(wire(records[-1]) + "\n")
            verify_frozen()
            if row["status"] != "VALID_KNOWN" or row.get("complete_rollout") is not True:
                failure = dict(stage="episode", status=row["status"], episode=identity)
                break
            if fork_parent:
                prefix, branches, _ = full_rollouts(row, output=phase_path / (identity + "-forks"),
                    model=model, campaign=budget, verify_frozen=verify_frozen)
                prefixes.append(prefix)
                forks.extend(branches)
                save(phase_path / (identity + "-fork-records.json"), branches)
                verify_frozen()
                if any(b["status"] != "VALID_KNOWN" or b.get("complete_rollout") is not True for b in branches):
                    failure = dict(stage="fork", episode=identity)
                    break
    except Exception as error:
        failure = dict(stage="capability_permission" if isinstance(error, PermissionError) else "runtime_lease_failure",
                       type=type(error).__name__, message=str(error))
        if active_item is not None:
            # The consumer may have started work before raising. It is never an
            # unstarted cell, and missing metrics must not turn into zero cost.
            records.append(dict(world_id=active_item["world"], family=active_item["world"].split("/")[0],
                arm=active_item["arm"], n=active_item["n"], condition=active_item["condition"],
                campaign_component=active_item["component"], status="INVALID_ABORT", success=None,
                outcome=None, metrics=None, complete_rollout=False, error=failure, raw_episode_directory=active_identity,
                counts_toward_verdict=False))
    finally:
        save(phase_path / "records.json", records)
        save(phase_path / "fork-records.json", forks)
        try:
            accounting = budget.snapshot()
        except Exception as error:
            accounting = dict(status="INVALID_ABORT", held_token_upper_bound=None, held_call_slots=None,
                              error=dict(type=type(error).__name__, message=str(error)))
            failure = failure or dict(stage="accounting", error=accounting["error"])
        save(phase_path / "accounting.json", accounting)
        known_tokens, known_slots = accounting["held_token_upper_bound"], accounting["held_call_slots"]
        save(phase_path / "combined-accounting.json", dict(
            current=accounting, predecessor=predecessor,
            held_token_upper_bound=known_tokens + predecessor["token_upper_bound"] if known_tokens is not None else None,
            held_intent_slots=known_slots + predecessor["retained_intent_slots"] if known_slots is not None else None,
            total_token_cap=500000, total_intent_cap=1000, counts_toward_verdict=False))
        completion = dict(status="COMPLETE" if failure is None and len(records) == len(grid) else "INVALID_ABORT",
            declared=len(grid), executed=len(records), failure=failure,
            records_sha256=digest(records),
            unstarted=[{**item, "outcome": None, "cost": None, "reason": "collection_stopped_after_invalid_or_unresolved_work"}
                       for item in grid[len(records):]], counts_toward_verdict=False)
        save(phase_path / "campaign-completion.json", completion)
    if phase == "actionability":
        report = admission(records, config)
        if completion["status"] != "COMPLETE":
            report["admitted"] = False
        save(phase_path / "admission.json", report)
    else:
        report, paired_exports = collaboration_analysis(config, completion, records, prefixes, forks)
        save(phase_path / "sharing-analysis.json", report)
        exports = phase_path / "paired-exports"
        exports.mkdir()
        for n in (2, 4):
            save(exports / f"n{n}.json", paired_exports[n])
    return report


def cli_result(report, phase_path, phase):
    """Map retained collection state to the experimental CLI v1 exit contract.

    A negative research result is valid completion. Non-admission is distinct
    from incomplete or unresolved collection; neither permits shell chaining.
    This reports state only and does not authorize a subsequent phase.
    """
    result = dict(profile="coordination_repair_cli_v1", status="INVALID_ABORT", exit_code=2)
    try:
        completion = json.loads((phase_path / "campaign-completion.json").read_text())
        accounting = json.loads((phase_path / "accounting.json").read_text())
        complete = (completion["status"] == "COMPLETE" and completion["failure"] is None
                    and completion["unstarted"] == []
                    and completion["executed"] == completion["declared"] > 0)
        settled = (accounting["known_tokens_complete"] is True and accounting["violation"] is None
                   and all(a["state"] == "terminal" and a["unknown_tokens"] == 0
                           for a in accounting["allotments"]))
        if not complete or not settled:
            return result
        if phase == "actionability" and report.get("measurement_status") == "COMPLETE":
            if report.get("admitted") is False:
                return {**result, "status": "NOT_ADMITTED", "exit_code": 3}
            if report.get("admitted") is True:
                return {**result, "status": "COMPLETED", "exit_code": 0}
        if phase == "collaboration" and report.get("status") in {"VALID_KNOWN", "NO_ELIGIBLE_PREFIXES"}:
            return {**result, "status": "COMPLETED", "exit_code": 0}
    except (OSError, ValueError, KeyError, TypeError):
        # Missing/unreadable status is not a successful collection. Do not
        # replace any retained report, outcome or unknown accounting value.
        pass
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--phase", choices=("actionability", "collaboration"), required=True)
    parser.add_argument("--predecessor-root", type=Path, required=True)
    parser.add_argument("--authorized-additional-campaign", action="store_true")
    args = parser.parse_args()
    report = collect(json.loads(args.config.read_text()), args.output, args.model_path,
                     args.phase, args.predecessor_root,
                     additional_campaign_authorized=args.authorized_additional_campaign)
    cli = cli_result(report, args.output / args.phase, args.phase)
    print(wire({**report, "cli": cli}))
    return cli["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
