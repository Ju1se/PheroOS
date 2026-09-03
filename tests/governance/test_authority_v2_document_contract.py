from __future__ import annotations

import ast
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs/protocol/authority-v2-decision.md"
THREAT_MODEL_PATH = ROOT / "docs/protocol/authority-trust-model-v2.md"
MIGRATION_PATH = ROOT / "docs/protocol/authority-v2-migration.md"
STORE_PATH = ROOT / "docs/protocol/authority-store-v2.md"
RUNTIME_INTEGRATION_PATH = ROOT / "docs/protocol/runtime-integration.md"
PUBLIC_INVENTORY_PATH = ROOT / "pheroos/conformance/abi/public-python-api-v1.json"

NEGATIVE_MATRIX_START = "<!-- authority-v2-negative-matrix:start -->"
NEGATIVE_MATRIX_END = "<!-- authority-v2-negative-matrix:end -->"

EXPECTED_VERSION_REGISTRY = (
    ("Protocol semantics", "pheroos.protocol.v2"),
    ("Protocol schema selector", "pheroos-protocol-schema-v3"),
    ("Capability schema selector", "pheroos-capability-schema-v3"),
    ("Authority policy", "pheroos-scoped-authority-policy-v2"),
    ("Local profile", "pheroos-scoped-authority-local-v2"),
    ("Authenticated profile", "pheroos-scoped-authority-authenticated-v2"),
    ("Wire", "pheroos-authority-wire-v2"),
    ("Canonicalization", "pheroos-authority-canonical-v2"),
    ("Authority schema selector", "pheroos-authority-schema-v2"),
    (
        "Authority read-set schema",
        "pheroos-governance-authority-read-set-v2",
    ),
    ("Ledger", "pheroos-governance-authority-ledger-v2"),
    ("StateStore", "pheroos-governance-state-store-v2"),
    (
        "StateStore Conformance",
        "pheroos-governance-state-store-conformance-v2",
    ),
    ("Atomic Trace batch", "pheroos-governance-trace-batch-v2"),
    (
        "Grant-verifier Conformance",
        "pheroos-issuer-grant-verifier-conformance-v2",
    ),
    ("Scoped authority TCK", "pheroos-scoped-authority-tck-v2"),
    ("Source profile", "pheroos-source-v4"),
)

EXPECTED_SCHEMA_REGISTRY = (
    (
        "Protocol",
        "protocol-v3.schema.json",
        "https://pheroos.dev/schemas/protocol-v3.schema.json",
        "pheroos-protocol-schema-v3",
    ),
    (
        "Capability",
        "capability-v3.schema.json",
        "https://pheroos.dev/schemas/capability-v3.schema.json",
        "pheroos-capability-schema-v3",
    ),
    (
        "Authority wire",
        "authority-v2.schema.json",
        "https://pheroos.dev/schemas/authority-v2.schema.json",
        "pheroos-authority-schema-v2",
    ),
    (
        "Scoped authority TCK",
        "scoped-authority-tck-v2.schema.json",
        "https://pheroos.dev/schemas/scoped-authority-tck-v2.schema.json",
        "pheroos-scoped-authority-tck-v2",
    ),
)

EXPECTED_DISPOSITIONS = {
    "COMMITTED": "committed",
    "DENIED": "denied",
    "RETRY_REQUIRED": "retry_required",
    "FINALITY_UNAVAILABLE": "finality_unavailable",
    "INVALID": "invalid",
}
EXPECTED_POSITIONS = {
    "CURRENT": "current",
    "SUPERSEDED": "superseded",
    "SEALED": "sealed",
}

