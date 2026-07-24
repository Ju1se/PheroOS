from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from pheroos.cli.main import main
from pheroos.conformance.public_api_inventory import build_public_api_inventory
from pheroos.conformance.stable_api_candidate import load_stable_api_candidate


ROOT = Path(__file__).resolve().parents[2]


def _invoke(capsys: Any, *argv: str) -> tuple[int, dict[str, Any]]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, json.loads(captured.out)


def test_version_reports_all_versioned_management_surfaces(capsys: Any) -> None:
    code, payload = _invoke(capsys, "version")

    assert code == 0
    assert payload["ok"] is True
    assert payload["package_version"] == "0.1.0"
    assert payload["protocol_versions"] == ["pheroos.protocol.v1"]
    assert payload["capability_schema_versions"] == [
        "pheroos-capability-schema-v1",
        "pheroos-capability-schema-v2",
        "pheroos-capability-schema-v3",
    ]
    assert payload["protocol_schema_versions"] == [
        "pheroos-protocol-schema-v1",
        "pheroos-protocol-schema-v2",
        "pheroos-protocol-schema-v3",
    ]
    assert payload["authority_ledger_version"].endswith("-v1")
    assert payload["driver_descriptor_version"] == "pheroos-driver-descriptor-v2"
    assert payload["kernel_plan_version"] == "pheroos-kernel-plan-v2"
    assert payload["conformance_report_version"].endswith("-v2")
    assert len(payload["commit_tck_versions"]) == 2


def test_profile_show_consumes_the_manifest_and_lists_required_checks(
    capsys: Any,
) -> None:
    code, payload = _invoke(
        capsys,
        "profile",
        "show",
        "examples/hybrid-commit-protocol/capability.json",
    )

    assert code == 0
    assert payload["ok"] is True
    assert payload["protocol_version"] == "pheroos.protocol.v1"
    assert payload["profile"]["version"].startswith("pheroos-hybrid-commit-")
    assert "commit_channel_separation" in payload["profile"]["required_checks"]


def test_schema_list_and_show_are_versioned_and_deterministic(capsys: Any) -> None:
    list_code, listed = _invoke(capsys, "schema", "list")
    show_code, shown = _invoke(capsys, "schema", "show", "scoped-trace")

    assert list_code == show_code == 0
    surfaces = [item["surface"] for item in listed["schemas"]]
    assert surfaces == sorted(surfaces, key=surfaces.index)
    assert "commit-tck-request-v2" in surfaces
    assert "conformance-report" in surfaces
    assert shown["$id"].endswith("scoped-trace-event-v1.schema.json")


def test_wire_validate_accepts_protocol_and_rejects_duplicate_json_keys(
    capsys: Any,
    tmp_path: Path,
) -> None:
    valid = Path("examples/toy-protocol/capability.json")
    good_code, good = _invoke(capsys, "wire", "validate", "capability", str(valid))

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"event_type":"ext.test","event_type":"ext.other",'
        '"protocol_id":"p","target":"t","reason":"r","lineage":{}}',
        encoding="utf-8",
    )
    bad_code, bad = _invoke(
        capsys,
        "wire",
        "validate",
        "trace",
        str(duplicate),
    )

    assert good_code == 0
    assert good["ok"] is True
    assert bad_code == 1
    assert bad["ok"] is False
    assert "duplicate JSON object key" in bad["diagnostics"][0]["message"]


def test_wire_validate_tck_v2_artifact_executes_typed_loader(capsys: Any) -> None:
    code, payload = _invoke(
        capsys,
        "wire",
        "validate",
        "commit-tck-v2",
        "pheroos/conformance/tck/commit-integrity-v2.json",
    )

    assert code == 0
    assert payload["ok"] is True


def test_tck_run_v2_emits_exact_adapter_report(capsys: Any) -> None:
    code, payload = _invoke(capsys, "tck", "run", "--version", "v2")

    assert code == 0
    assert payload["ok"] is True
    assert payload["tck_version"].endswith("-v2")
    assert len(payload["results"]) >= 23
    assert all(item["ok"] for item in payload["results"])


