#!/usr/bin/env python3
"""Offline audit for CI pinning, constraints, and release provenance policy."""

from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"
CONSTRAINTS = ROOT / "requirements" / "ci-constraints.txt"
CONSTRAINT_DIGEST = ROOT / "requirements" / "ci-constraints.sha256"

ACTION_PINS = {
    "actions/checkout": "de0fac2e4500dabe0009e67214ff5f5447ce83dd",
    "actions/setup-python": "a309ff8b426b58ec0e2a45f0f869d46889d02405",
    "actions/upload-artifact": "330a01c490aca151604b8cf639adc76d48f6c5d4",
    "actions/download-artifact": "018cc2cf5baa6db3ef3c5f8a56943fffe632ef53",
    "actions/attest": "59d89421af93a897026c735860bf21b6eb4f7b26",
}

REQUIRED_JOBS = {
    "python-tests",
    "lint-and-typing",
    "schema-version-drift",
    "public-abi-shape-drift",
    "manifest-negative",
    "tck-v1-legacy",
    "tck-v2-reference",
    "tck-v2-independent",
    "external-adapter-adversarial",
    "consumer-compat",
    "scope-concurrency-lifecycle",
    "authority-restart-atomicity",
    "wheel-sdist-external-cwd",
    "import-dag-and-cold-import",
    "reference-performance",
    "supply-chain",
    "provenance",
}

REQUIRED_TOOLS = {
    "build",
    "jsonschema",
    "mypy",
    "pytest",
    "ruff",
    "setuptools",
    "wheel",
}

PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([^\s;]+)$")
USE = re.compile(r"^\s*-?\s*uses:\s*([^@\s]+)@([^\s#]+)", re.MULTILINE)
JOB = re.compile(r"^  ([a-z0-9][a-z0-9-]*):\s*$", re.MULTILINE)


