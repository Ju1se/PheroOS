from __future__ import annotations

from pathlib import Path
import re

import pytest

from scripts.check_ci_supply_chain import (
    FORBIDDEN_VALIDATION_MARKERS,
    REQUIRED_VALIDATION_MARKERS,
    audit_workflow,
)
from scripts.check_quality_gate import (
    CANONICAL_REPOSITORY,
    PROVENANCE_JOB,
    REQUIRED_VALIDATION_JOBS,
    evaluate_quality_gate,
)


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"


def _needs(
    *,
    provenance: str,
    overrides: dict[str, str] | None = None,
) -> dict[str, dict[str, object]]:
    results = {
        job: {"result": "success", "outputs": {}} for job in REQUIRED_VALIDATION_JOBS
    }
    results[PROVENANCE_JOB] = {"result": provenance, "outputs": {}}
    for job, result in (overrides or {}).items():
        results[job] = {"result": result, "outputs": {}}
    return results


def test_pull_request_accepts_only_a_skipped_provenance_job() -> None:
    errors = evaluate_quality_gate(
        _needs(provenance="skipped"),
        event_name="pull_request",
        ref="refs/pull/41/merge",
        repository=CANONICAL_REPOSITORY,
    )

    assert errors == []


def test_fork_main_push_accepts_only_a_skipped_provenance_job() -> None:
    errors = evaluate_quality_gate(
        _needs(provenance="skipped"),
        event_name="push",
        ref="refs/heads/main",
        repository="fork-owner/PheroOS",
    )

    assert errors == []


def test_trusted_main_requires_successful_provenance() -> None:
    errors = evaluate_quality_gate(
        _needs(provenance="success"),
        event_name="push",
        ref="refs/heads/main",
        repository=CANONICAL_REPOSITORY,
    )

    assert errors == []


@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped", "pending"])
def test_validation_jobs_never_accept_non_success_results(result: str) -> None:
    job = REQUIRED_VALIDATION_JOBS[0]

    errors = evaluate_quality_gate(
        _needs(provenance="skipped", overrides={job: result}),
        event_name="pull_request",
        ref="refs/pull/42/merge",
        repository=CANONICAL_REPOSITORY,
    )

    assert any(job in error and "success" in error for error in errors)


def test_missing_or_unclassified_needs_fail_closed() -> None:
    missing = _needs(provenance="skipped")
    missing.pop(REQUIRED_VALIDATION_JOBS[0])
    extra = _needs(provenance="skipped")
    extra["unclassified-job"] = {"result": "success", "outputs": {}}

    missing_errors = evaluate_quality_gate(
        missing,
        event_name="pull_request",
        ref="refs/pull/43/merge",
        repository=CANONICAL_REPOSITORY,
    )
    extra_errors = evaluate_quality_gate(
        extra,
        event_name="pull_request",
        ref="refs/pull/43/merge",
        repository=CANONICAL_REPOSITORY,
    )

    assert any("missing" in error for error in missing_errors)
    assert any("unclassified" in error for error in extra_errors)


@pytest.mark.parametrize("result", ["success", "failure", "cancelled", "pending"])
def test_pull_request_rejects_any_provenance_result_other_than_skipped(
    result: str,
) -> None:
    errors = evaluate_quality_gate(
        _needs(provenance=result),
        event_name="pull_request",
        ref="refs/pull/44/merge",
        repository=CANONICAL_REPOSITORY,
    )

    assert any(PROVENANCE_JOB in error and "skipped" in error for error in errors)


@pytest.mark.parametrize("result", ["skipped", "failure", "cancelled", "pending"])
def test_trusted_main_rejects_any_provenance_result_other_than_success(
    result: str,
) -> None:
    errors = evaluate_quality_gate(
        _needs(provenance=result),
        event_name="push",
        ref="refs/heads/main",
        repository=CANONICAL_REPOSITORY,
    )

    assert any(PROVENANCE_JOB in error and "success" in error for error in errors)


def test_unknown_event_or_canonical_non_main_push_fails_closed() -> None:
    unknown = evaluate_quality_gate(
        _needs(provenance="skipped"),
        event_name="workflow_dispatch",
        ref="refs/heads/main",
        repository=CANONICAL_REPOSITORY,
    )
    wrong_ref = evaluate_quality_gate(
        _needs(provenance="skipped"),
        event_name="push",
        ref="refs/heads/release",
        repository=CANONICAL_REPOSITORY,
    )

    assert any("unsupported" in error for error in unknown)
    assert any("unsupported" in error for error in wrong_ref)


