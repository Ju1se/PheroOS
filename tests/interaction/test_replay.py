"""Synthetic retained receipts test replay failures without external data."""

from copy import deepcopy
from hashlib import sha256
import json
import sqlite3

import pytest

from pheroos_interaction import visibility
from pheroos_interaction.experiments.current.replay import ReplayMismatch, _hash, _replay_episode, _wire, run_replay


def save(path, value):
    path.write_text(json.dumps(value))


def make_cell(path):
    path.mkdir()
    records = [dict(id="root:task:simple_arithmetic", kind="root", owner="host", readers=["a", "b"],
                    round_index=-1, body={}, parents=[], provenance_known=True)]
    calls, rows, work, events = [], [], [], []
    for round_index in (0, 1, 2):
        contexts = {a: visibility.build_request("simple_arithmetic", a, "isolated_revision", round_index,
                    deepcopy(records), lambda r: r["body"]) for a in ("a", "b")}
        for agent in ("a", "b"):
            identifier = f"model-r{round_index}-{agent}"
            work.append(dict(id=identifier, declaration="{}"))
            events.append(dict(event_type="ext.session.claimed", lineage=dict(task_id=identifier)))
        for position, agent in enumerate(("b", "a") if round_index == 1 else ("a", "b")):
            identifier, context = f"model-r{round_index}-{agent}", contexts[agent]
            bad = round_index == 1 and agent == "b"
            raw = '{"action":"inspect","target":"graph"}' if bad else '{"action":"submit","answer":13,"citations":[]}'
            parsed = dict(valid=False, action=None, reason="invalid_json_action_or_window") if bad else dict(valid=True,
                          action=dict(action="submit", answer=13, citations=[]), reason=None)
            adapter = sha256(json.dumps(["session-v1", "inline-session", identifier], separators=(",", ":")).encode()).hexdigest()
            request = dict(task_id=identifier, version=1, messages=context["messages"], seed=2718 + round_index,
                           max_new_tokens=512, adapter_call_id=adapter)
            receipt = dict(usage=dict(prompt_tokens=20, completion_tokens=10, total_tokens=30),
                           response_id="fixture-" + identifier, request_id=None, returned_model="recorded_fixture")
            response = dict(**receipt, text=raw, prompt_tokens=20, completion_tokens=10, cost_cny="0.0004000")
            call = dict(id=identifier, work_id=identifier, version=1, epoch=1, action="model.generate", request=request,
                        state="received", response=response, actual=30)
            calls.append({**call, "request": _wire(request), "response": _wire(response)})
            binding = dict(session_call=call, confirmed_sent_record_ids=context["sent_record_ids"],
                           confirmed_public_task_sha256=context["public_task_sha256"], adapter_call_id=adapter,
                           money_call=dict(id=adapter, state="settled", actual=4000, receipt=receipt))
            row = dict(round_index=round_index, agent=agent, call_id=identifier, binding=binding, parsed=parsed,
                       proposal_id=f"proposal:r{round_index}:{agent}", quality=not bad, current_citations=not bad,
                       grounded_correct=not bad, status="VALID_KNOWN", dispatch_index=round_index * 2 + position)
            rows.append(row)
            save(path / f"r{round_index}-{agent}-intent.json", dict(projection=context, runtime_reads=[],
                                                                 seed=2718 + round_index, max_new_tokens=512))
            records.append(dict(id=row["proposal_id"], kind="proposal", owner=agent, readers=["a", "b"], round_index=round_index,
                body=dict(raw=raw, parsed=parsed, task_version=1), parents=context["sent_record_ids"] + ["root:task:simple_arithmetic"],
                provenance_known=True, call_id=identifier, session_path="/retained/inline/session.sqlite"))
    run = dict(run_id="inline-session", status="cancelled")
    db = sqlite3.connect(path / "session.sqlite")
    for table, values in (("calls", calls), ("work", work), ("run", [run])):
        columns = list(values[0])
        schema = ','.join(c + (' INTEGER' if type(values[0][c]) is int else ' TEXT') for c in columns)
        db.execute(f"CREATE TABLE {table} ({schema})")
        db.executemany(f"INSERT INTO {table} VALUES ({','.join('?' for _ in columns)})", [[r[c] for c in columns] for r in values])
    db.execute("CREATE TABLE artifacts (ref TEXT)")
    db.execute("CREATE TABLE coordination_inspections_v1 (work_id TEXT)")
    db.execute("CREATE TABLE coordination_sources_v1 (id TEXT, readers TEXT)")
    db.execute("CREATE TABLE events (seq INTEGER PRIMARY KEY, value TEXT)")
    db.executemany("INSERT INTO events(value) VALUES (?)", [(_wire(e),) for e in events])
    db.commit()
    db.close()
    save(path / "session-snapshot.json", dict(calls=calls, artifacts=[], work=work, run=run, events=events))
    save(path / "tool-receipts.json", [])
    save(path / "records.json", records)
    return dict(world_id="simple_arithmetic", arm="isolated_revision", calls=rows,
                tool_calls=0, actual_tool_executions=0, model_calls=6, actual_tokens=180)


