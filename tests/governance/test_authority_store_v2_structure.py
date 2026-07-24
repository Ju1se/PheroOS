from __future__ import annotations

import ast
from dataclasses import MISSING, fields
import importlib
from inspect import Parameter, signature
from pathlib import Path
import pickle

import pheroos.governance.authority_store_v2 as authority_store_v2
import pheroos.protocol.authority_v2 as protocol_authority_v2


PUBLIC_MODULE = "pheroos.governance.authority_store_v2"
PRIVATE_PACKAGE = "pheroos.governance._authority_store_v2_contracts"

EXPECTED_ALL = (
    "AUTHORITY_AUTHENTICATED_PROFILE_V2",
    "AUTHORITY_DOMAIN_SCHEMA_V2",
    "AUTHORITY_LEDGER_VERSION_V2",
    "AUTHORITY_LOCAL_PROFILE_V2",
    "AUTHORITY_POLICY_VERSION_V2",
    "AUTHORITY_WIRE_VERSION_V2",
    "GOVERNANCE_COMMITTED_TRANSITION_SCHEMA_V2",
    "GOVERNANCE_COMMIT_ATTEMPT_SCHEMA_V2",
    "GOVERNANCE_COMMIT_BATCH_SCHEMA_V2",
    "GOVERNANCE_COMMIT_INCLUSION_PROOF_SCHEMA_V2",
    "GOVERNANCE_COMMIT_POSITION_OBSERVATION_SCHEMA_V2",
    "GOVERNANCE_COMMIT_RECEIPT_SCHEMA_V2",
    "GOVERNANCE_COMMIT_VIEW_SCHEMA_V2",
    "GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2",
    "GOVERNANCE_DOMAIN_SEAL_SCHEMA_V2",
    "GOVERNANCE_FAILURE_SCHEMA_V2",
    "GOVERNANCE_GENESIS_PARENT_ROOT_V2",
    "GOVERNANCE_HEAD_SCHEMA_V2",
    "GOVERNANCE_STATE_SCHEMA_V2",
    "GOVERNANCE_STATE_STORE_VERSION_V2",
    "GOVERNANCE_TRACE_BATCH_VERSION_V2",
    "MAX_GOVERNANCE_NON_LIFECYCLE_STREAMS_V2",
    "MAX_GOVERNANCE_TRACE_EVENTS_V2",
    "PREPARED_GOVERNANCE_TRANSITION_SCHEMA_V2",
    "AuthorityDiagnosticCodeV2",
    "AuthorityDomainV2",
    "GovernanceAuthorityReadSetV2",
    "GovernanceCommitAttemptV2",
    "GovernanceCommitBatchV2",
    "GovernanceCommitDispositionV2",
    "GovernanceCommitInclusionProofV2",
    "GovernanceCommitPositionObservationV2",
    "GovernanceCommitPositionV2",
    "GovernanceCommitReceiptV2",
    "GovernanceCommitViewV2",
    "GovernanceCommittedTransitionV2",
    "GovernanceDomainSealV2",
    "GovernanceFailureStageV2",
    "GovernanceFailureV2",
    "GovernanceHeadV2",
    "GovernanceStateReaderV2",
    "GovernanceStateStoreV2",
    "GovernanceStateWriterV2",
    "GovernanceTraceBatchV2",
    "PreparedGovernanceTransitionV2",
    "governance_authority_state_root_v2",
)

NATIVE_OBJECT_OWNERS = {
    "GovernanceCommitDispositionV2": "foundation",
    "GovernanceCommitPositionV2": "foundation",
    "GovernanceFailureStageV2": "foundation",
    "AuthorityDomainV2": "domain",
    "GovernanceHeadV2": "domain",
    "PreparedGovernanceTransitionV2": "domain",
    "governance_authority_state_root_v2": "domain",
    "GovernanceTraceBatchV2": "batch",
    "GovernanceDomainSealV2": "batch",
    "GovernanceCommitBatchV2": "batch",
    "GovernanceCommitReceiptV2": "receipt",
    "GovernanceCommitInclusionProofV2": "receipt",
    "GovernanceCommittedTransitionV2": "receipt",
    "GovernanceCommitPositionObservationV2": "receipt",
    "GovernanceFailureV2": "results",
    "GovernanceCommitAttemptV2": "results",
    "GovernanceCommitViewV2": "results",
    "GovernanceStateReaderV2": "results",
    "GovernanceStateWriterV2": "results",
    "GovernanceStateStoreV2": "results",
}

