from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from pheroos.protocol import (
    CommitWireError,
    canonical_commit_payload,
    commit_payload_fingerprint,
)


PAYLOAD = {"alpha": 1, "items": ["x", "y"], "ready": True}
SCHEMA = "pheroos-tck-vector-v1"
PROFILE = "pheroos-commit-integrity-v1"
EXPECTED_ROOT = "sha256:16071f8a1e64bbaef6488b366c6e917f4fbb34dfd1d38e14b6991214777e1d6b"


def test_canonical_wire_has_exact_golden_bytes_and_root() -> None:
    encoded = canonical_commit_payload(PAYLOAD, schema=SCHEMA, profile=PROFILE)

    assert encoded == (
        '{"payload":{"alpha":1,"items":["x","y"],"ready":true},'
        '"profile":"pheroos-commit-integrity-v1",'
        '"schema":"pheroos-tck-vector-v1",'
        '"version":"pheroos-commit-wire-v1"}'
    )
    assert commit_payload_fingerprint(
        PAYLOAD,
        schema=SCHEMA,
        profile=PROFILE,
    ) == EXPECTED_ROOT


def test_canonical_root_is_independent_of_cwd_hash_seed_and_mapping_order(
    tmp_path: Path,
) -> None:
    code = """
from pheroos.protocol import commit_payload_fingerprint
payload = dict([('ready', True), ('items', ['x', 'y']), ('alpha', 1)])
print(commit_payload_fingerprint(payload, schema='pheroos-tck-vector-v1', profile='pheroos-commit-integrity-v1'))
"""
    observed: list[str] = []
    for seed in ("1", "8675309"):
        environment = dict(os.environ)
        environment["PYTHONHASHSEED"] = seed
        observed.append(
            subprocess.check_output(
                [sys.executable, "-c", code],
                cwd=tmp_path,
                env=environment,
                text=True,
            ).strip()
        )

    assert observed == [EXPECTED_ROOT, EXPECTED_ROOT]


@pytest.mark.parametrize(
    "payload",
    [
        {"value": 1.0},
        {"value": float("nan")},
        {" value": 1},
        {"value": "de\u0301composed"},
    ],
)
def test_canonical_wire_rejects_nonportable_values(payload: dict[str, object]) -> None:
    with pytest.raises(CommitWireError):
        canonical_commit_payload(payload, schema=SCHEMA, profile=PROFILE)


def test_canonical_wire_preserves_ordered_arrays() -> None:
    first = json.loads(
        canonical_commit_payload(
            {"ordered": ["a", "b"]},
            schema=SCHEMA,
            profile=PROFILE,
        )
    )
    second = json.loads(
        canonical_commit_payload(
            {"ordered": ["b", "a"]},
            schema=SCHEMA,
            profile=PROFILE,
        )
    )

    assert first["payload"] != second["payload"]
