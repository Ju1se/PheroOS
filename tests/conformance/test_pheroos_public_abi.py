from __future__ import annotations

import json
import re
from pathlib import Path

from pheroos.cli import conformance_report, validate_capability_path
from pheroos.drivers import DataProviderDriverDescriptor, ToolDriverDescriptor
from pheroos.protocol.manifest import load_capability_protocol
from pheroos.protocol.schema import schema_paths


ROOT = Path(__file__).resolve().parents[2]


def test_public_identity_is_pheroos_first() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert 'name = "pheroos"' in pyproject
    assert "Protocol-governed AI-as-OS kernel" in pyproject
    assert '"wrds"' not in pyproject
    assert readme.startswith("# PheroOS")
    assert "PheroOS Kernel + PheroOS Protocol" in readme
    assert ("Local " + "Agent Platform") not in readme


def test_schema_files_are_valid_json_objects() -> None:
    schemas = schema_paths()

    assert set(schemas) == {"protocol", "capability", "signal", "evidence", "trace"}
    for name, path in schemas.items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["$schema"].startswith("https://json-schema.org/")
        assert payload["$id"].endswith(f"pheroos.{name}.v0.1.schema.json")
        assert payload["type"] == "object"


def test_protocol_package_boundary_has_no_runtime_host_or_provider_imports() -> None:
    forbidden = re.compile(r"\b(fastapi|langgraph|tools\.wrds_tools|openai|anthropic|zhipuai|minimax)\b")
    offenders = []
    for path in sorted((ROOT / "pheroos" / "protocol").rglob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        if forbidden.search(text):
            offenders.append(path.relative_to(ROOT).as_posix())

    assert offenders == []


def test_protocol_loader_wraps_existing_runtime_manifest_validation() -> None:
    loaded = load_capability_protocol(ROOT / "capabilities" / "toy-review")

    assert loaded.ok is True
    assert loaded.capability_id == "toy-review"
    assert loaded.protocol["schema_version"] == "pheroos.capability_protocol.v1"


def test_cli_validation_and_conformance_reports_for_valid_capability() -> None:
    path = ROOT / "capabilities" / "toy-review" / "capability.json"

    validation = validate_capability_path(path)
    conformance = conformance_report(path)

    assert validation["ok"] is True
    assert validation["checks"]["manifest_schema"] == "PASS"
    assert conformance["ok"] is True
    assert conformance["conformance_level"] == "pheroos.v0.1.basic"
    assert conformance["checks"]["candidate_declaration"] == "PASS"


def test_cli_validation_reports_protocol_errors(tmp_path: Path) -> None:
    capability_dir = tmp_path / "bad-capability"
    capability_dir.mkdir()
    manifest = {
        "id": "bad-capability",
        "name": "Bad Capability",
        "version": "0.1.0",
        "description": "Invalid protocol references.",
        "capability_types": ["bad.review"],
        "permissions": ["data:read"],
        "risk_level": "low",
        "trust_level": "first_party_reviewed",
        "protocol": {
            "intents": ["bad_review"],
            "targets": [{"target": "gate:known"}],
            "candidates": [
                {
                    "candidate": "candidate:bad:approve",
                    "target": "gate:missing",
                }
            ],
        },
    }
    (capability_dir / "capability.json").write_text(json.dumps(manifest), encoding="utf-8")

    report = validate_capability_path(capability_dir)

    assert report["ok"] is False
    assert report["checks"]["protocol_validation"] == "FAIL"
    assert any(item["code"] == "candidate_target_unknown" for item in report["diagnostics"])


def test_driver_descriptors_are_structured_contracts() -> None:
    tool = ToolDriverDescriptor(
        tool_id="mock_lookup",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        permissions=["data:read"],
    ).to_dict()
    data = DataProviderDriverDescriptor(
        provider_id="mock-provider",
        dataset_kind="toy_evidence",
        coverage={"scope": "fixture"},
    ).to_dict()

    assert tool["driver_kind"] == "tool"
    assert tool["side_effect_class"] == "read_only"
    assert data["driver_kind"] == "data_provider"
    assert data["provider_id"] == "mock-provider"
    assert data["dataset_kind"] == "toy_evidence"


def test_new_public_abi_surface_has_no_domain_specific_core_terms() -> None:
    forbidden = ("wrds", "value_investing", "formal_valuation", "buy", "sell", "watch", "avoid")
    offenders = []
    paths = [
        *sorted((ROOT / "pheroos").rglob("*.py")),
        *sorted((ROOT / "docs" / "kernel").rglob("*.md")),
        *sorted((ROOT / "schemas").rglob("*.json")),
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        for term in forbidden:
            if term in text:
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{term}")

    assert offenders == []
