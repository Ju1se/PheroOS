from __future__ import annotations

from hashlib import sha256
from importlib import import_module
from inspect import signature
import json
import os
from pathlib import Path
import pickle
import subprocess
import sys

from pheroos.governance import (
    AuthorityDomain,
    GovernanceCommitBatch,
    GovernanceCommitReceipt,
    GovernanceHead,
    GovernanceStateStore,
    InMemoryGovernanceStateStore,
    PreparedGovernanceTransition,
)


ROOT = Path(__file__).resolve().parents[2]
SCOPE_REF = "sha256:0614cdfc724c6129d3766c84f133ebf22333382aaeb1b1d08a03e3098a7fa662"
STREAM = "authority:decision"
TRANSITION_ID = "transition:v1:001"

DOMAIN_WIRE = (
    b'{"schema":"pheroos-authority-domain-v1",'
    b'"scope_ref":"sha256:0614cdfc724c6129d3766c84f133ebf22333382aaeb1b1d08a03e3098a7fa662"}'
)
HEAD_WIRE = (
    b'{"parent_root":"sha256:4f4ef5d47a3e66397cb9220e6177de6373bc51fb10d9619bd4176fb1b114c203",'
    b'"revision":0,"schema":"pheroos-governance-head-v1",'
    b'"scope_ref":"sha256:0614cdfc724c6129d3766c84f133ebf22333382aaeb1b1d08a03e3098a7fa662",'
    b'"state_root":"sha256:4f4ef5d47a3e66397cb9220e6177de6373bc51fb10d9619bd4176fb1b114c203",'
    b'"stream":"authority:decision","transition_id":"genesis"}'
)
TRANSITION_WIRE = (
    b'{"domain":{"schema":"pheroos-authority-domain-v1",'
    b'"scope_ref":"sha256:0614cdfc724c6129d3766c84f133ebf22333382aaeb1b1d08a03e3098a7fa662"},'
    b'"expected_parent_root":"sha256:4f4ef5d47a3e66397cb9220e6177de6373bc51fb10d9619bd4176fb1b114c203",'
    b'"expected_revision":0,'
    b'"expected_state_root":"sha256:4f4ef5d47a3e66397cb9220e6177de6373bc51fb10d9619bd4176fb1b114c203",'
    b'"identity_claims":{"claim:reviewer":{"principal":"agent:reviewer",'
    b'"roles":["reviewer","auditor"]}},'
    b'"schema":"pheroos-prepared-governance-transition-v1",'
    b'"scope_ref":"sha256:0614cdfc724c6129d3766c84f133ebf22333382aaeb1b1d08a03e3098a7fa662",'
    b'"state_records":{"decision":{"candidate":"candidate:a","score":7},'
    b'"unicode":"\\u8702\\u7fa4"},'
    b'"state_root":"sha256:58f0a6d589fcba8a52be85e0cbd5300263b2aa1326bd0d96268badecb612c109",'
    b'"stream":"authority:decision","transition_id":"transition:v1:001"}'
)
BATCH_WIRE = (
    b'{"batch_root":"sha256:084bfea59821e0b2dfc476fddc826d599f176c09757fec7274ae31b10bd4ff26",'
    b'"schema":"pheroos-governance-commit-batch-v1","trace_records":'
    b'[{"event":"decision_committed",'
    b'"scope_ref":"sha256:0614cdfc724c6129d3766c84f133ebf22333382aaeb1b1d08a03e3098a7fa662",'
    b'"stream":"authority:decision","trace_id":"trace:v1:001",'
    b'"transition_id":"transition:v1:001",'
    b'"value":{"approved":true,"candidate":"candidate:a"}}],'
    b'"trace_root":"sha256:2ff0164e0953c243b84e84756f6e3442ce9d5f6f424e42ed8c94d83e4679a5ea",'
    b'"transition":' + TRANSITION_WIRE + b"}"
)
RECEIPT_WIRE = (
    b'{"batch_root":"sha256:084bfea59821e0b2dfc476fddc826d599f176c09757fec7274ae31b10bd4ff26",'
    b'"parent_root":"sha256:4f4ef5d47a3e66397cb9220e6177de6373bc51fb10d9619bd4176fb1b114c203",'
    b'"receipt_root":"sha256:afe66a9892198875653bb7b9858de6f0339e29c64d9c0eed4969573b844423c9",'
    b'"revision":1,"schema":"pheroos-governance-commit-receipt-v1",'
    b'"scope_ref":"sha256:0614cdfc724c6129d3766c84f133ebf22333382aaeb1b1d08a03e3098a7fa662",'
    b'"state_root":"sha256:58f0a6d589fcba8a52be85e0cbd5300263b2aa1326bd0d96268badecb612c109",'
    b'"stream":"authority:decision",'
    b'"trace_root":"sha256:2ff0164e0953c243b84e84756f6e3442ce9d5f6f424e42ed8c94d83e4679a5ea",'
    b'"transition_id":"transition:v1:001"}'
)

