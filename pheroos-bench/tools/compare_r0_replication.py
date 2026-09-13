"""Compare the three frozen G1 captures; consistency evidence, not authentication.

Run with the separately installed R0 bench interpreter. UUIDs and independent
task interleavings are normalized only after checking each trace's own bindings.
Historical inputs and the frozen analyzer are never modified.
"""

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from pheroos_bench.r0_runtime import reconcile_snapshot


NAMES = ("completed", "cancelled_unknown", "cancelled_late_receipt")
COUNTERS = ("actual_units", "reserved_units", "unknown_units", "remaining_units")
EXPECTED = ((26, 0, 0, 0), (0, 1, 1, 25), (1, 0, 0, 25))
SCOPES = (
    "sha256:0026a79b267e22f9a32cee214d3bb3e35783cfaabfc421e1809dcfad25b90f2b",
    "sha256:91a396af899f6309e02e412accc6cabe631acb337928b6ad32865a9cfc743974",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def root(value):
    return "sha256:" + sha256(canonical(value).encode("ascii")).hexdigest()


def decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result

    value = json.loads(raw, object_pairs_hook=unique)
    canonical(value)  # Reject non-finite numbers, including nested values.
    return value


def indexed(rows, key):
    result = {row[key]: row for row in rows}
    require(len(result) == len(rows), f"duplicate {key}")
    return result


def receipt_projection(receipt, call, scope):
    common = {
        "scope_ref": scope, "driver_id": f"driver.{call['action']}",
        "invocation_id": call["id"], "operation": "driver:invoke",
        "capability": f"capability:{call['action']}", "idempotency_key": call["id"],
    }
    request_digest = root(common | {
        "version": "pheroos-driver-invocation-request-v2", "payload": call["request"],
    })
    provenance = "provider-free:g1-pure-adapter"
    result_digest = root(common | {
        "version": "pheroos-driver-invocation-result-v2", "payload": call["response"],
        "request_digest": request_digest, "ok": True, "provenance": provenance,
    })
    expected = {key: common[key] for key in ("scope_ref", "driver_id", "invocation_id")}
    expected |= {"request_digest": request_digest, "result_digest": result_digest,
                 "provenance": provenance}
    require(canonical(receipt) == canonical(expected), "driver receipt binding/digest mismatch")
    return {key: receipt[key] for key in ("scope_ref", "driver_id", "provenance")}


def project(snapshot, name):
    ledger = reconcile_snapshot(snapshot)
    require(ledger["validation_status"] == "VALID", f"ledger: {ledger['diagnostics']}")
    index = NAMES.index(name)
    require(tuple(snapshot[k] for k in COUNTERS) == EXPECTED[index], "unexpected accounting")
    complete = name == "completed"
    scope = SCOPES[0 if complete else 1]
    run = snapshot["run"]
    require(run["scope_ref"] == scope and run["budget"] == 26, "run scope/budget mismatch")
    require(run["run_id"] == ("r0-complete" if complete else "r0-interrupted"), "run identity")
    require(run["status"] == ("completed" if complete else "cancelled"), "run status")
    tasks = indexed(snapshot["tasks"], "id")
    artifacts = indexed(snapshot["artifacts"], "task_id")
    declarations = [(f"square-{i}", "square", i, []) for i in range(1, 9)]
    declarations += [(f"pair-{i}", "sum", None, [f"square-{2*i-1}", f"square-{2*i}"])
                     for i in range(1, 5)]
    declarations += [("total", "sum", None, [f"pair-{i}" for i in range(1, 5)])]
    require(set(tasks) == {d[0] for d in declarations}, "task inventory")
    require(set(artifacts) == (set(tasks) if complete else set()), "artifact inventory")
    values = {}
    for ordinal, (task_id, kind, seed, deps) in enumerate(declarations):
        task = tasks[task_id]
        expected = dict(id=task_id, ordinal=ordinal, kind=kind, seed=seed, deps=canonical(deps),
                        version=1, status="done" if complete else "cancelled", owner=None,
                        epoch=1 if complete or task_id == "square-1" else 0, expires=None)
        require(canonical(task) == canonical(expected), f"task declaration/state: {task_id}")
        values[task_id] = seed * seed if kind == "square" else sum(values[p] for p in deps)
        if complete:
            artifact = artifacts[task_id]
            require(type(artifact["value"]) is int and artifact["value"] == values[task_id],
                    f"independent arithmetic: {task_id}")
            require(artifact["version"] == 1 and artifact["scope_ref"] == scope
                    and decode(artifact["parents"]) == deps, f"artifact lineage: {task_id}")
    require(values["total"] == 204, "independent DAG total")
    calls = indexed(deepcopy(snapshot["calls"]), "id")
    call_keys = {}
    for identity, call in calls.items():
        key = (call["task_id"], call["version"], call["epoch"], call["action"])
        require(key not in call_keys.values(), "duplicate semantic call")
        call_keys[identity] = key
        call["request"] = decode(call["request"])
        call["response"] = decode(call["response"]) if call["response"] is not None else None
        task = tasks[call["task_id"]]
        deps = decode(task["deps"])
        parents = [dict(task_id=p, version=1, value=values[p], scope_ref=scope) for p in deps]
        request = dict(task_id=task["id"], version=1, kind=task["kind"], parents=parents,
                       inputs=[values[p] for p in deps] if deps else [task["seed"]])
        if call["action"] == "tool.evaluate":
            request["operation"] = task["kind"]
        require(canonical(call["request"]) == canonical(request), "call input/dependency mismatch")
        response = ({"operation": task["kind"]} if call["action"] == "mock.propose"
                    else {"value": values[task["id"]]})
        require(canonical(call["response"]) == canonical(None if index == 1 else response),
                "call response mismatch")
    expected_calls = ({(task, 1, 1, action) for task in tasks
                       for action in ("mock.propose", "tool.evaluate")} if complete
                      else {("square-1", 1, 1, "tool.evaluate")})
    require(set(call_keys.values()) == expected_calls, "call inventory")
    by_task = {task: [] for task in tasks}
    by_task[""] = []
    published, received = {}, {}
    for event in snapshot["events"]:
        payload = decode(event["payload"])
        lineage = payload["lineage"]
        task_id = event["task_id"]
        kind = payload["reason"]
        if kind == "claimed":
            require(isinstance(lineage["owner"], str) and lineage["owner"], "worker identity")
            lineage["owner"] = "<worker>"
            require(all(p in published for p in decode(tasks[task_id]["deps"])),
                    "child claimed before parent publication")
        if "call_id" in lineage:
            identity = lineage["call_id"]
            call = calls[identity]
            if kind == "received":
                lineage["driver_receipt"] = receipt_projection(lineage["driver_receipt"], call, scope)
                received[identity] = event["seq"]
            lineage["call_id"] = call_keys[identity]
        if kind in ("dispatched", "published"):
            authority = lineage["authority"]
            require(authority["scope_ref"] == scope and authority["task_id"] == task_id
                    and authority["version"] == 1 and authority["reusable_authority"] is False
                    and authority["action"] == ("artifact.publish" if kind == "published"
                                                 else call["action"]), "authority binding")
        if kind == "published":
            require(task_id not in published, "duplicate publication")
            artifact = artifacts[task_id]
            expected = {k: artifact[k] for k in ("task_id", "version", "scope_ref", "value")}
            expected |= {"parents": decode(artifact["parents"]), "epoch": 1,
                         "authority": decode(artifact["authority"])}
            require(canonical(lineage) == canonical(expected), "publication/artifact mismatch")
            require(all(identity in received for identity, key in call_keys.items()
                        if key[0] == task_id), "publication before receipts")
            published[task_id] = event["seq"]
        by_task[task_id].append(payload)
    require(set(published) == set(artifacts), "publication inventory")
    return {"run": run, "tasks": tasks, "artifacts": artifacts,
            "calls": {canonical(call_keys[k]): {n: v for n, v in c.items() if n != "id"}
                      for k, c in calls.items()}, "events_per_task": by_task,
            "accounting": {k: snapshot[k] for k in COUNTERS},
            "final_value": values["total"] if complete else None}


def load_bundle(directory):
    provenance = decode((directory / "provenance.json").read_bytes())
    require(provenance["kind"] == "R0_G1_MOCK_SNAPSHOTS", "provenance kind")
    require(set(provenance["snapshots"]) == set(NAMES), "provenance snapshot inventory")
    snapshots = {}
    for name in NAMES:
        raw = (directory / f"{name}.json").read_bytes()
        require(sha256(raw).hexdigest() == provenance["snapshots"][name], f"raw digest: {name}")
        snapshots[name] = decode(raw)
    before, after = (snapshots[n] for n in NAMES[1:])
    require(after["events"][:-1] == before["events"] and
            after["events"][-1]["event_type"] == "ext.runtime.received", "late receipt prefix")
    require(before["calls"][0]["id"] == after["calls"][0]["id"], "late receipt call identity")
    return snapshots, provenance


def compare(reference, candidate):
    report = {"status": "R0_REPLICATION_FAILED", "counts_toward_verdict": False,
              "guarantee": "Tested G1 snapshot semantics and consistency; not authentication, "
                           "current authority, universal hardware independence or swarm efficacy.",
              "excluded_from_equality": ["call UUIDs and their checked Driver digests",
                                         "worker identities", "independent task event interleaving",
                                         "raw snapshot hashes and serialized byte counters"],
              "differences": [], "snapshots": {}}
    try:
        left, left_provenance = load_bundle(reference)
        right, right_provenance = load_bundle(candidate)
        require(left_provenance["runtime_source_sha256"] == right_provenance["runtime_source_sha256"],
                "runtime source fingerprints differ")
        report["provenance"] = {"reference": left_provenance, "candidate": right_provenance}
        for name in NAMES:
            a, b = project(left[name], name), project(right[name], name)
            different = [key for key in a if canonical(a[key]) != canonical(b[key])]
            report["differences"].extend(f"{name}.{key}" for key in different)
            report["snapshots"][name] = {"equal": not different, "semantic_sha256": root(b),
                                         "accounting": b["accounting"], "final_value": b["final_value"]}
        if not report["differences"]:
            report["status"] = "R0_REPLICATION_PASSED"
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, OSError) as error:
        report["differences"].append(str(error))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = compare(args.reference, args.candidate)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({"status": report["status"], "output": str(args.output)}))
    return 0 if report["status"] == "R0_REPLICATION_PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
