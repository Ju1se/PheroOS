"""One bounded local actionability campaign, then one gated collaboration pilot."""

import argparse
from collections import Counter
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

from . import coordination_repair_v1_tasks as tasks
from .coordination_repair_v1 import digest, run_episode, save, wire
from .coordination_repair_v1_forks import full_rollouts
from .coordination_repair_v1_measurement import analyze_forks, paired_call_export


CONFIG_VERSION = "coordination_repair_local_cycle_v1"


def configuration():
    return dict(config_version=CONFIG_VERSION, counts_toward_verdict=False,
        model={"repository": "Qwen/Qwen2.5-Coder-3B-Instruct",
               "revision": "488639f1ff808d1d3d0ba301aef8c11461451ec5",
               "manifest_sha256": "cf4593f14704152d28ea15c6630ee7abaca52580973524a386e05ba217391777"},
        provider="existing_local_cuda", context_tokens=2048, max_new_tokens=256,
        generation=dict(do_sample=True, temperature=0.7, top_p=0.9, top_k=50),
        cycle_caps=dict(tokens=500000, model_dispatches=1000,
                        actionability_campaigns=1, collaboration_campaigns=1),
        actionability=dict(worlds=tasks.worlds("development"), conditions={
            "D0": {"steps": 1, "token_cap": 2048},
            "D1": {"steps": 4, "token_cap": 6144},
            "D2": {"steps": 8, "token_cap": 10240}},
            intervention_probes=dict(worlds=["interval_intersection/dev_b","inventory_reconciliation/dev_b"],
                policies=["blackboard","candidate"], n=2, steps=6, token_cap=6144,
                minimum_changed_pairs=1, endpoint="executed normalized actions or materialized source provenance; labels and suggestions excluded"),
            admission=dict(min_d0_public_submission_fraction=0.75,
                           min_d0_objective_fraction=0.50,
                           max_interface_rejection_fraction=0.20,
                           min_d2_objective_fraction=0.50,
                           min_d2_successful_families=2,
                           require_complete_known_records=True)),
        collaboration=dict(worlds=tasks.worlds("pilot"), arms=[
            {"policy": "single", "n": 1}, {"policy": "blackboard", "n": 2},
            {"policy": "blackboard", "n": 4}, {"policy": "candidate", "n": 2},
            {"policy": "candidate", "n": 4}, {"policy": "no_ownership", "n": 4},
            {"policy": "no_reuse", "n": 4}], steps=8, token_cap=8192,
            fork_arm={"policy": "candidate", "n": 2}, fork_after_turn=1,
            fork_branches=["relevant", "withheld", "irrelevant"],
            fork_rule="every fixed prefix reached with current optional information not previously read by every eligible agent",
            require_actionability_gate=True, require_provider_free_gate=True),
        seed=1729, attention=dict(ttl_steps=3, item_cap=4),
        stop_rule="first public-accepted final-version submission, D0 one opportunity, or declared resource limit; never hidden success",
        limitations=["12 constructed worlds; not a task-population sample", "one local model, not calibrated external strong-model evidence",
                     "8 development worlds are below the optional 20–40-task API diagnostic suggestion",
                     "sequential one-GPU inference; logical agents have bounded local state",
                     "negative capability gate does not constitute a collaboration efficacy result"])


