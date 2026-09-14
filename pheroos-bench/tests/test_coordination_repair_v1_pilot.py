from copy import deepcopy

from pheroos_bench.coordination_repair_v1_pilot import configuration, admit_actionability


def records(config):
    rows = []
    for world in config["actionability"]["worlds"]:
        for condition in config["actionability"]["conditions"]:
            rows.append(dict(world_id=world, family=world.split("/")[0], condition=condition,
                arm="single", status="VALID_KNOWN", success=True, stop="public_accepted_submission",
                campaign_component="capability", turns=[dict(model_response={"text":"reply"},
                    validation={"valid":True,"stage":"accepted","normalized_action":{"action":"submit"}},
                    materialized_receipts=["source-a"])]))
    for world in config["actionability"]["intervention_probes"]["worlds"]:
        for arm in ("blackboard","candidate"):
            rows.append(dict(world_id=world, family=world.split("/")[0], condition="D2", arm=arm,
                campaign_component="intervention_probe", status="VALID_KNOWN", success=True,
                stop="public_accepted_submission", metrics={"tool_calls":2,"inspection_dispatches":1},
                turns=[dict(agent="agent0" if arm=="blackboard" else "agent1", suggested_work=arm,
                    model_response={"text":"reply"}, validation={"valid":True,"stage":"accepted",
                    "normalized_action":{"action":"inspect","target":"source-a"}},materialized_receipts=[])]))
    return rows


def test_declared_complete_grid_including_all_possible_forks_fits_cycle_caps():
    c = configuration()
    diagnostics = len(c["actionability"]["worlds"])*sum(x["token_cap"] for x in c["actionability"]["conditions"].values())
    probe=c["actionability"]["intervention_probes"]
    probes=len(probe["worlds"])*len(probe["policies"])*probe["token_cap"]
    pilot=c["collaboration"]
    collection=len(pilot["worlds"])*len(pilot["arms"])*pilot["token_cap"]
    forks=len(pilot["worlds"])*len(pilot["fork_branches"])*pilot["token_cap"]
    assert diagnostics+probes+collection+forks == 499712
    assert diagnostics+probes+collection+forks <= c["cycle_caps"]["tokens"]
    assert c["counts_toward_verdict"] is False


def test_agent_relabeling_alone_cannot_admit_collaboration_collection():
    c=configuration()
    report=admit_actionability(records(c),c)
    assert report["checks"]["complete_known_records"]
    assert report["checks"]["d0_objective"]
    assert not report["checks"]["intervention_relevance"]
    assert not report["admitted"]


def test_real_dispatch_reuse_can_be_relevant_without_claiming_objective_gain():
    c=configuration()
    rows=records(c)
    next(r for r in rows if r["arm"]=="candidate")["metrics"]["inspection_dispatches"]=0
    report=admit_actionability(rows,c)
    assert report["admitted"]
    assert report["counts_toward_verdict"] is False
    assert report["intervention_comparisons"][0]["changed"] is False


def test_failed_diagnostic_missing_and_duplicate_cells_never_pass_gate():
    c=configuration()
    original=records(c)
    original[-1]["metrics"]["inspection_dispatches"]=0
    assert admit_actionability(original,c)["admitted"]
    missing=deepcopy(original);missing.pop(0)
    duplicate=deepcopy(original);duplicate.append(deepcopy(duplicate[0]))
    unresolved=deepcopy(original);unresolved[0]["status"]="VALID_UNRESOLVED"
    invalid=deepcopy(original);invalid[0]["status"]="INVALID_ABORT"
    for rows in (missing,duplicate,unresolved,invalid):
        report=admit_actionability(rows,c)
        assert not report["admitted"]
        assert not report["checks"]["complete_known_records"]
    duplicated_probe=deepcopy(original);duplicated_probe.append(deepcopy(duplicated_probe[-1]))
    assert not admit_actionability(duplicated_probe,c)["checks"]["intervention_relevance"]