DOMAIN_ROOT = "sha256:be77935f4e11334a80c1dda53c74880f18486b57bb9a7cd2963226ebe705921a"
HEAD_ROOT = "sha256:3f0cae331661fbfb1da96524b1a97036a4e2a26f8f271e346730c45da7a3b883"
STATE_ROOT = "sha256:58f0a6d589fcba8a52be85e0cbd5300263b2aa1326bd0d96268badecb612c109"
TRANSITION_ROOT = (
    "sha256:d0e732b527f76c818f1a1bdc65659148422aebf90c9a9392ac3831232a9314a2"
)
TRACE_ROOT = "sha256:2ff0164e0953c243b84e84756f6e3442ce9d5f6f424e42ed8c94d83e4679a5ea"
BATCH_ROOT = "sha256:084bfea59821e0b2dfc476fddc826d599f176c09757fec7274ae31b10bd4ff26"
RECEIPT_ROOT = "sha256:afe66a9892198875653bb7b9858de6f0339e29c64d9c0eed4969573b844423c9"
CHECKPOINT_ROOT = (
    "sha256:f017f3ab823f1e70f3e42c44c9010564f30b05771f95813ed6bc5e95790f7c44"
)
SNAPSHOT_ROOT = (
    "sha256:c6ba840c273fb55196b3a566efd74c706e56112ca8afc6ca7dd80dd716e167d5"
)


def _canonical_v1_wire(payload: object) -> bytes:
    """Encode the historical v1 portable wire without importing private owners."""

    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _fixture() -> tuple[
    AuthorityDomain,
    GovernanceHead,
    PreparedGovernanceTransition,
    GovernanceCommitBatch,
]:
    domain = AuthorityDomain(SCOPE_REF)
    head = GovernanceHead.genesis(SCOPE_REF, STREAM)
    transition = PreparedGovernanceTransition.from_head(
        head,
        transition_id=TRANSITION_ID,
        state_records={
            "unicode": "蜂群",
            "decision": {"score": 7, "candidate": "candidate:a"},
        },
        identity_claims={
            "claim:reviewer": {
                "roles": ["reviewer", "auditor"],
                "principal": "agent:reviewer",
            }
        },
    )
    batch = GovernanceCommitBatch(
        transition,
        [
            {
                "value": {"approved": True, "candidate": "candidate:a"},
                "transition_id": TRANSITION_ID,
                "stream": STREAM,
                "scope_ref": SCOPE_REF,
                "trace_id": "trace:v1:001",
                "event": "decision_committed",
            }
        ],
    )
    return domain, head, transition, batch


def test_v1_authority_fixture_keeps_exact_canonical_bytes_and_roots() -> None:
    domain, head, transition, batch = _fixture()
    store = InMemoryGovernanceStateStore()
    receipt = store.atomic_commit(batch)

    assert (
        SCOPE_REF
        == "sha256:" + sha256(b"pheroos-wp02-v1-differential-scope").hexdigest()
    )
    assert isinstance(receipt, GovernanceCommitReceipt)
    assert _canonical_v1_wire(domain.to_dict()) == DOMAIN_WIRE
    assert _canonical_v1_wire(head.to_dict()) == HEAD_WIRE
    assert _canonical_v1_wire(transition.to_dict()) == TRANSITION_WIRE
    assert _canonical_v1_wire(batch.to_dict()) == BATCH_WIRE
    assert _canonical_v1_wire(receipt.to_dict()) == RECEIPT_WIRE

    assert domain.fingerprint() == DOMAIN_ROOT
    assert head.fingerprint() == HEAD_ROOT
    assert transition.state_root == STATE_ROOT
    assert transition.fingerprint() == TRANSITION_ROOT
    assert batch.trace_root == TRACE_ROOT
    assert batch.batch_root == batch.fingerprint() == BATCH_ROOT
    assert receipt.receipt_root == receipt.fingerprint() == RECEIPT_ROOT


