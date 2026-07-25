from __future__ import annotations

import ast
from pathlib import Path
from types import MappingProxyType

from pheroos.governance._commit_finality_v2 import (
    CommitFinalityOwnerV2,
    commit_finality_owner_genesis_snapshot_root_v2,
    commit_finality_owner_stream_ref_v2,
)
from pheroos.governance._distributed_v2 import state_contracts, state_handle
from pheroos.governance.distributed_commit_v2 import (
    DistributedLaneV2,
    distributed_genesis_snapshot_root_v2,
    distributed_lane_stream_ref_v2,
)


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "pheroos/governance/_distributed_v2"


def test_distributed_dispatch_tables_are_read_only_and_cannot_drift() -> None:
    proxy_type = type(MappingProxyType({}))
    assert type(state_contracts._STATE_TYPE_BY_LANE) is proxy_type
    assert type(state_contracts._DEPENDENCIES_BY_LANE) is proxy_type
    assert type(state_contracts._MUTATIONS_BY_LANE) is proxy_type
    assert type(state_handle._HANDLE_BY_LANE) is proxy_type
    assert type(state_handle._LANE_BY_HANDLE) is proxy_type


def test_distributed_package_has_no_module_global_mutable_container() -> None:
    mutable_nodes = (
        ast.Dict,
        ast.List,
        ast.Set,
        ast.DictComp,
        ast.ListComp,
        ast.SetComp,
    )
    mutable_calls = {"dict", "list", "set", "defaultdict"}
    violations: list[str] = []
    for path in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            value: ast.expr | None = None
            if isinstance(node, ast.Assign):
                value = node.value
                names = tuple(
                    target.id for target in node.targets if isinstance(target, ast.Name)
                )
            elif isinstance(node, ast.AnnAssign):
                value = node.value
                names = (node.target.id,) if isinstance(node.target, ast.Name) else ()
            else:
                names = ()
            if names == ("__all__",):
                continue
            if isinstance(value, mutable_nodes) or (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id in mutable_calls
            ):
                violations.append(f"{path.name}:{node.lineno}")
    assert violations == []


def test_neutral_finality_owner_identity_is_byte_identical_to_certificate_lane() -> (
    None
):
    values = (
        "scope:distributed:identity",
        "protocol:distributed:identity",
        "run:distributed:identity",
        "target:distributed:identity",
    )
    assert commit_finality_owner_stream_ref_v2(
        CommitFinalityOwnerV2.DISTRIBUTED, *values
    ) == distributed_lane_stream_ref_v2(*values, DistributedLaneV2.CERTIFICATE)
    assert commit_finality_owner_genesis_snapshot_root_v2(
        CommitFinalityOwnerV2.DISTRIBUTED
    ) == distributed_genesis_snapshot_root_v2(DistributedLaneV2.CERTIFICATE)


def test_distributed_sources_stay_small_and_avoid_dynamic_authority_shortcuts() -> None:
    forbidden = ("typing.Any", "type: ignore", "legacy_registry", "global_registry")
    for path in sorted(PACKAGE.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert len(source.splitlines()) < 600, path
        assert all(marker not in source for marker in forbidden), path