def test_abi_show_and_runtime_diff_use_packaged_inventory(capsys: Any) -> None:
    show_code, shown = _invoke(
        capsys,
        "abi",
        "show",
        "--package",
        "pheroos.kernel",
    )
    diff_code, diffed = _invoke(capsys, "abi", "diff")

    assert show_code == 0
    assert shown["inventory"]["package"] == "pheroos.kernel"
    assert shown["inventory"]["surface"]["export_count"] > 0
    assert diff_code == 0
    assert diffed["ok"] is True
    assert diffed["differences"] == []


def test_abi_stable_only_reads_and_builds_the_draft_candidate(capsys: Any) -> None:
    show_code, shown = _invoke(
        capsys,
        "abi",
        "show",
        "--stable-only",
        "--package",
        "pheroos.kernel",
    )
    diff_code, diffed = _invoke(capsys, "abi", "diff", "--stable-only")

    assert show_code == diff_code == 0
    assert shown["stable_only"] is True
    assert shown["inventory"]["artifact_version"] == ("pheroos-stable-python-api-v1")
    assert shown["inventory"]["surface"]["closure_count"] > 0
    assert diffed["candidate_status"] == "promotion_candidate"
    assert diffed["formal_stable"] is False
    assert diffed["stable_breaking"] is False
    assert diffed["breaking_differences"] == []
    assert diffed["differences"] == []


def test_abi_stable_only_ignores_draft_changes_outside_candidate_closure(
    capsys: Any,
    tmp_path: Path,
) -> None:
    candidate = load_stable_api_candidate(ROOT)
    closure = {
        entry["binding"]
        for package in candidate["packages"].values()
        for entry in package["exports"]
    }
    closure.update(entry["binding"] for entry in candidate["constant_dependencies"])
    observed = deepcopy(build_public_api_inventory())
    package_name, shape = next(
        (name, item)
        for name, package in observed["packages"].items()
        for item in package["exports"]
        if f"{name}.{item['name']}" not in closure
    )
    shape["signature"] = {"synthetic": "expert-draft-change"}
    artifact = tmp_path / "observed.json"
    artifact.write_text(json.dumps(observed), encoding="utf-8")

    code, payload = _invoke(
        capsys,
        "abi",
        "diff",
        "--stable-only",
        str(artifact),
    )

    assert package_name.startswith("pheroos.")
    assert code == 0
    assert payload["ok"] is True
    assert payload["differences"] == []
    assert payload["stable_breaking"] is False


def test_abi_stable_only_reports_candidate_drift_without_calling_it_stable(
    capsys: Any,
    tmp_path: Path,
) -> None:
    candidate = load_stable_api_candidate(ROOT)
    observed = deepcopy(build_public_api_inventory())
    selected = next(
        entry["binding"]
        for package in candidate["packages"].values()
        for entry in package["exports"]
    )
    package_name, export_name = selected.rsplit(".", 1)
    shape = next(
        item
        for item in observed["packages"][package_name]["exports"]
        if item["name"] == export_name
    )
    shape["signature"] = {"synthetic": "candidate-drift"}
    artifact = tmp_path / "observed.json"
    artifact.write_text(json.dumps(observed), encoding="utf-8")

    code, payload = _invoke(
        capsys,
        "abi",
        "diff",
        "--stable-only",
        str(artifact),
    )

    assert code == 1
    assert payload["ok"] is False
    assert payload["differences"]
    assert payload["formal_stable"] is False
    assert payload["stable_breaking"] is False
    assert payload["breaking_differences"] == []


def test_invalid_management_input_has_stable_error_envelope(capsys: Any) -> None:
    code, payload = _invoke(capsys, "profile", "show", "missing.json")

    assert code == 2
    assert payload == {
        "error_code": "cli_input_invalid",
        "error_type": "FileNotFoundError",
        "message": payload["message"],
        "ok": False,
        "output_version": "pheroos-cli-output-v1",
    }