EXPECTED_DIAGNOSTICS = (
    "authority_profile_unsupported",
    "authority_session_required",
    "authority_session_store_mismatch",
    "authority_scope_mismatch",
    "authority_operation_denied",
    "authority_binding_mismatch",
    "authority_grant_unverified",
    "authority_grant_expired",
    "authority_grant_revoked",
    "governance_read_set_invalid",
    "governance_read_set_stale",
    "governance_transition_conflict",
    "governance_domain_sealed",
    "governance_finality_unavailable",
    "governance_committed_transition_invalid",
    "governance_action_not_authorized",
    "governance_trace_lineage_invalid",
)
EXPECTED_DIAGNOSTIC_DISPOSITIONS = {
    "authority_profile_unsupported": "INVALID",
    "authority_session_required": "DENIED",
    "authority_session_store_mismatch": "INVALID",
    "authority_scope_mismatch": "INVALID",
    "authority_operation_denied": "DENIED",
    "authority_binding_mismatch": "INVALID",
    "authority_grant_unverified": "DENIED",
    "authority_grant_expired": "DENIED",
    "authority_grant_revoked": "DENIED",
    "governance_read_set_invalid": "INVALID",
    "governance_read_set_stale": "RETRY_REQUIRED",
    "governance_transition_conflict": "INVALID",
    "governance_domain_sealed": "DENIED",
    "governance_finality_unavailable": "FINALITY_UNAVAILABLE",
    "governance_committed_transition_invalid": "INVALID",
    "governance_action_not_authorized": "DENIED",
    "governance_trace_lineage_invalid": "INVALID",
}

EXPECTED_AUTHORITY_LEVEL_FUNCTIONS = (
    "assemble_portable_distributed_commit_certificate",
    "assess_optimal_commit",
    "bind_evidence",
    "epoch_transition_certificate_body_root",
    "evidence_commit_certificate_body_root",
    "issue_action_permission",
    "issue_commit_evaluation_context",
    "issue_counterevidence_disposition",
    "outcome_certificate_body_root",
    "verify_challenge_attestation",
    "verify_observation_attestation",
    "verify_principal_attestation",
    "verify_signal_input",
    "verify_stop_resolution",
)
AUTHORITY_DIAGNOSTIC_OWNER = "pheroos.protocol.authority_v2.AuthorityDiagnosticCodeV2"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"expected one start marker: {start}"
    assert text.count(end) == 1, f"expected one end marker: {end}"
    before, remainder = text.split(start, 1)
    selected, after = remainder.split(end, 1)
    assert before or start.startswith("#")
    assert after or end.endswith("\n")
    return selected


