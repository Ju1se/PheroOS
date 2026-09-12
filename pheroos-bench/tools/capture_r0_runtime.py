"""Capture real G1 mock snapshots using the external runtime's interpreter.

This optional acceptance tool is not imported by bench or protocol-core.
"""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import tempfile

from pheroos_runtime import authority, engine, store as storage
from pheroos_runtime.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="r0-runtime-") as staging:
        database = Path(staging) / "complete.sqlite"
        Store.create(database, "r0-complete")
        engine.run(str(database), workers=4, policy="blackboard")
        snapshots = {"completed": Store(database).snapshot()}
        interrupted = Store.create(
            Path(staging) / "interrupted.sqlite", "r0-interrupted"
        )
        lease = interrupted.claim("worker")
        request = interrupted.context(lease) | {"operation": "square"}
        call_id = interrupted.reserve(lease, "tool.evaluate", request)
        interrupted.dispatch(lease, call_id, authority.authorize)
        interrupted.cancel()
        snapshots["cancelled_unknown"] = interrupted.snapshot()
        # Deterministic pure tool response arrives after cancellation. Usage
        # settles while the task stays cancelled; no artifact is published.
        reply = engine.invoke(
            interrupted.scope(lease.task_id), call_id, "tool.evaluate", request
        )
        interrupted.receive(
            call_id,
            dict(reply.result.payload),
            driver_receipt={
                "scope_ref": reply.receipt.scope_ref,
                "driver_id": reply.receipt.driver_id,
                "invocation_id": reply.receipt.invocation_id,
                "request_digest": reply.receipt.request_digest,
                "result_digest": reply.receipt.result_digest,
                "provenance": reply.receipt.provenance,
            },
        )
        snapshots["cancelled_late_receipt"] = interrupted.snapshot()
        for name, snapshot in snapshots.items():
            with (args.output / f"{name}.json").open("x") as output:
                json.dump(snapshot, output, separators=(",", ":"))
                output.write("\n")
        provenance = {
            "kind": "R0_G1_MOCK_SNAPSHOTS",
            "runtime_source_sha256": {
                name: sha256(
                    (Path(storage.__file__).parent / name).read_bytes()
                ).hexdigest()
                for name in ("store.py", "engine.py", "authority.py", "adapters.py")
            },
            "snapshots": {
                name: sha256((args.output / f"{name}.json").read_bytes()).hexdigest()
                for name in snapshots
            },
        }
        with (args.output / "provenance.json").open("x") as output:
            json.dump(provenance, output, indent=2)
            output.write("\n")
        print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