def test_v1_store_behavior_and_restart_roots_are_unchanged() -> None:
    _domain, genesis, _transition, batch = _fixture()
    store = InMemoryGovernanceStateStore()

    first = store.atomic_commit(batch)
    retry = store.atomic_commit(GovernanceCommitBatch.from_dict(batch.to_dict()))

    assert retry == first
    assert retry is not first
    assert first.matches(batch) is True
    assert store.load_head(SCOPE_REF, STREAM) == GovernanceHead(
        scope_ref=SCOPE_REF,
        stream=STREAM,
        revision=1,
        parent_root=genesis.state_root,
        state_root=STATE_ROOT,
        transition_id=TRANSITION_ID,
    )
    assert store.load_state(SCOPE_REF, STREAM) == {
        "decision": {"candidate": "candidate:a", "score": 7},
        "unicode": "蜂群",
    }
    assert store.trace_records(SCOPE_REF, STREAM) == batch.trace_records
    assert store.load_receipt(SCOPE_REF, TRANSITION_ID) == first
    assert len(store.trace_records(SCOPE_REF, STREAM)) == 1
    assert store.checkpoint(SCOPE_REF)["checkpoint_root"] == CHECKPOINT_ROOT
    assert store.snapshot()["snapshot_root"] == SNAPSHOT_ROOT
    assert store.fingerprint() == SNAPSHOT_ROOT

    checkpoint_restart = InMemoryGovernanceStateStore.from_checkpoint(
        json.loads(json.dumps(store.checkpoint(SCOPE_REF)))
    )
    snapshot_restart = InMemoryGovernanceStateStore.from_snapshot(
        json.loads(json.dumps(store.snapshot()))
    )
    assert checkpoint_restart.fingerprint() == SNAPSHOT_ROOT
    assert snapshot_restart.fingerprint() == SNAPSHOT_ROOT
    assert snapshot_restart.load_receipt(SCOPE_REF, TRANSITION_ID) == first


def test_v1_public_and_pickle_identities_remain_canonical() -> None:
    owner = import_module("pheroos.governance.authority_domain")
    ledger = import_module("pheroos.governance._authority.ledger")
    facade = import_module("pheroos.governance")
    public_names = (
        "AuthorityDomain",
        "GovernanceHead",
        "PreparedGovernanceTransition",
        "GovernanceCommitBatch",
        "GovernanceCommitReceipt",
        "GovernanceStateStore",
    )

    for name in public_names:
        canonical = getattr(owner, name)
        assert getattr(facade, name) is canonical
        assert pickle.loads(pickle.dumps(canonical)) is canonical
    assert facade.InMemoryGovernanceStateStore is ledger.InMemoryGovernanceStateStore
    assert pickle.loads(pickle.dumps(InMemoryGovernanceStateStore)) is (
        InMemoryGovernanceStateStore
    )

    _domain, head, _transition, batch = _fixture()
    receipt = InMemoryGovernanceStateStore().atomic_commit(batch)
    for value in (AuthorityDomain(SCOPE_REF), head, receipt):
        restored = pickle.loads(pickle.dumps(value))
        assert restored == value
        assert type(restored) is type(value)