def test_small_retained_cell_reexecutes_policy_parser_and_evaluator(tmp_path):
    cell = tmp_path / "cell"
    episode = make_cell(cell)
    result = _replay_episode(cell, episode, v2=False)
    assert len(result["calls"]) == 6 and result["cache_hits"] == 0
    assert all(c["mode"] == "offline_replay" and not c["new_provider_receipt"] for c in result["calls"])
    assert sum(c["quality"] for c in result["calls"]) == 5
    assert all(c["raw_usage"] == {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30} for c in result["calls"])
    assert all(c["cache_field_status"] == "UNKNOWN_PRICED_UNCACHED" for c in result["calls"])


@pytest.mark.parametrize("corruption", ["sent_message", "record_parent", "cost", "parse_reason"])
def test_replay_rejects_changed_inputs_parents_cost_and_reasons(tmp_path, corruption):
    cell = tmp_path / "cell"
    episode = make_cell(cell)
    if corruption == "sent_message":
        p = cell / "r0-a-intent.json"
        data = json.loads(p.read_text())
        data["projection"]["messages"][1]["content"] += " "
        save(p, data)
    elif corruption == "record_parent":
        p = cell / "records.json"
        data = json.loads(p.read_text())
        data[1]["parents"] = []
        save(p, data)
    elif corruption == "cost":
        episode["calls"][0]["binding"]["money_call"]["actual"] += 1
    else:
        episode["calls"][0]["parsed"]["reason"] = "changed"
    with pytest.raises(ReplayMismatch):
        _replay_episode(cell, episode, v2=False)


def test_top_level_replay_retains_failure_and_refuses_overwrite(tmp_path):
    source, output = tmp_path / "source", tmp_path / "output"
    source.mkdir()
    save(source / "frozen-config.json", visibility.configuration())
    save(source / "records.json", [])
    save(source / "expected-grid.json", visibility.expected_grid())
    with pytest.raises(ReplayMismatch):
        run_replay(source, output)
    report = json.loads((output / "report.json").read_text())
    assert report["status"] == "FAIL" and report["new_provider_receipts"] == 0
    with pytest.raises(FileExistsError):
        run_replay(source, output)


@pytest.mark.parametrize("relationship", ["same", "descendant", "ancestor", "symlink"])
def test_replay_rejects_output_overlapping_frozen_input_before_writing(tmp_path, relationship):
    source = tmp_path / "frozen" / "run"
    source.mkdir(parents=True)
    marker = source / "retained.json"
    marker.write_text('{"unchanged":true}\n')
    output = {"same": source, "descendant": source / "new" / "output",
              "ancestor": tmp_path / "frozen", "symlink": tmp_path / "alias"}[relationship]
    if relationship == "symlink":
        output.symlink_to(source, target_is_directory=True)
    before = sorted(str(p.relative_to(source)) for p in source.rglob("*"))
    with pytest.raises(ReplayMismatch, match="separate from the retained input tree"):
        run_replay(source, output)
    assert marker.read_text() == '{"unchanged":true}\n'
    assert sorted(str(p.relative_to(source)) for p in source.rglob("*")) == before
    assert not (source / "new").exists()
