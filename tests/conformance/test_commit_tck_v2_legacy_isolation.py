from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import itertools
import json
from pathlib import Path
import pickle
import subprocess
import sys

import pytest

from pheroos.conformance.commit_tck_v2 import (
    CommitTckV2ProtocolError,
    PheroosPublicCommitTckV2Adapter,
    _mutate_json_leaf,
    _scalar_leaf_paths,
    load_commit_tck_v2_cases,
    run_commit_tck_v2,
)
from pheroos.conformance.commit_tck_v2_spec_adapter import (
    IndependentCommitSpecModelAdapter,
)
from pheroos.governance.commit_semantics import select_terminal_outcome_kind
from pheroos.governance.historical_certificate import (
    verify_evidence_commit_certificate,
)


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_MODULE = "pheroos.governance._legacy.authority_registry"
TERMINAL_PREDECESSOR_ROOT = (
    "fc200be7d5331e0ff4b58eec68fd659c78d206f3e96d54668c0bafa0a2aa6585"
)
CERTIFICATE_PREDECESSOR_ROOT = (
    "a052e6f7242c0a8ed335e3a37ca9e1378200b11c0fa460f9e9c6056ec4cf418e"
)


def _isolated_python() -> str:
    local = ROOT / ".venv" / "bin" / "python"
    return str(local) if local.is_file() else sys.executable


def test_registry_free_leaves_preserve_legacy_object_and_pickle_identity() -> None:
    from pheroos.governance.certificate import (
        verify_evidence_commit_certificate as legacy_verify,
    )
    from pheroos.governance.commit_state import (
        select_terminal_outcome_kind as legacy_select,
    )

    assert select_terminal_outcome_kind is legacy_select
    assert verify_evidence_commit_certificate is legacy_verify
    assert select_terminal_outcome_kind.__module__ == (
        "pheroos.governance.commit_state"
    )
    assert verify_evidence_commit_certificate.__module__ == (
        "pheroos.governance.certificate"
    )
    assert pickle.loads(pickle.dumps(select_terminal_outcome_kind)) is legacy_select
    assert (
        pickle.loads(pickle.dumps(verify_evidence_commit_certificate)) is legacy_verify
    )


def test_terminal_selector_preserves_the_exhaustive_predecessor_matrix() -> None:
    fields = (
        "invalid",
        "safety_violation",
        "blocked",
        "evidence_commit_ready",
        "finality_unavailable",
        "deadline_reached",
    )
    rows: list[dict[str, object]] = []
    for deadline_outcome in ("safe_fallback", "advisory"):
        for conditions in itertools.product((False, True), repeat=len(fields)):
            selected = select_terminal_outcome_kind(
                **dict(zip(fields, conditions, strict=True)),
                deadline_outcome=deadline_outcome,
            )
            rows.append(
                {
                    "conditions": list(conditions),
                    "deadline_outcome": deadline_outcome,
                    "result": selected.value if selected is not None else None,
                }
            )

    encoded = json.dumps(rows, separators=(",", ":"), sort_keys=True).encode()

    assert len(rows) == 128
    assert sha256(encoded).hexdigest() == TERMINAL_PREDECESSOR_ROOT


def test_historical_reader_preserves_every_frozen_certificate_leaf_result() -> None:
    selected = next(
        case
        for case in load_commit_tck_v2_cases()
        if case.request.inputs["operation"] == "certificate_leaf_binding"
    )
    payload = deepcopy(selected.request.inputs["certificate_payload"])
    trusted = selected.request.inputs["trusted_issuer_attestations"]
    assert isinstance(payload, dict)
    assert isinstance(trusted, dict)
    rows: list[list[object]] = [
        [
            "base",
            verify_evidence_commit_certificate(
                payload,
                trusted_issuer_attestations=trusted,
            ),
        ]
    ]
    for path in _scalar_leaf_paths(payload):
        mutated = deepcopy(payload)
        _mutate_json_leaf(mutated, path)
        rows.append(
            [
                list(path),
                verify_evidence_commit_certificate(
                    mutated,
                    trusted_issuer_attestations=trusted,
                ),
            ]
        )

    encoded = json.dumps(rows, separators=(",", ":"), sort_keys=True).encode()

    assert len(rows) == 52
    assert sum(bool(row[1]) for row in rows) == 1
    assert sha256(encoded).hexdigest() == CERTIFICATE_PREDECESSOR_ROOT


def test_mutation_helper_rejects_a_container_selected_as_a_leaf() -> None:
    with pytest.raises(CommitTckV2ProtocolError, match="selected a container"):
        _mutate_json_leaf({"nested": {"value": 1}}, ("nested",))


def test_clean_subject_matches_all_frozen_cases_and_independent_oracle() -> None:
    cases = load_commit_tck_v2_cases()
    subject = run_commit_tck_v2(cases, adapter=PheroosPublicCommitTckV2Adapter())
    oracle = run_commit_tck_v2(
        cases,
        adapter=IndependentCommitSpecModelAdapter(),
    )

    assert subject.ok is True
    assert oracle.ok is True
    assert [result.actual for result in subject.results] == [
        result.expected for result in cases
    ]
    assert [result.actual for result in subject.results] == [
        result.actual for result in oracle.results
    ]


@pytest.mark.parametrize(
    "operation",
    ("manifest_deadline_outcome", "certificate_leaf_binding"),
)
def test_fresh_process_operation_never_initializes_legacy_registry(
    operation: str,
    tmp_path: Path,
) -> None:
    script = f"""
import sys

REGISTRY_MODULE = {REGISTRY_MODULE!r}

def cardinality():
    registry_module = sys.modules.get(REGISTRY_MODULE)
    if registry_module is None:
        return 0
    return registry_module.LEGACY_AUTHORITY_REGISTRY.total_record_count()

before = cardinality()
from pheroos.conformance.commit_tck_v2 import (
    PheroosPublicCommitTckV2Adapter,
    load_commit_tck_v2_cases,
)
after_import = cardinality()
assert REGISTRY_MODULE not in sys.modules
case = next(
    item
    for item in load_commit_tck_v2_cases()
    if item.request.inputs["operation"] == {operation!r}
)
response = PheroosPublicCommitTckV2Adapter().evaluate(case.request)
after_evaluation = cardinality()
assert response.actual == case.expected
assert REGISTRY_MODULE not in sys.modules
assert before == after_import == after_evaluation == 0
"""

    completed = subprocess.run(
        [_isolated_python(), "-I", "-B", "-c", script],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
