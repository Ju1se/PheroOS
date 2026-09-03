from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.check_legacy_authority_inventory import (
    INVENTORY_KEYS,
    INVENTORY_PATH,
    INVENTORY_VERSION,
    POLICY,
    STORE_REHYDRATABLE_OPAQUE_TOKENS,
    _imports_legacy_registry,
    build_inventory,
    inventory_failures,
    load_inventory,
    render_inventory,
    write_inventory,
)


ROOT = Path(__file__).resolve().parents[2]


def _append_entry(
    value: dict[str, object],
    category: str,
    entry: object,
) -> None:
    inventory = value["inventory"]
    counts = value["counts"]
    assert isinstance(inventory, dict)
    assert isinstance(counts, dict)
    entries = inventory[category]
    assert isinstance(entries, list)
    entries.append(entry)
    entries.sort(key=lambda item: json.dumps(item, sort_keys=True))
    counts[category] = len(entries)


def _remove_first_entry(value: dict[str, object], category: str) -> None:
    inventory = value["inventory"]
    counts = value["counts"]
    assert isinstance(inventory, dict)
    assert isinstance(counts, dict)
    entries = inventory[category]
    assert isinstance(entries, list)
    entries.pop(0)
    counts[category] = len(entries)


def test_checked_inventory_exactly_matches_recursive_governance_scan() -> None:
    checked = load_inventory()
    observed = build_inventory()

    assert checked["version"] == INVENTORY_VERSION
    assert checked["policy"] == POLICY
    assert inventory_failures(checked, observed) == []
    assert INVENTORY_PATH.read_bytes() == render_inventory(checked)


def test_wp05_initial_inventory_counts_and_nested_surfaces_are_explicit() -> None:
    value = build_inventory()
    counts = value["counts"]
    inventory = value["inventory"]
    assert isinstance(counts, dict)
    assert isinstance(inventory, dict)

    assert counts == {
        "cursor_types": 6,
        "legacy_namespaces": 14,
        "registry_importers": 0,
        "sentinel_only_issuance_candidates": 40,
        "store_rehydratable_opaque_tokens": 5,
    }
    assert inventory["registry_importers"] == []
    assert {entry["namespace"] for entry in inventory["legacy_namespaces"]} >= {
        "legacy.commit.window_cursors",
        "legacy.distributed.epoch_certificates_by_id",
        "legacy.support.replay_cursors",
    }


def test_v2_store_rehydratable_tokens_are_not_legacy_sentinel_candidates() -> None:
    inventory = build_inventory()["inventory"]
    assert isinstance(inventory, dict)
    opaque = {
        (entry["path"], entry["symbol"])
        for entry in inventory["store_rehydratable_opaque_tokens"]
    }
    candidates = {
        (entry["path"], entry["symbol"])
        for entry in inventory["sentinel_only_issuance_candidates"]
    }

    assert opaque == STORE_REHYDRATABLE_OPAQUE_TOKENS
    assert candidates.isdisjoint(opaque)
    assert {
        "_CAPABILITY_TOKEN",
        "_FINALITY_INPUT_TOKEN_V2",
        "_SESSION_TOKEN",
        "_SOURCE_TOKEN_V2",
    } == {symbol for _, symbol in opaque}
    assert all(
        not any(
            owner in path
            for owner in (
                "_authority_session_v2",
                "_commit_decision_v2",
                "_distributed_v2",
            )
        )
        and path != "pheroos/governance/_commit_finality_v2.py"
        for path, _ in candidates
    )


@pytest.mark.parametrize(
    ("category", "entry"),
    (
        (
            "registry_importers",
            "pheroos/governance/_new_legacy_consumer.py",
        ),
        (
            "legacy_namespaces",
            {
                "namespace": "legacy.new.authority",
                "path": "pheroos/governance/_new_legacy_consumer.py",
                "symbol": "_LEGACY_NEW_AUTHORITY",
            },
        ),
        (
            "cursor_types",
            {
                "path": "pheroos/governance/_new_legacy_consumer.py",
                "type": "_NewAuthorityCursor",
            },
        ),
        (
            "sentinel_only_issuance_candidates",
            {
                "path": "pheroos/governance/_new_legacy_consumer.py",
                "symbol": "_NEW_AUTHORITY_ISSUANCE",
            },
        ),
        (
            "store_rehydratable_opaque_tokens",
            {
                "path": "pheroos/governance/_new_authority_v2/contracts.py",
                "symbol": "_NEW_TOKEN",
            },
        ),
    ),
)
def test_every_observed_authority_surface_is_an_upper_bound(
    category: str,
    entry: object,
) -> None:
    checked = build_inventory()
    expanded = deepcopy(checked)
    _append_entry(expanded, category, entry)

    failures = inventory_failures(checked, expanded)

    assert any(
        "legacy authority expansion" in failure and category in failure
        for failure in failures
    )


