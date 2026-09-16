"""Execution constraints stay real while the replacement policy stays replaceable."""

from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from pheroos_interaction.runner import inspection


def write(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n")


def load(path):
    return json.loads(path.read_text())


@pytest.fixture
def case(tmp_path, monkeypatch):
    monkeypatch.setattr(inspection, "source_identity", lambda: {"test/source.py": "a" * 64})
    source = tmp_path / "source"
    source.mkdir()
    write(source / "value.json", {"outcome": False})
    config = {
        "scope": "fixture", "reader": "analyst", "source_id": "binary-source", "source_version": 3,
        "tool": "read_binary_source", "tool_version": "binary-json-v1",
        "assumptions": {"family": "fixed-prior-symmetric-positive-copy-v1", "version": "assumption-v1",
                        "source": "declared fixture channel", "applicability": "test fixture only",
                        "prior": .5, "q_low": .9, "q_high": .95, "rho_low": 0, "rho_high": 0},
        "losses": {"false_accept": 8, "false_reject": 4, "abstain": 1}, "query_cost": .2,
        "limits": {"max_calls": 3, "token_cap": 0},
    }
    descriptor = {key: config[key] for key in ("scope", "source_id", "source_version", "tool", "tool_version")}
    descriptor.update(readers=["analyst"], state_fingerprint=sha256((source / "value.json").read_bytes()).hexdigest())
    write(source / "source.json", descriptor)
    config_path = tmp_path / "request.json"
    write(config_path, config)
    return config_path, source, tmp_path / "run"


def change_config(case, mutate):
    config = load(case[0])
    mutate(config)
    write(case[0], config)


def assert_replay(case, status):
    assert inspection.replay_inspection(case[2])["result"]["status"] == status


def test_receipt_bound_to_frozen_plan_after_durable_dispatch(case, monkeypatch):
    original_read = inspection._read
    reads = []

    def read(path, limit):
        if Path(path).name == "value.json":
            with sqlite3.connect(case[2] / "session.sqlite") as db:
                assert db.execute("SELECT state FROM calls").fetchone()[0] == "dispatched"
            assert (case[2] / "frozen.json").is_file()
            reads.append(path)
        return original_read(path, limit)

    monkeypatch.setattr(inspection, "_read", read)
    result = inspection.run_inspection(*case)
    assert result["status"] == "COMPLETE" and result["action"] == "reject"
    assert result["call_count"] == len(reads) == 1
    snapshot = load(case[2] / "session.json")
    assert json.loads(snapshot["run"]["limits"])["max_calls"] == 3
    assert snapshot["actual_tokens"] == 0 and snapshot["unknown_calls"] == 0
    receipt = load(case[2] / "receipt.json")
    frozen = load(case[2] / "frozen.json")
    assert receipt["artifact"]["plan_sha256"] == frozen["plan_sha256"]
    assert frozen["config"]["assumptions"]["reference"] is True
    assert frozen["config"]["assumptions"]["source"] == "declared fixture channel"
    assert_replay(case, "COMPLETE")


def test_cost_screen_never_reads_missing_payload_or_reserves(case, monkeypatch):
    change_config(case, lambda c: c.update(query_cost=2))
    (case[1] / "value.json").unlink()
    monkeypatch.setattr(inspection.CoordinationSession, "create", lambda *a, **kw: pytest.fail("skip cannot reserve"))
    result = inspection.run_inspection(*case)
    assert result["status"] == "SKIPPED" and result["call_count"] == 0
    assert not (case[2] / "session.sqlite").exists()
    assert load(case[2] / "frozen.json")["plan"]["query_delta"] is None
    assert_replay(case, "SKIPPED")


def test_known_channel_without_value_does_not_claim_real_independence(case):
    change_config(case, lambda c: c["assumptions"].update(rho_high=1))
    (case[1] / "value.json").unlink()
    result = inspection.run_inspection(*case)
    assert result["status"] == "SKIPPED"
    assert load(case[2] / "frozen.json")["plan"]["risk_basis"].endswith("verification of actual dependencies")


@pytest.mark.parametrize("key,value", [
    ("scope", "foreign-scope"), ("source_version", 4), ("source_id", "other-source"), ("reader", "outsider"),
])
def test_actual_source_contract_rejects_mismatch_before_output(case, key, value):
    change_config(case, lambda c: c.update({key: value}))
    with pytest.raises(PermissionError):
        inspection.run_inspection(*case)
    assert not case[2].exists()


@pytest.mark.parametrize("mutate", [
    lambda c: c.update(tool="model.generate"),
    lambda c: c.update(tool_version="unrecognized"),
    lambda c: c["assumptions"].update(family="unknown-family"),
    lambda c: c["assumptions"].update(reference=False),
    lambda c: c["losses"].pop("false_accept"),
    lambda c: c["limits"].update(max_calls=0),
    lambda c: c["limits"].update(token_cap=True),
])
def test_no_tool_family_loss_or_limit_fallback(case, mutate):
    change_config(case, mutate)
    with pytest.raises((ValueError, TypeError)):
        inspection.run_inspection(*case)
    assert not case[2].exists()


def test_unknown_source_outcome_consumes_one_attempt_and_abstains(case):
    write(case[1] / "value.json", {"outcome": None})
    descriptor = load(case[1] / "source.json")
    descriptor["state_fingerprint"] = sha256((case[1] / "value.json").read_bytes()).hexdigest()
    write(case[1] / "source.json", descriptor)
    result = inspection.run_inspection(*case)
    assert result["status"] == "UNKNOWN" and result["action"] == "abstain" and result["call_count"] == 1
    assert result["unknown_calls"] == 0  # A settled null outcome differs from missing receipt.
    assert_replay(case, "UNKNOWN")


def test_dispatched_io_error_remains_unresolved_and_cannot_retry(case, monkeypatch):
    original = inspection._read
    attempts = []

    def fail_payload(path, limit):
        if Path(path).name == "value.json":
            attempts.append(path)
            raise OSError("test unavailable source")
        return original(path, limit)

    monkeypatch.setattr(inspection, "_read", fail_payload)
    result = inspection.run_inspection(*case)
    assert result["status"] == "UNKNOWN" and result["unknown_calls"] == 1
    assert result["action"] == "abstain" and len(attempts) == 1
    assert_replay(case, "UNKNOWN")
    with pytest.raises(FileExistsError):
        inspection.run_inspection(*case)
    assert len(attempts) == 1


@pytest.mark.parametrize("boundary,expected_count,expected_unknown", [
    ("before_reserve", 0, 0), ("after_reserve", 1, 0), ("after_dispatch", 1, 1), ("before_publish", 1, 0)
])
def test_cancellation_fences_actions_at_execution_boundaries(case, monkeypatch, boundary, expected_count, expected_unknown):
    target = {"before_reserve": "evaluate", "after_reserve": "reserve", "after_dispatch": "dispatch", "before_publish": "publish_received"}[boundary]
    cls = inspection.SessionDriver if target == "evaluate" else inspection.CoordinationSession
    original = getattr(cls, target)

    def cancel_at_boundary(self, *args, **kwargs):
        session = self.session if target == "evaluate" else self
        if boundary in ("before_reserve", "before_publish"):
            session.cancel()
            return original(self, *args, **kwargs)
        result = original(self, *args, **kwargs)
        session.cancel()
        return result

    monkeypatch.setattr(cls, target, cancel_at_boundary)
    result = inspection.run_inspection(*case)
    assert result["status"] == "CANCELLED" and result["action"] == "abstain"
    assert result["call_count"] == expected_count and result["unknown_calls"] == expected_unknown
    assert not load(case[2] / "session.json")["artifacts"]
    assert_replay(case, "CANCELLED")


def test_source_revision_changed_after_dispatch_prevents_payload_read(case, monkeypatch):
    original = inspection.CoordinationSession.dispatch

    def change_after_dispatch(self, *args):
        result = original(self, *args)
        source = load(case[1] / "source.json")
        source["source_version"] += 1
        write(case[1] / "source.json", source)
        (case[1] / "value.json").unlink()
        return result

    monkeypatch.setattr(inspection.CoordinationSession, "dispatch", change_after_dispatch)
    result = inspection.run_inspection(*case)
    assert result["status"] == "UNKNOWN" and result["error_type"] == "PermissionError"
    assert_replay(case, "UNKNOWN")


def test_source_readers_changed_before_publication_blocks_action(case, monkeypatch):
    original = inspection._read

    def revoke_after_payload(path, limit):
        raw = original(path, limit)
        if Path(path).name == "value.json":
            descriptor = load(case[1] / "source.json")
            descriptor["readers"] = ["new-reader"]
            write(case[1] / "source.json", descriptor)
        return raw

    monkeypatch.setattr(inspection, "_read", revoke_after_payload)
    result = inspection.run_inspection(*case)
    assert result["status"] == "STOPPED" and result["action"] == "abstain"
    assert result["unknown_calls"] == 0
    assert not load(case[2] / "session.json")["artifacts"]
    assert_replay(case, "STOPPED")


def test_mismatched_payload_is_retained_as_unresolved(case):
    write(case[1] / "value.json", {"outcome": True})
    result = inspection.run_inspection(*case)
    assert result["status"] == "UNKNOWN" and result["action"] == "abstain"
    assert result["error_type"] == "StateError"
    assert_replay(case, "UNKNOWN")


def test_strategy_is_not_replanned_after_receipt(case, monkeypatch):
    original, invocations = inspection.plan_inspection, []

    def once(*args, **kwargs):
        invocations.append(args)
        assert len(invocations) == 1
        return original(*args, **kwargs)

    monkeypatch.setattr(inspection, "plan_inspection", once)
    assert inspection.run_inspection(*case)["status"] == "COMPLETE"


def test_replay_never_reads_source_or_opens_writable_session(case, monkeypatch):
    inspection.run_inspection(*case)
    for path in case[1].iterdir():
        path.unlink()
    case[1].rmdir()
    before = {path.name: sha256(path.read_bytes()).hexdigest() for path in case[2].iterdir()}
    monkeypatch.setattr(inspection.SessionDriver, "evaluate", lambda *a, **kw: pytest.fail("replay cannot dispatch"))
    monkeypatch.setattr(inspection.CoordinationSession, "__init__", lambda *a, **kw: pytest.fail("replay cannot open Session"))
    replay = inspection.replay_inspection(case[2])
    assert replay["status"] == "PASS" and replay["new_tool_calls"] == 0
    assert before == {path.name: sha256(path.read_bytes()).hexdigest() for path in case[2].iterdir()}


@pytest.mark.parametrize("file,mutate", [
    ("frozen.json", lambda value: value["plan"].update(stop_action="accept")),
    ("frozen.json", lambda value: value["config"]["assumptions"].update(version="new-version")),
    ("receipt.json", lambda value: value["artifact"].update(outcome=True)),
    ("receipt.json", lambda value: value["artifact"].update(plan_sha256="b" * 64)),
    ("result.json", lambda value: value.update(action="accept")),
    ("session.json", lambda value: value.update(call_count=0)),
])
def test_tampered_plan_receipt_result_or_snapshot_rejects_replay(case, file, mutate):
    inspection.run_inspection(*case)
    value = load(case[2] / file)
    mutate(value)
    write(case[2] / file, value)
    with pytest.raises(ValueError):
        inspection.replay_inspection(case[2])


def test_source_identity_mismatch_requires_explicit_historical_replay(case, monkeypatch):
    inspection.run_inspection(*case)
    monkeypatch.setattr(inspection, "source_identity", lambda: {"test/source.py": "b" * 64})
    with pytest.raises(ValueError, match="source identity"):
        inspection.replay_inspection(case[2])
    result = inspection.replay_inspection(case[2], require_source_match=False)
    assert result["status"] == "PASS" and not result["source_match"]


def test_source_identity_drift_blocks_publication(case, monkeypatch):
    original = inspection.SessionDriver.evaluate

    def drift(self, *args):
        response = original(self, *args)
        monkeypatch.setattr(inspection, "source_identity", lambda: {"test/source.py": "b" * 64})
        return response

    monkeypatch.setattr(inspection.SessionDriver, "evaluate", drift)
    result = inspection.run_inspection(*case)
    assert result["status"] == "STOPPED" and result["action"] == "abstain"
    assert inspection.replay_inspection(case[2], False)["status"] == "PASS"


def test_duplicate_fields_and_payload_byte_bounds_are_enforced(case):
    case[0].write_text('{"scope":"fixture","scope":"foreign"}')
    with pytest.raises(ValueError, match="duplicate"):
        inspection.run_inspection(*case)
    assert not case[2].exists()


@pytest.mark.parametrize("table,column,value", [
    ("coordination_sources_v1", "readers", '["outsider"]'),
    ("coordination_sources_v1", "version", 4),
    ("coordination_inspections_v1", "tool_version", "foreign-tool-v2"),
    ("coordination_inspections_v1", "source_version", 4),
    ("coordination_inspections_v1", "readers", '["outsider"]'),
])
def test_durable_contract_tamper_rejects_even_with_updated_snapshot_digest(case, table, column, value):
    inspection.run_inspection(*case)
    with sqlite3.connect(case[2] / "session.sqlite") as db:
        db.execute(f"UPDATE {table} SET {column}=?", (value,))
    snapshot = inspection._snapshot_readonly(case[2] / "session.sqlite")
    write(case[2] / "session.json", snapshot)
    result = load(case[2] / "result.json")
    result["session_sha256"] = inspection._digest(snapshot)
    write(case[2] / "result.json", result)
    with pytest.raises(ValueError, match="durable source or inspection"):
        inspection.replay_inspection(case[2])


def test_recorded_source_revocation_is_replayable_without_publishing(case, monkeypatch):
    original = inspection.SessionDriver.evaluate

    def revoke(self, *args):
        response = original(self, *args)
        artifact = response["artifact"]
        self.session.source_update(artifact["source_id"], artifact["source_version"], [], artifact["state_fingerprint"])
        return response

    monkeypatch.setattr(inspection.SessionDriver, "evaluate", revoke)
    result = inspection.run_inspection(*case)
    assert result["status"] == "STOPPED" and result["action"] == "abstain"
    assert not load(case[2] / "session.json")["artifacts"]
    assert_replay(case, "STOPPED")


def test_exception_after_settlement_retains_durable_receipt_without_retry(case, monkeypatch):
    original = inspection.CoordinationSession.receive
    invocations = []

    def fail_after_settlement(self, *args):
        original(self, *args)
        invocations.append(args)
        raise OSError("receipt committed before interrupted return")

    monkeypatch.setattr(inspection.CoordinationSession, "receive", fail_after_settlement)
    result = inspection.run_inspection(*case)
    assert result["status"] == "STOPPED" and result["action"] == "abstain"
    assert result["unknown_calls"] == 0 and len(invocations) == 1
    assert (case[2] / "receipt.json").is_file()
    assert_replay(case, "STOPPED")


def test_expired_lease_after_settlement_reclaims_and_publishes_without_second_read(case, monkeypatch):
    original = inspection.CoordinationSession.receive
    invocations = []

    def expire_after_settlement(self, *args):
        original(self, *args)
        invocations.append(args)
        self.clock = lambda: 10**12

    monkeypatch.setattr(inspection.CoordinationSession, "receive", expire_after_settlement)
    result = inspection.run_inspection(*case)
    snapshot = load(case[2] / "session.json")
    assert result["status"] == "COMPLETE" and result["action"] == "reject"
    assert result["call_count"] == len(invocations) == 1
    assert snapshot["work"][0]["epoch"] == 2
    assert snapshot["calls"][0]["epoch"] == 1
    assert snapshot["actual_tokens"] == snapshot["unknown_calls"] == 0
    assert len(snapshot["artifacts"]) == 1
    assert_replay(case, "COMPLETE")


@pytest.mark.parametrize("raw", [b'{"outcome":false}' + b' ' * 257, b'{"outcome":false,"outcome":true}', b'{"outcome":1}'])
def test_raw_source_bounds_and_exact_binary_shape_are_not_silently_repaired(case, raw):
    (case[1] / "value.json").write_bytes(raw)
    descriptor = load(case[1] / "source.json")
    descriptor["state_fingerprint"] = sha256(raw).hexdigest()
    write(case[1] / "source.json", descriptor)
    result = inspection.run_inspection(*case)
    assert result["status"] == "UNKNOWN" and result["unknown_calls"] == 1
    assert result["error_type"] == "ValueError"
    assert not (case[2] / "receipt.json").exists()
    assert_replay(case, "UNKNOWN")


@pytest.mark.parametrize("different_source,historical", [(False, False), (False, True), (True, True)])
def test_replay_control_limit_depends_on_executed_source_identity(case, monkeypatch, different_source, historical):
    inspection.run_inspection(*case)
    source = load(case[2] / "frozen.json")["source"]
    update = {"id": source["source_id"], "version": source["source_version"],
              "readers": source["readers"], "state_fingerprint": source["state_fingerprint"]}
    # This history was possible before enforcement: one claim plus eight
    # accepted identical updates, despite the frozen limit of eight controls.
    event = {"event_type": "interaction.evidence.source_updated", "details": update}
    with sqlite3.connect(case[2] / "session.sqlite") as db:
        db.executemany("INSERT INTO events(value) VALUES (?)", [(json.dumps(event),)] * 8)
    snapshot = inspection._snapshot_readonly(case[2] / "session.sqlite")
    write(case[2] / "session.json", snapshot)
    result = load(case[2] / "result.json")
    result["session_sha256"] = inspection._digest(snapshot)
    write(case[2] / "result.json", result)
    if different_source:
        monkeypatch.setattr(inspection, "source_identity", lambda: {"test/source.py": "b" * 64})
        with pytest.raises(ValueError, match="explicit historical"):
            inspection.replay_inspection(case[2])
        replay = inspection.replay_inspection(case[2], require_source_match=not historical)
        assert replay["source_match"] is False and replay["new_tool_calls"] == 0
    else:
        with pytest.raises(ValueError, match="control operation bound"):
            inspection.replay_inspection(case[2], require_source_match=not historical)
