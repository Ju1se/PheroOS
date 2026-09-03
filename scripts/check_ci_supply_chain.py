#!/usr/bin/env python3
"""Offline audit for CI pinning, constraints, and provenance policy."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from hashlib import sha256
import importlib
from pathlib import Path
import re
from types import ModuleType


def _load_quality_gate_module() -> ModuleType:
    try:
        return importlib.import_module("scripts.check_quality_gate")
    except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
        return importlib.import_module("check_quality_gate")


_quality_gate = _load_quality_gate_module()
CANONICAL_REPOSITORY: str = _quality_gate.CANONICAL_REPOSITORY
PROVENANCE_JOB: str = _quality_gate.PROVENANCE_JOB
QUALITY_GATE_JOB: str = _quality_gate.QUALITY_GATE_JOB
REQUIRED_VALIDATION_JOBS: tuple[str, ...] = _quality_gate.REQUIRED_VALIDATION_JOBS


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"
RELEASE_CANDIDATE_WORKFLOW = ROOT / ".github" / "workflows" / "release-candidate.yml"
CONSTRAINTS = ROOT / "requirements" / "ci-constraints.txt"
CONSTRAINT_DIGEST = ROOT / "requirements" / "ci-constraints.sha256"

ACTION_PINS = {
    "actions/checkout": "de0fac2e4500dabe0009e67214ff5f5447ce83dd",
    "actions/setup-python": "a309ff8b426b58ec0e2a45f0f869d46889d02405",
    "actions/upload-artifact": "330a01c490aca151604b8cf639adc76d48f6c5d4",
    "actions/download-artifact": "018cc2cf5baa6db3ef3c5f8a56943fffe632ef53",
    "actions/attest": "59d89421af93a897026c735860bf21b6eb4f7b26",
}
RELEASE_CANDIDATE_ACTION_PINS = {
    action: ACTION_PINS[action]
    for action in (
        "actions/checkout",
        "actions/setup-python",
        "actions/upload-artifact",
    )
}
RELEASE_CANDIDATE_BUILD_COMMAND = (
    "python scripts/release_candidate.py --staging-dir "
    '"$RUNNER_TEMP/pheroos-release-candidate"'
)
RELEASE_CANDIDATE_VERIFY_COMMAND = (
    "python scripts/release_candidate.py --verify-staging "
    '"$RUNNER_TEMP/pheroos-release-candidate"'
)

REQUIRED_JOBS = set(REQUIRED_VALIDATION_JOBS) | {
    PROVENANCE_JOB,
    QUALITY_GATE_JOB,
}
COVERAGE_MEASUREMENT_SHARDS = (
    "foundation",
    "governance-1",
    "governance-2",
    "governance-3",
    "governance-distributed-totality",
    "governance-4",
    "trace-1",
    "trace-2",
    "conformance-1",
    "conformance-finality-reference",
    "conformance-finality-independent",
    "conformance-2",
    "conformance-runtime",
    "ecosystem",
    "policy",
)
REQUIRED_TOOLS = {
    "build",
    "coverage",
    "jsonschema",
    "mypy",
    "pip",
    "pytest",
    "ruff",
    "setuptools",
    "wheel",
}
REQUIRED_VALIDATION_MARKERS = {
    "python-tests": ('python scripts/run_test_shard.py "${{ matrix.shard }}"',),
    "lint-and-typing": (
        "python -m ruff check pheroos scripts tests",
        "python -m ruff format --check pheroos scripts tests",
        "python -m mypy --no-incremental pheroos",
        "python -m mypy --no-incremental scripts/release_candidate.py",
        "scripts/generate_release_sbom.py",
        "scripts/check_distribution_reproducibility.py",
        "scripts/check_ci_supply_chain.py",
        "scripts/check_repository_policy.py",
        "python scripts/check_stable_typing.py --check",
    ),
    "schema-version-drift": (
        "tests/cli/test_schema_export.py",
        "python scripts/generate_schema_artifacts.py --check",
        "python scripts/generate_commit_tck.py --check",
        "python scripts/generate_public_api_inventory.py --check",
        "python scripts/generate_governance_public_api.py --check",
        "python scripts/check_legacy_authority_inventory.py --check",
    ),
    "public-abi-shape-drift": (
        "tests/test_public_api_inventory.py",
        "tests/conformance/test_public_api_lifecycle.py",
    ),
    "manifest-negative": (
        "tests/protocol/test_manifest_validation.py",
        "tests/conformance/test_protocol_version_fail_closed.py",
    ),
    "tck-v1-legacy": (
        "tests/conformance/test_commit_tck.py",
        "python -m pheroos.cli.main tck run --version v1",
    ),
    "tck-v2-reference": (
        "python -m pheroos.cli.main tck run --version v2",
        "schemas_are_public or declarative_golden",
    ),
    "tck-v2-independent": (
        '--adapter "python -I -m pheroos.conformance.commit_tck_v2_spec_adapter"',
        "independent_spec_model or real_jsonl_handshake",
    ),
    "external-adapter-adversarial": (
        "hard_coded or expected_echo",
        "versions_are_distinct or incompatible_handshake",
    ),
    "consumer-compat": (
        "python -m pytest -q tests/e2e tests/test_public_api_contract.py",
        "tests/examples/test_hybrid_replay_protocol.py",
        "pheroos conformance examples/distributed-commit-protocol",
    ),
    "scope-concurrency-lifecycle": ("tests/kernel/test_runtime_scope.py",),
    "authority-restart-atomicity": (
        "tests/governance/test_authority_ledger.py",
        "tests/governance/test_atomic_hybrid_commit.py",
        "tests/conformance/test_authority_ledger_contract.py",
        "tests/governance/test_hybrid_replay_v2_*.py",
        "test_hybrid_replay_v2_adversarial_support_uses_only_public_abi_proxies",
        "test_hybrid_replay_v2_resource_support_uses_only_public_constructors",
        "tests/trace/test_hybrid_replay_v2_trace_contract.py",
    ),
    "wheel-sdist-external-cwd": (
        "python -m build --no-isolation\n"
        "          python scripts/normalize_sdist.py dist/*.tar.gz",
        'python -m build --no-isolation --outdir "$RUNNER_TEMP/pheroos-repro"',
        "python scripts/check_distribution_reproducibility.py",
        '"$PHEROOS" wire validate capability-v3',
        "examples/hybrid-replay-protocol/run.py",
        '"$PHEROOS" source-conformance',
        '"$PHEROOS" tck run --version v2',
    ),
    "import-dag-and-cold-import": (
        "tests/kernel/test_kernel_import_boundary.py",
        "tests/trace/test_static_contracts.py",
        "python scripts/benchmark_governance_import.py --samples 5 --check",
    ),
    "reference-performance": (
        "tests/performance/test_reference_performance_contract.py",
        "python scripts/check_reference_performance.py --check --quick",
    ),
    "engineering-baseline": (
        "python scripts/check_engineering_baseline.py --check",
        "tests/ci/test_engineering_baseline.py",
        "tests/ci/test_repository_policy.py",
        "tests/governance/test_wp00_legacy_characterization.py",
    ),
    "coverage-measure": (
        "--require-hashes --only-binary=:all: -r requirements/ci-constraints.txt",
        '--measure-shard "${{ matrix.shard }}"',
        "--measure-only",
        "include-hidden-files: true",
    ),
    "coverage-gate": (
        "--require-hashes --only-binary=:all: -r requirements/ci-constraints.txt",
        "python scripts/check_coverage_gate.py --emit-ci-base",
        "--combine-shards-dir coverage-data",
        "--data-file .coverage",
        '--base-ref "$COVERAGE_BASE_REF"',
        "tests/ci/test_coverage_gate.py",
    ),
    "authority-mutation": (
        "python scripts/check_authority_mutation.py --profile pr",
        "tests/ci/test_authority_mutation_gate.py",
        "tests/ci/test_authority_mutation_probes.py",
    ),
    "supply-chain": (
        "python scripts/check_ci_supply_chain.py --check",
        "python scripts/check_repository_policy.py --check",
        "python scripts/generate_release_sbom.py dist",
        "python -m unittest -q tests.ci.test_supply_chain",
    ),
}

FORBIDDEN_VALIDATION_MARKERS = {
    "lint-and-typing": (
        "python -m ruff check --select",
        "python -m mypy --incremental",
        "--follow-imports=skip",
        "--ignore-missing-imports",
    ),
}
REQUIRED_VALIDATION_MARKER_COUNTS = {
    (
        "wheel-sdist-external-cwd",
        '"$PHEROOS" wire validate capability-v3',
    ): 2,
    (
        "wheel-sdist-external-cwd",
        "examples/hybrid-replay-protocol/run.py",
    ): 2,
    (
        "wheel-sdist-external-cwd",
        '"$PHEROOS" source-conformance',
    ): 2,
    (
        "wheel-sdist-external-cwd",
        '"$PHEROOS" tck run --version v2',
    ): 2,
}

# These digests bind the complete execution context, not only command text:
# events, permissions, environment, runner, matrix, ordered steps, action inputs,
# shell controls, and run scalars.  The semantic checks below retain readable
# diagnostics while any workflow change requires deliberate contract refresh.
WORKFLOW_HEADER_DIGEST = (
    "7dcc8bdd0bf04d1d3815717093c2f79f80174975a7a6c935bc3197e6e57e19fc"
)
WORKFLOW_JOB_DIGESTS = {
    "python-tests": "db44ef360b52e4fd9e975d2ff965eac0c6d4fac6816a15fb86efc6bf7a3a0845",
    "lint-and-typing": "5ceada187b115a4737af295db42c7f04afc3a51d967076c6e8d8827fac1d37ae",
    "schema-version-drift": (
        "8156a5c2fe5063ae430c04763fbde4dd4093fa1f79425a6d0940c29f09548710"
    ),
    "public-abi-shape-drift": (
        "d7c4751f0ad88b40419b6d7c8d08639eda90290e7dde737c6d570fb8f830af5c"
    ),
    "manifest-negative": (
        "687c235487c984f28369c61256852432bab069ffc71be8aa71287911643ec1f0"
    ),
    "tck-v1-legacy": "95346fa14875a22a578b271b8753dfff253f67ed6cedd0e60c3da12f60531171",
    "tck-v2-reference": (
        "1410b34b06d2d435309ae3c41cd9f6bc02a430a697675ab55265da0c767d9453"
    ),
    "tck-v2-independent": (
        "06d5d58e9dd311f7e18281856239a54663247e6ebe0689bb0c213ee39b519b49"
    ),
    "external-adapter-adversarial": (
        "239f8e8f68a22aed57b3fcb0b4a2af65576d964a4b4516336af6f9e3c3277a19"
    ),
    "consumer-compat": (
        "4ad4ce1e3e40fb3945a56bf8a7e5add2963e17da987aac7816d93d76ab59739b"
    ),
    "scope-concurrency-lifecycle": (
        "458a058ac5ffb6670581c8e3d2afd0d3a7242ce21c6f2ecb240714cbd638fcff"
    ),
    "authority-restart-atomicity": (
        "5dd6cfb4f6c905be491159087fa0633f4cd84145bd73547bcfc7f7092cca45a8"
    ),
    "wheel-sdist-external-cwd": (
        "0d4f125339abeaf0dc2dfb65c5e0237dc85206c0c8ce4a375283dcded6ed152f"
    ),
    "import-dag-and-cold-import": (
        "7057afec87fb8b73f3b1978545d9e0fd7e607f79533388881fe2850b4fe07397"
    ),
    "reference-performance": (
        "b62d450d74b3d91e177fed494b243812f01cd293d0d6685c5bb62712ae305798"
    ),
    "engineering-baseline": (
        "d4b75cdbb099b8c41a62ee5f7a7c1c29f92fb27ef2bcff654c004b572b5f615c"
    ),
    "coverage-measure": (
        "5c2a0d400d812ab09a4ff064b855b0a8d2138d738147d030b8ccf9d86f31982f"
    ),
    "coverage-gate": "a0faaad9af9f2b6b8f3be9d4262679bd763d3bd720c870eecfc59776580ff748",
    "authority-mutation": (
        "0c6ed88f4fc908722641ba0dd090a5c36301192f537d9f8ed2e41570e5f9d6af"
    ),
    "supply-chain": "1f5f498a2c881326114102a0955f5f7336239e3161abdd1934d65b1818e947e4",
    PROVENANCE_JOB: "dec1bf4def4b220dee051d00b5a884e80e2a4c777b77ec6ae7803cb1bcf2b8ac",
    QUALITY_GATE_JOB: (
        "07aeb4161606f8022a64640bc63ebda3a07fa890b37bf2c90677a09ea60caf70"
    ),
}
RELEASE_CANDIDATE_HEADER_DIGEST = (
    "5d22378984a395180a4b36db6cd99011838be7e16913f2a469c8291e6435769b"
)
RELEASE_CANDIDATE_JOB_DIGEST = (
    "038dd056c64c28ed61e20f2204c73749a72878634226b2d14763dbdda957c57a"
)

PIN = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([^\s;]+)"
    r'(?:\s*;\s*(python_version\s*>=\s*"3\.13"))?\s+\\$'
)
HASH_LINE = re.compile(r"^    --hash=sha256:([0-9a-f]{64})(?: \\)?$")
USE = re.compile(r"^\s*-?\s*uses:\s*([^@\s]+)@([^\s#]+)", re.MULTILINE)
JOB = re.compile(r"^  ([a-z0-9][a-z0-9-]*):\s*$", re.MULTILINE)


def _lock_header(line: str, line_number: int) -> tuple[str, str]:
    match = PIN.fullmatch(line)
    if match is None:
        raise ValueError(f"CI wheel lock line {line_number} is not an exact hashed pin")
    name, version, marker = match.groups()
    normalized = name.lower().replace("_", "-")
    if normalized == "librt":
        if marker != 'python_version >= "3.13"':
            raise ValueError("librt must be limited to Python 3.13 and newer")
    elif marker is not None:
        raise ValueError(f"unexpected environment marker for {normalized}")
    return normalized, version


def _lock_hashes(
    lines: list[str],
    index: int,
    *,
    requirement: str,
) -> tuple[int, tuple[str, ...]]:
    hashes: list[str] = []
    continued = True
    while index < len(lines) and continued:
        match = HASH_LINE.fullmatch(lines[index])
        if match is None:
            break
        digest = match.group(1)
        if digest in hashes:
            raise ValueError(f"duplicate wheel hash for {requirement}")
        hashes.append(digest)
        continued = lines[index].endswith(" \\")
        index += 1
    if not hashes or continued:
        raise ValueError(
            f"CI wheel lock requirement lacks closed hashes: {requirement}"
        )
    return index, tuple(hashes)


def parse_hashed_requirements(constraints: bytes) -> dict[str, str]:
    """Parse the exact, hash-locked wheel requirements used by CI."""

    try:
        lines = constraints.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("CI wheel lock must be UTF-8") from error
    pins: dict[str, str] = {}
    previous = ""
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line or line.startswith("#"):
            index += 1
            continue
        normalized, version = _lock_header(line, index + 1)
        if normalized in pins:
            raise ValueError(f"duplicate CI wheel lock requirement: {normalized}")
        if previous and normalized < previous:
            raise ValueError("CI wheel lock requirements must be canonically sorted")
        index += 1
        index, _ = _lock_hashes(lines, index, requirement=normalized)
        pins[normalized] = version
        previous = normalized
    return pins


def _job_blocks(workflow: str) -> tuple[dict[str, str], set[str]]:
    parts = workflow.split("\njobs:\n", maxsplit=1)
    if len(parts) != 2:
        return {}, set()
    jobs_source = parts[1]
    matches = list(JOB.finditer(jobs_source))
    blocks: dict[str, str] = {}
    duplicates: set[str] = set()
    for index, match in enumerate(matches):
        name = match.group(1)
        end = matches[index + 1].start() if index + 1 < len(matches) else None
        if name in blocks:
            duplicates.add(name)
        blocks[name] = jobs_source[match.start() : end]
    return blocks, duplicates


def _workflow_contract_failures(
    workflow: str,
    blocks: Mapping[str, str],
    *,
    expected_header_digest: str,
    expected_job_digests: Mapping[str, str],
    label: str,
) -> list[str]:
    failures: list[str] = []
    parts = workflow.split("\njobs:\n", maxsplit=1)
    if len(parts) != 2:
        return [f"{label} lacks the exact jobs boundary"]
    first_job = JOB.search(parts[1])
    if first_job is None or first_job.start() != 0:
        failures.append(
            f"{label} execution contract contains unclassified content "
            "before its first exact job"
        )
    observed_header = sha256(parts[0].encode("utf-8")).hexdigest()
    if observed_header != expected_header_digest:
        failures.append(f"{label} header differs from its exact execution contract")
    if set(expected_job_digests) != set(blocks):
        failures.append(f"{label} job digest inventory is not exact")
    for job, expected_digest in expected_job_digests.items():
        observed = sha256(blocks.get(job, "").encode("utf-8")).hexdigest()
        if observed != expected_digest:
            failures.append(
                f"job {job} differs from its exact execution-context contract"
            )
    return failures


def _execution_control_failures(
    block: str,
    *,
    job: str,
    allow_job_condition: bool,
) -> list[str]:
    failures: list[str] = []
    if not allow_job_condition and re.search(r"^ {4}if\s*:", block, re.MULTILINE):
        failures.append(f"job {job} must not be conditional or skippable")
    if re.search(r"^ {8}if\s*:", block, re.MULTILINE):
        failures.append(f"job {job} must not contain conditional or skippable steps")
    if re.search(r"^ {4}continue-on-error\s*:", block, re.MULTILINE):
        failures.append(f"job {job} must not use job-level continue-on-error")
    if re.search(r"^ {8}continue-on-error\s*:", block, re.MULTILINE):
        failures.append(f"job {job} must not use step-level continue-on-error")
    if re.search(r"^ {4}shell\s*:", block, re.MULTILINE):
        failures.append(f"job {job} must not override the job shell")
    if re.search(r"^ {8}shell\s*:", block, re.MULTILINE):
        failures.append(f"job {job} must not override a step shell")
    return failures


def _block_list(block: str, field: str) -> set[str]:
    match = re.search(
        rf"^    {re.escape(field)}:\s*\n"
        r"((?:^      - [a-z0-9][a-z0-9-]*\s*$\n?)+)",
        block,
        re.MULTILINE,
    )
    if match is None:
        return set()
    return set(
        re.findall(
            r"^      - ([a-z0-9][a-z0-9-]*)\s*$",
            match.group(1),
            re.MULTILINE,
        )
    )


def _workflow_safety_failures(workflow: str) -> list[str]:
    failures: list[str] = []
    if "pull_request_target:" in workflow:
        failures.append("workflow must not use pull_request_target")
    if "secrets." in workflow:
        failures.append("read-only validation workflow must not consume secrets")
    return failures


def _permission_mappings(
    source: str,
    *,
    indent: int,
) -> list[dict[str, str]]:
    """Parse the deliberately small GitHub permissions mapping surface."""

    lines = source.splitlines()
    prefix = " " * indent
    declarations: list[dict[str, str]] = []
    for index, line in enumerate(lines):
        match = re.fullmatch(rf"{re.escape(prefix)}permissions:\s*(.*)", line)
        if match is None:
            continue
        inline = match.group(1).strip()
        if inline:
            declarations.append({"*": inline})
            continue
        mapping: dict[str, str] = {}
        child_prefix = " " * (indent + 2)
        for child in lines[index + 1 :]:
            if not child.strip():
                continue
            child_indent = len(child) - len(child.lstrip(" "))
            if child_indent <= indent:
                break
            item = re.fullmatch(
                rf"{re.escape(child_prefix)}([a-z0-9-]+):\s*([a-z-]+)\s*",
                child,
            )
            if item is None or item.group(1) in mapping:
                mapping["!invalid"] = child.strip()
                continue
            mapping[item.group(1)] = item.group(2)
        declarations.append(mapping)
    return declarations


def _top_level_permission_failures(workflow: str, *, label: str) -> list[str]:
    header = workflow.split("\njobs:\n", maxsplit=1)[0]
    observed = _permission_mappings(header, indent=0)
    if observed != [{"contents": "read"}]:
        return [f"{label} top-level permissions must be exactly contents: read"]
    return []


def _job_permission_failures(
    block: str,
    *,
    job: str,
    expected: Mapping[str, str] | None,
) -> list[str]:
    observed = _permission_mappings(block, indent=4)
    if expected is None:
        if observed:
            return [f"validation job {job} must not override workflow permissions"]
        return []
    if observed != [dict(expected)]:
        return [f"job {job} permissions differ from the exact allowlist"]
    return []


def _action_failures(
    workflow: str,
    *,
    action_pins: Mapping[str, str] = ACTION_PINS,
) -> list[str]:
    failures: list[str] = []
    uses = USE.findall(workflow)
    if not uses:
        failures.append("workflow has no actions")
    for action, revision in uses:
        expected = action_pins.get(action)
        if expected is None:
            failures.append(f"unapproved action dependency: {action}")
        elif revision != expected:
            failures.append(f"{action} is not pinned to the audited full SHA")
        if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
            failures.append(f"{action} does not use a full commit SHA")
    for action, revision in action_pins.items():
        if (action, revision) not in uses:
            failures.append(f"workflow does not exercise pinned action: {action}")
    failures.extend(_checkout_credential_failures(workflow, action_pins))
    return failures


def _checkout_credential_failures(
    workflow: str,
    action_pins: Mapping[str, str],
) -> list[str]:
    failures: list[str] = []
    checkout_pin = action_pins.get("actions/checkout")
    if checkout_pin is not None:
        checkout_count = workflow.count(f"uses: actions/checkout@{checkout_pin}")
        credential_count = workflow.count("persist-credentials: false")
        if checkout_count == 0 or credential_count != checkout_count:
            failures.append(
                "every checkout must disable persisted repository credentials"
            )
        if "persist-credentials: true" in workflow:
            failures.append("checkout must not persist repository credentials")
    return failures


def audit_release_candidate_workflow(workflow: str) -> list[str]:
    """Audit the separate read-only RC workflow and its exact action allowlist."""

    failures = _workflow_safety_failures(workflow)
    failures.extend(
        _action_failures(
            workflow,
            action_pins=RELEASE_CANDIDATE_ACTION_PINS,
        )
    )
    failures.extend(
        _top_level_permission_failures(workflow, label="release-candidate workflow")
    )
    blocks, duplicates = _job_blocks(workflow)
    if duplicates or set(blocks) != {"release-candidate-dry-run"}:
        failures.append("release-candidate workflow must contain one classified job")
    release_block = blocks.get("release-candidate-dry-run", "")
    failures.extend(
        _job_permission_failures(
            release_block,
            job="release-candidate-dry-run",
            expected=None,
        )
    )
    failures.extend(
        _masked_validation_command_failures(
            "release-candidate-dry-run",
            _without_yaml_comments(release_block),
        )
    )
    failures.extend(
        _workflow_contract_failures(
            workflow,
            blocks,
            expected_header_digest=RELEASE_CANDIDATE_HEADER_DIGEST,
            expected_job_digests={
                "release-candidate-dry-run": RELEASE_CANDIDATE_JOB_DIGEST
            },
            label="release-candidate workflow",
        )
    )
    failures.extend(
        _execution_control_failures(
            release_block,
            job="release-candidate-dry-run",
            allow_job_condition=False,
        )
    )
    failures.extend(_installation_failures(workflow, require_editable=False))
    for command in (
        RELEASE_CANDIDATE_BUILD_COMMAND,
        RELEASE_CANDIDATE_VERIFY_COMMAND,
    ):
        if release_block.count(f"        run: {command}\n") != 1:
            failures.append(
                "release-candidate workflow must run each exact orchestrator "
                f"command once: {command}"
            )
    return failures


def _job_inventory_failures(
    workflow: str,
    blocks: dict[str, str],
    duplicates: set[str],
) -> list[str]:
    failures: list[str] = []
    if duplicates:
        failures.append(f"workflow has duplicate jobs: {sorted(duplicates)}")
    jobs = set(blocks)
    missing_jobs = REQUIRED_JOBS - jobs
    unknown_jobs = jobs - REQUIRED_JOBS
    if missing_jobs:
        failures.append(f"missing required CI jobs: {sorted(missing_jobs)}")
    if unknown_jobs:
        failures.append(f"unclassified CI jobs: {sorted(unknown_jobs)}")

    for version in ('"3.12"', '"3.13"', '"3.14"'):
        if version not in workflow:
            failures.append(f"Python matrix is missing {version}")
    failures.extend(_top_level_permission_failures(workflow, label="workflow"))
    return failures


def _installation_failures(
    workflow: str,
    *,
    require_editable: bool = True,
) -> list[str]:
    failures: list[str] = []
    workflow_lines = workflow.splitlines()
    lock_marker = (
        "--require-hashes --only-binary=:all: -r requirements/ci-constraints.txt"
    )
    editable_installs = [
        index
        for index, line in enumerate(workflow_lines)
        if "pip install --no-deps --no-build-isolation -e ." in line
    ]
    if require_editable and not editable_installs:
        failures.append("workflow has no explicit editable CI installation")
    for index in editable_installs:
        preceding = "\n".join(workflow_lines[max(0, index - 3) : index])
        if lock_marker not in preceding:
            failures.append(
                "no-deps editable install lacks the complete hashed wheel lock"
            )
    for line in workflow_lines:
        if "pip install" not in line:
            continue
        local_install = (
            "pip install --no-deps dist/*.whl" in line
            or "pip install --no-build-isolation --no-deps dist/*.tar.gz" in line
            or "pip install --no-deps --no-build-isolation -e ." in line
        )
        hashed_install = (
            "--require-hashes" in line
            and "--only-binary=:all:" in line
            and "requirements/ci-constraints.txt" in line
        )
        if not local_install and not hashed_install:
            failures.append(
                "every network-capable pip install must use the complete hashed lock"
            )
    if "--constraint requirements/ci-constraints.txt" in workflow:
        failures.append("workflow must not use version-only constraints")
    return failures


def _reproducibility_failures(workflow: str) -> list[str]:
    failures: list[str] = []
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
    return failures


def _validation_job_failures(blocks: dict[str, str]) -> list[str]:
    failures: list[str] = []
    for job in REQUIRED_VALIDATION_JOBS:
        block = blocks.get(job, "")
        executable = _without_yaml_comments(block)
        failures.extend(_job_permission_failures(block, job=job, expected=None))
        failures.extend(
            _execution_control_failures(
                block,
                job=job,
                allow_job_condition=False,
            )
        )
        for marker in REQUIRED_VALIDATION_MARKERS[job]:
            expected_count = REQUIRED_VALIDATION_MARKER_COUNTS.get(
                (job, marker),
                1,
            )
            if executable.count(marker) != expected_count:
                failures.append(
                    f"validation job {job} has the wrong semantic command marker "
                    f"count ({expected_count} required): {marker}"
                )
        for marker in FORBIDDEN_VALIDATION_MARKERS.get(job, ()):
            if marker in executable:
                failures.append(
                    f"validation job {job} contains forbidden weak command marker: "
                    f"{marker}"
                )
        failures.extend(_masked_validation_command_failures(job, executable))

    python_tests = blocks.get("python-tests", "")
    if (
        "--require-hashes --only-binary=:all: -r requirements/ci-constraints.txt"
    ) not in python_tests:
        failures.append("python-tests must install the complete hashed CI wheel lock")
    return failures


def _without_yaml_comments(block: str) -> str:
    return "\n".join(line.split("#", maxsplit=1)[0] for line in block.splitlines())


def _masked_validation_command_failures(job: str, block: str) -> list[str]:
    shell = "\n".join(
        line
        for line in block.splitlines()
        if re.fullmatch(r"\s*[A-Za-z0-9_-]+:\s*[|>]-?\s*", line) is None
    )
    patterns = (
        r"\|\|",
        r"(?<!\|)\|(?!\|)",
        r"&&",
        r"(?<!&)&(?!&)",
        r";",
        r"`",
        r"\$\(",
        r"^\s*(?:run:\s*)?!\s+",
        r"^\s*set\s+\+e(?:\s|$)",
        r"^\s*exit\s+0(?:\s|$)",
        r"^\s*run:\s*(?:true|:)\s*$",
        (
            r"^\s*(?:if|then|elif|else|fi|case|esac|for|select|while|until|do|done|"
            r"function|eval|source|trap)(?:\s|$)"
        ),
        r"^\s*\.\s+",
        r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*\(\)\s*\{",
        r"\b(?:bash|sh)\s+-c\b",
    )
    if any(re.search(pattern, shell, re.MULTILINE) for pattern in patterns):
        return [f"validation job {job} contains a masked or empty success command"]
    return []


def _provenance_permission_failures(workflow: str, provenance: str) -> list[str]:
    failures: list[str] = []
    write_permissions = (
        "attestations: write",
        "id-token: write",
        "artifact-metadata: write",
    )
    if any(permission not in provenance for permission in write_permissions):
        failures.append("provenance job lacks explicit minimal attestation permissions")
    for permission in write_permissions:
        if workflow.count(permission) != 1 or provenance.count(permission) != 1:
            failures.append(f"{permission} must appear only in the provenance job")
    failures.extend(
        _job_permission_failures(
            provenance,
            job=PROVENANCE_JOB,
            expected={
                "artifact-metadata": "write",
                "attestations": "write",
                "contents": "read",
                "id-token": "write",
            },
        )
    )
    return failures


def _provenance_failures(workflow: str, blocks: dict[str, str]) -> list[str]:
    failures: list[str] = []
    provenance = blocks.get(PROVENANCE_JOB, "")
    provenance_needs = _block_list(provenance, "needs")
    if provenance_needs != set(REQUIRED_VALIDATION_JOBS):
        failures.append(
            "provenance needs must equal every validation job: "
            f"missing={sorted(set(REQUIRED_VALIDATION_JOBS) - provenance_needs)}, "
            f"unknown={sorted(provenance_needs - set(REQUIRED_VALIDATION_JOBS))}"
        )
    provenance_condition = (
        "    if: >-\n"
        "      github.event_name == 'push' &&\n"
        "      github.ref == 'refs/heads/main' &&\n"
        f"      github.repository == '{CANONICAL_REPOSITORY}'\n"
    )
    if provenance_condition not in provenance:
        failures.append(
            "provenance must be restricted to a canonical trusted main push"
        )
    failures.extend(_provenance_permission_failures(workflow, provenance))
    if "name: pheroos-release-artifacts" not in provenance:
        failures.append("provenance does not consume the supply-chain artifact")
    if "python -m build" in provenance:
        failures.append("provenance must attest supplied bytes, not rebuild subjects")
    if "python -m unittest -q tests.ci.test_supply_chain" not in provenance:
        failures.append("provenance does not revalidate downloaded SBOM hashes")
    failures.extend(
        _execution_control_failures(
            provenance,
            job=PROVENANCE_JOB,
            allow_job_condition=True,
        )
    )
    return failures


def _quality_gate_failures(blocks: dict[str, str]) -> list[str]:
    failures: list[str] = []
    quality_gate = blocks.get(QUALITY_GATE_JOB, "")
    quality_needs = _block_list(quality_gate, "needs")
    expected_quality_needs = set(REQUIRED_VALIDATION_JOBS) | {PROVENANCE_JOB}
    if quality_needs != expected_quality_needs:
        failures.append(
            "quality-gate needs must equal validation plus provenance jobs: "
            f"missing={sorted(expected_quality_needs - quality_needs)}, "
            f"unknown={sorted(quality_needs - expected_quality_needs)}"
        )
    if "    name: quality-gate\n" not in quality_gate:
        failures.append("quality-gate must expose the fixed name quality-gate")
    if "    if: ${{ always() }}\n" not in quality_gate:
        failures.append("quality-gate must use job-level if: always()")
    failures.extend(
        _job_permission_failures(
            quality_gate,
            job=QUALITY_GATE_JOB,
            expected={"contents": "read"},
        )
    )
    if "QUALITY_GATE_NEEDS: ${{ toJSON(needs) }}" not in quality_gate:
        failures.append("quality-gate must pass the complete needs context")
    if "python scripts/check_quality_gate.py" not in quality_gate:
        failures.append("quality-gate must invoke the checked policy evaluator")
    failures.extend(
        _execution_control_failures(
            quality_gate,
            job=QUALITY_GATE_JOB,
            allow_job_condition=True,
        )
    )
    return failures


def _engineering_baseline_failures(blocks: dict[str, str]) -> list[str]:
    engineering = blocks.get("engineering-baseline", "")
    engineering_requirements = (
        "python scripts/check_engineering_baseline.py --check",
        "tests/ci/test_engineering_baseline.py",
        "tests/ci/test_quality_gate.py",
        "tests/ci/test_repository_policy.py",
        "tests/governance/test_wp00_legacy_characterization.py",
        "--require-hashes --only-binary=:all: -r requirements/ci-constraints.txt",
        "pip install --no-deps --no-build-isolation -e .",
    )
    if any(requirement not in engineering for requirement in engineering_requirements):
        return ["engineering-baseline must install exact tools and run all WP-00 tests"]
    return []


def _coverage_pipeline_failures(blocks: dict[str, str]) -> list[str]:
    measurement = blocks.get("coverage-measure", "")
    python_block = blocks.get("python-tests", "")
    observed = _matrix_shards(measurement)
    python_tests = _matrix_shards(python_block)
    failures: list[str] = []
    if 'python-version: ["3.12", "3.13", "3.14"]' not in python_block:
        failures.append("Python test matrix must run exact 3.12, 3.13, and 3.14")
    if python_tests != COVERAGE_MEASUREMENT_SHARDS:
        failures.append("Python test matrix must equal every locked test shard")
    if observed != COVERAGE_MEASUREMENT_SHARDS:
        failures.append("coverage measurement matrix must equal every locked shard")
    if "timeout-minutes: 30" not in python_block:
        failures.append("Python test shards must keep the locked 30-minute ceiling")
    if "timeout-minutes: 30" not in measurement:
        failures.append("coverage shards must keep the locked 30-minute ceiling")

    gate = blocks.get("coverage-gate", "")
    required = (
        "needs: [coverage-measure]",
        "pattern: pheroos-coverage-*",
        "merge-multiple: true",
        "--combine-shards-dir coverage-data",
    )
    if any(item not in gate for item in required):
        failures.append("coverage gate must depend on and combine the complete matrix")
    for shard in COVERAGE_MEASUREMENT_SHARDS:
        if shard not in measurement:
            failures.append(f"coverage shard is not end-to-end declared: {shard}")
    if "--measure" in gate:
        failures.append(
            "coverage gate must consume shards, not rerun a monolithic suite"
        )
    return failures


def _matrix_shards(block: str) -> tuple[str, ...]:
    match = re.search(
        r"^        shard:\s*\n((?:^          - [a-z0-9-]+\s*$\n?)+)",
        block,
        re.MULTILINE,
    )
    if match is None:
        return ()
    return tuple(
        re.findall(
            r"^          - ([a-z0-9-]+)\s*$",
            match.group(1),
            re.MULTILINE,
        )
    )


def _supply_chain_failures(blocks: dict[str, str]) -> list[str]:
    failures: list[str] = []
    supply_chain = blocks.get("supply-chain", "")
    if "needs: [wheel-sdist-external-cwd]" not in supply_chain:
        failures.append("supply-chain is not gated by external distribution checks")
    if "name: pheroos-distributions" not in supply_chain:
        failures.append("supply-chain does not consume validated distributions")
    if "python -m build" in supply_chain:
        failures.append("supply-chain must not replace externally validated bytes")
    if "python scripts/check_repository_policy.py --check" not in supply_chain:
        failures.append("supply-chain does not verify the proposed repository policy")
    return failures


def audit_workflow(workflow: str) -> list[str]:
    """Audit workflow text with all event-sensitive checks scoped to jobs."""

    blocks, duplicates = _job_blocks(workflow)
    failures = _workflow_safety_failures(workflow)
    failures.extend(_action_failures(workflow))
    failures.extend(_job_inventory_failures(workflow, blocks, duplicates))
    failures.extend(
        _workflow_contract_failures(
            workflow,
            blocks,
            expected_header_digest=WORKFLOW_HEADER_DIGEST,
            expected_job_digests=WORKFLOW_JOB_DIGESTS,
            label="workflow",
        )
    )
    failures.extend(_installation_failures(workflow))
    failures.extend(_reproducibility_failures(workflow))
    failures.extend(_validation_job_failures(blocks))
    failures.extend(_provenance_failures(workflow, blocks))
    failures.extend(_quality_gate_failures(blocks))
    failures.extend(_engineering_baseline_failures(blocks))
    failures.extend(_coverage_pipeline_failures(blocks))
    failures.extend(_supply_chain_failures(blocks))
    return failures


def audit() -> list[str]:
    failures: list[str] = []
    constraints = CONSTRAINTS.read_bytes()

    try:
        pins = parse_hashed_requirements(constraints)
    except ValueError as error:
        failures.append(str(error))
        pins = {}
    missing_tools = REQUIRED_TOOLS - set(pins)
    if missing_tools:
        failures.append(f"missing required CI pins: {sorted(missing_tools)}")

    expected_digest_line = CONSTRAINT_DIGEST.read_text(encoding="utf-8").strip()
    observed_digest = sha256(constraints).hexdigest()
    canonical_digest_line = f"{observed_digest}  requirements/ci-constraints.txt"
    if expected_digest_line != canonical_digest_line:
        failures.append("ci-constraints.sha256 does not bind the constraints file")

    failures.extend(audit_workflow(WORKFLOW.read_text(encoding="utf-8")))
    failures.extend(
        audit_release_candidate_workflow(
            RELEASE_CANDIDATE_WORKFLOW.read_text(encoding="utf-8")
        )
    )
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
