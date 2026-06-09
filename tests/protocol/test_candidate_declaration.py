from pheroos.protocol.models import CandidateSpec, ProtocolManifest, QuorumPolicy, TargetSpec
from pheroos.protocol.validation import validate_capability_manifest
from pheroos.protocol.models import CapabilityManifest


def test_candidate_must_reference_declared_target() -> None:
    protocol = ProtocolManifest(
        protocol_version="pheroos.protocol.v1",
        id="toy.invalid",
        targets=[TargetSpec(id="decision:review")],
        candidates=[CandidateSpec(id="candidate:accept", target="decision:missing")],
        quorum_policy=QuorumPolicy(target="decision:review", fallback_candidate="candidate:accept"),
    )
    manifest = CapabilityManifest(id="toy", name="Toy", version="0.1.0", protocol=protocol)

    codes = {item.code for item in validate_capability_manifest(manifest)}

    assert "candidate_target_missing" in codes
