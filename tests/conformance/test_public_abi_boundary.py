from __future__ import annotations

import pheroos.governance as governance

from pheroos.conformance.checks import public_abi_boundary


def test_public_abi_boundary_proves_ownership_and_defensive_snapshots() -> None:
    result = public_abi_boundary.check()

    assert result.ok is True, result.detail


def test_public_abi_boundary_rejects_noncanonical_kind_profile_export(
    monkeypatch: object,
) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        governance,
        "PheromoneKindProfile",
        object,
    )

    result = public_abi_boundary.check()

    assert result.ok is False
    assert "ownership:pheromone_kind_profile" in result.detail
