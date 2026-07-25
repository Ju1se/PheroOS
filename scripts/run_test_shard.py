#!/usr/bin/env python3
"""Run one checked deterministic test shard without coverage instrumentation."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import importlib
import subprocess
import sys
from types import ModuleType


def _load_inventory_module() -> ModuleType:
    try:
        return importlib.import_module("scripts.check_coverage_gate")
    except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
        return importlib.import_module("check_coverage_gate")


_inventory = _load_inventory_module()
MEASUREMENT_SHARDS: tuple[str, ...] = _inventory.MEASUREMENT_SHARDS
load_coverage_manifest = _inventory.load_coverage_manifest
manifest_shape_failures = _inventory.manifest_shape_failures
pytest_targets_for_shard = _inventory.pytest_targets_for_shard


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shard", choices=MEASUREMENT_SHARDS)
    args = parser.parse_args(argv)
    manifest = load_coverage_manifest()
    failures = manifest_shape_failures(manifest)
    if failures:
        for failure in failures:
            print(f"test shard: FAIL: {failure}", file=sys.stderr)
        return 2
    targets = pytest_targets_for_shard(manifest, args.shard)
    print(f"test shard {args.shard}: files={len(targets)}", flush=True)
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *targets],
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
