from dataclasses import replace

import pytest

from pheroos.protocol.models import CandidateSpec, CapabilityManifest, ProtocolManifest, QuorumPolicy, TargetSpec
from pheroos.protocol.validation import validate_capability_manifest


def test_quorum_fallback_must_be_declared_safe_candidate() -> None:
    protocol = ProtocolManifest(
        protocol_version="pheroos.protocol.v1",
        id="toy.invalid",
        targets=[TargetSpec(id="decision:review")],
        candidates=[CandidateSpec(id="candidate:return", target="decision:review")],
        quorum_policy=QuorumPolicy(target="decision:review", fallback_candidate="candidate:return"),
    )
    manifest = CapabilityManifest(id="toy", name="Toy", version="0.1.0", protocol=protocol)

    codes = {item.code for item in validate_capability_manifest(manifest)}

    assert "quorum_fallback_not_safe" in codes


def test_quorum_fallback_must_target_quorum_target() -> None:
    protocol = ProtocolManifest(
        protocol_version="pheroos.protocol.v1",
        id="toy.invalid",
        targets=[TargetSpec(id="decision:review"), TargetSpec(id="decision:other")],
        candidates=[CandidateSpec(id="candidate:other", target="decision:other", safe_fallback=True)],
        quorum_policy=QuorumPolicy(target="decision:review", fallback_candidate="candidate:other"),
    )
    manifest = CapabilityManifest(id="toy", name="Toy", version="0.1.0", protocol=protocol)

    codes = {item.code for item in validate_capability_manifest(manifest)}

    assert "quorum_fallback_target_mismatch" in codes


@pytest.mark.parametrize("commit_threshold", [0, -1, True, 1.0, "1"])
def test_typed_quorum_policy_requires_positive_integer_threshold(
    commit_threshold: object,
) -> None:
    protocol = ProtocolManifest(
        protocol_version="pheroos.protocol.v1",
        id="toy.invalid",
        targets=[TargetSpec(id="decision:review")],
        candidates=[
            CandidateSpec(
                id="candidate:fallback",
                target="decision:review",
                safe_fallback=True,
            )
        ],
        quorum_policy=QuorumPolicy(
            target="decision:review",
            fallback_candidate="candidate:fallback",
            commit_threshold=commit_threshold,
        ),
    )
    manifest = CapabilityManifest(id="toy", name="Toy", version="0.1.0", protocol=protocol)

    diagnostics = validate_capability_manifest(manifest)

    assert "quorum_commit_threshold_invalid" in {item.code for item in diagnostics}


@pytest.mark.parametrize(
    ("field_name", "diagnostic"),
    [
        ("target", "quorum_target_invalid"),
        ("fallback_candidate", "quorum_fallback_invalid"),
    ],
)
def test_typed_quorum_policy_requires_nonempty_authority_bindings(
    field_name: str,
    diagnostic: str,
) -> None:
    protocol = ProtocolManifest(
        protocol_version="pheroos.protocol.v1",
        id="toy.invalid",
        targets=[TargetSpec(id="decision:review")],
        candidates=[
            CandidateSpec(
                id="candidate:fallback",
                target="decision:review",
                safe_fallback=True,
            )
        ],
        quorum_policy=replace(
            QuorumPolicy(
                target="decision:review",
                fallback_candidate="candidate:fallback",
            ),
            **{field_name: ""},
        ),
    )
    manifest = CapabilityManifest(id="toy", name="Toy", version="0.1.0", protocol=protocol)

    diagnostics = validate_capability_manifest(manifest)

    assert diagnostic in {item.code for item in diagnostics}
