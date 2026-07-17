#!/usr/bin/env python3
"""Generate or verify the checked Commit Integrity v1 JSON TCK.

The runtime conformance path never invokes this script.  It compares an
implementation against the checked golden artifact.  This developer command
replays the public reference ABI to make an intentional golden refresh
reviewable and reproducible.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Any

from pheroos.conformance.commit_tck import (
    COMMIT_TCK_VERSION,
    CommitTckVector,
    ReferenceCommitTckAdapter,
    _request_from_vector,
    _variant_vector,
)
from pheroos.conformance.profile import profile_for_manifest
from pheroos.protocol.manifest import capability_manifest_from_dict


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "pheroos" / "conformance" / "tck" / "commit-integrity-v1.json"
SPLIT_DIRECTORY = ROOT / "tests" / "fixtures" / "commit-integrity" / "v1"

TITLES = (
    "Positive evidence independence-group cap",
    "Counterevidence duplicate-group cap",
    "Unresolved critical counterevidence blocks commit",
    "Fake rebuttal without independent proof is rejected",
    "Low-weight domains do not inflate diversity",
    "Support clusters deduplicate principal identities",
    "Invalid support leases never count",
    "Same-cluster double lease exposes equivocation",
    "Non-monotonic risk bands invalidate the manifest",
    "Changed authority heads reject stale windows",
    "Hybrid attention cannot alter commit truth",
    "Single ready step remains pending",
    "Continuous stability window authorizes commit",
    "Gate, leader, step, and epoch changes reset windows",
    "Evidence growth preserves a continuous ready leader",
    "Ties never use candidate identifiers as authority",
    "Input permutations preserve canonical outputs",
    "Pending becomes terminal at the absolute deadline",
    "Deadline never lowers commit gates",
    "Declared no-commit terminal policy is honored",
    "Hard commit stops cannot be bypassed by fallback",
    "Commit, publish, and execute gates are isolated",
    "Stops are isolated by target",
    "Outcome certificates cannot impersonate commit certificates",
    "Any certificate or trace leaf mutation is rejected",
    "Replay is isolated by target, candidate, and epoch",
    "Distributed n and q satisfy Byzantine intersection",
    "Sub-quorum partitions cannot finalize",
    "One quorum prevents a conflicting minority final",
    "Conflicting final certificates freeze publication",
    "Finality unavailable terminates without commit",
    "Expired publication permission preserves historical commit",
    "Every terminal outcome remains deliverable",
    "Active assurance never downgrades missing proof inputs",
    "Active conformance checks cannot skip or report N/A",
    "Unknown critical extensions and versions fail closed",
    "Legacy quorum behavior remains byte-stable in projection",
    "Packaged TCK is complete and external-CWD independent",
)


def _load(path: str) -> dict[str, Any]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _profile(manifest: dict[str, Any]) -> str:
    return profile_for_manifest(
        capability_manifest_from_dict(manifest)
    ).version


def _empty_result() -> dict[str, Any]:
    return {
        "metrics": {},
        "roots": {},
        "progress": None,
        "outcome": None,
        "trace_sequence": [],
        "certificate": None,
        "failure_code": None,
    }


def _mutation(
    identifier: str,
    path: list[str | int],
    replacement: Any,
    *,
    authority_namespace: str = "isolated",
) -> dict[str, Any]:
    return {
        "id": identifier,
        "authority_namespace": authority_namespace,
        "path": path,
        "replacement": replacement,
        "expected": _empty_result(),
    }


def _permutation(
    identifier: str,
    path: list[str | int],
    order: str | list[int],
    *,
    authority_namespace: str = "shared",
) -> dict[str, Any]:
    return {
        "id": identifier,
        "authority_namespace": authority_namespace,
        "path": path,
        "order": order,
        "expected": _empty_result(),
    }


def _seed_vectors() -> list[CommitTckVector]:
    hybrid = _load("examples/hybrid-commit-protocol/capability.json")
    distributed = _load("examples/distributed-commit-protocol/capability.json")
    legacy = _load("examples/toy-protocol/capability.json")

    certified = deepcopy(hybrid)
    certified_policy = certified["protocol"]["collective_commit_policy"]
    certified_policy["assurance"] = "certified"
    certified_policy["certificate"].update(
        mode="portable",
        issuer_attestation_required=True,
        independent_verification_required=True,
    )

    non_monotonic = deepcopy(hybrid)
    non_monotonic["protocol"]["collective_commit_policy"]["risk_bands"][
        "MODERATE"
    ]["minimum_positive_evidence"] = 1

    unknown_critical = deepcopy(hybrid)
    unknown_critical["protocol"]["collective_commit_policy"][
        "x-critical.unrecognized"
    ] = {"enabled": True}

    advisory = deepcopy(hybrid)
    advisory["protocol"]["collective_commit_policy"]["terminal_outcome"][
        "deadline_outcome"
    ] = "advisory"

    terminal_variants = {
        key: {"manifest": deepcopy(hybrid), "profile": _profile(hybrid)}
        for key in (
            "evidence_commit",
            "safe_fallback",
            "blocked",
            "invalid",
            "safety_violation",
            "finality_unavailable",
        )
    }
    terminal_variants["advisory"] = {
        "manifest": advisory,
        "profile": _profile(advisory),
    }

    vectors: list[CommitTckVector] = []
    for matrix_case, title in enumerate(TITLES, start=1):
        if 27 <= matrix_case <= 31:
            manifest = distributed
        elif matrix_case in {25, 26}:
            manifest = certified
        elif matrix_case == 9:
            manifest = non_monotonic
        elif matrix_case == 36:
            manifest = unknown_critical
        elif matrix_case == 37:
            manifest = legacy
        else:
            manifest = hybrid

        inputs: dict[str, Any] = {"operation": "matrix_case"}
        mutations: list[dict[str, Any]] = []
        permutations: list[dict[str, Any]] = []
        if matrix_case == 9:
            mutations.append(
                _mutation(
                    "restore-monotonic-moderate-threshold",
                    [
                        "manifest",
                        "protocol",
                        "collective_commit_policy",
                        "risk_bands",
                        "MODERATE",
                        "minimum_positive_evidence",
                    ],
                    2_500_000,
                )
            )
        elif matrix_case == 11:
            inputs["attention_candidate"] = "candidate:beta"
            mutations.append(
                _mutation(
                    "redirect-attention-to-commit-leader",
                    ["inputs", "attention_candidate"],
                    "candidate:alpha",
                    authority_namespace="shared",
                )
            )
        elif matrix_case == 17:
            inputs["candidate_order"] = [0, 1]
            permutations.append(
                _permutation(
                    "reverse-candidate-order",
                    ["inputs", "candidate_order"],
                    "reverse",
                )
            )
        elif matrix_case == 20:
            mutations.append(
                _mutation(
                    "declared-advisory-deadline",
                    [
                        "manifest",
                        "protocol",
                        "collective_commit_policy",
                        "terminal_outcome",
                        "deadline_outcome",
                    ],
                    "advisory",
                )
            )
        elif matrix_case == 25:
            inputs.update(
                certificate_mutation_path=[],
                trace_mutation_path=[],
            )
            mutations.extend(
                (
                    _mutation(
                        "mutate-certificate-candidate-leaf",
                        ["inputs", "certificate_mutation_path"],
                        ["candidate_id"],
                    ),
                    _mutation(
                        "mutate-trace-record-root-leaf",
                        ["inputs", "trace_mutation_path"],
                        ["record_ref"],
                    ),
                )
            )
        elif matrix_case == 33:
            inputs["terminal_variants"] = terminal_variants
        elif matrix_case == 34:
            inputs["evaluation_mutation_field"] = ""
            mutations.append(
                _mutation(
                    "mutate-embedded-evaluation-root",
                    ["inputs", "evaluation_mutation_field"],
                    "evaluation_root",
                    authority_namespace="shared",
                )
            )
        elif matrix_case == 36:
            mutations.append(
                _mutation(
                    "unknown-commit-policy-version",
                    [
                        "manifest",
                        "protocol",
                        "collective_commit_policy",
                        "policy_version",
                    ],
                    "pheroos-collective-commit-policy-v999",
                )
            )
        elif matrix_case == 37:
            inputs.update(
                candidate_id="candidate:accept",
                source_id="agent:tck:legacy",
            )

        vectors.append(
            CommitTckVector(
                id=f"commit-integrity-v1-case-{matrix_case:02d}",
                tck_version=COMMIT_TCK_VERSION,
                matrix_case=matrix_case,
                title=title,
                manifest=deepcopy(manifest),
                profile=(
                    _profile(hybrid)
                    if matrix_case == 36
                    else _profile(manifest)
                ),
                prior_authoritative_state={
                    "kind": "declared-empty-authority-head",
                    "revision": 0,
                },
                inputs=inputs,
                expected=_empty_result(),
                mutations=tuple(mutations),
                permutations=tuple(permutations),
            )
        )
    return vectors


def _evaluate_exact(
    adapter: ReferenceCommitTckAdapter,
    vector: CommitTckVector,
) -> dict[str, Any]:
    first = dict(adapter.evaluate(_request_from_vector(vector)))
    repeated = dict(adapter.evaluate(_request_from_vector(vector)))
    if repeated != first:
        raise RuntimeError(f"non-repeatable TCK probe: {vector.id}")
    return first


def _materialize(
    vectors: list[CommitTckVector],
    *,
    include_case_38: bool,
) -> list[CommitTckVector]:
    adapter = ReferenceCommitTckAdapter()
    materialized: list[CommitTckVector] = []
    for seed in vectors:
        if seed.matrix_case == 38 and not include_case_38:
            materialized.append(seed)
            continue
        base_expected = _evaluate_exact(adapter, seed)
        base = replace(seed, expected=base_expected)
        mutations: list[dict[str, Any]] = []
        for specification in base.mutations:
            normalized = deepcopy(specification)
            variant = _variant_vector(base, normalized, permutation=False)
            normalized["expected"] = _evaluate_exact(adapter, variant)
            mutations.append(normalized)
        permutations: list[dict[str, Any]] = []
        for specification in base.permutations:
            normalized = deepcopy(specification)
            variant = _variant_vector(base, normalized, permutation=True)
            normalized["expected"] = _evaluate_exact(adapter, variant)
            permutations.append(normalized)
        materialized.append(
            replace(
                base,
                mutations=tuple(mutations),
                permutations=tuple(permutations),
            )
        )
    return materialized


def _vector_payload(vector: CommitTckVector) -> dict[str, Any]:
    return {
        "id": vector.id,
        "tck_version": vector.tck_version,
        "matrix_case": vector.matrix_case,
        "title": vector.title,
        "manifest": deepcopy(vector.manifest),
        "profile": vector.profile,
        "prior_authoritative_state": deepcopy(vector.prior_authoritative_state),
        "inputs": deepcopy(vector.inputs),
        "expected": deepcopy(vector.expected),
        "mutations": deepcopy(list(vector.mutations)),
        "permutations": deepcopy(list(vector.permutations)),
    }


def _artifact_payload(vectors: list[CommitTckVector]) -> dict[str, Any]:
    return {
        "tck_version": COMMIT_TCK_VERSION,
        "vectors": [_vector_payload(vector) for vector in vectors],
    }


def _render(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=False,
    ) + "\n"


def _write_outputs(vectors: list[CommitTckVector]) -> None:
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    SPLIT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(_render(_artifact_payload(vectors)), encoding="utf-8")
    expected_names = set()
    for vector in vectors:
        name = f"case-{vector.matrix_case:02d}.json"
        expected_names.add(name)
        (SPLIT_DIRECTORY / name).write_text(
            _render(_vector_payload(vector)),
            encoding="utf-8",
        )
    for existing in SPLIT_DIRECTORY.glob("case-*.json"):
        if existing.name not in expected_names:
            existing.unlink()


def _checked_outputs_match(vectors: list[CommitTckVector]) -> bool:
    if not ARTIFACT.is_file():
        return False
    if ARTIFACT.read_text(encoding="utf-8") != _render(
        _artifact_payload(vectors)
    ):
        return False
    expected_names = {f"case-{case:02d}.json" for case in range(1, 39)}
    observed_names = {item.name for item in SPLIT_DIRECTORY.glob("case-*.json")}
    if observed_names != expected_names:
        return False
    return all(
        (SPLIT_DIRECTORY / f"case-{vector.matrix_case:02d}.json").read_text(
            encoding="utf-8"
        )
        == _render(_vector_payload(vector))
        for vector in vectors
    )


def _generate_for_write() -> list[CommitTckVector]:
    seeds = _seed_vectors()
    first_pass = _materialize(seeds, include_case_38=False)
    prior = ARTIFACT.read_bytes() if ARTIFACT.is_file() else None
    try:
        # Case 38 intentionally probes the packaged aggregate.  Install a
        # complete provisional index, then obtain its real resource/external-
        # CWD projection through the same public adapter as every consumer.
        ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT.write_text(
            _render(_artifact_payload(first_pass)),
            encoding="utf-8",
        )
        case_38 = _materialize(
            [first_pass[-1]],
            include_case_38=True,
        )[0]
        final = [*first_pass[:-1], case_38]
        _write_outputs(final)
        return final
    except Exception:
        if prior is None:
            ARTIFACT.unlink(missing_ok=True)
        else:
            ARTIFACT.write_bytes(prior)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)

    if arguments.write:
        vectors = _generate_for_write()
        print(f"wrote {len(vectors)} Commit TCK vectors")
        return 0

    if not ARTIFACT.is_file():
        print(f"missing Commit TCK artifact: {ARTIFACT}", file=sys.stderr)
        return 1
    vectors = _materialize(_seed_vectors(), include_case_38=True)
    if not _checked_outputs_match(vectors):
        print("checked Commit TCK artifacts are stale", file=sys.stderr)
        return 1
    print(f"verified {len(vectors)} Commit TCK vectors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
