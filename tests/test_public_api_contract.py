from __future__ import annotations

from hashlib import sha256
from importlib import import_module

import pheroos.governance as governance
import pheroos.protocol as protocol
import pheroos.trace as trace


EXPECTED_PUBLIC_API = {
    "pheroos.protocol": (27, "4a019a816c812913dc891a3aae744dc1c1b03b008887214b0dbfcc35d51ef7e7"),
    "pheroos.governance": (108, "3bd0b7b919905eaada029125e66bfee91a2a5ca25c1c92bb766aed321256bb7a"),
    "pheroos.kernel": (14, "f195fda8c36d48bb30c4fdbc6eb69ffe38db26958f60925eb5c7f9952cb500d1"),
    "pheroos.drivers": (20, "b3c27fe18c2a1a9c8ddcbbb30f8fe2ad5a8a2b32606eaedd168b690823fc0da4"),
    "pheroos.trace": (13, "12e4b3ef5cab6c366e14630e3c646c4128ffae25a22775793238cd75b2f443f6"),
    "pheroos.conformance": (5, "e471adab090a6e74b3b0bbb002f08cb3082b1ac52120668da26baafb4cb94185"),
}


def test_public_package_exports_match_the_intentional_abi_snapshot() -> None:
    for module_name, (expected_count, expected_digest) in EXPECTED_PUBLIC_API.items():
        module = import_module(module_name)
        exported = tuple(module.__all__)

        assert len(exported) == expected_count
        assert len(exported) == len(set(exported))
        assert all(hasattr(module, name) for name in exported)
        observed = sha256("\n".join(sorted(exported)).encode()).hexdigest()
        assert observed == expected_digest, f"undeclared public ABI drift in {module_name}"


def test_canonical_public_types_are_owned_by_their_declared_surfaces() -> None:
    assert governance.PheromoneKindProfile is protocol.PheromoneKindProfile
    assert protocol.PheromoneKindProfile.__module__ == "pheroos.protocol.models"
    assert governance.TraceEvent is trace.TraceEvent
    assert trace.TraceEvent.__module__ == "pheroos.trace"
    assert governance.PheromoneTrail.__module__ == "pheroos.governance.pheromone"
    assert governance.LayerProposal.__module__ == "pheroos.governance.layer_coordination"
    assert governance.PolicyAdjustmentProposal.__module__ == "pheroos.governance.policy_adjustment"
    assert governance.HybridCollectiveStep.__module__ == "pheroos.governance.collective"
    assert governance.HybridReplayState.__module__ == "pheroos.governance.collective"