def _replace_in_job(
    workflow: str,
    job: str,
    old: str,
    new: str,
) -> str:
    delimiter = f"\n  {job}:\n"
    prefix, suffix = workflow.split(delimiter, maxsplit=1)
    next_job = re.search(r"^  [a-z0-9][a-z0-9-]*:\s*$", suffix, re.MULTILINE)
    end = next_job.start() if next_job is not None else len(suffix)
    block = suffix[:end]
    return prefix + delimiter + block.replace(old, new, 1) + suffix[end:]


def _replace_in_quality_gate(workflow: str, old: str, new: str) -> str:
    return _replace_in_job(workflow, "quality-gate", old, new)


def test_checked_in_workflow_satisfies_quality_gate_policy() -> None:
    assert audit_workflow(WORKFLOW.read_text(encoding="utf-8")) == []


def test_workflow_policy_rejects_non_always_aggregator() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    mutated = _replace_in_quality_gate(
        workflow,
        "if: ${{ always() }}",
        "if: ${{ success() }}",
    )

    assert any("always" in failure for failure in audit_workflow(mutated))


def test_workflow_policy_rejects_missing_aggregated_job() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    job = REQUIRED_VALIDATION_JOBS[0]
    mutated = _replace_in_quality_gate(workflow, f"      - {job}\n", "")

    assert any("quality-gate needs" in failure for failure in audit_workflow(mutated))


def test_workflow_policy_rejects_conditional_validation_job() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    job = REQUIRED_VALIDATION_JOBS[0]
    mutated = workflow.replace(
        f"  {job}:\n",
        f"  {job}:\n    if: ${{{{ false }}}}\n",
        1,
    )

    assert any(
        job in failure and "conditional" in failure
        for failure in audit_workflow(mutated)
    )


def test_workflow_policy_rejects_conditional_validation_step() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    mutated = workflow.replace(
        "      - name: Run one checked deterministic test shard\n"
        '        run: python scripts/run_test_shard.py "${{ matrix.shard }}"\n',
        "      - name: Run one checked deterministic test shard\n"
        "        if: ${{ false }}\n"
        '        run: python scripts/run_test_shard.py "${{ matrix.shard }}"\n',
        1,
    )

    assert mutated != workflow
    assert any(
        "python-tests" in failure and "conditional" in failure
        for failure in audit_workflow(mutated)
    )


@pytest.mark.parametrize(
    "insertion",
    (
        "    continue-on-error: true\n",
        "      - name: Run one checked deterministic test shard\n"
        "        continue-on-error: true\n"
        '        run: python scripts/run_test_shard.py "${{ matrix.shard }}"\n',
    ),
)
def test_workflow_policy_rejects_validation_continue_on_error(
    insertion: str,
) -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    if insertion.startswith("    continue"):
        mutated = workflow.replace(
            "  python-tests:\n",
            "  python-tests:\n" + insertion,
            1,
        )
    else:
        mutated = workflow.replace(
            "      - name: Run one checked deterministic test shard\n"
            '        run: python scripts/run_test_shard.py "${{ matrix.shard }}"\n',
            insertion,
            1,
        )

    assert mutated != workflow
    assert any(
        "python-tests" in failure and "continue-on-error" in failure
        for failure in audit_workflow(mutated)
    )


@pytest.mark.parametrize(
    ("current", "mutated_value"),
    (
        (
            '  SOURCE_DATE_EPOCH: "315532800"\n',
            '  SOURCE_DATE_EPOCH: "315532800"\n  PYTEST_ADDOPTS: --collect-only\n',
        ),
        (
            "  python-tests:\n",
            "  python-tests:\n    env:\n      PYTEST_ADDOPTS: --collect-only\n",
        ),
        (
            "      - name: Run one checked deterministic test shard\n"
            '        run: python scripts/run_test_shard.py "${{ matrix.shard }}"\n',
            "      - name: Run one checked deterministic test shard\n"
            "        env:\n"
            "          PATH: /tmp/forged\n"
            '        run: python scripts/run_test_shard.py "${{ matrix.shard }}"\n',
        ),
        (
            "\njobs:\n",
            "\ndefaults:\n"
            "  run:\n"
            "    working-directory: /tmp/stale-checkout\n"
            "\njobs:\n",
        ),
        (
            "\njobs:\n  python-tests:\n",
            "\njobs:\n"
            '  "shadow":\n'
            "    permissions: write-all\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: true\n"
            "  python-tests:\n",
        ),
        (
            "      - name: Run one checked deterministic test shard\n"
            '        run: python scripts/run_test_shard.py "${{ matrix.shard }}"\n',
            "      - name: Run one checked deterministic test shard\n"
            "        working-directory: /tmp/stale-checkout\n"
            '        run: python scripts/run_test_shard.py "${{ matrix.shard }}"\n',
        ),
        (
            "        with:\n          persist-credentials: false\n",
            "        with:\n"
            "          persist-credentials: false\n"
            "          ref: main\n",
        ),
        (
            "          python-version: ${{ matrix.python-version }}\n",
            '          python-version: "3.12"\n',
        ),
        (
            "    runs-on: ubuntu-latest\n",
            "    runs-on: self-hosted\n",
        ),
        (
            "  pull_request:\n",
            "  workflow_dispatch:\n",
        ),
    ),
)
def test_workflow_policy_binds_the_complete_execution_context(
    current: str,
    mutated_value: str,
) -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    mutated = workflow.replace(current, mutated_value, 1)

    failures = audit_workflow(mutated)

    assert mutated != workflow
    assert any("contract" in failure for failure in failures)