REQUIRED = object()
DATACLASS_FIELDS_AND_DEFAULTS = {
    "AuthorityDomainV2": (
        (
            "policy_version",
            "profile",
            "wire_version",
            "canonical_version",
            "ledger_version",
            "state_store_version",
            "trace_batch_version",
            "read_set_version",
            "scope_ref",
            "schema",
            "domain_root",
        ),
        (REQUIRED,) * 9 + ("pheroos-governance-authority-domain-v2", ""),
    ),
    "GovernanceHeadV2": (
        (
            "domain_root",
            "scope_ref",
            "stream_ref",
            "revision",
            "parent_root",
            "state_root",
            "transition_id",
            "batch_root",
            "canonical_version",
            "ledger_version",
            "schema",
            "head_root",
        ),
        (REQUIRED,) * 8
        + (
            "pheroos-authority-canonical-v2",
            "pheroos-governance-authority-ledger-v2",
            "pheroos-governance-authority-head-v2",
            "",
        ),
    ),
    "PreparedGovernanceTransitionV2": (
        (
            "domain_root",
            "scope_ref",
            "stream_ref",
            "transition_id",
            "expected_revision",
            "expected_root",
            "read_set_root",
            "state_records",
            "canonical_version",
            "ledger_version",
            "schema",
            "state_root",
            "transition_root",
        ),
        (REQUIRED,) * 8
        + (
            "pheroos-authority-canonical-v2",
            "pheroos-governance-authority-ledger-v2",
            "pheroos-governance-prepared-transition-v2",
            "",
            "",
        ),
    ),
    "GovernanceTraceBatchV2": (
        (
            "canonical_version",
            "domain_root",
            "scope_ref",
            "stream_ref",
            "transition_id",
            "_event_snapshots",
            "schema",
            "trace_root",
        ),
        (REQUIRED,) * 8,
    ),
    "GovernanceDomainSealV2": (
        (
            "domain_root",
            "scope_ref",
            "transition_id",
            "expected_revision",
            "expected_root",
            "final_heads",
            "canonical_version",
            "ledger_version",
            "schema",
            "final_heads_root",
            "seal_root",
        ),
        (REQUIRED,) * 6
        + (
            "pheroos-authority-canonical-v2",
            "pheroos-governance-authority-ledger-v2",
            "pheroos-governance-domain-seal-v2",
            "",
            "",
        ),
    ),
    "GovernanceCommitBatchV2": (
        (
            "domain",
            "scope_ref",
            "stream_ref",
            "transition_id",
            "kind",
            "read_set",
            "trace_batch",
            "transition",
            "seal",
            "canonical_version",
            "ledger_version",
            "schema",
            "domain_root",
            "read_set_root",
            "transition_root",
            "seal_root",
            "trace_root",
            "batch_root",
        ),
        (REQUIRED,) * 7
        + (
            None,
            None,
            "pheroos-authority-canonical-v2",
            "pheroos-governance-authority-ledger-v2",
            "pheroos-governance-commit-batch-v2",
            "",
            "",
            None,
            None,
            "",
            "",
        ),
    ),
    "GovernanceCommitReceiptV2": (
        (
            "domain_root",
            "scope_ref",
            "stream_ref",
            "transition_id",
            "revision",
            "parent_root",
            "head_root",
            "state_root",
            "read_set_root",
            "trace_root",
            "batch_root",
            "canonical_version",
            "ledger_version",
            "schema",
            "receipt_root",
        ),
        (REQUIRED,) * 11
        + (
            "pheroos-authority-canonical-v2",
            "pheroos-governance-authority-ledger-v2",
            "pheroos-governance-commit-receipt-v2",
            "",
        ),
    ),
    "GovernanceCommitInclusionProofV2": (
        (
            "domain_root",
            "scope_ref",
            "stream_ref",
            "transition_id",
            "revision",
            "batch_root",
            "receipt_root",
            "head_root",
            "canonical_version",
            "ledger_version",
            "schema",
            "inclusion_root",
        ),
        (REQUIRED,) * 8
        + (
            "pheroos-authority-canonical-v2",
            "pheroos-governance-authority-ledger-v2",
            "pheroos-governance-commit-inclusion-proof-v2",
            "",
        ),
    ),
    "GovernanceCommittedTransitionV2": (
        (
            "batch",
            "receipt",
            "inclusion_proof",
            "canonical_version",
            "ledger_version",
            "schema",
            "committed_transition_root",
        ),
        (REQUIRED,) * 3
        + (
            "pheroos-authority-canonical-v2",
            "pheroos-governance-authority-ledger-v2",
            "pheroos-governance-committed-transition-v2",
            "",
        ),
    ),
    "GovernanceCommitPositionObservationV2": (
        (
            "domain_root",
            "scope_ref",
            "stream_ref",
            "transition_id",
            "receipt_root",
            "observed_revision",
            "observed_head_root",
            "position",
            "seal_root",
            "canonical_version",
            "ledger_version",
            "schema",
            "observation_root",
        ),
        (REQUIRED,) * 8
        + (
            None,
            "pheroos-authority-canonical-v2",
            "pheroos-governance-authority-ledger-v2",
            "pheroos-governance-commit-position-observation-v2",
            "",
        ),
    ),
    "GovernanceFailureV2": (
        ("code", "path", "stage", "schema", "failure_root"),
        (REQUIRED,) * 3 + ("pheroos-governance-failure-v2", ""),
    ),
    "GovernanceCommitAttemptV2": (
        (
            "domain_root",
            "scope_ref",
            "stream_ref",
            "transition_id",
            "disposition",
            "failure",
            "committed_transition",
            "position_observation",
            "canonical_version",
            "schema",
            "attempt_root",
        ),
        (REQUIRED,) * 8
        + (
            "pheroos-authority-canonical-v2",
            "pheroos-governance-commit-attempt-v2",
            "",
        ),
    ),
    "GovernanceCommitViewV2": (
        (
            "domain_root",
            "scope_ref",
            "stream_ref",
            "transition_id",
            "expected_receipt_root",
            "disposition",
            "failure",
            "committed_transition",
            "position_observation",
            "observed_revision",
            "observed_head_root",
            "canonical_version",
            "schema",
            "view_root",
        ),
        (REQUIRED,) * 11
        + ("pheroos-authority-canonical-v2", "pheroos-governance-commit-view-v2", ""),
    ),
}


