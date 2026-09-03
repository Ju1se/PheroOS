from __future__ import annotations

import json
from pathlib import Path

import pheroos.governance as governance

from pheroos.conformance.checks import public_abi_boundary
from pheroos.conformance.public_api_inventory import (
    PUBLIC_API_INVENTORY_PATH,
    build_public_api_inventory,
)
from pheroos.conformance.public_api_lifecycle import (
    PUBLIC_API_LIFECYCLE_PATH,
    build_public_api_lifecycle,
)


ROOT = Path(__file__).resolve().parents[2]


def test_public_abi_boundary_proves_ownership_and_defensive_snapshots() -> None:
    result = public_abi_boundary.check()

    assert result.ok is True, result.detail


def test_public_abi_boundary_rejects_noncanonical_commit_type_export(
    monkeypatch: object,
) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        governance,
        "CommitAction",
        object,
    )

    result = public_abi_boundary.check()

    assert result.ok is False
    assert "ownership:commit_action" in result.detail


def test_public_abi_boundary_rejects_stale_shape_inventory(tmp_path: Path) -> None:
    inventory = build_public_api_inventory()
    policy = next(
        item
        for item in inventory["packages"]["pheroos.protocol"]["exports"]
        if item["name"] == "CollectiveDecisionPolicy"
    )
    policy["dataclass"]["fields"][0]["default"]["value"] = "stale"
    registry = next(
        item
        for item in inventory["packages"]["pheroos.drivers"]["exports"]
        if item["name"] == "DriverRegistry"
    )
    get_method = next(
        member for member in registry["members"] if member["name"] == "get"
    )
    get_method["signature"]["parameters"][0]["name"] = "stale_driver_id"
    artifact = tmp_path / PUBLIC_API_INVENTORY_PATH
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps(inventory), encoding="utf-8")
    lifecycle_artifact = tmp_path / PUBLIC_API_LIFECYCLE_PATH
    lifecycle_artifact.write_text(
        json.dumps(build_public_api_lifecycle(ROOT)),
        encoding="utf-8",
    )

    result = public_abi_boundary.check(tmp_path)

    assert result.ok is False
    assert (
        "inventory:$.packages.pheroos.protocol.exports[CollectiveDecisionPolicy]"
        ".dataclass.fields[0].default.value"
    ) in result.detail
    assert (
        "inventory:$.packages.pheroos.drivers.exports[DriverRegistry]"
        ".members[get].signature.parameters[0].name"
    ) in result.detail


def test_public_abi_boundary_rejects_stale_lifecycle_metadata(
    tmp_path: Path,
) -> None:
    inventory_artifact = tmp_path / PUBLIC_API_INVENTORY_PATH
    inventory_artifact.parent.mkdir(parents=True)
    inventory_artifact.write_text(
        json.dumps(build_public_api_inventory()),
        encoding="utf-8",
    )
    lifecycle = build_public_api_lifecycle(ROOT)
    lifecycle["packages"]["pheroos.drivers"]["exports"][0]["replacement"] = (
        "pheroos.drivers.NoSuchDescriptor"
    )
    lifecycle_artifact = tmp_path / PUBLIC_API_LIFECYCLE_PATH
    lifecycle_artifact.write_text(json.dumps(lifecycle), encoding="utf-8")

    result = public_abi_boundary.check(tmp_path)

    assert result.ok is False
    assert "lifecycle:entry:pheroos.drivers." in result.detail
    assert ":replacement" in result.detail