def source_identity():
    import pheroos_runtime
    import pheroos_runtime.coordination_v1
    runtime_root = Path(pheroos_runtime.__file__).parent
    bench_root = Path(__file__).parent
    files = list(bench_root.glob("coordination_repair_v1*.py"))
    files += [runtime_root / name for name in ("coordination_v1.py", "campaign_v1.py",
              "recorded_local_v1.py", "session_v1.py", "session_driver_v1.py", "authority.py")]
    return {str(p): sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def admit_actionability(records, config):
    probes = [r for r in records if r.get("campaign_component") == "intervention_probe"]
    records = [r for r in records if r.get("campaign_component") != "intervention_probe"]
    gate = config["actionability"]["admission"]
    expected = {(w,c) for w in config["actionability"]["worlds"] for c in config["actionability"]["conditions"]}
    identities = [(r["world_id"],r.get("condition")) for r in records]
    complete = len(identities) == len(set(identities)) and set(identities) == expected and all(r["status"] == "VALID_KNOWN" for r in records)
    d0 = [r for r in records if r.get("condition") == "D0"]
    d2 = [r for r in records if r.get("condition") == "D2"]
    fractions = dict(d0_public_submission=sum(r.get("stop") == "public_accepted_submission" for r in d0)/len(d0) if d0 else 0,
        d0_objective=sum(r["success"] is True for r in d0)/len(d0) if d0 else 0,
        d2_objective=sum(r["success"] is True for r in d2)/len(d2) if d2 else 0)
    stages = Counter()
    actions = 0
    for record in records:
        for turn in record.get("turns", []):
            if turn.get("model_response") is not None:
                actions += 1
                if turn.get("validation") and not turn["validation"]["valid"]:
                    stages[turn["validation"]["stage"]] += 1
    interface = sum(stages[k] for k in ("transport_format", "action_schema", "undeclared_target"))/actions if actions else 1
    families = sorted({r["family"] for r in d2 if r["success"] is True})
    checks = dict(complete_known_records=complete,
        d0_public_submission=fractions["d0_public_submission"] >= gate["min_d0_public_submission_fraction"],
        d0_objective=fractions["d0_objective"] >= gate["min_d0_objective_fraction"],
        interface_rejection=interface <= gate["max_interface_rejection_fraction"],
        d2_objective=fractions["d2_objective"] >= gate["min_d2_objective_fraction"],
        d2_families=len(families) >= gate["min_d2_successful_families"])
    comparisons = []
    probe_spec = config["actionability"]["intervention_probes"]
    expected_probes = {(w,arm) for w in probe_spec["worlds"] for arm in probe_spec["policies"]}
    probe_keys = [(r["world_id"],r["arm"]) for r in probes]
    probes_complete = len(probe_keys) == len(set(probe_keys)) and set(probe_keys) == expected_probes
    for world in config["actionability"]["intervention_probes"]["worlds"]:
        pair = {r["arm"]: r for r in probes if r["world_id"] == world}
        if len(pair) != 2 or any(r["status"] != "VALID_KNOWN" for r in pair.values()):
            comparisons.append({"world":world,"valid":False,"changed":None})
            continue
        def functional(record):
            return [(r["validation"]["normalized_action"] if r.get("validation") else None,
                     r["materialized_receipts"]) for r in record["turns"]]
        comparisons.append(dict(world=world,valid=True,
            changed=functional(pair["blackboard"]) != functional(pair["candidate"]),
            blackboard_tool_calls=pair["blackboard"]["metrics"]["tool_calls"],
            candidate_tool_calls=pair["candidate"]["metrics"]["tool_calls"],
            inspection_dispatch_change=pair["candidate"]["metrics"]["inspection_dispatches"]-pair["blackboard"]["metrics"]["inspection_dispatches"]))
    checks["intervention_relevance"] = probes_complete and all(p["valid"] for p in comparisons) and sum(p["changed"] is True or p.get("inspection_dispatch_change",0) != 0 for p in comparisons) >= config["actionability"]["intervention_probes"]["minimum_changed_pairs"]
    return dict(admitted=all(checks.values()), checks=checks, fractions=fractions,
                interface_rejection_fraction=interface, stages=dict(stages), model_action_denominator=actions,
                d2_successful_families=families, intervention_comparisons=comparisons, counts_toward_verdict=False)


def collect(config, output, model_path, phase, provider_free_report):
    from pheroos_runtime.campaign_v1 import CampaignBudget
    from pheroos_runtime.recorded_local_v1 import RecordedLocalModelAdapter

    if wire(config) != wire(configuration()):
        raise ValueError("configuration differs from declared v1 cycle; create a new version, never mutate a collected cycle")
    if provider_free_report.get("status") != "PASS":
        raise ValueError("provider-free reachability and fork gate must pass before live collection")
    output, model_path = Path(output), Path(model_path)
    manifest = model_path / "manifest.json"
    if sha256(manifest.read_bytes()).hexdigest() != config["model"]["manifest_sha256"]:
        raise ValueError("model manifest identity mismatch; no substitution")
    if importlib.metadata.version("pheroos-runtime") != "0.1.0.dev2":
        raise ValueError("new installed experimental runtime cohort required")
    campaign_path = output / "campaign.sqlite"
    phase_path = output / phase
    if phase_path.exists():
        raise FileExistsError("one campaign per phase; an interrupted directory cannot be rerun")
    if phase == "collaboration":
        gate = json.loads((output / "actionability" / "admission.json").read_text())
        if not gate["admitted"]:
            raise ValueError("actionability gate did not admit collaboration; retain unexecuted status")
    if not output.exists():
        output.mkdir(parents=True)
    if not campaign_path.exists():
        if phase != "actionability":
            raise ValueError("actionability must precede collaboration")
        budget = CampaignBudget.create(campaign_path, token_cap=config["cycle_caps"]["tokens"],
             dispatch_cap=config["cycle_caps"]["model_dispatches"], config_digest=digest(config))
        save(output / "frozen-config.json", config)
    else:
        budget = CampaignBudget(campaign_path)
        if budget.snapshot()["config_digest"] != digest(config):
            raise ValueError("campaign identity mismatch")
    phase_path.mkdir()
    sources = source_identity()
    freeze = dict(config_sha256=digest(config), sources=sources, runtime_version=importlib.metadata.version("pheroos-runtime"),
        python=sys.version, executable=sys.executable, bench_version=importlib.metadata.version("pheroos-bench"), model_manifest_sha256=config["model"]["manifest_sha256"],
        provider_free_report_sha256=digest(provider_free_report), phase=phase, counts_toward_verdict=False)
    save(phase_path / "freeze.json", freeze)
    print(wire({"phase": phase, "status": "FROZEN_LOADING_MODEL", "config_sha256": digest(config)}), flush=True)
    model = RecordedLocalModelAdapter(model_path)
    save(phase_path / "model-identity.json", model.identity)
    records, prefixes, forks = [], [], []
    if phase == "actionability":
        grid = [(w,"single",1,c,opts,"capability") for w in config[phase]["worlds"] for c,opts in config[phase]["conditions"].items()]
        probe = config[phase]["intervention_probes"]
        grid += [(w,arm,probe["n"],"D2",{k:probe[k] for k in ("steps","token_cap")},"intervention_probe")
                 for w in probe["worlds"] for arm in probe["policies"]]
    else:
        grid = [(w,arm["policy"],arm["n"],"D2",{k:config[phase][k] for k in ("steps","token_cap")},"collaboration")
                for w in config[phase]["worlds"] for arm in config[phase]["arms"]]
    save(phase_path / "expected-grid.json", [dict(world=w,arm=a,n=n,condition=c,component=component,**opts) for w,a,n,c,opts,component in grid])
    for index, (world, arm, n, condition, limits, component) in enumerate(grid):
        if source_identity() != sources:
            raise RuntimeError("source changed after freeze; stop without restarting")
        identity = f"{phase}-{index:03d}-{arm}-n{n}-{condition}"
        record = run_episode(world=world, arm=arm, n=n, condition=condition,
            output=phase_path / identity, model=model, campaign=budget, allocation_id=identity,
            seed=config["seed"]+tasks.worlds("development").index(world)*100 if phase == "actionability"
            else config["seed"]+10000+tasks.worlds("pilot").index(world)*100,
            capture_step=config["collaboration"]["fork_after_turn"] if phase == "collaboration" and arm == "candidate" and n == 2 else None,
            **limits)
        records.append({**record, "campaign_component":component})
        print(wire({"episode":identity,"world":world,"status":record["status"],"success":record["success"],
                    "tokens":record.get("metrics",{}).get("tokens") if record.get("metrics") else None,
                    "campaign_upper_bound":budget.snapshot()["held_token_upper_bound"]}),flush=True)
        if phase == "collaboration" and arm == "candidate" and n == 2:
            prefix, branches, _ = full_rollouts(record, output=phase_path / (identity+"-forks"), model=model, campaign=budget)
            prefixes.append(prefix)
            forks.extend(branches)
        if record["status"] != "VALID_KNOWN":
            # Unknown/invalid spending is retained; never auto-retry an external call.
            break
    save(phase_path / "records.json", records)
    save(phase_path / "accounting.json", budget.snapshot())
    save(phase_path / "campaign-completion.json", {"status":"COMPLETE" if len(records)==len(grid) else "INVALID_ABORT",
        "declared":len(grid),"executed":len(records),"unstarted":[dict(world=w,arm=a,n=n,condition=c,component=component,
            outcome=None,cost=None,reason="collection_stopped_after_invalid_or_unresolved_episode") for w,a,n,c,opts,component in grid[len(records):]],
        "counts_toward_verdict":False})
    if phase == "actionability":
        report = admit_actionability(records, config)
        save(phase_path / "admission.json", report)
    else:
        report = analyze_forks(prefixes, forks)
        save(phase_path / "sharing-analysis.json", report)
        exports = phase_path / "paired-exports"
        exports.mkdir()
        for n in (2,4):
            selected = [r for r in records if r["n"] == n and r["arm"] in ("blackboard","candidate")]
            world_ids = {family:[w for w in config[phase]["worlds"] if w.startswith(family+"/")] for family in tasks.FAMILIES}
            save(exports / f"n{n}.json", paired_call_export(selected, arms=("blackboard","candidate"),world_ids=world_ids))
    print(wire({"phase":phase,"report":report,"actual_budget":budget.snapshot()["held_token_upper_bound"]}),flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--phase", choices=("actionability","collaboration"), required=True)
    parser.add_argument("--provider-free-report", type=Path, required=True)
    args = parser.parse_args()
    collect(json.loads(args.config.read_text()),args.output,args.model_path,args.phase,
            json.loads(args.provider_free_report.read_text()))


if __name__ == "__main__":
    main()