def _markdown_rows(section: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [cell.strip() for cell in line[1:-1].split("|")]
        if all(cell and set(cell) <= {"-", ":"} for cell in cells):
            continue
        rows.append(cells)
    return rows


def _code(cell: str) -> str:
    assert cell.startswith("`") and cell.endswith("`")
    return cell[1:-1]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        assert key not in result, f"duplicate JSON key: {key}"
        result[key] = value
    return result


def _negative_matrix() -> dict[str, Any]:
    text = _read(THREAT_MODEL_PATH)
    section = _between(text, NEGATIVE_MATRIX_START, NEGATIVE_MATRIX_END)
    match = re.fullmatch(r"\s*```json\s*\n(.*?)\n```\s*", section, re.DOTALL)
    assert match is not None
    payload = json.loads(
        match.group(1),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=lambda value: (_ for _ in ()).throw(
            AssertionError(f"non-finite JSON constant: {value}")
        ),
    )
    assert isinstance(payload, dict)
    return payload


def _migration_ah_diagnostics() -> dict[str, tuple[str, ...]]:
    migration = _read(MIGRATION_PATH)
    section = _between(
        migration,
        "### 7.2 AH-to-diagnostic and negative-test coverage",
        "Reader/selector negative cases remain mandatory:",
    )
    rows = _markdown_rows(section)
    assert rows[0] == [
        "Threat test",
        "Invariant",
        "Required concrete diagnostics",
        "Required negative case",
    ]
    expected_invariants = [f"AH-{number:03d}" for number in range(1, 15)]
    result: dict[str, tuple[str, ...]] = {}
    for row, expected_invariant in zip(rows[1:], expected_invariants, strict=True):
        test_id = _code(row[0])
        invariant_id = row[1]
        assert invariant_id == expected_invariant
        assert test_id == f"AUTH-V2-{invariant_id}"
        diagnostic_cell = row[2]
        diagnostics = (
            EXPECTED_DIAGNOSTICS
            if diagnostic_cell.startswith("all 17")
            else tuple(re.findall(r"`([^`]+)`", diagnostic_cell))
        )
        assert diagnostics
        assert len(diagnostics) == len(set(diagnostics))
        assert set(diagnostics) <= set(EXPECTED_DIAGNOSTICS)
        result[invariant_id] = diagnostics
    assert len(rows[1:]) == 14
    return result


def _inventory_authority_level_functions() -> tuple[str, ...]:
    inventory = json.loads(_read(PUBLIC_INVENTORY_PATH))
    exports = inventory["packages"]["pheroos.governance"]["exports"]
    return tuple(
        export["name"]
        for export in exports
        if export["kind"] == "function"
        and any(
            parameter["name"] == "authority"
            and parameter["annotation"] == "AuthorityLevel"
            for parameter in export["signature"]["parameters"]
        )
    )


def _ast_authority_level_functions() -> dict[str, tuple[str, ...]]:
    locations: dict[str, list[str]] = {}
    for path in sorted((ROOT / "pheroos/governance").rglob("*.py")):
        tree = ast.parse(_read(path), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_"):
                continue
            arguments = (
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            )
            if any(
                argument.arg == "authority"
                and argument.annotation is not None
                and ast.unparse(argument.annotation) == "AuthorityLevel"
                for argument in arguments
            ):
                locations.setdefault(node.name, []).append(
                    path.relative_to(ROOT).as_posix()
                )
    return {name: tuple(paths) for name, paths in locations.items()}


def test_adr_frozen_version_and_schema_registries_are_exact() -> None:
    text = _read(ADR_PATH)
    version_section = _between(
        text,
        "### Frozen version registry",
        "The existing `pheroos.trace.TraceEvent` remains",
    )
    version_rows = _markdown_rows(version_section)
    assert version_rows[0] == ["Axis", "Exact identifier", "Decision"]
    observed_versions = tuple((row[0], _code(row[1])) for row in version_rows[1:])

    schema_section = _between(
        text,
        "### Schema files and `$id` values",
        "Protocol and Capability schema-document v3 require",
    )
    schema_rows = _markdown_rows(schema_section)
    assert schema_rows[0] == [
        "Surface",
        "File",
        "Exact `$id`",
        "Selector/discriminator",
    ]
    observed_schemas = tuple(
        (row[0], _code(row[1]), _code(row[2]), _code(row[3])) for row in schema_rows[1:]
    )

    assert observed_versions == EXPECTED_VERSION_REGISTRY
    assert observed_schemas == EXPECTED_SCHEMA_REGISTRY


def test_adr_commit_disposition_and_position_wire_sets_are_closed() -> None:
    text = _read(ADR_PATH)
    disposition_section = _between(
        text,
        "`GovernanceCommitDispositionV2` is a closed wire enum:",
        "`GovernanceCommitPositionV2` is a separate closed wire enum:",
    )
    position_section = _between(
        text,
        "`GovernanceCommitPositionV2` is a separate closed wire enum:",
        "Position is present only after committed inclusion has been verified.",
    )

    disposition_rows = _markdown_rows(disposition_section)
    position_rows = _markdown_rows(position_section)
    assert disposition_rows[0] == ["Python label", "Wire value", "Meaning"]
    assert position_rows[0] == ["Python label", "Wire value", "Meaning"]
    dispositions = {_code(row[0]): _code(row[1]) for row in disposition_rows[1:]}
    positions = {_code(row[0]): _code(row[1]) for row in position_rows[1:]}

    assert dispositions == EXPECTED_DISPOSITIONS
    assert positions == EXPECTED_POSITIONS
    assert "RETIRED" not in positions


def test_trust_model_negative_matrix_has_every_ah_invariant_once() -> None:
    matrix = _negative_matrix()
    assert set(matrix) == {
        "format_version",
        "policy",
        "profiles",
        "diagnostic_dispositions",
        "cases",
    }
    assert matrix["format_version"] == 1
    assert matrix["policy"] == "pheroos-scoped-authority-policy-v2"
    assert matrix["profiles"] == [
        "pheroos-scoped-authority-local-v2",
        "pheroos-scoped-authority-authenticated-v2",
    ]
    assert matrix["diagnostic_dispositions"] == (EXPECTED_DIAGNOSTIC_DISPOSITIONS)

    cases = matrix["cases"]
    assert isinstance(cases, list)
    assert len(cases) == 14
    expected_invariants = [f"AH-{number:03d}" for number in range(1, 15)]
    assert [case["invariant_id"] for case in cases] == expected_invariants
    assert len({case["invariant_id"] for case in cases}) == 14

    for case in cases:
        assert set(case) == {
            "invariant_id",
            "owner",
            "expected_dispositions",
            "denial_code",
            "diagnostics",
            "trace_rules",
            "negative_test_id",
        }
        assert case["negative_test_id"] == f"AUTH-V2-{case['invariant_id']}"
        assert case["owner"]
        assert case["denial_code"]
        assert case["expected_dispositions"]
        assert len(case["expected_dispositions"]) == len(
            set(case["expected_dispositions"])
        )
        assert set(case["expected_dispositions"]) <= set(EXPECTED_DISPOSITIONS)
        assert case["diagnostics"]
        assert len(case["diagnostics"]) == len(set(case["diagnostics"]))
        assert set(case["diagnostics"]) <= set(EXPECTED_DIAGNOSTICS)
        mapped_dispositions = {
            EXPECTED_DIAGNOSTIC_DISPOSITIONS[diagnostic]
            for diagnostic in case["diagnostics"]
        }
        if case["invariant_id"] == "AH-006":
            mapped_dispositions.add("COMMITTED")
        assert set(case["expected_dispositions"]) == mapped_dispositions
        assert case["trace_rules"]
        assert set(case["trace_rules"]) <= {
            "TR-0",
            "TR-1",
            "TR-2",
            "TR-3",
            "TR-4",
        }


def test_draft_diagnostic_registry_and_matrix_cover_exactly_17() -> None:
    migration = _read(MIGRATION_PATH)
    migration_section = _between(
        migration,
        "### 7.1 Exact Draft diagnostic registry",
        "The registry uses only the five ADR commit dispositions.",
    )
    rows = re.findall(
        r"^\| `AUTH-V2-DIAG-(\d{3})` \| `([^`]+)` \| `([A-Z_]+)` \|",
        migration_section,
        re.MULTILINE,
    )
    assert [number for number, _, _ in rows] == [
        f"{number:03d}" for number in range(1, 18)
    ]
    assert tuple(diagnostic for _, diagnostic, _ in rows) == EXPECTED_DIAGNOSTICS
    diagnostic_dispositions = {
        diagnostic: disposition for _, diagnostic, disposition in rows
    }
    assert diagnostic_dispositions == EXPECTED_DIAGNOSTIC_DISPOSITIONS
    assert diagnostic_dispositions["governance_read_set_stale"] == ("RETRY_REQUIRED")
    assert diagnostic_dispositions["governance_transition_conflict"] == "INVALID"
    assert diagnostic_dispositions["governance_finality_unavailable"] == (
        "FINALITY_UNAVAILABLE"
    )

    threat_model = _read(THREAT_MODEL_PATH)
    threat_registry = _between(
        threat_model,
        "The implementation-oriented stable diagnostic registry is exactly:",
        "These 17 identifiers are closed for the selected v2 profiles.",
    )
    threat_diagnostics = tuple(
        match.group(1)
        for match in re.finditer(
            r"^\| `([^`]+)` \| .+ \|$",
            threat_registry,
            re.MULTILINE,
        )
    )
    assert threat_diagnostics == EXPECTED_DIAGNOSTICS

    matrix = _negative_matrix()
    assert matrix["diagnostic_dispositions"] == diagnostic_dispositions
    matrix_diagnostics = {
        diagnostic for case in matrix["cases"] for diagnostic in case["diagnostics"]
    }
    matrix_dispositions = {
        disposition
        for case in matrix["cases"]
        for disposition in case["expected_dispositions"]
    }
    assert matrix_diagnostics == set(EXPECTED_DIAGNOSTICS)
    assert matrix_dispositions == set(EXPECTED_DISPOSITIONS)


def test_migration_and_machine_matrix_ah_diagnostic_mappings_are_identical() -> None:
    migration_mapping = _migration_ah_diagnostics()
    matrix = _negative_matrix()
    matrix_mapping = {
        case["invariant_id"]: tuple(case["diagnostics"]) for case in matrix["cases"]
    }

    assert matrix_mapping == migration_mapping


def test_migration_cohort_matches_public_inventory_and_source_ast() -> None:
    migration = _read(MIGRATION_PATH)
    cohort_section = _between(
        migration,
        "## 4. The 14-symbol `authority: AuthorityLevel` cohort",
        "### 4.1 Deprecation decision",
    )
    match = re.search(r"```text\n(.*?)\n```", cohort_section, re.DOTALL)
    assert match is not None
    documented = tuple(
        line.strip() for line in match.group(1).splitlines() if line.strip()
    )
    inventory = _inventory_authority_level_functions()
    ast_locations = _ast_authority_level_functions()

    assert len(documented) == 14
    assert len(set(documented)) == 14
    assert documented == EXPECTED_AUTHORITY_LEVEL_FUNCTIONS
    assert inventory == EXPECTED_AUTHORITY_LEVEL_FUNCTIONS
    assert set(EXPECTED_AUTHORITY_LEVEL_FUNCTIONS) <= set(ast_locations)
    assert all(
        len(ast_locations[name]) == 1 for name in EXPECTED_AUTHORITY_LEVEL_FUNCTIONS
    )


def test_authority_v2_stability_dispatch_and_version_axis_gates_are_explicit() -> None:
    adr = " ".join(_read(ADR_PATH).split())
    migration = " ".join(_read(MIGRATION_PATH).split())
    threat_model = " ".join(_read(THREAT_MODEL_PATH).split())
    store = " ".join(_read(STORE_PATH).split())
    runtime = " ".join(_read(RUNTIME_INTEGRATION_PATH).split())

    verifier_gate = (
        "Promotion of the authenticated production path to Stable requires at "
        "least one independent external adapter to pass "
        "`pheroos-issuer-grant-verifier-conformance-v2`."
    )
    assert verifier_gate in adr
    assert (
        "Promotion of the authenticated production path to Stable requires at "
        "least one independent external verifier adapter to pass "
        "`pheroos-issuer-grant-verifier-conformance-v2`."
    ) in migration
    assert "The version ADR must decide whether an external verifier" not in (
        threat_model
    )

    assert (
        "The local scoped-authority profile is an active Draft selection; it "
        "never falls back to a v1 reader or assurance profile."
    ) in adr
    assert "### 2.4 Strict no-fallback rule" in migration
    assert (
        "`pheroos.protocol.v2` with the exact local profile is therefore active Draft."
    ) in migration
    assert "There is no fallback from authenticated to local." in adr

    assert (
        "`pheroos-protocol-schema-v2` and `pheroos-capability-schema-v2` are "
        "strict schema-document versions for payloads whose semantic "
        "discriminator remains `pheroos.protocol.v1`;"
    ) in adr
    assert "They are not authority v2" in migration

    assert (
        "Status: **Draft, independently audited, Conformance-backed, and used "
        "by the active local scoped-authority profile**"
    ) in store
    assert "owned by the future" not in adr
    assert "### 7.1 Exact Stable diagnostic registry" not in migration
    assert "WP-08 must add them to the owning closed registry" not in migration
    assert "The v2 readers remain unsupported." not in migration
    assert "Before WP-02 or WP-03 implementation begins" not in threat_model
    assert (
        "The exact local `pheroos.protocol.v2` scoped-authority profile is active "
        "as a Draft protocol-core composition."
    ) in runtime
    assert (
        "The Draft `GovernanceStateReaderV2` StateStore contract and reference "
        "reader are implemented and Conformance-backed"
    ) in migration


def test_delivery_is_unconditional_and_not_a_current_authority_action() -> None:
    threat_model = _read(THREAT_MODEL_PATH)
    classification_section = _between(
        threat_model,
        "## 6. Record classification",
        "## 7. Required envelope and read-set bindings",
    )
    rows = _markdown_rows(classification_section)
    current_action = next(
        row for row in rows if row[0] == "Current action authorization"
    )
    assert current_action[2] == (
        "Authorizes exactly one declared `publish` or `execute` external effect"
    )
    assert "delivery" not in current_action[2].lower()

    binding_section = _between(
        threat_model,
        "## 7. Required envelope and read-set bindings",
        "## 8. Historical validity, currentness, and sealing",
    )
    action_binding = re.search(
        r"- action class \((.*?)\), action reference, and exact",
        binding_section,
        re.DOTALL,
    )
    assert action_binding is not None
    assert re.findall(r"`([^`]+)`", action_binding.group(1)) == [
        "publish",
        "execute",
    ]
    assert "deliver" not in action_binding.group(1).lower()
    assert (
        "Terminal outcome delivery is not an action class or external authority effect."
    ) in " ".join(binding_section.split())

    diagnostic_section = _between(
        threat_model,
        "The implementation-oriented stable diagnostic registry is exactly:",
        "These 17 identifiers are closed for the selected v2 profiles.",
    )
    diagnostic_rows = _markdown_rows(diagnostic_section)
    action_diagnostic = next(
        row for row in diagnostic_rows if row[0] == "`governance_action_not_authorized`"
    )
    assert action_diagnostic[1] == (
        "Publish or execute effect lacks exact current action authority"
    )
    assert "delivery" not in action_diagnostic[1].lower()

    availability_section = " ".join(
        _between(
            threat_model,
            "## 13. Availability and final-output rule",
            "## 14. Explicit non-goals",
        ).split()
    )
    assert "authorize delivery" not in availability_section.lower()
    assert "independently authorize publication or execution." in (availability_section)
    assert (
        "Every Governance-issued terminal outcome is unconditionally delivery-eligible"
    ) in availability_section
    assert (
        "`governance_action_not_authorized`; that diagnostic applies only to "
        "publish or execute."
    ) in availability_section
    assert "never result gates and never authority" in availability_section
    assert "cannot reverse the commit or suppress return of the outcome" in (
        availability_section
    )


def test_wp02_freezes_one_total_public_commit_view() -> None:
    plan = _read(ROOT / "docs/process/production-readiness-hardening-goal-plan.md")
    wp02 = _between(
        plan,
        "## 8. WP-02 — StateStore v2、historical finality 与 typed failures",
        "## 9. WP-03 — Scope-bound issuer capability",
    )
    normalized = " ".join(wp02.split())

    assert (
        "load_commit_view_v2(\n"
        "    scope_ref,\n"
        "    stream_ref,\n"
        "    transition_id,\n"
        "    *,\n"
        "    expected_receipt_root=None,\n"
        ") -> GovernanceCommitViewV2"
    ) in wp02
    assert (
        "`load_commit_view_v2()` 是公开的 total、单次一致性快照读取。"
    ) in normalized
    assert not re.search(
        r"load_committed_transition\s*\([^)]*\)\s*->[^\n`]*\|\s*None",
        wp02,
    )
    assert not re.search(
        r"inspect_commit_position\s*\([^)]*\)\s*->\s*(?:enum|GovernanceCommitPositionV2)",
        wp02,
    )

    recovery_section = _between(
        wp02,
        "崩溃恢复路径：",
        "不得再用“receipt 必须等于当前 head”判断 commit 是否发生。",
    )
    assert "load_commit_view_v2" in recovery_section
    assert "load_committed_transition" not in recovery_section
    assert "inspect_commit_position" not in recovery_section

    assert "`disposition=COMMITTED` 时 `failure is None`" in normalized
    assert (
        "任何非 `COMMITTED` disposition 必须带一个由 stable diagnostic 与 "
        "canonical path 组成的 `GovernanceFailureV2`"
    ) in normalized
    assert ("`COMMITTED` 才能携带 committed transition 与 position") in normalized
    assert (
        "可达 disposition 只有 `COMMITTED`、`INVALID` 与 `FINALITY_UNAVAILABLE`"
    ) in normalized


def test_denied_audit_is_non_authoritative_in_every_wp01_contract() -> None:
    adr_section = _between(
        _read(ADR_PATH),
        "### Typed commit outcome and historical position",
        "### Same-process boundary",
    )
    trust_section = _between(
        _read(THREAT_MODEL_PATH),
        "## 10. Trace and audit rules",
        "## 11. AH invariant and negative-test registry",
    )
    migration_section = "`DENIED` never creates an authority receipt" + _between(
        _read(MIGRATION_PATH),
        "`DENIED` never creates an authority receipt",
        "All diagnostic payloads must carry a stable code",
    )
    plan_section = _between(
        _read(ROOT / "docs/process/production-readiness-hardening-goal-plan.md"),
        "### 7.3 验收门",
        "## 8. WP-02 — StateStore v2、historical finality 与 typed failures",
    )

    for section in (
        adr_section,
        trust_section,
        migration_section,
        plan_section,
    ):
        lowered = " ".join(section.split()).lower()
        assert "denied" in lowered
        assert "receipt" in lowered
        assert "inclusion" in lowered
        assert "position" in lowered
        assert (
            "committed transition" in lowered
            or "governancecommittedtransitionv2" in lowered
        )
        assert "traceevent" in lowered
        assert "idempotent" in lowered or "幂等" in section
        assert "non-author" in lowered or "非 authority" in section
        assert "pheroos-governance-trace-batch-v2" in lowered
        assert (
            "must not use" in lowered
            or "is not a" in lowered
            or "only a successful authority state change uses" in lowered
            or "不得使用" in section
            or "不能使用" in section
        )
        assert (
            "cannot change" in lowered
            or "does not change" in lowered
            or "must not change" in lowered
            or "不改变" in section
        )
        assert "policy" in lowered or "协议" in section
        assert "require" in lowered or "要求" in section
        assert "one idempotent append attempt" in lowered or (
            "一次" in section and "幂等" in section and "append attempt" in lowered
        )
        assert "must" in lowered or "必须" in section
        assert (
            "outcome separately" in lowered
            or "separate non-authority audit telemetry" in lowered
            or "结果作为独立 audit telemetry 暴露" in section
        )


def test_authority_diagnostic_enum_has_one_protocol_owner() -> None:
    documents = (
        _read(ADR_PATH),
        _read(THREAT_MODEL_PATH),
        _read(MIGRATION_PATH),
        _read(ROOT / "docs/process/production-readiness-hardening-goal-plan.md"),
    )
    for document in documents:
        normalized = " ".join(document.split())
        lowered = normalized.lower()
        assert f"`{AUTHORITY_DIAGNOSTIC_OWNER}`" in normalized
        assert "governance" in lowered
        assert (
            "same object" in lowered
            or "identical object" in lowered
            or "same enum" in lowered
            or "同一 enum" in normalized
        )
        assert (
            "must not define" in lowered
            or "不得重新定义" in normalized
            or "不得再建" in normalized
        )
        assert (
            "before authority-v2 dispatch" in lowered
            or "before authority v2 dispatch" in lowered
            or "dispatch 尚未建立前" in normalized
        )
        assert (
            "not relabeled" in lowered
            or "not be relabeled" in lowered
            or "never relabeled" in lowered
            or "keeps the existing generic" in lowered
            or "不得重标" in normalized
        )


def test_migration_frozen_identifier_tokens_exactly_match_the_adr() -> None:
    adr = _read(ADR_PATH)
    version_rows = _markdown_rows(
        _between(
            adr,
            "### Frozen version registry",
            "The existing `pheroos.trace.TraceEvent` remains",
        )
    )
    schema_rows = _markdown_rows(
        _between(
            adr,
            "### Schema files and `$id` values",
            "Protocol and Capability schema-document v3 require",
        )
    )
    adr_identifiers = tuple(_code(row[1]) for row in version_rows[1:])
    adr_schema_files = tuple(_code(row[1]) for row in schema_rows[1:])
    adr_schema_ids = tuple(_code(row[2]) for row in schema_rows[1:])
    expected_tokens = (
        *adr_identifiers,
        *adr_schema_files,
        *adr_schema_ids,
    )

    migration_rows = _markdown_rows(
        _between(
            _read(MIGRATION_PATH),
            "## 1. Frozen identifiers",
            "## 2. Exact manifest selection",
        )
    )
    assert migration_rows[0] == ["Axis", "Exact identifier"]
    migration_tokens = tuple(
        token
        for row in migration_rows[1:]
        for token in re.findall(r"`([^`]+)`", row[1])
    )

    assert len(adr_identifiers) == 17
    assert len(adr_schema_files) == 4
    assert len(adr_schema_ids) == 4
    assert len(expected_tokens) == len(set(expected_tokens)) == 25
    assert len(migration_tokens) == len(set(migration_tokens)) == 25
    assert set(migration_tokens) == set(expected_tokens)


def test_authority_v2_documents_report_local_draft_activation_without_overclaim() -> (
    None
):
    primary_documents = (ADR_PATH, THREAT_MODEL_PATH, MIGRATION_PATH)
    for path in primary_documents:
        match = re.search(r"^Status:\s*(.+)$", _read(path), re.MULTILINE)
        assert match is not None
        status = match.group(1).strip().strip("*").lower()
        assert "accepted" in status
        assert "active" in status or "implemented" in status
        assert "inactive" not in status

    conformance = _read(ROOT / "docs/conformance/conformance-suite.md")
    conformance_status = _between(
        conformance,
        "The exact local scoped-authority v2 profile is now active as Draft",
        "Commit profile selection takes precedence",
    ).lower()
    schema_status = _between(
        _read(ROOT / "docs/process/schema-v1-v2-migration.md"),
        "## Scoped Authority vNext Documents",
        "## Reader Selection",
    ).lower()

    for status in (conformance_status, schema_status):
        assert "active" in status or "shipped" in status
        assert "draft" in status
        assert "authenticated" in status
        assert "stable" in status or "promotion" in status
