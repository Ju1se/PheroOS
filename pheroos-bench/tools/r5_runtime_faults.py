"""Versioned provider-free fault acceptance against an explicitly installed runtime.

Example: python tools/r5_runtime_faults.py --runtime-python /path/to/python \
    --config r5-runtime-faults-v1.json --output results/r5-runtime-faults-v1
Production modules are never edited. Child-only injection selects durable boundaries.
"""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import selectors
import signal
import sqlite3
import subprocess
import sys


METHOD = "r5-runtime-faults-v1"
CASES = ("before_receipt", "receipt_before_commit", "receipt_committed_before_ack",
         "receipts_reordered", "transient_write_lock")
RESPONSE = {"text": "answer", "prompt_tokens": 2, "completion_tokens": 1,
            "elapsed_ns": 0, "peak_cuda_bytes": 0}


def dump(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def save(path, value):
    with path.open("x") as stream:
        stream.write(dump(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def rejected(error_type, action):
    try:
        action()
    except error_type as error:
        return f"{type(error).__name__}: {error}"
    raise AssertionError(f"expected {error_type.__name__}")


def probe():
    import pheroos_runtime
    root = Path(pheroos_runtime.__file__).resolve().parent
    return {"python": sys.version, "executable": sys.executable,
            "platform": platform.platform(), "runtime_root": str(root),
            "runtime_sha256": {str(p): sha256(p.read_bytes()).hexdigest()
                               for p in sorted(root.glob("*.py"))}}


def pause_at(case):
    print(dump({"boundary_ready": case}), file=sys.stderr, flush=True)
    signal.pause()
    raise AssertionError("boundary resumed without SIGKILL")


def crash_child(case, path):
    from types import SimpleNamespace
    from pheroos.kernel import RuntimeScope
    from pheroos_runtime import r3_local
    from pheroos_runtime.r3_ledger import PilotLedger

    class CommitPause:
        """Only substitutes commit on this test connection after receipt UPDATE."""
        def __init__(self, connection):
            self.connection = connection

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def commit(self):
            pause_at(case)

    class BoundaryLedger(PilotLedger):
        def received(self, call_id, response):
            if case == "before_receipt":
                pause_at(case)
            if case == "receipt_before_commit":
                self.db = CommitPause(self.db)
            super().received(call_id, response)

    class FakeModel:
        def inputs(self, _messages):
            return {"input_ids": SimpleNamespace(shape=(1, 2))}

        def generate(self, *_args):
            return dict(RESPONSE)

    r3_local.PilotLedger = BoundaryLedger
    request = {"op": "generate", "scope": RuntimeScope("r3-local", "run:r5", "task:r5").to_dict(),
               "task_id": "task:r5", "version": 1, "messages": [{"role": "user", "content": "fixture"}],
               "max_new_tokens": 8, "seed": 17, "ledger_path": str(path),
               "token_cap": 10, "max_calls": 3, "call_id": "one"}
    result = r3_local.handle(FakeModel(), request)
    assert case == "receipt_committed_before_ack"
    pause_at(case)
    r3_local.emit({"ok": True, "result": result})


def inspect_crash(case, path):
    from pheroos_runtime.r3_ledger import PilotLedger
    ledger = PilotLedger(path, 10, 3)
    try:
        before = ledger.snapshot()
        known = case == "receipt_committed_before_ack"
        assert before["actual_tokens"] == (3 if known else 0)
        assert before["unknown_tokens"] == (0 if known else 10)
        assert before["reserved_tokens"] == 0 and before["call_count"] == 1
        call = before["calls"][0]
        assert call["state"] == ("received" if known else "dispatched")
        assert call["response"] == (RESPONSE if known else None)
        refusals = [rejected(ValueError, lambda: ledger.dispatched("one")),
                    rejected(ValueError, lambda: ledger.reserve("one", {}, 2, 8))]
        if known:
            ledger.received("one", dict(RESPONSE))
        else:
            refusals.append(rejected(ValueError, lambda: ledger.reserve("other", {}, 0, 1)))
        assert ledger.snapshot() == before
        return {"ledger": before, "refusals": refusals, "reopened_in_fresh_process": True}
    finally:
        ledger.close()


def sequence_case(case, path, busy_ms):
    from pheroos_runtime.r3_ledger import PilotLedger
    ledger = PilotLedger(path, 20, 3)
    observations = []
    snapshots = []
    try:
        if case == "receipts_reordered":
            for call_id in ("one", "two"):
                ledger.reserve(call_id, {"call": call_id}, 2, 8)
                ledger.dispatched(call_id)
            snapshots.append({"stage": "both_dispatched", "ledger": ledger.snapshot()})
            for call_id, text in (("two", "second"), ("one", "first")):
                reply = RESPONSE | {"text": text}
                ledger.received(call_id, reply)
                settled = ledger.snapshot()
                ledger.received(call_id, dict(reversed(list(reply.items()))))
                observations.append(rejected(ValueError, lambda: ledger.received(
                    call_id, reply | {"text": "conflict"})))
                assert ledger.snapshot() == settled
                snapshots.append({"stage": f"settled_{call_id}", "ledger": settled})
            final = ledger.snapshot()
            assert final["actual_tokens"] == 6
            assert [c["response"]["text"] for c in final["calls"]] == ["first", "second"]
        else:
            assert case == "transient_write_lock"
            ledger.db.execute(f"PRAGMA busy_timeout={busy_ms}")
            blocker = sqlite3.connect(path, isolation_level=None)
            try:
                for stage in ("reserve", "receive"):
                    before = ledger.snapshot()
                    blocker.execute("BEGIN IMMEDIATE")
                    action = (lambda: ledger.reserve("one", {}, 2, 8)) if stage == "reserve" else (
                        lambda: ledger.received("one", RESPONSE))
                    observations.append(rejected(sqlite3.OperationalError, action))
                    blocker.rollback()
                    assert ledger.snapshot() == before
                    snapshots.append({"stage": f"refused_{stage}", "ledger": before})
                    if stage == "reserve":
                        assert before["call_count"] == 0
                        ledger.reserve("one", {}, 2, 8)
                        ledger.dispatched("one")
                    else:
                        assert before["unknown_tokens"] == 10 and before["actual_tokens"] == 0
                        ledger.received("one", RESPONSE)
                final = ledger.snapshot()
                assert final["actual_tokens"] == 3 and final["call_count"] == 1
            finally:
                blocker.close()
        assert final["unknown_tokens"] == final["reserved_tokens"] == 0
        return {"ledger": final, "refusals": observations, "snapshots": snapshots}
    finally:
        ledger.close()


def run(args):
    config = json.loads(args.config.read_text())
    assert config["method"] == METHOD and config["cases"] == list(CASES)
    assert config["sqlite_busy_timeout_ms"] == 100
    assert config["kill_ready_timeout_seconds"] == 20
    assert os.name == "posix", "this method requires POSIX SIGKILL"
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    command = [str(args.runtime_python.resolve()), str(Path(__file__).resolve())]

    def child(*parts):
        return subprocess.run(command + list(parts), capture_output=True, text=True,
                              env=environment, timeout=30, check=True)

    identity = json.loads(child("--probe").stdout)
    args.output.mkdir(parents=True, exist_ok=False)
    save(args.output / "freeze.json", {"method": METHOD,
         "frozen_at": datetime.now(timezone.utc).isoformat(), "environment": identity,
         "config": config, "config_path": str(args.config.resolve()),
         "config_sha256": sha256(args.config.read_bytes()).hexdigest(),
         "script_path": str(Path(__file__).resolve()),
         "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest()})
    outcomes = []
    for case in CASES:
        path = args.output.resolve() / f"{case}.sqlite"
        row = {"case": case, "status": "FAIL"}
        try:
            if case in CASES[:3]:
                process = subprocess.Popen(command + ["--child", case, "--database", str(path)],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           text=True, env=environment)
                try:
                    with selectors.DefaultSelector() as ready:
                        ready.register(process.stderr, selectors.EVENT_READ)
                        assert ready.select(config["kill_ready_timeout_seconds"]), "boundary timeout"
                        control = process.stderr.readline()
                    assert json.loads(control) == {"boundary_ready": case}
                    process.kill()
                    stdout, stderr = process.communicate(timeout=5)
                    row.update(exitcode=process.returncode, stdout=stdout, stderr=control + stderr)
                    assert process.returncode == -signal.SIGKILL and stdout == ""
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate(timeout=5)
                completed = child("--inspect", case, "--database", str(path))
            else:
                completed = child("--child", case, "--database", str(path))
            row.update(json.loads(completed.stdout))
            row["status"] = "PASS"
        except Exception as error:
            row["error"] = f"{type(error).__name__}: {error}"
            if isinstance(error, subprocess.CalledProcessError):
                row.update(child_stdout=error.stdout, child_stderr=error.stderr)
        outcomes.append(row)
        save(args.output / f"{case}.json", row)
    after = json.loads(child("--probe").stdout)
    summary = {"method": METHOD, "cases": len(outcomes),
               "passed": sum(row["status"] == "PASS" for row in outcomes),
               "runtime_hashes_unchanged": identity == after,
               "gpu_calls": 0, "g5_complete": False}
    summary["status"] = "PASS" if summary["passed"] == len(CASES) and identity == after else "FAIL"
    save(args.output / "summary.json", summary)
    print(dump(summary))
    return 0 if summary["status"] == "PASS" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-python", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--probe", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--child", choices=CASES, help=argparse.SUPPRESS)
    parser.add_argument("--inspect", choices=CASES[:3], help=argparse.SUPPRESS)
    parser.add_argument("--database", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.probe:
        print(dump(probe()))
    elif args.inspect:
        print(dump(inspect_crash(args.inspect, args.database)))
    elif args.child in CASES[:3]:
        crash_child(args.child, args.database)
    elif args.child:
        print(dump(sequence_case(args.child, args.database, 100)))
    else:
        if not all((args.runtime_python, args.config, args.output)):
            parser.error("--runtime-python, --config and --output are required")
        return run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
