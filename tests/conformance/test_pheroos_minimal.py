from __future__ import annotations

import json
from pathlib import Path

from pheroos.cli import main
from pheroos.minimal import init_minimal_project, latest_minimal_trace, run_minimal_task
from pheroos.protocol.manifest import load_capability_protocol


ROOT = Path(__file__).resolve().parents[2]


def test_minimal_init_creates_no_key_workspace(tmp_path: Path) -> None:
    report = init_minimal_project(tmp_path)
    config = json.loads((tmp_path / "pheroos-minimal.json").read_text(encoding="utf-8"))

    assert report["ok"] is True
    assert report["external_api_required"] is False
    assert report["enabled_capabilities"] == ["toy-review"]
    assert (tmp_path / ".pheroos" / "minimal-traces.jsonl").exists()
    assert config["enabled_capabilities"] == ["toy-review"]
    assert all(driver.get("external_api_required") is not True for driver in config["drivers"])
    assert config["forbidden_runtime_assumptions"] == [
        "external_api_key",
        "financial_data_provider",
        "provider_secret",
    ]


def test_minimal_run_writes_trace_without_network_or_secrets(tmp_path: Path) -> None:
    init_minimal_project(tmp_path)
    protocol = load_capability_protocol(ROOT / "capabilities" / "toy-review").protocol

    report = run_minimal_task("review this toy claim", workspace=tmp_path)
    latest = latest_minimal_trace(workspace=tmp_path)

    assert report["ok"] is True
    assert report["network_access"] == "none"
    assert report["secrets_used"] == []
    assert report["capabilities"] == [{"id": "toy-review", "source": "reference_capability"}]
    assert report["governance"]["protocol_source"] == "capabilities/toy-review/capability.json"
    assert report["quorum"]["candidate_set"] == [candidate["candidate"] for candidate in protocol["candidates"]]
    assert report["quorum"]["fallback_candidate"] == protocol["quorum_policy"]["candidate_fallback"]
    assert report["quorum"]["committed_candidate"] == protocol["candidates"][0]["candidate"]
    assert report["output"]["required_caveats"] == protocol["output_policy"]["required_caveats"]
    assert report["governance"]["final_judge_required_checks"] == protocol["output_policy"]["final_judge_required_checks"]
    assert report["output"]["publication_permission"] is True
    assert latest["ok"] is True
    assert latest["trace"]["run_id"] == report["run_id"]


def test_minimal_run_uses_declared_fallback_when_evidence_is_missing(tmp_path: Path) -> None:
    protocol = load_capability_protocol(ROOT / "capabilities" / "toy-review").protocol

    report = run_minimal_task("review this missing evidence claim", workspace=tmp_path)

    assert report["ok"] is True
    assert report["evidence"]["evidence_available"] is False
    assert report["quorum"]["committed_candidate"] == protocol["quorum_policy"]["candidate_fallback"]
    assert report["output"]["mode"] == "defect_memo"
    assert report["output"]["publication_permission"] is False


def test_minimal_run_rejects_network_or_secret_config(tmp_path: Path) -> None:
    init_minimal_project(tmp_path)
    config_path = tmp_path / "pheroos-minimal.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["network_access"] = "open"
    config["secrets_required"] = ["provider-key"]
    config_path.write_text(json.dumps(config), encoding="utf-8")

    report = run_minimal_task("review this toy claim", workspace=tmp_path)

    assert report["ok"] is False
    assert "minimal distro must not request network access" in report["errors"]
    assert "minimal distro must not require secrets" in report["errors"]


def test_minimal_cli_roundtrip(tmp_path: Path, capsys) -> None:
    assert main(["init", "minimal", str(tmp_path)]) == 0
    init_report = json.loads(capsys.readouterr().out)
    assert init_report["distro_id"] == "minimal"

    assert main(["run", "review this toy claim", "--distro", "minimal", "--workspace", str(tmp_path)]) == 0
    run_report = json.loads(capsys.readouterr().out)
    assert run_report["ok"] is True
    assert run_report["runtime"] == "pheroos.reference_runtime.mock"

    assert main(["trace", "latest", "--workspace", str(tmp_path)]) == 0
    trace_report = json.loads(capsys.readouterr().out)
    assert trace_report["ok"] is True
    assert trace_report["trace"]["run_id"] == run_report["run_id"]


def test_minimal_distro_manifest_is_no_key_json() -> None:
    manifest = json.loads((ROOT / "distros" / "minimal" / "pheroos.distro.json").read_text(encoding="utf-8"))

    assert manifest["schema_version"] == "pheroos.distro.v0.1"
    assert manifest["enabled_capabilities"] == ["toy-review"]
    assert manifest["network_access"] == "none"
    assert manifest["secrets_required"] == []
    assert all(driver.get("external_api_required") is not True for driver in manifest["drivers"])