def test_cold_v2_import_does_not_mutate_v1_contract_or_serialization() -> None:
    source = r"""
from importlib import import_module
from inspect import signature
from hashlib import sha256
import json
import pickle
import sys

import pheroos.governance as facade
from pheroos.governance import (
    AuthorityDomain,
    GovernanceCommitBatch,
    GovernanceCommitReceipt,
    GovernanceHead,
    GovernanceStateStore,
    InMemoryGovernanceStateStore,
    PreparedGovernanceTransition,
)

scope_ref = "sha256:" + sha256(
    b"pheroos-wp02-v1-differential-scope"
).hexdigest()

def fixture_wire():
    head = GovernanceHead.genesis(scope_ref, "authority:decision")
    transition = PreparedGovernanceTransition.from_head(
        head,
        transition_id="transition:v1:001",
        state_records={
            "unicode": "蜂群",
            "decision": {"score": 7, "candidate": "candidate:a"},
        },
        identity_claims={
            "claim:reviewer": {
                "roles": ["reviewer", "auditor"],
                "principal": "agent:reviewer",
            }
        },
    )
    batch = GovernanceCommitBatch(
        transition,
        [{
            "value": {"approved": True, "candidate": "candidate:a"},
            "transition_id": "transition:v1:001",
            "stream": "authority:decision",
            "scope_ref": scope_ref,
            "trace_id": "trace:v1:001",
            "event": "decision_committed",
        }],
    )
    store = InMemoryGovernanceStateStore()
    receipt = store.atomic_commit(batch)
    payload = {
        "domain": AuthorityDomain(scope_ref).to_dict(),
        "head": head.to_dict(),
        "transition": transition.to_dict(),
        "batch": batch.to_dict(),
        "receipt": receipt.to_dict(),
        "checkpoint": store.checkpoint(scope_ref),
        "snapshot": store.snapshot(),
    }
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()

names = (
    "AuthorityDomain",
    "GovernanceHead",
    "PreparedGovernanceTransition",
    "GovernanceCommitBatch",
    "GovernanceCommitReceipt",
    "GovernanceStateStore",
    "InMemoryGovernanceStateStore",
)
types_before = tuple(getattr(facade, name) for name in names)
modules_before = tuple(value.__module__ for value in types_before)
protocol_shape_before = tuple(
    (name, tuple(signature(getattr(GovernanceStateStore, name)).parameters))
    for name in (
        "load_head",
        "load_state",
        "trace_records",
        "load_receipt",
        "claim_identity",
        "compare_and_advance",
        "atomic_commit",
        "checkpoint",
        "rehydrate",
        "rehydrate_snapshot",
        "retire",
        "snapshot",
        "fingerprint",
    )
)
wire_before = fixture_wire()
assert "pheroos.governance.authority_store_v2" not in sys.modules

v2 = import_module("pheroos.governance.authority_store_v2")

types_after = tuple(getattr(facade, name) for name in names)
assert types_after == types_before
assert tuple(value.__module__ for value in types_after) == modules_before
assert tuple(
    (name, tuple(signature(getattr(GovernanceStateStore, name)).parameters))
    for name, _parameters in protocol_shape_before
) == protocol_shape_before
assert fixture_wire() == wire_before
assert isinstance(InMemoryGovernanceStateStore(), GovernanceStateStore)
assert v2.AuthorityDomainV2 is not AuthorityDomain
assert v2.GovernanceHeadV2 is not GovernanceHead
assert v2.PreparedGovernanceTransitionV2 is not PreparedGovernanceTransition
assert v2.GovernanceCommitBatchV2 is not GovernanceCommitBatch
assert v2.GovernanceCommitReceiptV2 is not GovernanceCommitReceipt
assert v2.GovernanceStateStoreV2 is not GovernanceStateStore
for value in types_before:
    assert pickle.loads(pickle.dumps(value)) is value

print(json.dumps({"wire_sha256": sha256(wire_before).hexdigest()}))
"""
    observed: list[dict[str, str]] = []
    for seed in ("1", "8675309"):
        environment = dict(os.environ)
        environment["PYTHONHASHSEED"] = seed
        completed = subprocess.run(
            [sys.executable, "-c", source],
            check=False,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        observed.append(json.loads(completed.stdout))

    assert observed == 2 * [
        {
            "wire_sha256": (
                "0b17bbdfaafc77d42bed4534aab48731c16ddb97a06337c6c4413544359e5576"
            )
        }
    ]


def test_v1_protocol_shape_is_still_the_frozen_thirteen_method_contract() -> None:
    store = InMemoryGovernanceStateStore()
    expected = {
        "load_head": ("self", "scope_ref", "stream"),
        "load_state": ("self", "scope_ref", "stream"),
        "trace_records": ("self", "scope_ref", "stream"),
        "load_receipt": ("self", "scope_ref", "transition_id"),
        "claim_identity": ("self", "scope_ref", "identity_id", "body"),
        "compare_and_advance": ("self", "batch"),
        "atomic_commit": ("self", "batch"),
        "checkpoint": ("self", "scope_ref"),
        "rehydrate": ("self", "payload"),
        "rehydrate_snapshot": ("self", "payload"),
        "retire": ("self", "scope_ref"),
        "snapshot": ("self",),
        "fingerprint": ("self",),
    }

    assert isinstance(store, GovernanceStateStore)
    assert {
        name: tuple(signature(getattr(GovernanceStateStore, name)).parameters)
        for name in expected
    } == expected
