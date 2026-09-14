"""Diagnostic contrasts, unchanged evaluator, and explicit failure boundaries."""

import json
from pathlib import Path

import pytest

from pheroos_bench import coordination_repair_v1_tasks as tasks
from pheroos_bench import model_interface_v1 as diagnostic
from pheroos_bench.model_interface_v1_pilot import configuration, expected_grid, verify_predecessor


def evidence(world):
    return [tasks.inspect(world, 2, s["source_id"]) for s in tasks.public_world(world, 2)["sources"] if s["required"]]


def test_frozen_views_match_all_retained_d0_prompts_and_output_contrast():
    retained = Path(__file__).parents[1] / "next-cycle/coordination-repair-live-v1/campaign/actionability"
    for index, world in enumerate(tasks.worlds("development")):
        record = json.loads((retained / f"actionability-{index * 3:03d}-single-n1-D0/episode-v2.json").read_text())
        prompt = diagnostic.build_messages(world, "envelope_256", evidence(world))
        assert prompt == record["turns"][0]["messages"]
        assert prompt == diagnostic.build_messages(world, "envelope_1024", evidence(world))


def test_compact_views_preserve_facts_versions_and_rule_without_hidden_scoring(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("hidden/reference answer reached prompt construction")
    monkeypatch.setattr(tasks, "score", forbidden)
    monkeypatch.setattr(tasks, "reference_action", forbidden)
    for world in tasks.worlds("development"):
        artifacts, public = evidence(world), tasks.public_world(world, 2)
        for arm in ("direct_json_256", "compact_action_256"):
            view = json.loads(diagnostic.build_messages(world, arm, artifacts)[1]["content"])
            assert view["sources"] == [{k: r[k] for k in ("source_id", "source_version", "content")} for r in artifacts]
            assert view["question"] == public["rule"]
            assert "agent" not in view and "private_feedback" not in view
            for key in ("requested_key", "task_ids", "item_ids"):
                if key in public:
                    assert view[key] == public[key]


def test_direct_wrapper_never_repairs_a_valid_wrong_answer():
    world = "interval_intersection/dev_a"
    result = diagnostic.validate_response(world, "direct_json_256", '{"selection":4}', evidence(world))
    assert result["valid"]
    assert result["compiled_action"]["answer"] == {"selection": 4}
    assert result["artifact"]["answer"] == {"selection": 4}
    assert result["citations_origin"] == "runtime_supplied"
    assert tasks.score(world, 2, result["artifact"]) is False


@pytest.mark.parametrize("raw", ['{"selection":4', '{"selection":4,"selection":5}',
                                  '{"selection":true}', '{"answer":{"selection":5}}'])
def test_direct_malformed_or_wrong_shape_is_not_repaired(raw):
    result = diagnostic.validate_response("interval_intersection/dev_a", "direct_json_256", raw,
                                          evidence("interval_intersection/dev_a"))
    assert result["valid"] is False and result["artifact"] is None and result["compiled_action"] is None


def test_direct_current_evidence_boundary_does_not_create_authority_for_stale_receipts():
    world = "version_correction/dev_a"
    stale = [tasks.inspect(world, 0, "current_values")]
    with pytest.raises(ValueError, match="stale"):
        diagnostic.build_messages(world, "direct_json_256", stale)
    result = diagnostic.validate_response(world, "direct_json_256", '{"value":11}', stale)
    assert result["valid"] is False and result["stage"] == "missing_or_stale_evidence"


def test_action_modes_keep_original_citation_validation_and_submit_only_boundary():
    world = "version_correction/dev_a"
    for arm in ("compact_action_256", "envelope_256", "envelope_1024"):
        result = diagnostic.validate_response(world, arm,
            '{"action":"submit","answer":{"value":11},"citations":[]}', evidence(world))
        assert result["valid"] is False and result["stage"] == "missing_or_stale_evidence"
        assert result["citations_origin"] == "model_supplied" and result["compiled_action"] is None
        result = diagnostic.validate_response(world, arm, '{"action":"inspect","target":"current_values"}', evidence(world))
        assert result["valid"] is False and result["stage"] == "action_schema"


def test_grid_pairs_two_seeds_inside_eight_worlds_and_retains_caps():
    config = configuration()
    rows = expected_grid(config)
    assert rows == expected_grid(json.loads(json.dumps(config, sort_keys=True)))
    assert len(rows) == len({tuple(r.values()) for r in rows}) == 64
    assert len({r["world"] for r in rows}) == 8
    for world in config["worlds"]:
        group = [r for r in rows if r["world"] == world]
        assert {r["arm"] for r in group} == set(diagnostic.ARMS)
        assert len({r["seed"] for r in group}) == 2
    assert config["campaign_token_cap"] + config["continuation"]["prior_tokens"] == 196734
    assert config["campaign_dispatch_cap"] + config["continuation"]["prior_intent_slots"] == 178
    config["arms"]["envelope_1024"]["max_new_tokens"] = 1
    assert configuration()["arms"]["envelope_1024"]["max_new_tokens"] == 1024
    assert configuration()["admission_thresholds"] is None


def test_partial_duplicate_or_unresolved_records_do_not_emit_valid_subset_summary():
    config = configuration()
    expected = expected_grid(config)
    rows = [{"world_id": r["world"], "arm": r["arm"], "seed": r["seed"],
             "status": "VALID_KNOWN", "complete": True} for r in expected]
    for records in (rows[:-1], rows[:-1] + [rows[0]], [{**rows[0], "status": "VALID_UNRESOLVED"}] + rows[1:]):
        result = diagnostic.summarize(records, expected)
        assert result["status"] == "INVALID" and result["effects"] is None
        assert result["collaboration_admitted"] is False


def test_prior_completed_negative_diagnostic_stays_known_and_charged():
    path = Path(__file__).parents[1] / "next-cycle/coordination-repair-live-v1/campaign/actionability"
    prior = verify_predecessor(path)
    assert prior["known_tokens"] == 65662 and prior["retained_intent_slots"] == 114
