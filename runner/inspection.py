"""One optional local binary read, using the existing durable execution boundary.

A valid declared channel is an assumption, not proof of source independence or
calibration. This runner accepts no provider, experiment truth, or fallback solver.
"""

from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3

from pheroos_interaction.inspection import ModelAssumptions, Losses, plan_inspection, apply_plan
from pheroos_interaction.records import StateError
from .driver import SessionDriver
from .evidence import CoordinationSession
from .identity import source_identity

_FORMAT = "inspection-local-v1"
_TOOL = "read_binary_source"
_TOOL_VERSION = "binary-json-v1"


def _wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value):
    return sha256(_wire(value)).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _parse(raw):
    return json.loads(raw, object_pairs_hook=_unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def _read(path, limit):
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("input exceeds byte bound")
    return raw


def _load(path, limit=65536):
    return _parse(_read(path, limit))


def _save(path, value):
    with Path(path).open("xb") as stream:
        stream.write(_wire(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(Path(path).parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _identity(value):
    if type(value) is not str or not value.strip() or len(value.encode()) > 128:
        raise ValueError("nonempty identity of at most 128 bytes required")


def _config(value):
    fields = {"scope", "reader", "source_id", "source_version", "tool", "tool_version",
              "assumptions", "losses", "query_cost", "limits"}
    if type(value) is not dict or set(value) != fields:
        raise ValueError("explicit inspection config fields required")
    for key in ("scope", "reader", "source_id", "tool", "tool_version"):
        _identity(value[key])
    if type(value["source_version"]) is not int or value["source_version"] < 1:
        raise ValueError("positive exact source version required")
    if (value["tool"], value["tool_version"]) != (_TOOL, _TOOL_VERSION):
        raise ValueError("unsupported local tool declaration")
    limits = value["limits"]
    if type(limits) is not dict or set(limits) != {"max_calls", "token_cap"}:
        raise ValueError("explicit max_calls and token_cap required")
    for key, lower in (("max_calls", 1), ("token_cap", 0)):
        if type(limits[key]) is not int or limits[key] < lower:
            raise ValueError("invalid session limit")
    assumptions = ModelAssumptions(**value["assumptions"])
    losses = Losses(**value["losses"])
    plan = plan_inspection(assumptions, losses, value["query_cost"])
    return {**value, "assumptions": asdict(assumptions), "losses": asdict(losses)}, plan


def _source(value, config):
    if type(value) is not dict or set(value) != {
        "scope", "source_id", "source_version", "readers", "tool", "tool_version", "state_fingerprint"
    }:
        raise ValueError("explicit source declaration required")
    for key in ("scope", "source_id", "source_version", "tool", "tool_version"):
        if type(value[key]) is not type(config[key]) or value[key] != config[key]:
            raise PermissionError("source identity, scope, version or tool mismatch")
    readers = value["readers"]
    if type(readers) is not list or not readers or len(readers) > 32:
        raise ValueError("bounded source readers required")
    for reader in readers:
        _identity(reader)
    if len(set(readers)) != len(readers) or config["reader"] not in readers:
        raise PermissionError("reader is not authorized by source")
    fingerprint = value["state_fingerprint"]
    if type(fingerprint) is not str or len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint):
        raise ValueError("SHA256 source fingerprint required")
    return value


def _arguments(frozen):
    return {"plan_sha256": frozen["plan_sha256"], **{
        key: frozen["source"][key] for key in ("scope", "source_id", "source_version", "tool", "tool_version", "state_fingerprint")}}


def _outcome(raw):
    value = _parse(raw)
    if type(value) is not dict or set(value) != {"outcome"} or value["outcome"] is not None and type(value["outcome"]) is not bool:
        raise ValueError("binary source must contain exactly a bool or null outcome")
    return value["outcome"]


def _receipt(response, frozen):
    if type(response) is not dict or set(response) != {
        "artifact", "tool_ref", "prompt_tokens", "completion_tokens", "adapter_elapsed_ns"
    } or response["tool_ref"] != _TOOL:
        raise ValueError("invalid tool receipt")
    for key in ("prompt_tokens", "completion_tokens", "adapter_elapsed_ns"):
        if type(response[key]) is not int or response[key] < 0:
            raise ValueError("invalid local usage receipt")
    if response["prompt_tokens"] or response["completion_tokens"]:
        raise ValueError("local binary source cannot charge model tokens")
    artifact = response["artifact"]
    expected = _arguments(frozen)
    if type(artifact) is not dict or set(artifact) != set(expected) | {"raw_value", "outcome"}:
        raise ValueError("invalid bound artifact")
    if any(type(artifact[key]) is not type(value) or artifact[key] != value for key, value in expected.items()):
        raise ValueError("receipt is not bound to frozen declaration")
    raw = artifact["raw_value"]
    if type(raw) is not str or len(raw.encode()) > 256 or sha256(raw.encode()).hexdigest() != expected["state_fingerprint"]:
        raise ValueError("receipt source fingerprint mismatch")
    outcome = _outcome(raw)
    if type(artifact["outcome"]) is not type(outcome) or artifact["outcome"] != outcome:
        raise ValueError("receipt outcome differs from raw source")
    return outcome


def _result(frozen, plan, snapshot, response, error_type):
    status, action, reason = "SKIPPED", plan.stop_action, plan.reason
    if snapshot is not None:
        action = "abstain"
        if snapshot["run"]["status"] == "cancelled":
            status, reason = "CANCELLED", "session_cancelled"
        elif snapshot["artifacts"] and error_type is None:
            outcome = _receipt(response, frozen)
            status, reason = ("COMPLETE", "bound_receipt") if outcome is not None else ("UNKNOWN", "unknown_source_outcome")
            action = apply_plan(plan, outcome)
        elif snapshot["unknown_calls"]:
            status, reason = "UNKNOWN", "unresolved_dispatch"
        else:
            status, reason = "STOPPED", "execution_blocked"
    return {"format": _FORMAT, "status": status, "action": action, "reason": reason,
            "plan_sha256": frozen["plan_sha256"],
            "receipt_sha256": _digest(response) if response is not None else None,
            "session_sha256": _digest(snapshot) if snapshot is not None else None,
            "call_count": snapshot["call_count"] if snapshot else 0,
            "unknown_calls": snapshot["unknown_calls"] if snapshot else 0,
            "error_type": error_type}


def run_inspection(config_path, source_dir, output_dir):
    """Freeze first, optionally read once, retain uncertain dispatch without retry.

    `max_calls` remains the caller's Session cap; one optional read is this
    strategy's scope. No tokens, money ledger or external model is involved.
    """
    config, plan = _config(_load(config_path, 32768))
    source_dir, output_dir = Path(source_dir), Path(output_dir)
    source = _source(_load(source_dir / "source.json", 8192), config)
    frozen = {"format": _FORMAT, "config": config, "source": source,
              "plan": json.loads(_wire(asdict(plan))), "source_identity": source_identity()}
    frozen["plan_sha256"] = _digest(frozen)
    output_dir.mkdir(parents=True, exist_ok=False)
    _save(output_dir / "frozen.json", frozen)
    if not plan.purchase:
        result = _result(frozen, plan, None, None, None)
        _save(output_dir / "result.json", result)
        return result

    args = _arguments(frozen)
    session = CoordinationSession.create(
        output_dir / "session.sqlite", config["scope"], agents=source["readers"],
        work=[{"id": "inspect", "version": config["source_version"], "dependencies": [],
               "agents": [config["reader"]], "actions": ["tool.evaluate"]}],
        sources=[{"id": source["source_id"], "version": source["source_version"],
                  "readers": source["readers"], "state_fingerprint": source["state_fingerprint"]}],
        inspections=[{"work_id": "inspect", "source_id": source["source_id"],
                      "source_version": source["source_version"], "tool_ref": _TOOL,
                      "tool_version": _TOOL_VERSION, "arguments": args,
                      "state_fingerprint": source["state_fingerprint"], "readers": source["readers"]}],
        max_index_entries=1, max_control_operations=8, **config["limits"])
    response, error_type = None, None

    def check_current():
        if source_identity() != frozen["source_identity"]:
            raise StateError("executable source changed after freeze")
        if _source(_load(source_dir / "source.json", 8192), config) != source:
            raise StateError("source declaration changed after freeze")

    def read_binary(arguments):
        session.check_current(lease)  # Current cancellation/lease fence after dispatch.
        if arguments != args:
            raise StateError("tool arguments differ from frozen declaration")
        check_current()
        raw = _read(source_dir / "value.json", 256)
        if sha256(raw).hexdigest() != source["state_fingerprint"]:
            raise StateError("source payload differs from declared fingerprint")
        return {**args, "raw_value": raw.decode("utf-8"), "outcome": _outcome(raw)}

    try:
        lease = session.claim(config["reader"], "inspect")
        if lease is None:
            raise StateError("inspection is unavailable or cancelled")
        check_current()
        response = SessionDriver(session, tools={_TOOL: read_binary}).evaluate(
            lease, "inspect:1", _TOOL, args)
        _receipt(response, frozen)
        check_current()
        session.publish(lease, "inspect:1", response["artifact"],
                        verify=lambda work, artifact: work == "inspect" and artifact == response["artifact"])
    except Exception as exc:
        error_type = type(exc).__name__
    snapshot = _snapshot_readonly(output_dir / "session.sqlite")
    # A driver exception after settlement never justifies another read. Recover
    # only the already committed raw receipt for faithful recording and replay.
    if response is None and snapshot["calls"] and snapshot["calls"][0]["state"] == "received":
        response = json.loads(snapshot["calls"][0]["response"])
    if response is not None:
        _save(output_dir / "receipt.json", response)
    _save(output_dir / "session.json", snapshot)
    result = _result(frozen, plan, snapshot, response, error_type)
    _save(output_dir / "result.json", result)
    return result


def _snapshot_readonly(path):
    """Read saved durable records without reopening a writable Session."""
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        rows = {table: [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                for table in ("run", "work", "calls", "artifacts", "events")}
        calls = rows["calls"]
        coordination = {table: [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                        for table in ("coordination_v1", "coordination_sources_v1", "coordination_inspections_v1")}
        return {"run": rows["run"][0], "work": rows["work"], "calls": calls, "coordination": coordination,
                "artifacts": rows["artifacts"], "events": [json.loads(row["value"]) for row in rows["events"]],
                "actual_tokens": sum(row["actual"] or 0 for row in calls),
                "reserved_tokens": sum(row["reserved"] for row in calls if row["state"] == "reserved"),
                "unknown_tokens": sum(row["reserved"] for row in calls if row["state"] == "dispatched"),
                "unknown_calls": sum(row["state"] == "dispatched" for row in calls), "call_count": len(calls)}
    finally:
        db.close()


def _verify_execution(snapshot, frozen, response):
    config, source, args = frozen["config"], frozen["source"], _arguments(frozen)
    declaration = {"id": "inspect", "version": config["source_version"], "dependencies": [],
                   "agents": [config["reader"]], "actions": ["tool.evaluate"]}
    run, work, coordination = snapshot["run"], snapshot["work"], snapshot["coordination"]
    expected_limits = {**config["limits"], "context_bytes": 4096, "artifact_bytes": 8192}
    if (run["run_id"] != config["scope"] or json.loads(run["agents"]) != source["readers"]
            or json.loads(run["limits"]) != expected_limits or len(work) != 1
            or work[0]["id"] != "inspect" or work[0]["version"] != config["source_version"]
            or json.loads(work[0]["declaration"]) != declaration):
        raise ValueError("durable execution declaration differs from freeze")
    if coordination["coordination_v1"] != [{"id": 1, "limits": _wire({"max_index_entries": 1, "max_control_operations": 8}).decode()}]:
        raise ValueError("coordination bounds differ from frozen execution")
    current = {"id": source["source_id"], "version": source["source_version"],
               "readers": source["readers"], "state_fingerprint": source["state_fingerprint"]}
    for event in snapshot["events"]:
        if event["event_type"] == "interaction.evidence.source_updated":
            update = event["details"]
            if (set(update) != set(current) or update["id"] != current["id"]
                    or type(update["version"]) is not int or update["version"] < current["version"]
                    or type(update["readers"]) is not list or not set(update["readers"]) <= set(source["readers"])
                    or len(set(update["readers"])) != len(update["readers"])
                    or update["version"] == current["version"] and update["state_fingerprint"] != current["state_fingerprint"]):
                raise ValueError("invalid recorded source update")
            current = update
    source_row = {"id": current["id"], "version": current["version"], "readers": _wire(current["readers"]).decode(),
                  "fingerprint": current["state_fingerprint"]}
    expected_inspection = {"work_id": "inspect", "source_id": source["source_id"],
                           "source_version": source["source_version"], "tool_ref": _TOOL,
                           "tool_version": _TOOL_VERSION, "arguments": args,
                           "state_fingerprint": source["state_fingerprint"]}
    key = _digest({"scope": config["scope"], "work_version": config["source_version"],
                   **{k: v for k, v in expected_inspection.items() if k != "work_id"}})
    inspection_row = {"work_id": "inspect", "key": key, "source_id": source["source_id"],
                      "source_version": source["source_version"], "tool_ref": _TOOL, "tool_version": _TOOL_VERSION,
                      "arguments": _wire(args).decode(), "fingerprint": source["state_fingerprint"],
                      "readers": _wire(source["readers"]).decode()}
    if (coordination["coordination_sources_v1"] != [source_row]
            or coordination["coordination_inspections_v1"] != [inspection_row]):
        raise ValueError("durable source or inspection declaration differs from recorded history")
    permission = {"profile": "trusted-host-local-v1", "scope_ref": "interaction:" + _digest([config["scope"], "inspect"]),
                  "task_id": "inspect", "version": config["source_version"], "owner": config["reader"], "action": "tool.evaluate"}
    calls = snapshot["calls"]
    if len(calls) > 1:
        raise ValueError("one-inspection strategy dispatched extra calls")
    if calls:
        call = calls[0]
        if (call["id"] != "inspect:1" or call["work_id"] != "inspect" or call["version"] != config["source_version"]
                or call["epoch"] != 1 or any(call[k] != 0 for k in ("prompt", "maximum", "reserved"))
                or call["actual"] not in (None, 0)
                or call["permission"] is not None and json.loads(call["permission"]) != permission
                or call["permission"] is None and call["state"] not in ("reserved", "abandoned")):
            raise ValueError("durable call lacks the declared current permission or usage")
    for artifact in snapshot["artifacts"]:
        if response is None:
            raise ValueError("publication lacks settled receipt")
        response_digest = _digest(response)
        published = {"task_id": "inspect", "version": config["source_version"], "artifact": response["artifact"],
                     "call_id": "inspect:1", "response_digest": response_digest, "scope_ref": permission["scope_ref"]}
        if (artifact["ref"] != "sha256:" + _digest(published) or artifact["work_id"] != "inspect"
                or artifact["version"] != config["source_version"] or artifact["publisher"] != config["reader"]
                or artifact["call_id"] != "inspect:1" or artifact["response_digest"] != response_digest
                or json.loads(artifact["permission"]) != {**permission, "action": "artifact.publish"}):
            raise ValueError("publication lacks the declared current permission")


def replay_inspection(run_dir, require_source_match=True):
    """Verify frozen strategy, exact local receipt and durable records; never read a source."""
    run_dir = Path(run_dir)
    frozen, stored = _load(run_dir / "frozen.json", 1048576), _load(run_dir / "result.json")
    if set(frozen) != {"format", "config", "source", "plan", "source_identity", "plan_sha256"} or frozen["format"] != _FORMAT:
        raise ValueError("unsupported inspection record")
    if _digest({key: value for key, value in frozen.items() if key != "plan_sha256"}) != frozen["plan_sha256"]:
        raise ValueError("frozen declaration digest mismatch")
    config, plan = _config(frozen["config"])
    _source(frozen["source"], config)
    if frozen["plan"] != json.loads(_wire(asdict(plan))):
        raise ValueError("frozen plan differs from recomputed strategy")
    if require_source_match and source_identity() != frozen["source_identity"]:
        raise ValueError("executable source identity differs; explicit historical replay required")
    response, snapshot = None, None
    if plan.purchase:
        snapshot = _load(run_dir / "session.json", 1048576)
        if snapshot != _snapshot_readonly(run_dir / "session.sqlite"):
            raise ValueError("saved snapshot differs from durable records")
        calls = snapshot["calls"]
        if len(calls) > 1 or snapshot["run"]["run_id"] != config["scope"] or json.loads(snapshot["run"]["limits"])["max_calls"] != config["limits"]["max_calls"]:
            raise ValueError("durable execution scope or call bound mismatch")
        if calls:
            expected = {"task_id": "inspect", "version": config["source_version"],
                        "tool_ref": _TOOL, "arguments": _arguments(frozen)}
            if json.loads(calls[0]["request"]) != expected or calls[0]["action"] != "tool.evaluate":
                raise ValueError("durable request differs from frozen plan")
            if calls[0]["state"] == "received":
                response = _load(run_dir / "receipt.json")
                if response != json.loads(calls[0]["response"]):
                    raise ValueError("raw receipt differs from durable receipt")
                _receipt(response, frozen)
        _verify_execution(snapshot, frozen, response)
        if snapshot["artifacts"]:
            if len(snapshot["artifacts"]) != 1 or response is None or json.loads(snapshot["artifacts"][0]["value"]) != response["artifact"]:
                raise ValueError("published artifact differs from bound receipt")
    elif any((run_dir / name).exists() for name in ("session.sqlite", "session.json", "receipt.json")):
        raise ValueError("skipped plan must not have an execution")
    expected_result = _result(frozen, plan, snapshot, response, stored.get("error_type"))
    if stored != expected_result:
        raise ValueError("result differs from frozen strategy and receipt")
    return {"status": "PASS", "mode": "offline replay", "source_match": source_identity() == frozen["source_identity"],
            "result": expected_result, "new_tool_calls": 0}
