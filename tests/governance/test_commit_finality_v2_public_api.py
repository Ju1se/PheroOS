from __future__ import annotations

from hashlib import sha256
import inspect
from itertools import permutations
import pickle
from pathlib import Path
import subprocess
import sys

import pytest

import pheroos.governance.commit_decision_v2 as decision_api
import pheroos.governance.commit_finality_v2 as api


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_PUBLIC = frozenset(
    {
        "COMMIT_FINALITY_INPUT_SCHEMA_V2",
        "COMMIT_FINALITY_PROJECTION_SCHEMA_V2",
        "CommitFinalityOwnerV2",
        "CommitFinalityProjectionV2",
        "CommitFinalityStatusV2",
        "VerifiedCommitFinalityInputV2",
        "commit_finality_owner_genesis_snapshot_root_v2",
        "commit_finality_owner_stream_ref_v2",
    }
)
PUBLIC_OBJECTS = (
    "CommitFinalityOwnerV2",
    "CommitFinalityProjectionV2",
    "CommitFinalityStatusV2",
    "VerifiedCommitFinalityInputV2",
    "commit_finality_owner_genesis_snapshot_root_v2",
    "commit_finality_owner_stream_ref_v2",
)
OWNER_MODULES = (
    "pheroos.governance.commit_certificate_v2",
    "pheroos.governance.commit_decision_v2",
    "pheroos.governance.distributed_commit_v2",
)


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def test_commit_finality_v2_is_the_exact_neutral_public_identity_owner() -> None:
    assert frozenset(api.__all__) == EXPECTED_PUBLIC
    assert len(api.__all__) == len(EXPECTED_PUBLIC)
    for name in PUBLIC_OBJECTS:
        value = getattr(api, name)
        assert inspect.isclass(value) or inspect.isfunction(value)
        assert value.__module__ == "pheroos.governance.commit_finality_v2"
    for forbidden in (
        "_CommitFinalityInputMaterialV2",
        "_FINALITY_INPUT_TOKEN_V2",
        "_issue_verified_commit_finality_input_v2",
        "_verified_commit_finality_input_material_v2",
    ):
        assert forbidden not in api.__all__
        assert not hasattr(api, forbidden)


def test_finality_facade_does_not_load_an_owner_facade() -> None:
    script = """
import json
import sys

import pheroos.governance.commit_finality_v2

owners = (
    "pheroos.governance.commit_certificate_v2",
    "pheroos.governance.commit_decision_v2",
    "pheroos.governance.distributed_commit_v2",
)
print(json.dumps({name: name in sys.modules for name in owners}, sort_keys=True))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == (
        '{"pheroos.governance.commit_certificate_v2": false, '
        '"pheroos.governance.commit_decision_v2": false, '
        '"pheroos.governance.distributed_commit_v2": false}'
    )


def test_all_owner_facade_import_orders_preserve_canonical_identity() -> None:
    for order in permutations(OWNER_MODULES):
        script = f"""
import importlib
import inspect

order = {order!r}
loaded = {{name: importlib.import_module(name) for name in order}}
finality = importlib.import_module("pheroos.governance.commit_finality_v2")
decision = loaded["pheroos.governance.commit_decision_v2"]
certificate = loaded["pheroos.governance.commit_certificate_v2"]
distributed = loaded["pheroos.governance.distributed_commit_v2"]
names = {PUBLIC_OBJECTS!r}
for name in names:
    canonical = getattr(finality, name)
    assert canonical.__module__ == "pheroos.governance.commit_finality_v2"
    assert getattr(decision, name) is canonical
assert inspect.signature(
    certificate.verified_commit_certificate_finality_input_v2
).return_annotation is finality.VerifiedCommitFinalityInputV2
assert inspect.signature(
    distributed.verified_distributed_commit_finality_input_v2
).return_annotation is finality.VerifiedCommitFinalityInputV2
"""
        subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )


def test_decision_aliases_and_legacy_pickle_globals_resolve_canonical_objects() -> None:
    for name in PUBLIC_OBJECTS:
        canonical = getattr(api, name)
        assert getattr(decision_api, name) is canonical
        legacy_global = (
            "cpheroos.governance.commit_decision_v2\n" + name + "\n."
        ).encode("ascii")
        assert pickle.loads(legacy_global) is canonical

    projection = api.CommitFinalityProjectionV2(
        owner=api.CommitFinalityOwnerV2.CERTIFICATE,
        status=api.CommitFinalityStatusV2.VERIFIED,
        stream_ref="authority:certificate:pickle",
        revision=1,
        transition_id="transition:certificate:pickle",
        snapshot_root=_root("snapshot"),
        head_root=_root("head"),
        receipt_root=_root("receipt"),
        seal_transition_id="transition:decision:seal",
        seal_root=_root("seal"),
        frozen_dependency_root=_root("dependencies"),
        verified_at_step=10,
        reason_codes=("certificate_verified",),
    )
    restored = pickle.loads(pickle.dumps(projection))
    assert type(restored) is api.CommitFinalityProjectionV2
    assert restored.to_dict() == projection.to_dict()


def test_neutral_facade_exposes_the_opaque_type_but_no_construction_path() -> None:
    with pytest.raises(TypeError, match="cannot be constructed"):
        api.VerifiedCommitFinalityInputV2()