def _default(field: object) -> object:
    value = getattr(field, "default")
    factory = getattr(field, "default_factory")
    assert factory is MISSING
    return REQUIRED if value is MISSING else value


def test_public_surface_and_protocol_owned_identity_are_exact() -> None:
    assert len(authority_store_v2.__all__) == 46
    assert tuple(authority_store_v2.__all__) == EXPECTED_ALL
    assert (
        authority_store_v2.AuthorityDiagnosticCodeV2
        is protocol_authority_v2.AuthorityDiagnosticCodeV2
    )
    assert (
        authority_store_v2.GovernanceAuthorityReadSetV2
        is protocol_authority_v2.GovernanceAuthorityReadSetV2
    )
    assert authority_store_v2.AuthorityDiagnosticCodeV2.__module__ == (
        "pheroos.protocol.authority_v2"
    )
    assert authority_store_v2.GovernanceAuthorityReadSetV2.__module__ == (
        "pheroos.protocol.authority_v2"
    )


def test_native_public_objects_keep_import_module_and_pickle_identity() -> None:
    for name, owner in NATIVE_OBJECT_OWNERS.items():
        public_object = getattr(authority_store_v2, name)
        private_module = importlib.import_module(f"{PRIVATE_PACKAGE}.{owner}")
        assert getattr(private_module, name) is public_object
        assert public_object.__module__ == PUBLIC_MODULE
        assert pickle.loads(pickle.dumps(public_object)) is public_object


def test_dataclass_field_order_defaults_and_constructor_shape_are_frozen() -> None:
    for name, (
        expected_names,
        expected_defaults,
    ) in DATACLASS_FIELDS_AND_DEFAULTS.items():
        record = getattr(authority_store_v2, name)
        record_fields = fields(record)
        assert tuple(item.name for item in record_fields) == expected_names
        assert tuple(_default(item) for item in record_fields) == expected_defaults
        if name == "GovernanceTraceBatchV2":
            parameters = tuple(signature(record).parameters.values())
            assert tuple(item.name for item in parameters) == (
                "domain_root",
                "scope_ref",
                "stream_ref",
                "transition_id",
                "events",
                "canonical_version",
                "schema",
                "trace_root",
            )
            assert all(item.kind is Parameter.KEYWORD_ONLY for item in parameters)
            continue
        parameters = tuple(signature(record).parameters.values())
        assert tuple(item.name for item in parameters) == expected_names
        assert all(item.kind is Parameter.POSITIONAL_OR_KEYWORD for item in parameters)


