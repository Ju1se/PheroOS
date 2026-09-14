"""Provider-free measurement and orchestration counterexamples for v2."""

from copy import deepcopy
import json

import pytest

from pheroos_bench import coordination_repair_v1 as original
from pheroos_bench import coordination_repair_v1_tasks as tasks
from pheroos_bench import coordination_repair_v2 as repaired










def test_prompt_repetition_is_separate_from_mailbox_delivery_and_excludes_abandoned():
    messages = [{"role": "system", "content": "fixed rule"}, {"role": "user", "content": "same observation"}]
    calls = [dict(action="model.generate", state=state, request=json.dumps({"messages": messages}))
             for state in ("received", "response_rejected", "abandoned", "dispatched")]
    result = repaired._communication(dict(events=[], calls=calls))
    assert result["prompt_message_exposures"] == 6
    assert result["repeated_prompt_message_exposures"] == 4
    assert result["message_delivery_count"] == result["message_duplicate_count"] == 0
    assert result["message_duplicate_rate"] is None


def test_unobserved_mailbox_deliveries_are_unknown_not_a_prompt_proxy():
    snapshot = {"events": [{"event_type": "ext.session.message_sent", "lineage": {"message_id": "m1"}}], "calls": []}
    result = repaired._communication(snapshot)
    assert result["mailbox_messages_sent"] == 1
    assert result["message_measurement_status"] == "UNOBSERVED_DELIVERIES"
    assert result["message_duplicate_count"] is None
    assert result["message_duplicate_denominator"] is None
    assert result["prompt_message_exposures"] == 0


def progress_fixture(*, world="interval_intersection/dev_a", source="lower_bounds", step=0, kind="supplied_current_evidence"):
    value = tasks.inspect(world, step, source)
    raw = dict(world_id=world, preparations=[{"kind": kind, "artifact_ref": "r"}], turns=[],
               artifact_history=[dict(ref="r", value=value, turn=-1)])
    snapshot = dict(events=[dict(event_type="ext.session.published", lineage={"artifact_ref": "r"})],
                    artifacts=[dict(ref="r", value=json.dumps(value))])
    return raw, snapshot


@pytest.mark.parametrize("case", ["irrelevant", "import", "stale", "unpublished"])
def test_progress_does_not_count_irrelevant_imported_stale_or_unpublished_evidence(case):
    if case == "irrelevant":
        raw, snapshot = progress_fixture(source="unrelated_notice")
    elif case == "import":
        raw, snapshot = progress_fixture(kind="prefix_import")
    elif case == "stale":
        raw, snapshot = progress_fixture(world="version_correction/dev_a", source="current_values")
    else:
        raw, snapshot = progress_fixture()
        snapshot["events"] = []
    assert repaired._progress(raw, snapshot, {"condition": "D0"}) is None


def test_progress_rejects_history_that_disagrees_with_actual_publication():
    raw, snapshot = progress_fixture()
    raw["artifact_history"][0]["value"]["content"]["bounds"] = [999]
    with pytest.raises(ValueError, match="differs"):
        repaired._progress(raw, snapshot, {"condition": "D0"})


def prefix_parent():
    world = "interval_intersection/dev_a"
    values = [tasks.inspect(world, 0, source) for source in ("lower_bounds", "upper_bounds")]
    history = [dict(value=value, publisher="agent" + str(i), turn=i, ref="r" + str(i),
                    origin={"session": "/test/parent.sqlite", "artifact_ref": "r" + str(i)})
               for i, value in enumerate(values)]
    return dict(world_id=world, scope_id="parent", arm="candidate", n=2, token_cap=200,
        status="VALID_KNOWN", metrics={"tokens": 60},
        captured_prefix=dict(world_id=world, prefix_id="step-1", next_step=2, next_scheduler_turn=2,
            remaining_steps=4, history=history, private_feedback={"agent0": ["private error"], "agent1": []},
            prefix_tokens=40, prefix_hash="f" * 64, submission=None, model_seed=17,
            knowledge_readers={values[0]["receipt_identity"]: ["agent0", "agent1"],
                               values[1]["receipt_identity"]: ["agent1"]},
            failure_pressure=[dict(agent="agent0", target="lower_bounds", count=1)]))


