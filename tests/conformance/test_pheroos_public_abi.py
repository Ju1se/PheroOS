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


def test_cli_conformance_uses_public_manifest_loader_boundary() -> None:
    cli_text = (ROOT / "pheroos" / "cli.py").read_text(encoding="utf-8")
    manifest_text = (ROOT / "pheroos" / "protocol" / "capability_manifest.py").read_text(encoding="utf-8")

    assert "from runtime.capability_registry import load_manifest" not in cli_text
    assert "load_public_capability_manifest" in cli_text
    assert "from runtime." not in manifest_text


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
    assert conformance["checks"]["quorum_fallback"] == "PASS"
    assert conformance["checks"]["recovery_protocol"] == "PASS"
    assert conformance["checks"]["tool_contract"] == "PASS"
    assert conformance["checks"]["output_contract"] == "PASS"
    assert conformance["checks"]["trace_contract"] == "PASS"
    assert conformance["checks"]["domain_leakage_guard"] == "PASS"
    assert conformance["checks"]["core_runtime_domain_leakage_guard"] == "PASS"
    assert conformance["check_details"]["trace_contract"]["lineage_sources"] == [
        "candidate_set",
        "quorum_policy",
        "recovery_protocols",
        "output_policy",
        "evidence_policy",
        "tool_policy",
    ]


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


def test_conformance_fails_when_quorum_candidates_are_not_declared(tmp_path: Path) -> None:
    capability_dir = write_capability_fixture(
        tmp_path,
        "missing-candidates",
        protocol={
            "intents": ["toy_review"],
            "targets": [{"target": "decision:toy_publish"}],
            "quorum_policy": {
                "candidates": ["candidate:toy:approve"],
                "candidate_fallback": "candidate:toy:approve",
            },
        },
    )

    report = conformance_report(capability_dir)

    assert report["ok"] is False
    assert report["checks"]["candidate_declaration"] == "FAIL"
    assert report["check_details"]["candidate_declaration"]["referenced"] == ["candidate:toy:approve"]


def test_conformance_fails_when_quorum_fallback_is_not_safe(tmp_path: Path) -> None:
    capability_dir = write_capability_fixture(
        tmp_path,
        "unsafe-fallback",
        protocol=governed_protocol(
            candidates=[
                {"candidate": "candidate:toy:approve", "target": "decision:toy_publish"},
                {"candidate": "candidate:toy:defer", "target": "decision:toy_publish"},
            ],
            quorum_policy={
                "candidates": ["candidate:toy:approve", "candidate:toy:defer"],
                "candidate_fallback": "candidate:toy:defer",
            },
        ),
    )

    report = conformance_report(capability_dir)

    assert report["ok"] is False
    assert report["checks"]["quorum_fallback"] == "FAIL"
    assert "safe_fallback" in report["check_details"]["quorum_fallback"]["message"]


def test_conformance_fails_when_recovery_is_not_protocol_selectable(tmp_path: Path) -> None:
    protocol = governed_protocol()
    protocol["recovery_protocols"] = [
        {
            "id": "broken_recovery",
            "trigger_targets": ["gate:toy_evidence_gate"],
            "recovery_failure_candidate": "candidate:toy:insufficient_evidence",
        }
    ]
    capability_dir = write_capability_fixture(tmp_path, "broken-recovery", protocol=protocol)

    report = conformance_report(capability_dir)

    assert report["ok"] is False
    assert report["checks"]["recovery_protocol"] == "FAIL"
    assert "broken_recovery:missing_role_tag_or_tool_selector" in report["check_details"]["recovery_protocol"]["failures"]
    assert "broken_recovery:missing_success_condition" in report["check_details"]["recovery_protocol"]["failures"]


def test_conformance_fails_when_tool_surface_has_no_permissions(tmp_path: Path) -> None:
    capability_dir = write_capability_fixture(
        tmp_path,
        "unpermissioned-tool",
        permissions=[],
        tools=["toy_lookup"],
        protocol={
            "intents": ["toy_review"],
            "targets": [{"target": "gate:toy_evidence_gate"}],
            "tool_policy": {"allowed_tool_targets": ["tool:toy_lookup"]},
        },
    )

    report = conformance_report(capability_dir)

    assert report["ok"] is False
    assert report["checks"]["tool_contract"] == "FAIL"
    assert "explicit permissions" in report["check_details"]["tool_contract"]["message"]