def test_function_and_store_protocol_signatures_are_frozen() -> None:
    state_root = signature(authority_store_v2.governance_authority_state_root_v2)
    assert tuple(state_root.parameters) == (
        "scope_ref",
        "stream_ref",
        "state_records",
    )
    reader = authority_store_v2.GovernanceStateReaderV2
    writer = authority_store_v2.GovernanceStateWriterV2
    assert tuple(signature(reader.load_head_v2).parameters) == (
        "self",
        "scope_ref",
        "stream_ref",
    )
    assert tuple(signature(reader.load_state_v2).parameters) == (
        "self",
        "scope_ref",
        "stream_ref",
    )
    view = tuple(signature(reader.load_commit_view_v2).parameters.values())
    assert tuple(item.name for item in view) == (
        "self",
        "scope_ref",
        "stream_ref",
        "transition_id",
        "expected_receipt_root",
    )
    assert view[-1].kind is Parameter.KEYWORD_ONLY
    assert view[-1].default is None
    assert tuple(signature(writer.atomic_commit_v2).parameters) == ("self", "batch")


def test_private_contract_import_graph_is_one_way_and_boundary_clean() -> None:
    package_dir = (
        Path(authority_store_v2.__file__).parent / "_authority_store_v2_contracts"
    )
    allowed_internal = {
        "foundation": frozenset(),
        "domain": frozenset({"foundation"}),
        "batch": frozenset({"domain", "foundation"}),
        "receipt": frozenset({"batch", "domain", "foundation"}),
        "results": frozenset({"batch", "domain", "foundation", "receipt"}),
    }
    forbidden = (
        "pheroos.governance.authority_store_v2",
        "pheroos.governance._authority_v2",
        "pheroos.conformance",
    )
    for module_name, allowed in allowed_internal.items():
        path = package_dir / f"{module_name}.py"
        source = path.read_text(encoding="utf-8")
        assert len(source.splitlines()) < 750
        assert not any(name in source for name in forbidden)
        tree = ast.parse(source)
        internal: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "pheroos.governance"
                prefix = f"{PRIVATE_PACKAGE}."
                if node.module is not None and node.module.startswith(prefix):
                    internal.add(node.module.removeprefix(prefix))
        assert internal <= allowed
    assert len(Path(authority_store_v2.__file__).read_text().splitlines()) < 200


def test_representative_wire_bytes_and_roots_remain_frozen() -> None:
    domain = authority_store_v2.AuthorityDomainV2(
        policy_version=authority_store_v2.AUTHORITY_POLICY_VERSION_V2,
        profile=authority_store_v2.AUTHORITY_LOCAL_PROFILE_V2,
        wire_version=authority_store_v2.AUTHORITY_WIRE_VERSION_V2,
        canonical_version=protocol_authority_v2.AUTHORITY_CANONICAL_VERSION_V2,
        ledger_version=authority_store_v2.AUTHORITY_LEDGER_VERSION_V2,
        state_store_version=authority_store_v2.GOVERNANCE_STATE_STORE_VERSION_V2,
        trace_batch_version=authority_store_v2.GOVERNANCE_TRACE_BATCH_VERSION_V2,
        read_set_version=(
            protocol_authority_v2.GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2
        ),
        scope_ref="scope:structure",
    )
    assert domain.domain_root == (
        "sha256:8a94f547e3aeeaca54d3cb7a44db5be03d31c0070a5d9cd5f96b8df201534a11"
    )
    assert domain.canonical_bytes() == (
        b'{"canonical_version":"pheroos-authority-canonical-v2",'
        b'"domain_root":"sha256:8a94f547e3aeeaca54d3cb7a44db5be03d31c0070a5d9cd5f96b8df201534a11",'
        b'"ledger_version":"pheroos-governance-authority-ledger-v2",'
        b'"policy_version":"pheroos-scoped-authority-policy-v2",'
        b'"profile":"pheroos-scoped-authority-local-v2",'
        b'"read_set_version":"pheroos-governance-authority-read-set-v2",'
        b'"schema":"pheroos-governance-authority-domain-v2",'
        b'"scope_ref":"scope:structure",'
        b'"state_store_version":"pheroos-governance-state-store-v2",'
        b'"trace_batch_version":"pheroos-governance-trace-batch-v2",'
        b'"wire_version":"pheroos-authority-wire-v2"}'
    )
    assert (
        authority_store_v2.governance_authority_state_root_v2(
            "scope:structure",
            "authority:alpha",
            {"nested": {"ok": True}, "count": 1},
        )
        == "sha256:a97006f68bd760d8d6ec5293234e8149dea403029257428ce7c91833445b8747"
    )
