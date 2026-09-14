"""Read-only final preservation check; writes one exclusive review receipt."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parents[1]
ROOT = BENCH.parent
cache = {}
checks = []


def digest(path):
    path = path.resolve()
    if path not in cache:
        value = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                value.update(block)
        cache[path] = value.hexdigest()
    return cache[path]


def read(path):
    return json.loads(path.read_text())


def verify(label, mapping, base=ROOT):
    assert mapping, label
    for name, expected in mapping.items():
        path = Path(name)
        if not path.is_absolute():
            path = base / path
        assert digest(path) == expected, str(path)
    checks.append(dict(check=label, files=len(mapping), status="PASS"))


initial_path = HERE / "initial-source-sha256.json"
assert digest(initial_path) == "6b2b9deb1cf57e0f8c4c3bb396d4ac791e1f80de232f4826d946baad34dd5522"
initial = read(initial_path)
changed = [name for name, expected in initial.items() if digest(ROOT / name) != expected]
assert changed == ["pheroos-bench/README.md"], changed
checks.append(dict(check="initial_repository_snapshot", files=len(initial), status="PASS_WITH_DECLARED_README_EDIT", changed=changed, missing=[]))

r1 = read(BENCH / "results/r1-coordination-pilot-v2/freeze.json")["sha256"]
verify("R1 frozen source/config", {("r1-coordination-pilot-v2.json" if k == "config" else k): v for k, v in r1.items()}, BENCH)
verify("R2 frozen source/config", read(BENCH / "results/r2-pilot-v1/freeze.json")["sha256"], BENCH)
capacity = read(BENCH / "results/r2-capacity-audit-v1/freeze.json")["sha256"]
aliases = dict(config="r2-capacity-audit-v1.json", contract="R2-capacity-v1-contract.md", method="src/pheroos_bench/r2_capacity.py", tests="tests/test_r2_capacity.py")
resolved = {}
for name, expected in capacity.items():
    if name.startswith("historical/"):
        name = "results/r2-pilot-v1/" + name.removeprefix("historical/")
    elif name.startswith("historical_source/"):
        name = name.removeprefix("historical_source/")
    else:
        name = aliases[name]
    resolved[name] = expected
verify("R2 capacity frozen historical evidence/source", resolved, BENCH)

audit_fields = {
    "r3-framed-pilot-v3/independent_audit.json": ["source_evidence_sha256", "audit_source_sha256"],
    "r3-session-capability-v1/independent_audit.json": ["frozen_input_hashes", "evidence_sha256", "audit_source_sha256"],
    "r4-session-scaling-pilot-v1/abort-independent-audit-v1.json": ["checked_input_sha256", "evidence_sha256", "audit_source_sha256"],
    "r4-session-scaling-replication-v1/independent-audit-v1.json": ["checked_input_sha256", "evidence_sha256", "audit_source_sha256"],
    "r5-session-faults-v1/independent-audit-v2.json": ["frozen_input_sha256", "original_evidence_sha256", "audit_source_sha256"],
}
for name, fields in audit_fields.items():
    audit_path = BENCH / "results" / name
    audit = read(audit_path)
    for field in fields:
        verify(name + ":" + field, audit[field], audit_path.parent)

for name in ["r3-session-capability-v1/G5-gate-review.json", "r4-session-scaling-replication-v1/R4-gate-review.json", "r5-session-faults-v1/R5-gate-review.json"]:
    path = BENCH / "results" / name
    gate = read(path)
    mapping = gate.get("evidence_sha256")
    if mapping:
        verify(name + ":gate_bindings", mapping, path.parent)

result = dict(method="master_final_preservation_check_v1", created_utc=datetime.now(timezone.utc).isoformat(), status="PASS", counts_toward_verdict=False, generated_model_calls=0, fault_cases_rerun=0, initial_snapshot_sha256=digest(initial_path), checks=checks, unique_files_hashed=len(cache), source_sha256=digest(Path(__file__)), limitations=["Verifies retained identities, not a new semantic audit or efficacy observation.", "Core full-suite interruption remains incomplete; this receipt does not claim a full-suite pass."])
with (HERE / "final-integrity-v1.json").open("x") as stream:
    json.dump(result, stream, indent=2)
    stream.write("\n")
print(json.dumps(dict(status=result["status"], checks=len(checks), unique_files_hashed=result["unique_files_hashed"], changed=changed)))