def test_workflow_policy_rejects_every_missing_semantic_command_marker() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    for job, markers in REQUIRED_VALIDATION_MARKERS.items():
        for marker in markers:
            mutated = _replace_in_job(workflow, job, marker, f"REMOVED-{job}")
            failures = audit_workflow(mutated)
            assert mutated != workflow, (job, marker)
            assert any(
                job in failure and "semantic command marker" in failure
                for failure in failures
            ), (job, marker, failures)


@pytest.mark.parametrize(
    ("current", "weakened", "forbidden"),
    (
        (
            "python -m ruff check pheroos scripts tests",
            "python -m ruff check --select E9,F63,F7,F82 pheroos scripts tests",
            "python -m ruff check --select",
        ),
        (
            "python -m mypy --no-incremental pheroos",
            (
                "python -m mypy --incremental --cache-dir .mypy_cache "
                "--follow-imports=skip --ignore-missing-imports "
                "pheroos/_scope.py"
            ),
            "python -m mypy --incremental",
        ),
    ),
)
def test_workflow_policy_rejects_narrow_or_import_skipping_static_gates(
    current: str,
    weakened: str,
    forbidden: str,
) -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    mutated = _replace_in_job(
        workflow,
        "lint-and-typing",
        current,
        weakened,
    )

    failures = audit_workflow(mutated)

    assert mutated != workflow
    assert forbidden in FORBIDDEN_VALIDATION_MARKERS["lint-and-typing"]
    assert any(
        "lint-and-typing" in failure
        and "forbidden weak command marker" in failure
        and forbidden in failure
        for failure in failures
    )


@pytest.mark.parametrize(
    "marker",
    (
        "python -m ruff format --check pheroos scripts tests",
        "python scripts/check_stable_typing.py --check",
    ),
)
def test_workflow_policy_rejects_omitted_format_or_stable_typing_gate(
    marker: str,
) -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    mutated = _replace_in_job(
        workflow,
        "lint-and-typing",
        marker,
        "REMOVED-FULL-STATIC-GATE",
    )

    failures = audit_workflow(mutated)

    assert mutated != workflow
    assert any(
        "lint-and-typing" in failure
        and "semantic command marker" in failure
        and marker in failure
        for failure in failures
    )


def test_workflow_policy_rejects_coverage_matrix_shard_omission() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    mutated = _replace_in_job(
        workflow,
        "coverage-measure",
        "          - governance-4\n",
        "",
    )

    assert mutated != workflow
    assert any(
        "coverage measurement matrix" in failure for failure in audit_workflow(mutated)
    )


def test_workflow_policy_rejects_python_test_matrix_shard_omission() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    mutated = _replace_in_job(
        workflow,
        "python-tests",
        "          - governance-4\n",
        "",
    )

    assert mutated != workflow
    assert any("Python test matrix" in failure for failure in audit_workflow(mutated))


def test_workflow_policy_rejects_python_version_matrix_omission() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    mutated = _replace_in_job(
        workflow,
        "python-tests",
        'python-version: ["3.12", "3.13", "3.14"]',
        'python-version: ["3.12", "3.14"]',
    )

    assert mutated != workflow
    assert any(
        "exact 3.12, 3.13, and 3.14" in failure for failure in audit_workflow(mutated)
    )


def test_workflow_policy_rejects_monolithic_coverage_gate() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    mutated = _replace_in_job(
        workflow,
        "coverage-gate",
        "python scripts/check_coverage_gate.py",
        (
            "python scripts/check_coverage_gate.py --measure "
            '--base-ref "$COVERAGE_BASE_REF"'
        ),
    )

    assert mutated != workflow
    assert any("must consume shards" in failure for failure in audit_workflow(mutated))


