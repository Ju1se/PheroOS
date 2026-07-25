from __future__ import annotations

from copy import deepcopy

from scripts.check_complexity_scope import (
    LOCKED_SCOPE_SHA256,
    REQUIRED_MODULE_PATHS,
    REQUIRED_TRUST_PATH_FUNCTIONS,
    complexity_scope_failures,
    load_complexity_manifest,
    locked_scope_sha256,
    manifest_shape_failures,
    observe_function_complexities,
    observe_module_lines,
    observe_repository_complexity,
)


def test_checked_in_complexity_scope_is_exact_and_baseline_green() -> None:
    manifest = load_complexity_manifest()

    assert manifest_shape_failures(manifest) == []
    assert locked_scope_sha256(manifest) == LOCKED_SCOPE_SHA256
    assert (
        complexity_scope_failures(
            manifest,
            function_complexities=observe_function_complexities(),
            module_lines=observe_module_lines(),
            repository_metrics=observe_repository_complexity(),
            require_targets=False,
        )
        == []
    )


def test_trust_path_scope_is_static_and_covers_every_commit_probe() -> None:
    manifest = load_complexity_manifest()
    names = tuple(item["qualified_function"] for item in manifest["functions"])

    assert names == REQUIRED_TRUST_PATH_FUNCTIONS
    assert len(names) == len(set(names)) == 86
    assert tuple(item["path"] for item in manifest["modules"]) == REQUIRED_MODULE_PATHS
    assert all(item["category"] == "trust_path" for item in manifest["functions"])
    assert all(
        f"pheroos.conformance._commit_tck.reference_adapter._probe_case_{case:02d}"
        in names
        for case in range(1, 39)
    )


def test_scope_cannot_drop_or_reclassify_a_trust_path_function() -> None:
    missing = deepcopy(load_complexity_manifest())
    missing["functions"].pop()
    reclassified = deepcopy(load_complexity_manifest())
    reclassified["functions"][0]["category"] = "ordinary"

    assert any("static WP-09 set" in item for item in manifest_shape_failures(missing))
    assert any("category" in item for item in manifest_shape_failures(reclassified))


def test_locked_baselines_and_targets_cannot_be_silently_relaxed() -> None:
    manifest = deepcopy(load_complexity_manifest())
    manifest["functions"][0]["baseline_complexity"] += 1
    manifest["modules"][0]["baseline_lines"] += 1
    manifest["repository_baseline"]["over_10_count"] += 1

    failures = manifest_shape_failures(manifest)

    assert any("immutable complexity scope drift" in item for item in failures)


def test_function_and_module_ratchets_fail_closed() -> None:
    manifest = load_complexity_manifest()
    functions = {
        item["qualified_function"]: item["baseline_complexity"]
        for item in manifest["functions"]
    }
    modules = {item["path"]: item["baseline_lines"] for item in manifest["modules"]}
    repository = {
        key: value
        for key, value in manifest["repository_baseline"].items()
        if key != "scope"
    }
    function_name = manifest["functions"][0]["qualified_function"]
    module_path = manifest["modules"][0]["path"]
    functions[function_name] += 1
    modules[module_path] += 1

    failures = complexity_scope_failures(
        manifest,
        function_complexities=functions,
        module_lines=modules,
        repository_metrics=repository,
        require_targets=False,
    )

    assert any(
        function_name in item and "baseline_complexity" in item for item in failures
    )
    assert any(module_path in item and "baseline_lines" in item for item in failures)


def test_missing_function_and_repository_regression_fail_closed() -> None:
    manifest = load_complexity_manifest()
    functions = {
        item["qualified_function"]: item["baseline_complexity"]
        for item in manifest["functions"]
    }
    missing_name = manifest["functions"][0]["qualified_function"]
    del functions[missing_name]
    repository = {
        key: value
        for key, value in manifest["repository_baseline"].items()
        if key != "scope"
    }
    repository["over_20_count"] += 1

    failures = complexity_scope_failures(
        manifest,
        function_complexities=functions,
        module_lines={
            item["path"]: item["baseline_lines"] for item in manifest["modules"]
        },
        repository_metrics=repository,
        require_targets=False,
    )

    assert any(f"missing: {missing_name}" in item for item in failures)
    assert any("over_20_count" in item and "baseline" in item for item in failures)


def test_target_mode_enforces_function_module_and_repository_targets() -> None:
    manifest = load_complexity_manifest()
    functions = {
        item["qualified_function"]: item["target_complexity"]
        for item in manifest["functions"]
    }
    modules = {item["path"]: item["target_lines"] for item in manifest["modules"]}
    repository = {
        "complexity_sum": 64 * 11,
        "maximum_observed": 20,
        "over_10_count": 64,
        "over_20_count": 0,
        "over_25_count": 0,
    }

    assert (
        complexity_scope_failures(
            manifest,
            function_complexities=functions,
            module_lines=modules,
            repository_metrics=repository,
            require_targets=True,
        )
        == []
    )

    functions[manifest["functions"][0]["qualified_function"]] += 1
    modules[manifest["modules"][0]["path"]] += 1
    repository["over_10_count"] += 1
    failures = complexity_scope_failures(
        manifest,
        function_complexities=functions,
        module_lines=modules,
        repository_metrics=repository,
        require_targets=True,
    )

    assert any("target_complexity" in item for item in failures)
    assert any("target_lines" in item for item in failures)
    assert any("final target" in item for item in failures)


def test_boolean_limits_are_rejected_as_non_integers() -> None:
    manifest = deepcopy(load_complexity_manifest())
    manifest["functions"][0]["target_complexity"] = True

    assert any(
        "target_complexity" in item for item in manifest_shape_failures(manifest)
    )
