from __future__ import annotations

from inspect import signature
from typing import get_type_hints

import pytest

from pheroos.governance import commit_finality_v2, distributed_commit_v2
from pheroos.governance.distributed_commit_v2 import (
    DistributedLaneV2,
    VerifiedDistributedCertificateStateV2,
    VerifiedDistributedEpochStateV2,
    VerifiedDistributedProposalStateV2,
    VerifiedDistributedStateV2,
    VerifiedDistributedWitnessStateV2,
    distributed_lane_stream_ref_v2,
    verified_distributed_commit_finality_input_v2,
)


def test_distributed_public_facade_is_closed_unique_and_canonical() -> None:
    exported = distributed_commit_v2.__all__
    assert len(exported) == len(set(exported))
    assert all(hasattr(distributed_commit_v2, name) for name in exported)
    for name in exported:
        value = getattr(distributed_commit_v2, name)
        if callable(value):
            assert value.__module__ == "pheroos.governance.distributed_commit_v2"


def test_distributed_opaque_base_is_nonconstructible_and_exactly_shared() -> None:
    with pytest.raises(TypeError, match="cannot be constructed"):
        VerifiedDistributedStateV2()
    assert issubclass(VerifiedDistributedEpochStateV2, VerifiedDistributedStateV2)
    assert issubclass(VerifiedDistributedProposalStateV2, VerifiedDistributedStateV2)
    assert issubclass(VerifiedDistributedWitnessStateV2, VerifiedDistributedStateV2)
    assert issubclass(VerifiedDistributedCertificateStateV2, VerifiedDistributedStateV2)


def test_distributed_finality_return_annotation_is_canonical_public_type() -> None:
    hints = get_type_hints(verified_distributed_commit_finality_input_v2)
    assert hints["return"] is commit_finality_v2.VerifiedCommitFinalityInputV2
    parameters = signature(verified_distributed_commit_finality_input_v2).parameters
    assert tuple(parameters) == (
        "certificate_state",
        "proposal_state",
        "witness_state",
        "epoch_state",
        "sealed_decision_state",
        "central_certificate_state",
        "membership_state",
        "manifest",
        "current_step",
    )


def test_distributed_fixed_lane_streams_are_distinct_and_deterministic() -> None:
    values = (
        "scope:distributed-v2:public",
        "protocol:distributed-v2:public",
        "run:distributed-v2:public",
        "target:distributed-v2:public",
    )
    first = tuple(
        distributed_lane_stream_ref_v2(*values, lane) for lane in DistributedLaneV2
    )
    second = tuple(
        distributed_lane_stream_ref_v2(*values, lane) for lane in DistributedLaneV2
    )
    assert first == second
    assert len(first) == len(set(first)) == 4