def test_conformance_fails_when_output_policy_gives_writer_fact_authority(tmp_path: Path) -> None:
    protocol = governed_protocol()
    protocol["output_policy"] = {
        "writer_can_create_facts": True,
        "final_judge_required_checks": ["committed_candidate"],
    }
    capability_dir = write_capability_fixture(tmp_path, "writer-authority", protocol=protocol)

    report = conformance_report(capability_dir)

    assert report["ok"] is False
    assert report["checks"]["protocol_validation"] == "FAIL"
    assert report["checks"]["output_contract"] == "FAIL"
    assert any(item["code"] == "writer_can_create_facts" for item in report["diagnostics"])


def test_conformance_fails_when_trace_lineage_has_no_targets(tmp_path: Path) -> None:
    capability_dir = write_capability_fixture(
        tmp_path,
        "no-trace-targets",
        protocol={
            "intents": ["toy_review"],
            "output_policy": {"writer_can_create_facts": False},
        },
    )

    report = conformance_report(capability_dir)

    assert report["ok"] is False
    assert report["checks"]["trace_contract"] == "FAIL"
    assert "targets" in report["check_details"]["trace_contract"]["message"]


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
    forbidden = (
        "w" "rds",
        "value" "_investing",
        "formal" "_valuation",
        "b" "uy",
        "s" "ell",
        "w" "atch",
        "a" "void",
    )
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


def test_core_runtime_governance_surface_has_no_domain_specific_terms() -> None:
    forbidden = re.compile(
        r"\b("
        + "|".join(
            re.escape(term)
            for term in (
                "w" "rds",
                "value" "_investing",
                "formal" "_valuation",
                "b" "uy",
                "s" "ell",
                "w" "atch",
                "a" "void",
            )
        )
        + r")\b",
        re.IGNORECASE,
    )
    offenders = []
    paths = [
        ROOT / "runtime" / "os_kernel.py",
        ROOT / "runtime" / "runtime_context.py",
        ROOT / "runtime" / "swarm" / "quorum.py",
        ROOT / "runtime" / "swarm" / "recovery_engine.py",
        ROOT / "runtime" / "swarm" / "control_loop.py",
        ROOT / "runtime" / "swarm" / "candidate_registry.py",
        ROOT / "runtime" / "nodes" / "output_chain.py",
        ROOT / "runtime" / "writer_guardrails.py",
        ROOT / "runtime" / "final_judge_guardrails.py",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        match = forbidden.search(text)
        if match:
            offenders.append(f"{path.relative_to(ROOT).as_posix()}:{match.group(0)}")

    assert offenders == []


def write_capability_fixture(
    tmp_path: Path,
    capability_id: str,
    *,
    protocol: dict,
    permissions: list[str] | None = None,
    tools: list[str] | None = None,
) -> Path:
    capability_dir = tmp_path / capability_id
    capability_dir.mkdir()
    manifest = {
        "id": capability_id,
        "name": capability_id.replace("-", " ").title(),
        "version": "0.1.0",
        "description": "Conformance fixture.",
        "capability_types": ["toy.review"],
        "permissions": ["data:read"] if permissions is None else permissions,
        "risk_level": "low",
        "trust_level": "first_party_reviewed",
        "tools": [] if tools is None else tools,
        "protocol": protocol,
    }
    (capability_dir / "capability.json").write_text(json.dumps(manifest), encoding="utf-8")
    return capability_dir


def governed_protocol(
    *,
    candidates: list[dict] | None = None,
    quorum_policy: dict | None = None,
) -> dict:
    candidate_list = candidates or [
        {"candidate": "candidate:toy:approve", "target": "decision:toy_publish"},
        {
            "candidate": "candidate:toy:insufficient_evidence",
            "target": "decision:toy_publish",
            "safe_fallback": True,
        },
    ]
    return {
        "intents": ["toy_review"],
        "targets": [
            {"target": "gate:toy_evidence_gate"},
            {"target": "decision:toy_publish"},
        ],
        "candidates": candidate_list,
        "quorum_policy": quorum_policy
        or {
            "candidates": [item["candidate"] for item in candidate_list],
            "candidate_fallback": "candidate:toy:insufficient_evidence",
        },
        "recovery_protocols": [
            {
                "id": "toy_evidence_recovery",
                "trigger_targets": ["gate:toy_evidence_gate"],
                "allowed_agent_roles": ["toy_scout"],
                "recovery_success_condition": "context.full_text_count > 0",
                "recovery_failure_candidate": "candidate:toy:insufficient_evidence",
            }
        ],
        "output_policy": {
            "writer_can_create_facts": False,
            "final_judge_required_checks": ["committed_candidate"],
        },
    }
