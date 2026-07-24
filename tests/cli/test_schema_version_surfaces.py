from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pheroos.cli.main import main, schema_for, wire_validation_payload
from pheroos.drivers import DRIVER_DESCRIPTOR_VERSION_V2
from pheroos.kernel import (
    KERNEL_PLAN_VERSION_V2,
    RUNTIME_SCOPE_VERSION,
    OSPlan,
    OSPlanDocument,
    RuntimeScope,
)
from pheroos.protocol import (
    CAPABILITY_SCHEMA_V1,
    CAPABILITY_SCHEMA_V2,
    CAPABILITY_SCHEMA_V3,
    PROTOCOL_SCHEMA_V1,
    PROTOCOL_SCHEMA_V2,
    PROTOCOL_SCHEMA_V3,
)


ROOT = Path(__file__).resolve().parents[2]


def test_legacy_schema_aliases_stay_pinned_while_v2_ids_are_distinct() -> None:
    assert schema_for("capability") == schema_for("capability-v1")
    assert schema_for("protocol") == schema_for("protocol-v1")
    assert schema_for("driver") == schema_for("driver-v1")
    assert schema_for("kernel") == schema_for("kernel-v1")
    assert schema_for("capability-v2")["$id"].endswith("capability-v2.schema.json")
    assert schema_for("protocol-v2")["$id"].endswith("protocol-v2.schema.json")
    assert schema_for("capability-v3")["$id"].endswith("capability-v3.schema.json")
    assert schema_for("protocol-v3")["$id"].endswith("protocol-v3.schema.json")
    assert schema_for("driver-v2")["$id"].endswith("driver-v2.schema.json")
    assert schema_for("kernel-v2")["$id"].endswith("kernel-v2.schema.json")
    assert schema_for("runtime-scope-v1")["$id"].endswith(
        "runtime-scope-v1.schema.json"
    )


def test_schema_list_reports_alias_status_version_and_digest(capsys: Any) -> None:
    code = main(["schema", "list"])
    payload = json.loads(capsys.readouterr().out)
    entries = {item["surface"]: item for item in payload["schemas"]}

    assert code == 0
    assert entries["driver"]["status"] == "legacy-alias"
    assert entries["capability"]["schema_version"] == CAPABILITY_SCHEMA_V1
    assert entries["capability-v2"]["schema_version"] == CAPABILITY_SCHEMA_V2
    assert entries["capability-v3"]["schema_version"] == CAPABILITY_SCHEMA_V3
    assert entries["protocol"]["schema_version"] == PROTOCOL_SCHEMA_V1
    assert entries["protocol-v2"]["schema_version"] == PROTOCOL_SCHEMA_V2
    assert entries["protocol-v3"]["schema_version"] == PROTOCOL_SCHEMA_V3
    assert entries["capability-v3"]["status"] == "draft"
    assert entries["protocol-v3"]["status"] == "draft"
    assert entries["driver-v1"]["status"] == "legacy-frozen"
    assert entries["driver-v2"]["schema_version"] == (DRIVER_DESCRIPTOR_VERSION_V2)
    assert entries["kernel-v2"]["schema_version"] == KERNEL_PLAN_VERSION_V2
    assert entries["kernel-v2"]["sha256"].startswith("sha256:")
    assert entries["runtime-scope-v1"]["status"] == "draft"
    assert entries["runtime-scope-v1"]["schema_version"] == RUNTIME_SCOPE_VERSION


