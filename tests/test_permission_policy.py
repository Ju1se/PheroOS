from __future__ import annotations

from pathlib import Path

from runtime.capability_registry import CapabilityManifest
from runtime.permission_policy import evaluate_capability_permissions


def make_manifest(*, permissions: list[str], risk_level: str = "low", requires_confirmation: bool = False) -> CapabilityManifest:
    return CapabilityManifest(
        id="demo",
        name="Demo",
        version="0.1.0",
        description="Demo",
        capability_types=["demo"],
        permissions=permissions,
        risk_level=risk_level,  # type: ignore[arg-type]
        requires_confirmation=requires_confirmation,
        connections=[],
        required_connections=[],
        tools=[],
        skills=[],
        data_packages=[],
        entrypoints={},
        agents_path=None,
        ui={},
        path=Path("capabilities/demo/capability.json"),
    )


def test_low_risk_auto_grant_permissions_can_auto_enable() -> None:
    decision = evaluate_capability_permissions(
        make_manifest(permissions=["data:read", "model:chat", "network:approved-provider"])
    )

    assert decision.auto_enable is True
    assert decision.needs_confirmation is False
    assert decision.blocked_permissions == []


def test_dangerous_permission_requires_confirmation() -> None:
    decision = evaluate_capability_permissions(make_manifest(permissions=["data:read", "shell:execute"]))

    assert decision.auto_enable is False
    assert decision.needs_confirmation is True
    assert decision.blocked_permissions == ["shell:execute"]


def test_medium_risk_requires_confirmation_even_with_safe_permissions() -> None:
    decision = evaluate_capability_permissions(make_manifest(permissions=["data:read"], risk_level="medium"))

    assert decision.auto_enable is False
    assert decision.needs_confirmation is True


def test_unknown_permission_requires_confirmation() -> None:
    decision = evaluate_capability_permissions(make_manifest(permissions=["data:read", "network:unknown"]))

    assert decision.auto_enable is False
    assert decision.needs_confirmation is True
    assert decision.blocked_permissions == ["network:unknown"]