@pytest.mark.parametrize("failed_status", ["INVALID_ABORT", "VALID_UNRESOLVED"])
def test_forks_stop_after_invalid_or_unresolved_and_keep_unstarted_rows(tmp_path, monkeypatch, failed_status):
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        return dict(status=failed_status, success=None, complete_rollout=True,  # must not trust this inconsistent flag
                    metrics={"tokens": 9, "unknown_calls": int(failed_status == "VALID_UNRESOLVED"), "invalid_actions": 2},
                    stop="budget_deadline_stop", diagnostics={"prefix_import_tool_dispatches": 1})

    monkeypatch.setattr(repaired, "run_episode", fail)
    prefix, records, episodes = repaired.full_rollouts(prefix_parent(), output=tmp_path / "forks")
    assert prefix["eligible"]
    assert len(calls) == len(episodes) == 1 and len(records) == 3
    assert [r["status"] for r in records] == [failed_status, "UNSTARTED", "UNSTARTED"]
    assert not any(r["complete_rollout"] for r in records)
    assert records[0]["incremental_tokens"] == 9
    assert records[0]["branch_setup_tool_calls"] == 1
    assert all(r["success"] is None and r["incremental_tokens"] is None for r in records[1:])
    assert not (tmp_path / "forks/withheld").exists()
    assert len(list((tmp_path / "forks").glob("*-record-v2.json"))) == 3


def test_valid_failed_rollouts_complete_all_branches_with_same_prefix_semantics(tmp_path, monkeypatch):
    calls = []

    def fail_objective(**kwargs):
        calls.append(kwargs)
        return dict(status="VALID_KNOWN", success=False, complete_rollout=True,
            scope_id=str(kwargs["output"]), metrics={"tokens": 8, "unknown_calls": 0, "invalid_actions": 1},
            stop="budget_deadline_stop", diagnostics={"prefix_import_tool_dispatches": 2})

    monkeypatch.setattr(repaired, "run_episode", fail_objective)
    parent = prefix_parent()
    before = deepcopy(parent)
    _, records, episodes = repaired.full_rollouts(parent, output=tmp_path / "forks")
    assert parent == before
    assert len(calls) == len(records) == len(episodes) == 3
    assert all(r["complete_rollout"] and r["success"] is False for r in records)
    for branch, call in zip(repaired.BRANCHES, calls):
        assert call["steps"] == 4 and call["token_cap"] == 160 and call["seed"] == 17
        assert call["start_step"] == call["scheduler_offset"] == 2
        assert call["initial_failures"] == before["captured_prefix"]["failure_pressure"]
        readers = {i["value"]["source_id"]: i["readers"] for i in call["imports"]}
        assert readers["lower_bounds"] == ["agent0", "agent1"]
        assert readers["upper_bounds"] == (["agent0", "agent1"] if branch == "relevant" else ["agent1"])
        assert bool(call["notes"]) is (branch == "irrelevant")


def test_unknown_parent_retains_eligibility_but_starts_no_branches(tmp_path, monkeypatch):
    parent = prefix_parent()
    parent["status"] = "VALID_UNRESOLVED"
    monkeypatch.setattr(repaired, "run_episode", lambda **kwargs: pytest.fail("must not launch a branch"))
    prefix, records, episodes = repaired.full_rollouts(parent, output=tmp_path / "forks")
    assert prefix["eligible"] and not episodes
    assert len(records) == 3 and all(r["status"] == "UNSTARTED" for r in records)


