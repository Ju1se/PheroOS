"""Narrow v2 adapter over the preserved R5 v1 checker.

The harness records the concrete JSONDecodeError caught as ValueError. V1
incorrectly required the base-class label for one exact malformed packet.
Run every original check, replacing only that one expected-label comparison
after independently reproducing the exact refusal. No study/runtime changes.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "tools/audit_r5_session_faults.py"
LEGACY_HASHES = {
    str(LEGACY): "c340d49b2be83f558c2a55e6e4120460b6d52a8eef8afce2759284c5d8ba453f",
    str(ROOT / "tests/test_audit_r5_session_faults.py"): "0a835a86685de9b4b2a302833801eb4fa7efe658d8a1d16296f62802ad31237c",
}
CASE = "transport:malformed_reply"
FAILURE_SHA256 = "c08b741735d9e542c9cb4edb5f319793b61dab765864412798f90354f70095ec"
FAILURE_RECEIPT_SHA256 = "d01c778091a87e6ebdc9bf5cad52b1f33a1f675afcaf605197d9b1feb2abf9b1"
METHOD = "r5_session_faults_independent_audit_v2"

for path, expected in LEGACY_HASHES.items():
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
        raise ValueError("preserved v1 checker closure changed: " + path)
spec = importlib.util.spec_from_file_location("r5_preserved_auditor_v1", LEGACY)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.verify_inputs(LEGACY_HASHES)


def prove_exact_refusal(row, directory):
    packet = base.read(directory / "transport.json")["raw_packet"]
    base.equal(packet, "malformed JSON", "v2 correction requires the exact retained malformed packet")
    try:
        base.decode(packet)
    except json.JSONDecodeError as error:
        refusal = f"{type(error).__name__}: {error}"
    else:
        raise ValueError("retained malformed packet unexpectedly parsed")
    base.check(issubclass(json.JSONDecodeError, ValueError), "exception class contract differs")
    base.equal(row["refusals"], [refusal], "v2 requires the exact concrete refusal")
    base.equal(row["accounting"], dict(actual_tokens=0, reserved_tokens=0, unknown_tokens=10, unknown_calls=1), "v2 requires retained unknown accounting")
    calls = row["snapshot"]["calls"]
    base.check(len(calls) == 1 and not row["snapshot"]["artifacts"], "v2 requires one unpublished call")
    base.equal({k: calls[0][k] for k in ("id", "action", "state", "prompt", "maximum", "reserved", "actual", "response")},
        dict(id="one", action="model.generate", state="dispatched", prompt=2, maximum=8, reserved=10, actual=None, response=None),
        "v2 requires the original unresolved dispatch")
    return dict(case=CASE, packet_sha256=base.digest(packet), independently_reproduced_refusal=refusal,
                corrected_expected_label="JSONDecodeError", legacy_expected_label="ValueError")


def observations(original, case, row, directory, applied):
    if case != CASE:
        return original(case, row, directory)
    proof = prove_exact_refusal(row, directory)
    original_equal, comparisons = base.equal, []
    def corrected_expected_label(left, right, reason):
        if reason == "reported refusal observation differs":
            original_equal(right, ["ValueError"], "preserved v1 expectation changed")
            original_equal(left, ["JSONDecodeError"], "unexpected concrete exception label")
            comparisons.append(reason)
            return
        original_equal(left, right, reason)
    # Single-threaded checker-local override; source and evidence remain intact.
    base.equal = corrected_expected_label
    try:
        original(case, row, directory)
    finally:
        base.equal = original_equal
    base.check(len(comparisons) == 1, "exactly one legacy comparison must be corrected")
    applied.append(proof)


def audit(output):
    base.check((output / "summary.json").is_file(), "terminal study summary required")
    legacy = output / "independent-audit-v1.json"
    legacy_receipt = output / "independent-audit-execution-v1.json"
    base.verify_inputs(LEGACY_HASHES | {str(legacy): FAILURE_SHA256, str(legacy_receipt): FAILURE_RECEIPT_SHA256})
    failed = base.read(legacy)
    base.equal([r["case"] for r in failed["cases"] if r["audit_status"] == "AUDIT_MISMATCH"], [CASE], "v1 has another unresolved audit issue")
    base.check(failed["audit_status"] == "AUDIT_MISMATCH" and failed["source_status"] == "PASS", "preserved v1 disposition differs")
    closure = LEGACY_HASHES | {str(p): base.file_hash(p) for p in (Path(__file__).resolve(), ROOT / "tests/test_audit_r5_session_faults_v2.py")}
    original, applied = base.observations, []
    base.observations = lambda case, row, directory: observations(original, case, row, directory, applied)
    try:
        result = base.audit(output)
    finally:
        base.observations = original
    base.check(len(applied) == 1, "the narrow correction did not run exactly once")
    base.verify_inputs(closure | {str(legacy): FAILURE_SHA256, str(legacy_receipt): FAILURE_RECEIPT_SHA256})
    result.update(audit_method=METHOD, audit_source_sha256=closure, correction=applied[0],
        retained_legacy_audit=dict(path=str(legacy), sha256=FAILURE_SHA256, status="AUDIT_MISMATCH", receipt_sha256=FAILURE_RECEIPT_SHA256),
        legacy_exit_rationale="Preserve v1 for its recorded audit. V2 reuses all v1 checks and replaces only its incorrect exact malformed-JSON exception-label expectation. No harness/runtime defect, study rerun, or independent new sample.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()
    base.check((args.output / "summary.json").is_file(), "terminal study summary required")
    base.check(not args.audit_output.exists(), "exclusive new audit output required")
    try:
        result = audit(args.output.resolve())
    except Exception as error:
        result = dict(audit_method=METHOD, audit_status="AUDIT_ERROR", counts_toward_verdict=False,
            error=f"{type(error).__name__}: {error}", source_summary=base.read(args.output / "summary.json"))
    with args.audit_output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(result["audit_status"])
    return 0 if result.get("engineering_gate") == "ELIGIBLE_FOR_ROOT_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