@pytest.mark.parametrize(
    "category",
    tuple(category for category in INVENTORY_KEYS if category != "registry_importers"),
)
def test_removal_requires_checked_artifact_tightening(category: str) -> None:
    checked = build_inventory()
    reduced = deepcopy(checked)
    _remove_first_entry(reduced, category)

    failures = inventory_failures(checked, reduced)

    assert failures == [
        f"legacy authority inventory can tighten in {category}; run --write"
    ]


def test_writer_accepts_shrink_then_refuses_restoration(
    tmp_path: Path,
) -> None:
    current = build_inventory()
    target = tmp_path / "legacy-authority-inventory-v1.json"
    write_inventory(target, observed=current)
    reduced = deepcopy(current)
    _remove_first_entry(reduced, "legacy_namespaces")

    write_inventory(target, observed=reduced)

    assert load_inventory(target) == reduced
    with pytest.raises(ValueError, match="would expand"):
        write_inventory(target, observed=current)


def test_writer_accepts_only_explicitly_reviewed_opaque_token_classification(
    tmp_path: Path,
) -> None:
    current = build_inventory()
    checked = deepcopy(current)
    _remove_first_entry(checked, "store_rehydratable_opaque_tokens")
    target = tmp_path / "legacy-authority-inventory-v1.json"
    target.write_bytes(render_inventory(checked))

    write_inventory(target, observed=current)

    assert load_inventory(target) == current
    expanded = deepcopy(current)
    _append_entry(
        expanded,
        "store_rehydratable_opaque_tokens",
        {
            "path": "pheroos/governance/_unreviewed.py",
            "symbol": "_UNREVIEWED_TOKEN",
        },
    )
    with pytest.raises(ValueError, match="would expand"):
        write_inventory(target, observed=expanded)


@pytest.mark.parametrize(
    "source",
    (
        "from pheroos.governance._legacy.authority_registry import "
        "LEGACY_AUTHORITY_REGISTRY\n",
        "from .._legacy.authority_registry import LEGACY_AUTHORITY_REGISTRY\n",
        "from pheroos.governance._legacy import LEGACY_AUTHORITY_REGISTRY\n",
        "import pheroos.governance._legacy.authority_registry\n",
        "importlib.import_module('pheroos.governance._legacy.authority_registry')\n",
        "import_module('pheroos.governance._legacy.authority_registry')\n",
        "__import__('pheroos.governance._legacy.authority_registry')\n",
    ),
)
def test_registry_import_detection_covers_direct_relative_and_dynamic_forms(
    source: str,
) -> None:
    assert _imports_legacy_registry(ast.parse(source))


def test_registry_import_detection_does_not_classify_v2_store_imports() -> None:
    tree = ast.parse(
        "from pheroos.governance.authority_store_v2 import GovernanceStateStoreV2\n"
    )

    assert not _imports_legacy_registry(tree)


@pytest.mark.parametrize(
    "payload",
    (
        '{"version": NaN}',
        '{"version": "first", "version": "second"}',
        "[]",
    ),
)
def test_loader_rejects_noncanonical_or_malformed_artifacts(
    tmp_path: Path,
    payload: str,
) -> None:
    target = tmp_path / "bad.json"
    target.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError):
        load_inventory(target)


def test_cli_check_is_read_only_and_clean() -> None:
    before = INVENTORY_PATH.read_bytes()

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/check_legacy_authority_inventory.py"),
            "--check",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "registry_importers=0" in completed.stdout
    assert "sentinel_only_issuance_candidates=40" in completed.stdout
    assert "store_rehydratable_opaque_tokens=5" in completed.stdout
    assert INVENTORY_PATH.read_bytes() == before