@pytest.mark.parametrize(
    ("job", "marker"),
    (
        (
            "schema-version-drift",
            "python scripts/check_legacy_authority_inventory.py --check",
        ),
        ("consumer-compat", "tests/examples/test_hybrid_replay_protocol.py"),
        (
            "authority-restart-atomicity",
            "tests/governance/test_hybrid_replay_v2_*.py",
        ),
        (
            "authority-restart-atomicity",
            ("test_hybrid_replay_v2_adversarial_support_uses_only_public_abi_proxies"),
        ),
        (
            "authority-restart-atomicity",
            "test_hybrid_replay_v2_resource_support_uses_only_public_constructors",
        ),
        (
            "authority-restart-atomicity",
            "tests/trace/test_hybrid_replay_v2_trace_contract.py",
        ),
        (
            "wheel-sdist-external-cwd",
            '"$PHEROOS" wire validate capability-v3',
        ),
        (
            "wheel-sdist-external-cwd",
            "examples/hybrid-replay-protocol/run.py",
        ),
    ),
)
def test_workflow_policy_fail_closes_wp05_hybrid_validation(
    job: str,
    marker: str,
) -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert marker in REQUIRED_VALIDATION_MARKERS[job]

    mutated = _replace_in_job(workflow, job, marker, "REMOVED-WP05-HYBRID")
    failures = audit_workflow(mutated)

    assert mutated != workflow
    assert any(
        job in failure and marker in failure and "semantic command marker" in failure
        for failure in failures
    )


@pytest.mark.parametrize(
    "replacement",
    (
        "run: true",
        'run: echo python scripts/run_test_shard.py "${{ matrix.shard }}"',
        'run: python scripts/run_test_shard.py "${{ matrix.shard }}" || true',
        'run: python scripts/run_test_shard.py "${{ matrix.shard }}" || echo ignored',
        "run: |\n          set +e\n          python scripts/run_test_shard.py policy",
        "run: |\n          python scripts/run_test_shard.py policy\n          exit 0",
        "run: |\n          if false; then\n"
        '            python scripts/run_test_shard.py "${{ matrix.shard }}"\n'
        "          fi",
        "run: |\n"
        '          if ! python scripts/run_test_shard.py "${{ matrix.shard }}"; '
        "then\n"
        "            :\n"
        "          fi",
        "run: |\n          gate() {\n"
        '            python scripts/run_test_shard.py "${{ matrix.shard }}"\n'
        "          }",
        "run: |\n          eval "
        "'python scripts/run_test_shard.py \"${{ matrix.shard }}\"'",
        'run: ! python scripts/run_test_shard.py "${{ matrix.shard }}"',
        'run: python scripts/run_test_shard.py "${{ matrix.shard }}" | true',
        'run: python scripts/run_test_shard.py "${{ matrix.shard }}" &',
        'run: python scripts/run_test_shard.py "${{ matrix.shard }}"\n'
        "        run: true",
        'shell: sh {0}\n        run: python scripts/run_test_shard.py "${{ matrix.shard }}"',
    ),
)
def test_workflow_policy_rejects_masked_or_empty_test_runs(
    replacement: str,
) -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    mutated = workflow.replace(
        'run: python scripts/run_test_shard.py "${{ matrix.shard }}"',
        replacement,
        1,
    )

    failures = audit_workflow(mutated)

    assert mutated != workflow
    assert any("python-tests" in failure for failure in failures)


def test_workflow_policy_rejects_validation_permission_escalation() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    mutated = workflow.replace(
        "  python-tests:\n",
        "  python-tests:\n    permissions: write-all\n",
        1,
    )

    assert any(
        "python-tests" in failure and "permissions" in failure
        for failure in audit_workflow(mutated)
    )


def test_workflow_policy_rejects_extra_provenance_write_permission() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    mutated = _replace_in_job(
        workflow,
        PROVENANCE_JOB,
        "      contents: read\n",
        "      contents: read\n      issues: write\n",
    )

    assert any(
        PROVENANCE_JOB in failure and "permissions" in failure
        for failure in audit_workflow(mutated)
    )


def test_workflow_policy_rejects_unhashed_network_install() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    mutated = workflow.replace(
        "pip install --require-hashes --only-binary=:all: "
        "-r requirements/ci-constraints.txt",
        "pip install build==1.3.0",
        1,
    )

    assert any("hashed lock" in failure for failure in audit_workflow(mutated))


def test_workflow_policy_rejects_persisted_checkout_credentials() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    mutated = workflow.replace(
        "persist-credentials: false",
        "persist-credentials: true",
        1,
    )

    assert any(
        "persist" in failure and "credentials" in failure
        for failure in audit_workflow(mutated)
    )


def test_workflow_policy_rejects_pull_request_target() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    mutated = workflow.replace(
        "  pull_request:\n", "  pull_request:\n  pull_request_target:\n", 1
    )

    assert any("pull_request_target" in failure for failure in audit_workflow(mutated))


def test_workflow_policy_rejects_provenance_on_pull_requests() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    mutated = workflow.replace(
        "github.event_name == 'push' &&",
        "(github.event_name == 'push' || github.event_name == 'pull_request') &&",
        1,
    )

    assert any(
        "canonical trusted main push" in failure for failure in audit_workflow(mutated)
    )
