"""Static owner catalog for every checked JSON Schema artifact.

Conformance may compose all core packages, but no core package imports this
catalog.  The tuple below is the only registry used by the schema generator and
the management CLI; it is deliberately closed and is not a plugin surface.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pheroos.conformance.commit_tck import (
    COMMIT_TCK_SCHEMA_ID,
    COMMIT_TCK_VERSION,
    commit_tck_schema,
    load_commit_tck_vectors,
)
from pheroos.conformance.commit_tck_v2 import (
    commit_tck_v2_schema,
    load_commit_tck_v2_cases,
)
from pheroos.conformance.commit_tck_v2_protocol import (
    COMMIT_TCK_REQUEST_SCHEMA_ID,
    COMMIT_TCK_REQUEST_VERSION,
    COMMIT_TCK_RESPONSE_SCHEMA_ID,
    COMMIT_TCK_RESPONSE_VERSION,
    COMMIT_TCK_V2_VERSION,
    CommitTckRequest,
    CommitTckResponse,
    commit_tck_request_v2_schema,
    commit_tck_response_v2_schema,
)
from pheroos.conformance.report import (
    CONFORMANCE_REPORT_SCHEMA_ID,
    CONFORMANCE_REPORT_VERSION,
    ConformanceReport,
    conformance_report_schema,
)
from pheroos.conformance.scoped_authority_tck_v2 import (
    SCOPED_AUTHORITY_TCK_SCHEMA_V2,
    SCOPED_AUTHORITY_TCK_SCHEMA_V2_ID,
    read_scoped_authority_tck_document_v2,
    scoped_authority_tck_v2_schema,
    validate_scoped_authority_tck_document_v2,
)
from pheroos.drivers._versions import (
    DRIVER_DESCRIPTOR_VERSION_V2,
    DRIVER_SCHEMA_V1_ID,
    DRIVER_SCHEMA_V2_ID,
)
from pheroos.drivers.document import (
    driver_descriptor_from_dict,
    driver_descriptor_v1_from_dict,
)
from pheroos.drivers.schema import driver_schema, driver_schema_v2
from pheroos.governance.authority_schema_v2 import (
    AUTHORITY_SCHEMA_V2,
    AUTHORITY_SCHEMA_V2_ID,
    authority_schema_v2,
    read_authority_wire_record_v2,
    validate_authority_wire_record_v2,
)
from pheroos.governance.schema import commit_schema, validate_commit_wire_record
from pheroos.kernel._versions import (
    KERNEL_PLAN_VERSION_V2,
    KERNEL_SCHEMA_V1_ID,
    KERNEL_SCHEMA_V2_ID,
)
from pheroos.kernel.plan_document import os_plan_from_dict, os_plan_v1_from_dict
from pheroos.kernel.run_scope import RuntimeScope
from pheroos.kernel.schema import (
    kernel_schema,
    kernel_schema_v2,
    runtime_scope_schema_v1,
)
from pheroos.protocol.authority_schema_v2 import (
    CAPABILITY_SCHEMA_V3,
    CAPABILITY_SCHEMA_V3_ID,
    PROTOCOL_SCHEMA_V3,
    PROTOCOL_SCHEMA_V3_ID,
    capability_schema_v3,
    protocol_schema_v3,
)
from pheroos.protocol.commit_models import COMMIT_WIRE_VERSION
from pheroos.protocol.models import CapabilityManifest, ProtocolManifest
from pheroos.protocol.schema import (
    CAPABILITY_SCHEMA_V1,
    CAPABILITY_SCHEMA_V1_ID,
    CAPABILITY_SCHEMA_V2,
    CAPABILITY_SCHEMA_V2_ID,
    PROTOCOL_SCHEMA_V1,
    PROTOCOL_SCHEMA_V1_ID,
    PROTOCOL_SCHEMA_V2,
    PROTOCOL_SCHEMA_V2_ID,
    capability_schema,
    capability_schema_v2,
    protocol_schema,
    protocol_schema_v2,
)
from pheroos.protocol.schema_document import (
    read_capability_manifest,
    read_protocol_manifest,
)
from pheroos.protocol.validation import validate_capability_manifest
from pheroos.trace.event import TraceEvent
from pheroos.trace.schema import trace_schema
from pheroos.trace.scoped import (
    SCOPED_TRACE_EVENT_SCHEMA_ID,
    SCOPED_TRACE_EVENT_VERSION,
    ScopedTraceEvent,
    scoped_trace_event_schema,
)

SCHEMA_CATALOG_VERSION = "pheroos-schema-artifact-catalog-v1"
SCHEMA_DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_ARTIFACT_DIRECTORY = "schemas"
COMMIT_SCHEMA_ID = "https://pheroos.dev/schemas/commit.schema.json"
TRACE_SCHEMA_ID = "https://pheroos.dev/schemas/trace.schema.json"
COMMIT_TCK_V2_SCHEMA_ID = "https://pheroos.dev/schemas/commit-tck-v2.schema.json"

SchemaFactory = Callable[[], dict[str, Any]]
ArtifactRenderer = Callable[[dict[str, Any]], bytes]
TypedReader = Callable[..., object]
SemanticValidator = Callable[..., object]
WireValidator = Callable[[object, str | Path], None]


@dataclass(frozen=True, slots=True)
class SchemaCliSurface:
    """One CLI name and its lifecycle role."""

    name: str
    status: str


@dataclass(frozen=True, slots=True)
class SchemaArtifactSpec:
    """One checked artifact and every surface that is allowed to expose it."""

    surface: str
    path: str
    schema_id: str
    schema_version: str
    factory: SchemaFactory
    typed_reader: TypedReader | None
    typed_reader_not_applicable_reason: str | None
    semantic_validator: SemanticValidator | None
    semantic_validator_not_applicable_reason: str | None
    wire_validator: WireValidator
    frozen: bool
    frozen_sha256: str | None
    cli_surfaces: tuple[SchemaCliSurface, ...]
    package_data_required: bool
    package_resource_path: str | None
    applicable_profiles: tuple[str, ...]
    applicable_tcks: tuple[str, ...]
    artifact_renderer: ArtifactRenderer | None


def _cli(*values: tuple[str, str]) -> tuple[SchemaCliSurface, ...]:
    return tuple(SchemaCliSurface(name, status) for name, status in values)


def _spec(
    *,
    surface: str,
    filename: str,
    schema_id: str,
    schema_version: str,
    factory: SchemaFactory,
    typed_reader: TypedReader | None,
    typed_reader_not_applicable_reason: str | None = None,
    semantic_validator: SemanticValidator | None = None,
    semantic_validator_not_applicable_reason: str | None = None,
    wire_validator: WireValidator,
    frozen: bool = False,
    frozen_sha256: str | None = None,
    aliases: tuple[SchemaCliSurface, ...],
    profiles: tuple[str, ...] = (),
    tcks: tuple[str, ...] = (),
    artifact_renderer: ArtifactRenderer | None = None,
) -> SchemaArtifactSpec:
    return SchemaArtifactSpec(
        surface=surface,
        path=f"{SCHEMA_ARTIFACT_DIRECTORY}/{filename}",
        schema_id=schema_id,
        schema_version=schema_version,
        factory=factory,
        typed_reader=typed_reader,
        typed_reader_not_applicable_reason=typed_reader_not_applicable_reason,
        semantic_validator=semantic_validator,
        semantic_validator_not_applicable_reason=(
            semantic_validator_not_applicable_reason
        ),
        wire_validator=wire_validator,
        frozen=frozen,
        frozen_sha256=frozen_sha256,
        cli_surfaces=aliases,
        package_data_required=False,
        package_resource_path=None,
        applicable_profiles=profiles,
        applicable_tcks=tcks,
        artifact_renderer=artifact_renderer,
    )


# Delay construction until the closed validator functions below are defined.
# The catalog remains a static tuple; this is import-order plumbing, not a
# runtime extension hook.
_SCHEMA_ARTIFACT_SPECS_FACTORY: Callable[[], tuple[SchemaArtifactSpec, ...]] = lambda: (  # noqa: E731
    _spec(
        surface="capability-v1",
        filename="capability.schema.json",
        schema_id=CAPABILITY_SCHEMA_V1_ID,
        schema_version=CAPABILITY_SCHEMA_V1,
        factory=capability_schema,
        typed_reader=read_capability_manifest,
        semantic_validator=validate_capability_manifest,
        wire_validator=_wire_capability_v1,
        frozen=True,
        frozen_sha256=(
            "5d3a88ed54d9acf83813713abec493ebb85e245cd6766de9fffa03351cdb62cf"
        ),
        aliases=_cli(
            ("capability", "legacy-alias"),
            ("capability-v1", "legacy-frozen"),
        ),
        profiles=("baseline", "swarm", "hybrid"),
        tcks=("manifest-schema",),
    ),
    _spec(
        surface="capability-v2",
        filename="capability-v2.schema.json",
        schema_id=CAPABILITY_SCHEMA_V2_ID,
        schema_version=CAPABILITY_SCHEMA_V2,
        factory=capability_schema_v2,
        typed_reader=read_capability_manifest,
        semantic_validator=validate_capability_manifest,
        wire_validator=_wire_capability_v2,
        frozen=True,
        frozen_sha256=(
            "b613b848978c32339ec47487c4c45f99f67a81b85d8f98565bf41ed908df8eb4"
        ),
        aliases=_cli(("capability-v2", "legacy-frozen")),
        profiles=("baseline", "swarm", "hybrid"),
        tcks=("manifest-schema",),
    ),
    _spec(
        surface="capability-v3",
        filename="capability-v3.schema.json",
        schema_id=CAPABILITY_SCHEMA_V3_ID,
        schema_version=CAPABILITY_SCHEMA_V3,
        factory=capability_schema_v3,
        typed_reader=read_capability_manifest,
        semantic_validator=validate_capability_manifest,
        wire_validator=_wire_capability_v3,
        aliases=_cli(("capability-v3", "draft")),
        profiles=("scoped-authority-v2",),
        tcks=("runtime-integration-v1",),
    ),
    _spec(
        surface="protocol-v1",
        filename="protocol.schema.json",
        schema_id=PROTOCOL_SCHEMA_V1_ID,
        schema_version=PROTOCOL_SCHEMA_V1,
        factory=protocol_schema,
        typed_reader=read_protocol_manifest,
        semantic_validator=None,
        semantic_validator_not_applicable_reason=(
            "the typed Protocol reader owns semantic validation"
        ),
        wire_validator=_wire_protocol_v1,
        frozen=True,
        frozen_sha256=(
            "1abc0b228c72fc05f8ec6272d327d9c06ca3e3a7e37ea2487ccfeff60c86cdb6"
        ),
        aliases=_cli(
            ("protocol", "legacy-alias"),
            ("protocol-v1", "legacy-frozen"),
        ),
        profiles=("baseline", "swarm", "hybrid"),
        tcks=("manifest-schema",),
    ),
    _spec(
        surface="protocol-v2",
        filename="protocol-v2.schema.json",
        schema_id=PROTOCOL_SCHEMA_V2_ID,
        schema_version=PROTOCOL_SCHEMA_V2,
        factory=protocol_schema_v2,
        typed_reader=read_protocol_manifest,
        semantic_validator=None,
        semantic_validator_not_applicable_reason=(
            "the typed Protocol reader owns semantic validation"
        ),
        wire_validator=_wire_protocol_v2,
        frozen=True,
        frozen_sha256=(
            "8f4aeb48d99827b381cb3138c9651d88eb0a2f0ce1c0de4aac8f1aaf5eebe877"
        ),
        aliases=_cli(("protocol-v2", "legacy-frozen")),
        profiles=("baseline", "swarm", "hybrid"),
        tcks=("manifest-schema",),
    ),
    _spec(
        surface="protocol-v3",
        filename="protocol-v3.schema.json",
        schema_id=PROTOCOL_SCHEMA_V3_ID,
        schema_version=PROTOCOL_SCHEMA_V3,
        factory=protocol_schema_v3,
        typed_reader=read_protocol_manifest,
        semantic_validator=None,
        semantic_validator_not_applicable_reason=(
            "the typed Protocol reader owns semantic validation"
        ),
        wire_validator=_wire_protocol_v3,
        aliases=_cli(("protocol-v3", "draft")),
        profiles=("scoped-authority-v2",),
        tcks=("runtime-integration-v1",),
    ),
    _spec(
        surface="driver-v1",
        filename="driver.schema.json",
        schema_id=DRIVER_SCHEMA_V1_ID,
        schema_version=DRIVER_SCHEMA_V1_ID,
        factory=driver_schema,
        typed_reader=driver_descriptor_v1_from_dict,
        semantic_validator=None,
        semantic_validator_not_applicable_reason=(
            "the typed Driver reader owns semantic validation"
        ),
        wire_validator=_wire_driver_v1,
        frozen=True,
        frozen_sha256=(
            "44171e85e1076231d9120f67abafcf521748ccbb8932a805df12c43823587fbd"
        ),
        aliases=_cli(
            ("driver", "legacy-alias"),
            ("driver-v1", "legacy-frozen"),
        ),
        tcks=("driver-lifecycle",),
    ),
    _spec(
        surface="driver-v2",
        filename="driver-v2.schema.json",
        schema_id=DRIVER_SCHEMA_V2_ID,
        schema_version=DRIVER_DESCRIPTOR_VERSION_V2,
        factory=driver_schema_v2,
        typed_reader=driver_descriptor_from_dict,
        semantic_validator=None,
        semantic_validator_not_applicable_reason=(
            "the typed Driver reader owns semantic validation"
        ),
        wire_validator=_wire_driver_v2,
        aliases=_cli(("driver-v2", "active")),
        tcks=("driver-invocation-store-v2",),
    ),
    _spec(
        surface="kernel-v1",
        filename="kernel.schema.json",
        schema_id=KERNEL_SCHEMA_V1_ID,
        schema_version=KERNEL_SCHEMA_V1_ID,
        factory=kernel_schema,
        typed_reader=os_plan_v1_from_dict,
        semantic_validator=None,
        semantic_validator_not_applicable_reason=(
            "the typed Kernel reader owns semantic validation"
        ),
        wire_validator=_wire_kernel_v1,
        frozen=True,
        frozen_sha256=(
            "da2e2001a61c19d2726bc96ef05392e1acb8618c6bb6a3dfb233bcc0398e0822"
        ),
        aliases=_cli(
            ("kernel", "legacy-alias"),
            ("kernel-v1", "legacy-frozen"),
        ),
    ),
    _spec(
        surface="kernel-v2",
        filename="kernel-v2.schema.json",
        schema_id=KERNEL_SCHEMA_V2_ID,
        schema_version=KERNEL_PLAN_VERSION_V2,
        factory=kernel_schema_v2,
        typed_reader=os_plan_from_dict,
        semantic_validator=None,
        semantic_validator_not_applicable_reason=(
            "the typed Kernel reader owns semantic validation"
        ),
        wire_validator=_wire_kernel_v2,
        aliases=_cli(("kernel-v2", "active")),
        tcks=("runtime-integration-v1",),
    ),
    _spec(
        surface="runtime-scope-v1",
        filename="runtime-scope-v1.schema.json",
        schema_id=str(runtime_scope_schema_v1()["$id"]),
        schema_version=str(
            runtime_scope_schema_v1()["properties"]["scope_version"]["const"]
        ),
        factory=runtime_scope_schema_v1,
        typed_reader=RuntimeScope.from_dict,
        semantic_validator=None,
        semantic_validator_not_applicable_reason=(
            "the typed RuntimeScope reader owns semantic validation"
        ),
        wire_validator=_wire_runtime_scope_v1,
        aliases=_cli(("runtime-scope-v1", "draft")),
        tcks=("runtime-integration-v1",),
    ),
    _spec(
        surface="trace",
        filename="trace.schema.json",
        schema_id=TRACE_SCHEMA_ID,
        schema_version=TRACE_SCHEMA_ID,
        factory=trace_schema,
        typed_reader=_read_trace_event,
        semantic_validator=TraceEvent.validate,
        wire_validator=_wire_trace,
        aliases=_cli(("trace", "active")),
        tcks=("trace-contract",),
    ),
    _spec(
        surface="commit",
        filename="commit.schema.json",
        schema_id=COMMIT_SCHEMA_ID,
        schema_version=COMMIT_WIRE_VERSION,
        factory=commit_schema,
        typed_reader=None,
        typed_reader_not_applicable_reason=(
            "Commit Wire is a closed union validated without one aggregate record"
        ),
        semantic_validator=validate_commit_wire_record,
        wire_validator=_wire_commit,
        aliases=_cli(("commit", "active")),
        profiles=("commit-integrity", "hybrid-commit", "certified", "distributed"),
        tcks=("commit-integrity-v1", "commit-integrity-v2"),
    ),
    _spec(
        surface="conformance-report",
        filename="conformance-report-v2.schema.json",
        schema_id=CONFORMANCE_REPORT_SCHEMA_ID,
        schema_version=CONFORMANCE_REPORT_VERSION,
        factory=conformance_report_schema,
        typed_reader=ConformanceReport.from_dict,
        semantic_validator=None,
        semantic_validator_not_applicable_reason=(
            "the typed ConformanceReport reader owns semantic validation"
        ),
        wire_validator=_wire_conformance_report,
        aliases=_cli(("conformance-report", "active")),
        tcks=("conformance-report",),
    ),
    _spec(
        surface="scoped-trace",
        filename="scoped-trace-event-v1.schema.json",
        schema_id=SCOPED_TRACE_EVENT_SCHEMA_ID,
        schema_version=SCOPED_TRACE_EVENT_VERSION,
        factory=scoped_trace_event_schema,
        typed_reader=ScopedTraceEvent.from_dict,
        semantic_validator=None,
        semantic_validator_not_applicable_reason=(
            "the typed ScopedTraceEvent reader owns semantic validation"
        ),
        wire_validator=_wire_scoped_trace,
        frozen=True,
        frozen_sha256=(
            "b05925809d83645734d205e814f2ced0ff8afe242a8526b2ed3aadb93dfccd01"
        ),
        aliases=_cli(("scoped-trace", "active")),
        tcks=("scoped-trace-store-v2",),
        artifact_renderer=_render_scoped_trace_v1_artifact,
    ),
    _spec(
        surface="authority-v2",
        filename="authority-v2.schema.json",
        schema_id=AUTHORITY_SCHEMA_V2_ID,
        schema_version=AUTHORITY_SCHEMA_V2,
        factory=authority_schema_v2,
        typed_reader=read_authority_wire_record_v2,
        semantic_validator=validate_authority_wire_record_v2,
        wire_validator=_wire_authority_v2,
        aliases=_cli(("authority-v2", "draft")),
        profiles=("scoped-authority-v2",),
        tcks=(
            "governance-state-store-v2",
            "governance-authority-session-v2",
            "governance-baseline-output-v2",
        ),
    ),
    _spec(
        surface="scoped-authority-tck-v2",
        filename="scoped-authority-tck-v2.schema.json",
        schema_id=SCOPED_AUTHORITY_TCK_SCHEMA_V2_ID,
        schema_version=SCOPED_AUTHORITY_TCK_SCHEMA_V2,
        factory=scoped_authority_tck_v2_schema,
        typed_reader=read_scoped_authority_tck_document_v2,
        semantic_validator=validate_scoped_authority_tck_document_v2,
        wire_validator=_wire_scoped_authority_tck_v2,
        aliases=_cli(("scoped-authority-tck-v2", "draft")),
        profiles=("scoped-authority-v2",),
        tcks=("scoped-authority-v2",),
    ),
    _spec(
        surface="commit-tck-v1",
        filename="commit-tck.schema.json",
        schema_id=COMMIT_TCK_SCHEMA_ID,
        schema_version=COMMIT_TCK_VERSION,
        factory=commit_tck_schema,
        typed_reader=load_commit_tck_vectors,
        semantic_validator=None,
        semantic_validator_not_applicable_reason=(
            "the exact TCK artifact loader owns semantic validation"
        ),
        wire_validator=_wire_commit_tck_v1,
        aliases=_cli(("commit-tck-v1", "active")),
        tcks=("commit-integrity-v1",),
    ),
    _spec(
        surface="commit-tck-v2",
        filename="commit-tck-v2.schema.json",
        schema_id=COMMIT_TCK_V2_SCHEMA_ID,
        schema_version=COMMIT_TCK_V2_VERSION,
        factory=commit_tck_v2_schema,
        typed_reader=load_commit_tck_v2_cases,
        semantic_validator=None,
        semantic_validator_not_applicable_reason=(
            "the exact TCK artifact loader owns semantic validation"
        ),
        wire_validator=_wire_commit_tck_v2,
        aliases=_cli(("commit-tck-v2", "active")),
        tcks=("commit-integrity-v2",),
    ),
    _spec(
        surface="commit-tck-request-v2",
        filename="commit-tck-request-v2.schema.json",
        schema_id=COMMIT_TCK_REQUEST_SCHEMA_ID,
        schema_version=COMMIT_TCK_REQUEST_VERSION,
        factory=commit_tck_request_v2_schema,
        typed_reader=CommitTckRequest.from_dict,
        semantic_validator=None,
        semantic_validator_not_applicable_reason=(
            "the typed CommitTckRequest reader owns semantic validation"
        ),
        wire_validator=_wire_commit_tck_request_v2,
        aliases=_cli(("commit-tck-request-v2", "active")),
        tcks=("commit-integrity-v2",),
    ),
    _spec(
        surface="commit-tck-response-v2",
        filename="commit-tck-response-v2.schema.json",
        schema_id=COMMIT_TCK_RESPONSE_SCHEMA_ID,
        schema_version=COMMIT_TCK_RESPONSE_VERSION,
        factory=commit_tck_response_v2_schema,
        typed_reader=CommitTckResponse.from_dict,
        semantic_validator=None,
        semantic_validator_not_applicable_reason=(
            "the typed CommitTckResponse reader owns semantic validation"
        ),
        wire_validator=_wire_commit_tck_response_v2,
        aliases=_cli(("commit-tck-response-v2", "active")),
        tcks=("commit-integrity-v2",),
    ),
)


def render_schema_artifact(spec: SchemaArtifactSpec) -> bytes:
    """Return the one canonical byte representation for an artifact."""

    document = spec.factory()
    if spec.artifact_renderer is not None:
        return spec.artifact_renderer(document)
    return (
        json.dumps(
            document,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def schema_surface_names() -> tuple[str, ...]:
    """Return the reviewed CLI order, including compatibility aliases."""

    return tuple(
        item.name for spec in SCHEMA_ARTIFACT_SPECS for item in spec.cli_surfaces
    )


def schema_spec_for_surface(surface: str) -> SchemaArtifactSpec:
    """Resolve one exact CLI surface without dynamic registration."""

    try:
        return _SURFACE_INDEX[surface]
    except KeyError as exc:
        raise ValueError(f"unknown schema surface: {surface}") from exc


def schema_for_surface(surface: str) -> dict[str, Any]:
    """Build a detached schema document from its owning factory."""

    return deepcopy(schema_spec_for_surface(surface).factory())


def schema_artifact_bytes_for_surface(surface: str) -> bytes:
    """Render the exact checked artifact bytes for one CLI surface."""

    return render_schema_artifact(schema_spec_for_surface(surface))


def schema_metadata_for_surface(surface: str) -> dict[str, object]:
    """Return file-backed digest and lifecycle metadata for one CLI name."""

    spec = schema_spec_for_surface(surface)
    status = next(item.status for item in spec.cli_surfaces if item.name == surface)
    return {
        "surface": surface,
        "canonical_surface": spec.surface,
        "path": spec.path,
        "schema_id": spec.schema_id,
        "schema_version": spec.schema_version,
        "status": status,
        "artifact_state": "frozen" if spec.frozen else "writeable",
        "sha256": "sha256:" + sha256(render_schema_artifact(spec)).hexdigest(),
        "package_data_required": spec.package_data_required,
    }


def validate_schema_wire(
    surface: str,
    payload: object,
    subject: str | Path,
) -> None:
    """Dispatch typed/semantic wire validation from the static catalog."""

    schema_spec_for_surface(surface).wire_validator(payload, subject)


def schema_catalog_problems(root: str | Path) -> tuple[str, ...]:
    """Return deterministic catalog, artifact, and packaging diagnostics."""

    base = Path(root)
    problems: list[str] = []
    expected_paths = {spec.path for spec in SCHEMA_ARTIFACT_SPECS}
    observed_paths = {
        path.relative_to(base).as_posix()
        for path in (base / SCHEMA_ARTIFACT_DIRECTORY).glob("*.json")
    }
    for path in sorted(expected_paths - observed_paths):
        problems.append(f"missing:{path}")
    for path in sorted(observed_paths - expected_paths):
        problems.append(f"orphan:{path}")
    _duplicates((spec.path for spec in SCHEMA_ARTIFACT_SPECS), "path", problems)
    _duplicates(
        (spec.schema_id for spec in SCHEMA_ARTIFACT_SPECS), "schema_id", problems
    )
    _duplicates(schema_surface_names(), "cli_surface", problems)
    for spec in SCHEMA_ARTIFACT_SPECS:
        _validate_spec(base, spec, problems)
    return tuple(sorted(problems))


def _validate_spec(
    root: Path,
    spec: SchemaArtifactSpec,
    problems: list[str],
) -> None:
    try:
        document = spec.factory()
        rendered = render_schema_artifact(spec)
    except Exception as exc:
        problems.append(f"factory:{spec.surface}:{type(exc).__name__}")
        return
    _validate_spec_metadata(document, spec, problems)
    _validate_spec_artifact(root, spec, rendered, problems)


def _validate_spec_metadata(
    document: Mapping[str, Any],
    spec: SchemaArtifactSpec,
    problems: list[str],
) -> None:
    if document.get("$schema") != SCHEMA_DRAFT_2020_12:
        problems.append(f"draft:{spec.surface}")
    if document.get("$id") != spec.schema_id:
        problems.append(f"schema_id:{spec.surface}")
    if (spec.typed_reader is None) == (spec.typed_reader_not_applicable_reason is None):
        problems.append(f"typed_reader:{spec.surface}")
    if (spec.semantic_validator is None) == (
        spec.semantic_validator_not_applicable_reason is None
    ):
        problems.append(f"semantic_validator:{spec.surface}")
    if sum(item.name == spec.surface for item in spec.cli_surfaces) != 1:
        problems.append(f"canonical_surface:{spec.surface}")
    if spec.frozen != (spec.frozen_sha256 is not None):
        problems.append(f"frozen_metadata:{spec.surface}")
    if spec.package_data_required != (spec.package_resource_path is not None):
        problems.append(f"package_data:{spec.surface}")


def _validate_spec_artifact(
    root: Path,
    spec: SchemaArtifactSpec,
    rendered: bytes,
    problems: list[str],
) -> None:
    path = root / spec.path
    try:
        observed = path.read_bytes()
    except FileNotFoundError:
        return
    if observed != rendered:
        problems.append(f"bytes:{spec.surface}")
    if spec.frozen and sha256(observed).hexdigest() != spec.frozen_sha256:
        problems.append(f"frozen_hash:{spec.surface}")


def _duplicates(values: Any, label: str, problems: list[str]) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            problems.append(f"duplicate_{label}:{value}")
        seen.add(value)


def _mapping(payload: object, label: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping) or not all(
        isinstance(key, str) for key in payload
    ):
        raise TypeError(f"{label} must be a string-keyed object")
    return payload


def _wire_capability_v1(payload: object, _: str | Path) -> None:
    manifest = read_capability_manifest(
        _mapping(payload, "Capability v1"),
        schema_version=CAPABILITY_SCHEMA_V1,
    )
    _validate_legacy_capability(manifest)


def _wire_capability_v2(payload: object, _: str | Path) -> None:
    manifest = read_capability_manifest(
        _mapping(payload, "Capability v2"),
        schema_version=CAPABILITY_SCHEMA_V2,
    )
    _validate_legacy_capability(manifest)


def _wire_capability_v3(payload: object, _: str | Path) -> None:
    read_capability_manifest(
        _mapping(payload, "Capability v3"),
        schema_version=CAPABILITY_SCHEMA_V3,
    )


def _wire_protocol_v1(payload: object, _: str | Path) -> None:
    protocol = read_protocol_manifest(
        _mapping(payload, "Protocol v1"),
        schema_version=PROTOCOL_SCHEMA_V1,
    )
    _validate_legacy_protocol(protocol)


def _wire_protocol_v2(payload: object, _: str | Path) -> None:
    protocol = read_protocol_manifest(
        _mapping(payload, "Protocol v2"),
        schema_version=PROTOCOL_SCHEMA_V2,
    )
    _validate_legacy_protocol(protocol)


def _wire_protocol_v3(payload: object, _: str | Path) -> None:
    read_protocol_manifest(
        _mapping(payload, "Protocol v3"),
        schema_version=PROTOCOL_SCHEMA_V3,
    )


def _validate_legacy_capability(manifest: object) -> None:
    if not isinstance(manifest, CapabilityManifest):
        raise ValueError("legacy Capability surface returned a scoped manifest")
    diagnostics = validate_capability_manifest(manifest)
    if diagnostics:
        raise ValueError("; ".join(item.message for item in diagnostics))


def _validate_legacy_protocol(protocol: object) -> None:
    if not isinstance(protocol, ProtocolManifest):
        raise ValueError("legacy Protocol surface returned a scoped manifest")
    manifest = CapabilityManifest(
        id="capability:wire-validation",
        name="Wire validation envelope",
        version="0.0.0",
        protocol=protocol,
    )
    diagnostics = validate_capability_manifest(manifest)
    if diagnostics:
        raise ValueError("; ".join(item.message for item in diagnostics))


def _wire_driver_v1(payload: object, _: str | Path) -> None:
    driver_descriptor_v1_from_dict(_mapping(payload, "Driver v1"))


def _wire_driver_v2(payload: object, _: str | Path) -> None:
    driver_descriptor_from_dict(_mapping(payload, "Driver v2"))


def _wire_kernel_v1(payload: object, _: str | Path) -> None:
    os_plan_v1_from_dict(_mapping(payload, "Kernel v1"))


def _wire_kernel_v2(payload: object, _: str | Path) -> None:
    os_plan_from_dict(_mapping(payload, "Kernel v2"))


def _wire_runtime_scope_v1(payload: object, _: str | Path) -> None:
    RuntimeScope.from_dict(_mapping(payload, "RuntimeScope v1"))


def _read_trace_event(payload: object) -> TraceEvent:
    body = _mapping(payload, "Trace event")
    expected = {"event_type", "protocol_id", "target", "reason", "lineage"}
    if set(body) != expected:
        raise ValueError("Trace event fields are not exact")
    event = TraceEvent(**dict(body))
    event.validate()
    return event


def _wire_trace(payload: object, _: str | Path) -> None:
    _read_trace_event(payload)


def _wire_commit(payload: object, _: str | Path) -> None:
    errors = validate_commit_wire_record(payload)
    if errors:
        raise ValueError("; ".join(errors))


def _wire_conformance_report(payload: object, _: str | Path) -> None:
    ConformanceReport.from_dict(dict(_mapping(payload, "Conformance report")))


def _wire_scoped_trace(payload: object, _: str | Path) -> None:
    ScopedTraceEvent.from_dict(_mapping(payload, "Scoped Trace event"))


def _wire_authority_v2(payload: object, _: str | Path) -> None:
    validate_authority_wire_record_v2(payload)


def _wire_scoped_authority_tck_v2(payload: object, _: str | Path) -> None:
    validate_scoped_authority_tck_document_v2(payload)


def _wire_commit_tck_v1(_: object, subject: str | Path) -> None:
    load_commit_tck_vectors(subject)


def _wire_commit_tck_v2(_: object, subject: str | Path) -> None:
    load_commit_tck_v2_cases(subject)


def _wire_commit_tck_request_v2(payload: object, _: str | Path) -> None:
    CommitTckRequest.from_dict(_mapping(payload, "Commit TCK request v2"))


def _wire_commit_tck_response_v2(payload: object, _: str | Path) -> None:
    CommitTckResponse.from_dict(_mapping(payload, "Commit TCK response v2"))


def _render_scoped_trace_v1_artifact(document: dict[str, Any]) -> bytes:
    """Preserve the byte-frozen v1 property order without changing its owner."""

    ordered = _sorted_json_value(document)
    if not isinstance(ordered, dict) or not isinstance(ordered.get("properties"), dict):
        raise TypeError("Scoped Trace v1 schema must declare object properties")
    properties = ordered["properties"]
    property_order = (
        "event",
        "event_root",
        "envelope_root",
        "scope_ref",
        "stream",
        "trace_id",
        "transition_id",
        "version",
    )
    if set(properties) != set(property_order):
        raise ValueError("Scoped Trace v1 frozen property set changed")
    ordered["properties"] = {name: properties[name] for name in property_order}
    return (
        json.dumps(ordered, allow_nan=False, indent=2, sort_keys=False) + "\n"
    ).encode("utf-8")


def _sorted_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sorted_json_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_sorted_json_value(item) for item in value]
    return value


SCHEMA_ARTIFACT_SPECS = _SCHEMA_ARTIFACT_SPECS_FACTORY()
del _SCHEMA_ARTIFACT_SPECS_FACTORY

_SURFACE_INDEX = MappingProxyType(
    {
        surface.name: spec
        for spec in SCHEMA_ARTIFACT_SPECS
        for surface in spec.cli_surfaces
    }
)


__all__ = [
    "SCHEMA_ARTIFACT_DIRECTORY",
    "SCHEMA_ARTIFACT_SPECS",
    "SCHEMA_CATALOG_VERSION",
    "SchemaArtifactSpec",
    "SchemaCliSurface",
    "render_schema_artifact",
    "schema_artifact_bytes_for_surface",
    "schema_catalog_problems",
    "schema_for_surface",
    "schema_metadata_for_surface",
    "schema_spec_for_surface",
    "schema_surface_names",
    "validate_schema_wire",
]