def test_cli_wire_validation_supports_driver_and_kernel_v1_v2(
    tmp_path: Path,
) -> None:
    driver_v1 = ROOT / "tests/fixtures/schema-v1/driver-descriptor.json"
    kernel_v1 = ROOT / "tests/fixtures/schema-v1/kernel-plan.json"
    driver_v2 = tmp_path / "driver-v2.json"
    driver_v2.write_text(
        json.dumps(
            {
                "descriptor_version": DRIVER_DESCRIPTOR_VERSION_V2,
                "id": "driver:strict",
                "kind": "tool",
                "version": "1",
                "capabilities": ["tool:invoke"],
                "permissions": ["driver:invoke"],
                "config_ref": "",
                "extensions": {},
            }
        )
    )
    kernel_v2 = tmp_path / "kernel-v2.json"
    kernel_v2.write_text(
        json.dumps(
            OSPlanDocument(
                OSPlan(
                    tenant_id="tenant:strict",
                    request_id="request:strict",
                    run_id="run:strict",
                    capability_resolutions=(),
                    runtime_ready=False,
                    degraded=True,
                )
            ).to_dict()
        )
    )

    assert wire_validation_payload("driver", driver_v1)["ok"] is True
    assert wire_validation_payload("driver-v1", driver_v1)["ok"] is True
    assert wire_validation_payload("driver-v2", driver_v2)["ok"] is True
    assert wire_validation_payload("kernel", kernel_v1)["ok"] is True
    assert wire_validation_payload("kernel-v1", kernel_v1)["ok"] is True
    assert wire_validation_payload("kernel-v2", kernel_v2)["ok"] is True


def test_cli_runtime_scope_dispatch_uses_the_authoritative_parser(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime-scope-v1.json"
    payload = RuntimeScope("tenant-a", "run-1", "request-1").to_dict()
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert wire_validation_payload("runtime-scope-v1", path)["ok"] is True

    path.write_text(
        json.dumps(payload | {"scope_ref": "sha256:" + "0" * 64}),
        encoding="utf-8",
    )
    report = wire_validation_payload("runtime-scope-v1", path)
    assert report["ok"] is False
    assert "scope_ref" in report["diagnostics"][0]["message"]


def test_cli_wire_validation_supports_protocol_schema_document_v1_v2(
    tmp_path: Path,
) -> None:
    capability = ROOT / "examples/toy-protocol/capability.json"
    protocol_payload = json.loads(capability.read_text())["protocol"]
    protocol = tmp_path / "protocol.json"

    # Avoid a second long-lived fixture: the CLI accepts any caller-owned JSON
    # document, while this test keeps the source manifest canonical.
    assert isinstance(protocol_payload, dict)
    protocol.write_text(json.dumps(protocol_payload))
    assert wire_validation_payload("capability", capability)["ok"] is True
    assert wire_validation_payload("capability-v1", capability)["ok"] is True
    assert wire_validation_payload("capability-v2", capability)["ok"] is True
    assert wire_validation_payload("protocol", protocol)["ok"] is True
    assert wire_validation_payload("protocol-v1", protocol)["ok"] is True
    assert wire_validation_payload("protocol-v2", protocol)["ok"] is True


def test_cli_wire_validation_supports_explicit_scoped_v3_declarations(
    tmp_path: Path,
) -> None:
    capability = ROOT / "examples/scoped-output-protocol/capability.json"
    protocol_payload = json.loads(capability.read_text())["protocol"]
    assert isinstance(protocol_payload, dict)

    assert wire_validation_payload("capability-v3", capability)["ok"] is True

    protocol = tmp_path / "protocol-v3.json"
    protocol.write_text(json.dumps(protocol_payload), encoding="utf-8")
    assert wire_validation_payload("protocol-v3", protocol)["ok"] is True


def test_cli_wire_validation_preserves_structured_version_failures(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.json"
    missing.write_text(json.dumps({"id": "driver:x", "kind": "tool", "version": "1"}))
    cross = tmp_path / "cross.json"
    cross.write_text(json.dumps({"plan_version": DRIVER_DESCRIPTOR_VERSION_V2}))

    driver_report = wire_validation_payload("driver-v2", missing)
    kernel_report = wire_validation_payload("kernel-v2", cross)

    assert driver_report["ok"] is False
    assert driver_report["diagnostics"][0]["code"] == (
        "driver_descriptor_version_missing"
    )
    assert driver_report["diagnostics"][0]["field_path"] == "$.descriptor_version"
    assert kernel_report["ok"] is False
    assert kernel_report["diagnostics"][0]["code"] == (
        "kernel_plan_version_unsupported"
    )
    assert kernel_report["diagnostics"][0]["field_path"] == "$.plan_version"
