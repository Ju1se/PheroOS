"""Local engineering consumer of the experimental session; no efficacy verdict."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

from pheroos_runtime import session_v1
from pheroos_runtime.session_v1 import Session
from pheroos_runtime.session_driver_v1 import LocalModelAdapter, SessionDriver


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class ObjectiveFailed(ValueError):
    pass


def proposal(text):
    def reject_constant(value):
        raise ValueError(f"nonstandard JSON constant: {value}")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    if type(text) is not str:
        raise ObjectiveFailed("proposal text must be a string")
    value = text.strip()
    fenced = re.fullmatch(r"```json\n(.*)\n```", value, re.DOTALL)
    if fenced:
        value = fenced[1]
    try:
        parsed = json.loads(value, object_pairs_hook=pairs, parse_constant=reject_constant)
    except (ValueError, RecursionError) as error:
        raise ObjectiveFailed(f"invalid proposal JSON: {error}") from error
    if type(parsed) is not dict or set(parsed) != {"total"} or type(parsed["total"]) is not int:
        raise ObjectiveFailed("proposal must contain exactly one integer total")
    return parsed


def run(output, *, items=(2, 3), model_path=None):
    items, output = list(items), Path(output)
    if not 1 <= len(items) <= 16 or any(type(v) is not int or abs(v) > 1000 for v in items):
        raise ValueError("declare 1–16 integers with absolute value at most 1000")
    output.mkdir(parents=True, exist_ok=False)
    config = {"version": "session-journey-v1", "items": items, "model_path": str(model_path) if model_path else None,
              "token_cap": 2048, "max_calls": 3, "context_bytes": 8192, "context_tokens": 2048,
              "max_new_tokens": 64, "seed": 7, "mailbox_messages": 1, "mailbox_bytes": 1024,
              "artifact_bytes": 8192, "proposal_format": "strict object or sole exact json fence"}
    work = [{"id": "discover", "version": 1, "dependencies": [], "agents": ["scout"], "actions": ["tool.evaluate"]},
            {"id": "solve", "version": 1, "dependencies": ["discover"], "agents": ["solver"],
             "actions": ["model.generate", "tool.evaluate"]}]
    config["work"] = work
    session, model_identity, raw_proposal, error, replay = None, None, None, None, None
    status, final_ref = "INVALID_ABORT", None

    def reporting_error(exc, stage):
        nonlocal error, status
        detail = {"type": type(exc).__name__, "message": str(exc), "stage": stage}
        if error is None:
            error = detail
        else:
            error.setdefault("secondary_errors", []).append(detail)
        status = "INVALID_ABORT"

    try:
        session = Session.create(output / "session.sqlite", "session-journey-v1", agents=["scout", "solver"], work=work,
            **{key: config[key] for key in ("token_cap", "max_calls", "context_bytes", "mailbox_messages", "mailbox_bytes", "artifact_bytes")})
        driver = SessionDriver(session, tools={"discover": lambda _: {"items": items}})
        scout = session.claim("scout", "discover")
        receipt = driver.evaluate(scout, "discover-1", "discover", {})
        ref = session.publish(scout, "discover-1", receipt["artifact"],
            verify=lambda task, value: task == "discover" and wire(value) == wire({"items": items}), authorize=driver.authorization)
        session.send("scout", "solver", ref)
        solver = session.claim("solver", "solve")
        message = session.mailbox("solver")[0]
        session.checkpoint(solver, {"input_ref": message["artifact_ref"]})
        session = Session(output / "session.sqlite")
        input_ref = session.context(solver)["private"]["input_ref"]
        discovered = session.artifact(input_ref)["value"]["items"]
        driver = SessionDriver(session, tools={"solve": lambda args: {
            "total": args["proposal"]["total"] if args["proposal"] is not None else sum(args["items"]),
            "source_ref": input_ref}})
        if model_path:
            model = LocalModelAdapter(model_path)
            model_identity = model.identity
            driver.models["local"] = model
            messages = [{"role": "user", "content": "Sum these integers. Reply with exactly a JSON object containing only integer total: " + wire({"items": discovered})}]
            reply = driver.generate(solver, "proposal-1", "local", messages,
                                    max_new_tokens=config["max_new_tokens"], seed=config["seed"])
            raw_proposal = reply.get("text")
            proposed = proposal(raw_proposal)
        else:
            proposed = None
        receipt = driver.evaluate(solver, "solve-1", "solve", {"items": discovered, "proposal": proposed})
        if wire(receipt["artifact"]) != wire({"total": sum(discovered), "source_ref": input_ref}):
            raise ObjectiveFailed("proposed total fails the independently computed objective")
        final_ref = session.publish(solver, "solve-1", receipt["artifact"],
            verify=lambda task, value: task == "solve" and wire(value) == wire({"total": sum(discovered), "source_ref": input_ref}),
            authorize=driver.authorization)
        session.ack("solver", message["id"])
        status = "engineering_complete"
    except Exception as exc:
        status = "failed" if isinstance(exc, ObjectiveFailed) else "INVALID_ABORT"
        error = {"type": type(exc).__name__, "message": str(exc)}
        if session is not None:
            try:
                session.cancel()
            except Exception as cleanup_error:
                reporting_error(cleanup_error, "cancel")
    snapshot = None
    if session is not None:
        try:
            snapshot = session.snapshot()
        except Exception as snapshot_error:
            reporting_error(snapshot_error, "snapshot")
    if snapshot is not None:
        if snapshot["unknown_calls"] or snapshot["reserved_tokens"]:
            status = "INVALID_ABORT"
        elif error and not error.get("secondary_errors") and any(call["state"] == "response_rejected" for call in snapshot["calls"]):
            status = "failed"  # Usage is known; unusable output fails this objective.
        settled = [call for call in snapshot["calls"] if call["state"] == "received"]
        if settled:
            call = next((call for call in settled if call["id"] == "proposal-1"), settled[-1])
            reopened = SessionDriver(Session(output / "session.sqlite"))
            try:
                reread = reopened.replay(call["id"])
                after = reopened.session.snapshot()
                replay = {"call_id": call["id"], "same_response": reread == json.loads(call["response"]),
                          "before_actual_tokens": snapshot["actual_tokens"], "after_actual_tokens": after["actual_tokens"],
                          "before_call_count": snapshot["call_count"], "after_call_count": after["call_count"]}
                if not replay["same_response"] or any(snapshot[key] != after[key] for key in ("actual_tokens", "call_count")):
                    raise RuntimeError("receipt reread changed content or accounting")
            except Exception as reread_error:
                reporting_error(reread_error, "receipt_reread")
    calls = snapshot["calls"] if snapshot else []
    dispatched = [event for event in snapshot["events"] if event["event_type"] == "ext.session.dispatched"] if snapshot else []
    dispatched_ids = {event["lineage"]["call_id"] for event in dispatched}
    accounting = {key: snapshot[key] for key in ("actual_tokens", "reserved_tokens", "unknown_tokens", "unknown_calls", "call_count")} if snapshot else None
    if accounting is not None:
        accounting.update({"logical_model_calls": sum(c["action"] == "model.generate" and c["id"] in dispatched_ids for c in calls),
                           "logical_tool_calls": sum(c["action"] == "tool.evaluate" and c["id"] in dispatched_ids for c in calls),
                           "request_bytes": sum(len(c["request"].encode()) for c in calls),
                           "response_bytes": sum(json.loads(c["response"])["response_bytes"] if c["state"] == "response_rejected"
                                                 else len((c["response"] or "").encode()) for c in calls),
                           "retained_response_bytes": sum(len((c["response"] or "").encode()) for c in calls),
                           "trace_bytes": sum(len(wire(event).encode()) for event in snapshot["events"])})
    sources = {str(path): sha256(path.read_bytes()).hexdigest() for path in [Path(__file__).resolve(), *sorted(Path(session_v1.__file__).parent.glob("*.py"))]}
    report = {"version": "session-journey-v1", "status": status, "counts_toward_verdict": False,
              "python": sys.version, "interpreter": sys.executable,
              "purpose": "local installed-consumer engineering journey; no efficacy or R5 completion claim",
              "objective_success": True if final_ref else False if status == "failed" else None, "final_artifact_ref": final_ref,
              "accounting": accounting, "receipt_reread": replay, "config_sha256": sha256((wire(config) + "\n").encode()).hexdigest(),
              "source_sha256": sources, "model_identity": model_identity,
              "limits": ["trusted single-host fixture", "tokens plus logical calls, not dollars or physical I/O", "JSON byte accounting; oversized reply bytes come from retained digest metadata", "no automatic retries"]}
    for name, value in (("config", config), ("snapshot", snapshot), ("proposal", raw_proposal), ("raw_error", error), ("report", report)):
        with (output / (name + ".json")).open("x") as stream:
            stream.write(wire(value) + "\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--items", type=int, nargs="+", default=[2, 3])
    args = parser.parse_args(argv)
    report = run(args.output, items=args.items, model_path=args.model_path)
    print(wire({"status": report["status"], "output": str(args.output)}))
    return {"engineering_complete": 0, "failed": 1, "INVALID_ABORT": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