def test_wrapper_exception_after_work_cannot_launch_later_forks_or_become_zero_cost(tmp_path, monkeypatch):
    invocations = []

    def interrupted(**kwargs):
        invocations.append(kwargs)
        raise OSError("simulated failure after raw work may have started")

    monkeypatch.setattr(repaired, "run_episode", interrupted)
    _, records, episodes = repaired.full_rollouts(prefix_parent(), output=tmp_path / "forks")
    assert len(invocations) == len(episodes) == 1
    assert [r["status"] for r in records] == ["INVALID_ABORT", "UNSTARTED", "UNSTARTED"]
    assert all(r["incremental_tokens"] is None and r["unknown_calls"] is None for r in records)
    assert records[0]["error"]["type"] == "OSError"
    assert all(not r["complete_rollout"] for r in records)


def test_missing_snapshot_is_explicit_and_permission_stage_still_preserved():
    raw = dict(method_version=original.METHOD, status="INVALID_ABORT", metrics=None,
               error={"type": "PermissionError", "stage": "runtime_lease_failure"}, success=None)
    corrected = repaired._correct(raw, None, {"model": object()})
    assert corrected["diagnostics"]["status"] == "UNAVAILABLE"
    assert corrected["metrics"] is None
    assert corrected["primary_failure_stage"] == "capability_permission"
    assert raw["error"]["stage"] == "runtime_lease_failure"


def test_missing_snapshot_cannot_preserve_nominal_known_success_or_erase_cost():
    raw = dict(method_version=original.METHOD, status="VALID_KNOWN", success=True,
               metrics={"tokens": 91}, stop="public_accepted_submission", primary_failure_stage=None)
    corrected = repaired._correct(raw, None, {})
    assert corrected["raw_status"] == "VALID_KNOWN"
    assert corrected["status"] == "INVALID_ABORT" and corrected["success"] is None
    assert corrected["metrics"]["tokens"] == 91
    assert corrected["primary_failure_stage"] == "runtime_lease_failure"
    assert corrected["complete_rollout"] is False


@pytest.mark.parametrize("after_execution", [False, True])
def test_source_guard_stops_branch_dispatch_and_preserves_already_returned_cost(tmp_path, monkeypatch, after_execution):
    executions, checks = [], []

    def verify():
        checks.append(1)
        if len(checks) == (2 if after_execution else 1):
            raise RuntimeError("frozen source changed")

    def finish(**kwargs):
        executions.append(kwargs)
        return dict(status="VALID_KNOWN", success=True, complete_rollout=True,
                    stop="public_accepted_submission", metrics={"tokens": 41, "unknown_calls": 0, "invalid_actions": 0})

    monkeypatch.setattr(repaired, "run_episode", finish)
    _, records, _ = repaired.full_rollouts(prefix_parent(), output=tmp_path / "forks", verify_frozen=verify)
    assert len(executions) == int(after_execution)
    assert [r["status"] for r in records] == ["INVALID_ABORT", "UNSTARTED", "UNSTARTED"]
    assert records[0]["execution_started"] is after_execution
    assert records[0]["incremental_tokens"] == (41 if after_execution else None)
    assert records[0]["raw_status"] == ("VALID_KNOWN" if after_execution else None)
    assert not any(r["complete_rollout"] for r in records)


def test_nominal_known_incomplete_branch_is_invalid_even_for_legacy_analysis(tmp_path, monkeypatch):
    def incomplete(**kwargs):
        return dict(status="VALID_KNOWN", success=False, complete_rollout=False,
                    stop="budget_deadline_stop", metrics={"tokens": 13, "unknown_calls": 0, "invalid_actions": 0})

    monkeypatch.setattr(repaired, "run_episode", incomplete)
    _, records, _ = repaired.full_rollouts(prefix_parent(), output=tmp_path / "forks")
    assert records[0]["status"] == "INVALID_ABORT" and records[0]["raw_status"] == "VALID_KNOWN"
    assert records[0]["incremental_tokens"] == 13
    assert [r["status"] for r in records[1:]] == ["UNSTARTED", "UNSTARTED"]