def audit() -> list[str]:
    failures: list[str] = []
    workflow = WORKFLOW.read_text(encoding="utf-8")
    constraints = CONSTRAINTS.read_bytes()

    pins: dict[str, str] = {}
    previous = ""
    for line_number, raw_line in enumerate(
        constraints.decode("utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN.fullmatch(line)
        if match is None:
            failures.append(
                f"constraint line {line_number} is not an exact name==version pin"
            )
            continue
        name, version = match.groups()
        normalized = name.lower().replace("_", "-")
        if normalized in pins:
            failures.append(f"duplicate constraint: {normalized}")
        if previous and normalized < previous:
            failures.append("constraints must be canonically sorted")
        pins[normalized] = version
        previous = normalized
    missing_tools = REQUIRED_TOOLS - set(pins)
    if missing_tools:
        failures.append(f"missing required CI pins: {sorted(missing_tools)}")

    expected_digest_line = CONSTRAINT_DIGEST.read_text(encoding="utf-8").strip()
    observed_digest = sha256(constraints).hexdigest()
    canonical_digest_line = (
        f"{observed_digest}  requirements/ci-constraints.txt"
    )
    if expected_digest_line != canonical_digest_line:
        failures.append("ci-constraints.sha256 does not bind the constraints file")

    uses = USE.findall(workflow)
    if not uses:
        failures.append("workflow has no actions")
    for action, revision in uses:
        expected = ACTION_PINS.get(action)
        if expected is None:
            failures.append(f"unapproved action dependency: {action}")
        elif revision != expected:
            failures.append(f"{action} is not pinned to the audited full SHA")
        if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
            failures.append(f"{action} does not use a full commit SHA")
    for action, revision in ACTION_PINS.items():
        if (action, revision) not in uses:
            failures.append(f"workflow does not exercise pinned action: {action}")

    jobs = set(JOB.findall(workflow))
    missing_jobs = REQUIRED_JOBS - jobs
    if missing_jobs:
        failures.append(f"missing required CI jobs: {sorted(missing_jobs)}")
    for version in ('"3.12"', '"3.13"', '"3.14"'):
        if version not in workflow:
            failures.append(f"Python matrix is missing {version}")
    if not re.search(
        r"^permissions:\s*\n\s+contents:\s+read\s*$",
        workflow,
        re.MULTILINE,
    ):
        failures.append("workflow top-level permissions must be contents: read")
    if "--constraint requirements/ci-constraints.txt" not in workflow:
        failures.append("workflow installs are not bound to CI constraints")
    workflow_lines = workflow.splitlines()
    editable_installs = [
        index
        for index, line in enumerate(workflow_lines)
        if '--no-build-isolation --constraint requirements/ci-constraints.txt -e ".[dev]"'
        in line
    ]
    if not editable_installs:
        failures.append("workflow has no explicit editable CI installation")
    bootstrap = (
        "python -m pip install --constraint requirements/ci-constraints.txt "
        "setuptools==80.9.0 wheel==0.45.1"
    )
    for index in editable_installs:
        preceding = "\n".join(workflow_lines[max(0, index - 3) : index])
        if bootstrap not in preceding:
            failures.append(
                "no-build-isolation editable install lacks an exact backend bootstrap"
            )
    for line in workflow_lines:
        if '-e ".[dev]"' in line and "--no-build-isolation" not in line:
            failures.append("editable install may invoke an unpinned isolated backend")
    if "sha256sum --check requirements/ci-constraints.sha256" not in workflow:
        failures.append("workflow does not verify the constraints digest")
    if 'SOURCE_DATE_EPOCH: "315532800"' not in workflow:
        failures.append("release epoch must use the reproducible ZIP-safe 1980 floor")
    if "python scripts/normalize_sdist.py" not in workflow:
        failures.append("workflow does not normalize sdist archive metadata")
    if "python scripts/check_distribution_reproducibility.py" not in workflow:
        failures.append("workflow does not compare repeated distribution bytes")
    if '--outdir "$RUNNER_TEMP/pheroos-repro"' not in workflow:
        failures.append("workflow does not perform an independent repeated build")
    if "python scripts/check_reference_performance.py --check --quick" not in workflow:
        failures.append("workflow does not enforce the reference performance budget")
    if "github.event_name == 'push'" not in workflow:
        failures.append("provenance is not restricted to a push event")
    if "github.ref == 'refs/heads/main'" not in workflow:
        failures.append("provenance is not restricted to main")
    if (
        "attestations: write" not in workflow
        or "id-token: write" not in workflow
        or "artifact-metadata: write" not in workflow
    ):
        failures.append("provenance job lacks explicit minimal attestation permissions")
    provenance = workflow.split("\n  provenance:\n", maxsplit=1)
    if len(provenance) != 2:
        failures.append("workflow does not define one provenance job")
    else:
        provenance_job = provenance[1]
        missing_dependencies = REQUIRED_JOBS - {"provenance"} - set(
            re.findall(r"^\s{6}- ([a-z0-9][a-z0-9-]*)$", provenance_job, re.MULTILINE)
        )
        if missing_dependencies:
            failures.append(
                "provenance is not gated by every validation job: "
                f"{sorted(missing_dependencies)}"
            )
        if "name: pheroos-release-artifacts" not in provenance_job:
            failures.append("provenance does not consume the supply-chain artifact")
        if "python -m build" in provenance_job:
            failures.append("provenance must attest supplied bytes, not rebuild subjects")
        if "python -m unittest -q tests.ci.test_supply_chain" not in provenance_job:
            failures.append("provenance does not revalidate downloaded SBOM hashes")
    supply_chain = workflow.split("\n  supply-chain:\n", maxsplit=1)
    if len(supply_chain) != 2:
        failures.append("workflow does not define one supply-chain job")
    else:
        supply_chain_job = supply_chain[1].split("\n  provenance:\n", maxsplit=1)[0]
        if "needs: [wheel-sdist-external-cwd]" not in supply_chain_job:
            failures.append("supply-chain is not gated by external distribution checks")
        if "name: pheroos-distributions" not in supply_chain_job:
            failures.append("supply-chain does not consume validated distributions")
        if "python -m build" in supply_chain_job:
            failures.append("supply-chain must not replace externally validated bytes")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    failures = audit()
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1 if args.check else 0
    print("CI supply-chain policy verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
